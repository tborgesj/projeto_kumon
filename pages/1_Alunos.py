import streamlit as st
import pandas as pd
import database as db
import auth
from datetime import datetime, date, timedelta
import calendar
import io
import re

# Tenta importar docxtpl para gerar contratos
try:
    from docxtpl import DocxTemplate
    HAS_DOCXTPL = True
except ImportError:
    HAS_DOCXTPL = False

st.set_page_config(page_title="Gestão de Alunos", layout="wide", page_icon="🎓")
if not auth.validar_sessao(): auth.tela_login(); st.stop()
auth.barra_lateral()

unidade_atual = st.session_state.get('unidade_ativa')
if not unidade_atual:
    st.error("Erro de Unidade. Faça login novamente.")
    st.stop()

st.title(f"🎓 Alunos - {st.session_state.get('unidade_nome')}")

# --- FUNÇÕES ÚTEIS (CPF & FORMATAÇÃO) ---

def format_brl(val):
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def get_valid_date(y, m, d):
    return date(y, m, min(d, calendar.monthrange(y, m)[1]))

def limpar_cpf(cpf_str):
    """Mantém apenas os números da string."""
    if not cpf_str: return ""
    return ''.join(filter(str.isdigit, str(cpf_str)))

def formatar_cpf(cpf_limpo):
    """Aplica a máscara XXX.XXX.XXX-XX"""
    if len(cpf_limpo) != 11: return cpf_limpo
    return f"{cpf_limpo[:3]}.{cpf_limpo[3:6]}.{cpf_limpo[6:9]}-{cpf_limpo[9:]}"

def validar_cpf(cpf_limpo):
    """Validação robusta do algoritmo de CPF (Módulo 11)"""
    if len(cpf_limpo) != 11 or cpf_limpo == cpf_limpo[0] * 11:
        return False
    try:
        for i in range(9, 11):
            soma = sum(int(cpf_limpo[num]) * ((i + 1) - num) for num in range(0, i))
            digito_esperado = ((soma * 10) % 11) % 10
            if digito_esperado != int(cpf_limpo[i]):
                return False
        return True
    except:
        return False

# --- POPUP DE SUCESSO ---
@st.dialog("Sucesso!")
def show_success(msg):
    st.success(msg)
    if st.button("OK"): st.rerun()

# --- DIALOG DE CONTRATO ---
@st.dialog("Gerar Contrato")
def popup_contrato(aluno_id, nome_aluno, responsavel, cpf, valor_mensal, dia_venc):
    if not HAS_DOCXTPL:
        st.error("Biblioteca 'docxtpl' ausente.")
        return

    st.subheader(f"Contrato: {nome_aluno}")
    
    conn = db.conectar()
    template_data = conn.execute("SELECT arquivo_binario FROM docs_templates WHERE unidade_id=? AND tipo='CONTRATO'", (unidade_atual,)).fetchone()
    taxa_aluno = conn.execute("SELECT valor_pago FROM pagamentos WHERE aluno_id=? AND tipo='TAXA_MATRICULA' AND unidade_id=? ORDER BY id DESC LIMIT 1", (aluno_id, unidade_atual)).fetchone()
    valor_taxa_real = taxa_aluno[0] if taxa_aluno else 0.0
    conn.close()
    
    if not template_data:
        st.error("Configure o modelo em 'Parâmetros' primeiro.")
        return

    with st.form("form_contrato_gen"):
        st.write("Deseja gerar o contrato com os dados atuais?")
        
        if st.form_submit_button("📄 Gerar Documento"):
            try:
                file_stream = io.BytesIO(template_data[0])
                doc = DocxTemplate(file_stream)
                
                meses_padrao = 12
                dt_hoje = date.today()
                dt_fim = dt_hoje + pd.DateOffset(months=meses_padrao)
                
                context = {
                    'NOME_ALUNO': nome_aluno,
                    'RESPONSAVEL': responsavel,
                    'CPF_RESPONSAVEL': formatar_cpf(limpar_cpf(cpf)) if cpf else "_____________ (CPF)",
                    'VALOR_MENSALIDADE': format_brl(valor_mensal),
                    'TAXA_MATRICULA': format_brl(valor_taxa_real),
                    'DIA_VENCIMENTO': str(dia_venc),
                    'DATA_INICIO': dt_hoje.strftime("%d/%m/%Y"),
                    'DATA_FIM': dt_fim.strftime("%d/%m/%Y"),
                    'QTD_MESES': str(meses_padrao)
                }
                
                doc.render(context)
                
                out_stream = io.BytesIO()
                doc.save(out_stream)
                out_stream.seek(0)
                
                st.session_state['contrato_file'] = out_stream
                st.session_state['contrato_name'] = f"Contrato_{nome_aluno.replace(' ', '_')}.docx"
                st.success("Contrato Gerado!")
                
            except Exception as e:
                st.error(f"Erro: {e}")

    if 'contrato_file' in st.session_state:
        st.download_button("⬇️ Baixar Contrato Word", st.session_state['contrato_file'], st.session_state['contrato_name'], "application/vnd.openxmlformats-officedocument.wordprocessingml.document")

# --- DIALOG CONCEDER BOLSA ---
@st.dialog("Conceder Bolsa de Estudos")
def popup_bolsa(matricula_id, disciplina, valor_atual):
    st.subheader(f"Bolsa: {disciplina}")
    
    c1, c2 = st.columns(2)
    c1.metric("Valor Atual", format_brl(valor_atual))
    c2.metric("Com Bolsa (50%)", format_brl(valor_atual * 0.5), delta="-50%", delta_color="inverse")
    st.caption("O desconto será aplicado automaticamente nas próximas mensalidades.")
    st.divider()
    
    conn = db.conectar()
    mes_atual = datetime.now().strftime("%m/%Y")
    pag_pendente = conn.execute("SELECT id, valor_pago FROM pagamentos WHERE matricula_id=? AND status='PENDENTE' AND mes_referencia=?", (matricula_id, mes_atual)).fetchone()
    conn.close()

    with st.form("form_bolsa"):
        meses = st.number_input("Duração da Bolsa (Meses)", min_value=1, max_value=24, value=6, step=1)
        
        atualizar_hoje = False
        if pag_pendente:
            st.warning(f"⚠️ Existe uma mensalidade de {mes_atual} pendente ({format_brl(pag_pendente[1])}).")
            atualizar_hoje = st.checkbox("Aplicar desconto já nesta mensalidade?", value=True)
        
        if st.form_submit_button("✅ Ativar Bolsa"):
            conn = db.conectar()
            try:
                saldo_meses = meses - 1 if atualizar_hoje else meses
                conn.execute("UPDATE matriculas SET bolsa_ativa=1, bolsa_meses_restantes=? WHERE id=?", (saldo_meses, matricula_id))
                
                if atualizar_hoje and pag_pendente:
                    novo_valor = valor_atual * 0.5
                    conn.execute("UPDATE pagamentos SET valor_pago=? WHERE id=?", (novo_valor, pag_pendente[0]))
                    st.toast(f"Mensalidade de {mes_atual} atualizada!")
                
                conn.commit()
                st.success("Bolsa ativada com sucesso!")
                st.rerun()
            except Exception as e: st.error(e)
            finally: conn.close()

# --- PARAMETROS DA TELA ---
params = db.get_parametros_unidade(unidade_atual)
VALOR_PADRAO = params['mensalidade']
canais_aquisicao = ["Indicação", "Fachada", "Google", "Instagram", "Facebook", "TikTok", "Parceria", "Outros"]

tab1, tab2 = st.tabs(["Novo Cadastro", "Gerenciar Aluno"])

# ==============================================================================
# TAB 1: NOVO CADASTRO
# ==============================================================================
with tab1:
    st.header("📝 Matricular Novo Aluno")
    if 'disciplinas_temp' not in st.session_state: st.session_state['disciplinas_temp'] = []
    
    # Disciplinas
    todas_disc = ["Matemática", "Português", "Inglês", "Japonês"]
    ja_tem = [x['disc'] for x in st.session_state['disciplinas_temp']]
    disp = [d for d in todas_disc if d not in ja_tem]
    
    c_sel, c_btn = st.columns([3, 1])
    d_sel = c_sel.selectbox("Disciplina:", ["Selecione..."] + disp)
    if c_btn.button("➕ Incluir") and d_sel != "Selecione...":
        st.session_state['disciplinas_temp'].append({'disc': d_sel, 'val': VALOR_PADRAO, 'just': ''})
        st.rerun()

    if st.session_state['disciplinas_temp']:
        for i, item in enumerate(st.session_state['disciplinas_temp']):
            cc1, cc2, cc3, cc4 = st.columns([2, 2, 3, 1])
            cc1.markdown(f"**{item['disc']}**")
            nv = cc2.number_input(f"R$", value=item['val'], step=10.0, key=f"v_{i}")
            nj = cc3.text_input(f"Obs.", value=item['just'], key=f"j_{i}")
            st.session_state['disciplinas_temp'][i]['val'] = nv; st.session_state['disciplinas_temp'][i]['just'] = nj
            if cc4.button("🗑️", key=f"d_{i}"): st.session_state['disciplinas_temp'].pop(i); st.rerun()
    st.divider()

    with st.form("form_matricula", clear_on_submit=False):
        col_n, col_r = st.columns(2)
        nome = col_n.text_input("Nome do Aluno")
        resp = col_r.text_input("Nome do Responsável")
        
        col_c, col_m = st.columns(2)
        cpf_input = col_c.text_input("CPF Responsável", placeholder="Apenas números ou com pontos", max_chars=14)
        canal = col_m.selectbox("Canal", canais_aquisicao)
        
        col_v, col_t = st.columns(2)
        dia_venc = col_v.number_input("Dia de Vencimento", 1, 31, 10)
        
        v_taxa = 0.0
        if params['campanha']: col_t.warning("Campanha: Taxa Isenta")
        else: v_taxa = col_t.number_input("Taxa Matrícula", value=params['taxa_matr'])
        
        submitted = st.form_submit_button("✅ Finalizar Matrícula")
        
        if submitted:
            cpf_clean = limpar_cpf(cpf_input)
            cpf_valido = True
            msg_erro = ""
            
            if cpf_clean:
                if not validar_cpf(cpf_clean):
                    cpf_valido = False
                    msg_erro = "CPF Inválido! Verifique os números."
            
            if not nome or not resp or not st.session_state['disciplinas_temp']:
                st.error("Preencha Nome, Responsável e Disciplinas.")
            elif not cpf_valido:
                st.error(msg_erro)
            else:
                conn = db.conectar()
                try:
                    cpf_final = formatar_cpf(cpf_clean) if cpf_clean else ""
                    cur = conn.execute("INSERT INTO alunos (unidade_id, nome, responsavel_nome, cpf_responsavel, canal_aquisicao) VALUES (?, ?, ?, ?, ?)", 
                                       (unidade_atual, nome, resp, cpf_final, canal))
                    aid = cur.lastrowid
                    
                    hj = datetime.now()
                    mes_cob = hj.month if hj.day <= 20 else hj.month + 1
                    ano_cob = hj.year
                    if mes_cob > 12: mes_cob=1; ano_cob+=1
                    mes_ref = f"{mes_cob:02d}/{ano_cob}"
                    dt_venc = get_valid_date(ano_cob, mes_cob, dia_venc)
                    
                    for item in st.session_state['disciplinas_temp']:
                        # ATENÇÃO: data_fim nasce NULL
                        cur.execute("INSERT INTO matriculas (unidade_id, aluno_id, disciplina, valor_acordado, dia_vencimento, justificativa_desconto, data_inicio, ativo) VALUES (?,?,?,?,?,?,DATE('now'),1)", 
                                    (unidade_atual, aid, item['disc'], item['val'], dia_venc, item['just']))
                        mid = cur.lastrowid
                        cur.execute("INSERT INTO pagamentos (unidade_id, matricula_id, aluno_id, mes_referencia, data_vencimento, valor_pago, status, tipo) VALUES (?,?,?,?,?,?, 'PENDENTE', 'MENSALIDADE')",
                                    (unidade_atual, mid, aid, mes_ref, dt_venc, item['val']))
                    
                    if v_taxa > 0:
                        dt_tx = date.today() + timedelta(days=1)
                        conn.execute("INSERT INTO pagamentos (unidade_id, aluno_id, mes_referencia, data_vencimento, valor_pago, status, tipo) VALUES (?,?,?,?,?, 'PENDENTE', 'TAXA_MATRICULA')",
                                     (unidade_atual, aid, dt_tx.strftime("%m/%Y"), dt_tx, v_taxa))
                    
                    conn.commit()
                    st.session_state['disciplinas_temp'] = []
                    show_success(f"Aluno {nome} cadastrado com sucesso!")
                except Exception as e: st.error(f"Erro: {e}")
                finally: conn.close()

# ==============================================================================
# TAB 2: GERENCIAR
# ==============================================================================
with tab2:
    st.header("🔍 Consultar e Editar")
    conn = db.conectar()
    
    c_f1, c_f2 = st.columns([1, 3])
    filtro = c_f1.radio("Exibir:", ["Ativos", "Todos"], horizontal=True)
    
    q = "SELECT id, nome, responsavel_nome, cpf_responsavel, canal_aquisicao FROM alunos WHERE unidade_id=?"
    if filtro == "Ativos": q += " AND id IN (SELECT aluno_id FROM matriculas WHERE ativo=1 AND unidade_id=?)"
    q += " ORDER BY nome"
    
    params_q = (unidade_atual, unidade_atual) if filtro == "Ativos" else (unidade_atual,)
    df_alunos = pd.read_sql_query(q, conn, params=params_q)
    
    sel = c_f2.selectbox("Aluno:", df_alunos['id'].tolist(), format_func=lambda x: df_alunos[df_alunos['id']==x]['nome'].values[0] if not df_alunos.empty else "")
    
    if sel:
        d_aluno = df_alunos[df_alunos['id']==sel].iloc[0]
        mats = conn.execute("SELECT id, disciplina, valor_acordado, dia_vencimento, ativo, bolsa_ativa, bolsa_meses_restantes FROM matriculas WHERE aluno_id=? AND unidade_id=? ORDER BY ativo DESC", (sel, unidade_atual)).fetchall()
        
        st.divider()
        cb1, cb2 = st.columns([1, 4])
        
        val_tot = sum([m[2] for m in mats if m[4]==1])
        dia_base = mats[0][3] if mats else 10
        if cb1.button("🖨️ Gerar Contrato", type="primary"):
            popup_contrato(sel, d_aluno['nome'], d_aluno['responsavel_nome'], d_aluno['cpf_responsavel'], val_tot, dia_base)
            
        with st.expander("📝 Editar Dados Cadastrais"):
            with st.form("edit_cad"):
                ec1, ec2 = st.columns(2)
                e_nome = ec1.text_input("Nome", value=d_aluno['nome'])
                e_resp = ec2.text_input("Responsável", value=d_aluno['responsavel_nome'])
                ec3, ec4 = st.columns(2)
                e_cpf = ec3.text_input("CPF Resp.", value=d_aluno['cpf_responsavel'] if d_aluno['cpf_responsavel'] else "", max_chars=14)
                curr_chn = d_aluno['canal_aquisicao']
                idx_c = canais_aquisicao.index(curr_chn) if curr_chn in canais_aquisicao else 0
                e_chn = ec4.selectbox("Canal", canais_aquisicao, index=idx_c)
                
                if st.form_submit_button("Salvar Alterações"):
                    cpfc = limpar_cpf(e_cpf)
                    if cpfc and not validar_cpf(cpfc): st.error("CPF Inválido!")
                    else:
                        conn.execute("UPDATE alunos SET nome=?, responsavel_nome=?, cpf_responsavel=?, canal_aquisicao=? WHERE id=?", 
                                     (e_nome, e_resp, formatar_cpf(cpfc), e_chn, sel))
                        conn.commit(); show_success("Atualizado!")
        
        st.divider()
        st.subheader("Disciplinas")
        
        with st.expander("➕ Adicionar Disciplina"):
            with st.form("add_disc"):
                ac1, ac2, ac3 = st.columns(3)
                ad = ac1.selectbox("Disc", ["Matemática", "Português", "Inglês", "Japonês"])
                av = ac2.number_input("Valor", value=VALOR_PADRAO)
                adi = ac3.number_input("Dia", 1, 31, 10)
                if st.form_submit_button("Salvar"):
                    cur = conn.execute("INSERT INTO matriculas (unidade_id, aluno_id, disciplina, valor_acordado, dia_vencimento, data_inicio, ativo) VALUES (?,?,?,?,?,DATE('now'),1)", (unidade_atual, sel, ad, av, adi))
                    mid = cur.lastrowid
                    hj = datetime.now(); mr = f"{hj.month:02d}/{hj.year}"
                    conn.execute("INSERT INTO pagamentos (unidade_id, matricula_id, aluno_id, mes_referencia, data_vencimento, valor_pago, status) VALUES (?,?,?,?,?,?,'PENDENTE')", (unidade_atual, mid, sel, mr, get_valid_date(hj.year, hj.month, adi), av))
                    conn.commit(); show_success("Adicionado!")
        
        # Listagem Matriculas
        for m in mats:
            mid, disc, val, dia, ativo, b_ativa, b_meses = m
            with st.container():
                stt = "ATIVO" if ativo else "INATIVO"
                icon = "🟢" if ativo else "🔴"
                
                c1, c2, c3, c4, c5 = st.columns([2.5, 2, 2, 1.5, 1.5])
                c1.markdown(f"### {icon} {disc}")
                
                if b_ativa:
                    c2.metric("Valor (Com Bolsa)", format_brl(val * 0.5), delta="50% OFF")
                    c3.write(f"**Bolsa Ativa:** Restam {b_meses} meses")
                    if c4.button("❌ Retirar Bolsa", key=f"del_b_{mid}"):
                        conn.execute("UPDATE matriculas SET bolsa_ativa=0, bolsa_meses_restantes=0 WHERE id=?", (mid,))
                        conn.commit(); st.rerun()
                else:
                    c2.metric("Valor", format_brl(val))
                    c3.write("Sem Bolsa")
                    if ativo and c4.button("🎓 Conceder Bolsa", key=f"add_b_{mid}"):
                        popup_bolsa(mid, disc, val)
                
                # --- BOTÃO INATIVAR (ATUALIZADO) ---
                if ativo and c5.button("Inativar", key=f"in_{mid}"):
                    # Agora salva também a data_fim para relatórios
                    conn.execute("UPDATE matriculas SET ativo=0, data_fim=DATE('now') WHERE id=?", (mid,))
                    conn.commit(); st.rerun()
            st.divider()
        
        # Ações Globais
        if any(m[4] for m in mats):
            if st.button("🛑 INATIVAR ALUNO (TUDO)", type="primary"):
                # Atualização em massa com data_fim
                conn.execute("UPDATE matriculas SET ativo=0, data_fim=DATE('now') WHERE aluno_id=?", (sel,))
                conn.commit(); show_success("Inativado.")
        
        st.subheader("Histórico Financeiro")
        h = pd.read_sql_query("SELECT mes_referencia, valor_pago, status, tipo FROM pagamentos WHERE aluno_id=? AND unidade_id=? ORDER BY id DESC", conn, params=(sel, unidade_atual))
        if not h.empty:
            h['valor_pago'] = h['valor_pago'].apply(format_brl)
            st.dataframe(h.style.map(lambda x: f'background-color: {"#d4edda" if x=="PAGO" else "#f8d7da"}', subset=['status']), use_container_width=True)

    conn.close()