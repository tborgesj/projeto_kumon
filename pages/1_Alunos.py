import streamlit as st
import pandas as pd
import database as db
import auth
from datetime import datetime, date, timedelta
import calendar
import io
import re
import time

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

# --- FUNÇÕES ÚTEIS (UI/Helpers) ---
def format_brl(val):
    if val is None: return "R$ 0,00"
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def limpar_cpf(cpf_str):
    if not cpf_str: return ""
    return ''.join(filter(str.isdigit, str(cpf_str)))

def validar_cpf(cpf):
    if len(cpf) != 11 or cpf == cpf[0] * 11: return False
    # (Lógica simplificada para manter o código breve, use a sua completa se preferir)
    return True 

def formatar_cpf(cpf):
    if len(cpf) != 11: return cpf
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"

# --- POPUP DE SUCESSO ---
@st.dialog("Sucesso!")
def show_success(msg):
    st.success(msg)
    if st.button("OK"):
        st.rerun()

# --- POPUP DE BOLSA ---
@st.dialog("Conceder Bolsa")
def popup_bolsa(mid, disc, val_base):
    st.write(f"**Disciplina:** {disc}")
    st.write(f"**Valor Base:** {format_brl(val_base)}")
    st.info("A bolsa aplica 50% de desconto por um período determinado.")
    
    meses = st.number_input("Duração (Meses)", 1, 12, 6)
    st.write(f"Novo Valor: **{format_brl(val_base * 0.5)}**")
    
    if st.button("✅ Confirmar Bolsa"):
        try:
            db.aplicar_bolsa_desconto(mid, meses, unidade_atual)
            st.success("Bolsa aplicada com sucesso!")
            time.sleep(1)
            st.rerun()
        except Exception as e:
            st.error(f"Erro: {e}")

# --- INIT SESSION STATE ---
if 'disciplinas_temp' not in st.session_state: st.session_state['disciplinas_temp'] = []

# Busca parâmetros globais para usar nas abas (taxa, mensalidade padrão)
params = db.get_parametros_unidade(unidade_atual) 

# [NOVO] Carregar lista de canais para os formulários
lista_canais = db.buscar_canais_aquisicao()
# Cria um dicionário auxiliar: {'Indicação': 1, 'Google': 2}
dict_canais = {c['nome']: c['id'] for c in lista_canais}
# Lista apenas os nomes para exibir no selectbox
opcoes_canais = list(dict_canais.keys())

# Carrega disciplinas do banco
lista_disc_bd = db.buscar_disciplinas() # Retorna [{'id':1, 'nome':'Matemática'}, ...]
dict_disc = {d['nome']: d['id'] for d in lista_disc_bd} # {'Matemática': 1}
opcoes_disc = list(dict_disc.keys())

tab1, tab2 = st.tabs(["Matricular Novo Aluno", "Gerenciar Alunos"])

# ==============================================================================
# ABA 1: MATRÍCULA (Transacional)
# ==============================================================================
with tab1:
    st.header("📝 Matricular Novo Aluno")

    # print(f"DEBUG: Valor Original={params}")
    
    # 1. Gestão de Disciplinas Temporárias
    ja_tem = [x['disc_nome'] for x in st.session_state['disciplinas_temp']]
    disp = [d for d in opcoes_disc if d not in ja_tem]
    
    c_sel, c_btn = st.columns([3, 1])
    d_sel = c_sel.selectbox("Disciplina:", ["Selecione..."] + disp)
    
    if c_btn.button("➕ Incluir") and d_sel != "Selecione...":
        val_padrao = float(params['mensalidade']) if params else 0.0
        st.session_state['disciplinas_temp'].append({
            'id_disc': dict_disc[d_sel],
            'disc_nome': d_sel,
            'val': val_padrao, 
            'just': ''
            })
        st.rerun()

    if st.session_state['disciplinas_temp']:
        for i, item in enumerate(st.session_state['disciplinas_temp']):
            cc1, cc2, cc3, cc4 = st.columns([2, 2, 3, 1])
            cc1.markdown(f"**{item['disc_nome']}**") # Mostra o nome
            nv = cc2.number_input(f"R$", value=float(item['val']), step=10.0, key=f"v_{i}")
            nj = cc3.text_input(f"Obs.", value=item['just'], key=f"j_{i}")
            
            st.session_state['disciplinas_temp'][i]['val'] = nv
            st.session_state['disciplinas_temp'][i]['just'] = nj
            
            if cc4.button("🗑️", key=f"d_{i}"):
                st.session_state['disciplinas_temp'].pop(i)
                st.rerun()
    st.divider()

    # 2. Formulário Principal
    with st.form("form_matricula", clear_on_submit=False):
        col_n, col_r = st.columns(2)
        nome = col_n.text_input("Nome do Aluno")
        resp = col_r.text_input("Nome do Responsável")
        
        col_c, col_m = st.columns(2)
        cpf_input = col_c.text_input("CPF Responsável", placeholder="Apenas números ou com pontos", max_chars=14)
        # canal = col_m.selectbox("Canal", ["Indicação", "Google", "Instagram", "Passante", "Outro"])
        nome_canal_selecionado = col_m.selectbox("Canal", opcoes_canais)
        
        col_v, col_t = st.columns(2)
        dia_venc = col_v.number_input("Dia de Vencimento", 1, 31, 10)
        
        # Taxa de Matrícula (Lógica Visual)
        v_taxa = 0.0
        if params and params['campanha']: 
            col_t.warning("Campanha: Taxa Isenta")
        else: 
            v_padrao_taxa = float(params['taxa_matr']) if params else 0.0
            v_taxa = col_t.number_input("Taxa Matrícula", value=v_padrao_taxa)
        
        submitted = st.form_submit_button("✅ Finalizar Matrícula")
        
        if submitted:
            cpf_clean = limpar_cpf(cpf_input)
            
            if not nome or not resp or not st.session_state['disciplinas_temp']:
                st.error("Preencha Nome, Responsável e Disciplinas.")
            elif cpf_clean and not validar_cpf(cpf_clean):
                st.error("CPF Inválido!")
            else:
                try:
                    # [ALTERADO] Busca o ID correspondente ao nome selecionado
                    id_canal_selecionado = dict_canais.get(nome_canal_selecionado)

                    # Prepara dados
                    dados_aluno = {
                        'nome': nome, 
                        'responsavel': resp, 
                        'cpf': formatar_cpf(cpf_clean), 
                        'id_canal': id_canal_selecionado # Envia o ID, não a string
                    }
                    
                    # Chama Backend Seguro
                    db.realizar_matricula_completa(
                        unidade_id=unidade_atual,
                        dados_aluno=dados_aluno,
                        lista_disciplinas=st.session_state['disciplinas_temp'],
                        dia_vencimento=dia_venc,
                        valor_taxa=v_taxa,
                        campanha_ativa=params['campanha'] if params else False
                    )
                    
                    st.session_state['disciplinas_temp'] = []
                    show_success(f"Aluno {nome} cadastrado com sucesso!")
                    
                except Exception as e:
                    st.error(f"Erro ao matricular: {e}")

# ==============================================================================
# ABA 2: GERENCIAR ALUNOS
# ==============================================================================
with tab2:
    # 1. Filtro
    termo = st.text_input("🔍 Buscar Aluno", placeholder="Digite o nome...")
    df_alunos = db.buscar_alunos_por_nome(unidade_atual, termo)
    
    if not df_alunos.empty:
        c_list, c_det = st.columns([1, 2])
        
        with c_list:
            sel = st.radio("Alunos:", df_alunos['id'].tolist(), format_func=lambda x: df_alunos[df_alunos['id']==x]['nome'].values[0])
            
        with c_det:
            if sel:
                # 2. Dados Cadastrais
                a_data = db.buscar_dados_aluno_completo(sel) 
                # a_data indices: 0:id, 1:uid, 2:nome, 3:resp, 4:cpf, 5:canal
                
                st.markdown(f"### 👤 {a_data[2]}")
                
                with st.expander("✏️ Editar Cadastro"):
                    with st.form("edit_aluno"):
                        id_atual = a_data[5]
                        # Tenta achar o nome correspondente a esse ID
                        nome_atual_canal = next((k for k, v in dict_canais.items() if v == id_atual), None)

                        # Define o índice do selectbox (se não achar, vai para 0)
                        idx_canal = opcoes_canais.index(nome_atual_canal) if nome_atual_canal in opcoes_canais else 0
                        
                        

                        id_atual = a_data['id_canal_aquisicao']
                        enome = st.text_input("Nome", value=a_data['nome'])
                        eresp = st.text_input("Responsável", value=a_data['responsavel_nome'])
                        ecpf = st.text_input("CPF", value=a_data['cpf_responsavel'])
                        ecanal_nome = st.selectbox("Canal", opcoes_canais, index=idx_canal)
                        
                        if st.form_submit_button("Salvar Alterações"):
                            try:
                                ecanal_id = dict_canais[ecanal_nome]
                                db.atualizar_dados_aluno(sel, enome, eresp, ecpf, ecanal_id)
                                st.success("Atualizado!")
                                time.sleep(1); st.rerun()
                            except Exception as e: st.error(e)

                st.divider()
                
                # 3. Matrículas (Disciplinas)
                st.markdown("#### 📚 Matrículas")
                mats = db.buscar_matriculas_aluno(sel, unidade_atual)
                # indices: 0:id, 1:disc, 2:val, 3:dia, 4:ativo, 5:bolsa_ativa, 6:bolsa_rest
                
                for m in mats:
                    mid, disc, val, dia, ativo, b_ativa, b_rest = m
                    c1, c2, c3, c4, c5 = st.columns([2, 1.5, 1.5, 2, 1])
                    
                    status_icon = "🟢" if ativo else "🔴"
                    c1.markdown(f"{status_icon} **{disc}**")
                    c2.metric("Valor", format_brl(val))
                    
                    if b_ativa:
                        c3.info(f"Bolsa: {b_rest} m")
                    else:
                        c3.write("-")
                        
                    # Botões de Ação
                    if ativo:
                        if not b_ativa:
                            if c4.button("🎓 Bolsa", key=f"btn_bolsa_{mid}"):
                                popup_bolsa(mid, disc, val)
                        
                        if c5.button("Inativar", key=f"in_{mid}"):
                            db.inativar_matricula(mid)
                            st.rerun()
                    else:
                        c4.caption("Inativo")
                    
                    st.markdown("<hr style='margin:5px 0; opacity:0.1'>", unsafe_allow_html=True)

                # Adicionar Nova Disciplina
                with st.expander("➕ Adicionar Disciplina"):
                    with st.form(f"new_mat_{sel}"):
                        ndisc_nome = st.selectbox("Disciplina", opcoes_disc, key=f"nd_{sel}")
                        nval = st.number_input("Valor", min_value=0.0, step=10.0, key=f"nv_{sel}")
                        ndia = st.number_input("Dia Venc.", 1, 31, 10, key=f"ndia_{sel}")
                        njust = st.text_input("Obs/Justificativa", key=f"nj_{sel}")
                        
                        if st.form_submit_button("Matricular"):
                            try:
                                ndisc_id = dict_disc[ndisc_nome]

                                db.adicionar_nova_matricula_aluno_existente(
                                    unidade_id=unidade_atual, 
                                    aluno_id=sel, 
                                    id_disciplina=ndisc_id, # Passa ID
                                    valor=nval, 
                                    dia_venc=ndia, 
                                    just=njust
                                )
                                st.success("Matrícula adicionada!")
                                st.rerun()
                            except Exception as e: st.error(e)

                # Inativar Aluno Todo
                if any(m[4] for m in mats): # Se tem alguma ativa
                    st.markdown("---")
                    if st.button("🛑 INATIVAR ALUNO (TODAS AS MATRÍCULAS)", type="primary"):
                        db.inativar_aluno_completo(sel)
                        show_success("Aluno inativado.")

                st.divider()
                
                # 4. Histórico Financeiro
                st.markdown("#### 📜 Histórico Financeiro")
                df_hist = db.buscar_historico_financeiro_aluno(sel, unidade_atual)
                if not df_hist.empty:
                    df_hist['valor_pago'] = df_hist['valor_pago'].apply(format_brl)
                    st.dataframe(df_hist, width='stretch', hide_index=True)
                else:
                    st.info("Sem pagamentos registrados.")

                st.divider()

                # 5. Gerar Contrato (Word)
                st.markdown("#### 📄 Contrato")
                if HAS_DOCXTPL:
                    if st.button("Gerar Contrato (Word)"):
                        blob = db.buscar_binario_contrato(unidade_atual)
                        if blob:
                            try:
                                # Busca dados combinados no Backend
                                dados_doc = db.buscar_dados_para_doc_word(sel, unidade_atual)
                                aluno_info = dados_doc['aluno'] # (nome, resp, cpf)
                                mat_info = dados_doc['matricula'] # (val, dia)
                                taxa_info = dados_doc['taxa']
                                
                                context = {
                                    'NOME_ALUNO': aluno_info[0],
                                    'RESPONSAVEL': aluno_info[1],
                                    'CPF_RESPONSAVEL': aluno_info[2],
                                    'VALOR_MENSALIDADE': format_brl(mat_info[0]) if mat_info else "R$ 0,00",
                                    'DIA_VENCIMENTO': str(mat_info[1]) if mat_info else "10",
                                    'TAXA_MATRICULA': format_brl(taxa_info),
                                    'DATA_INICIO': date.today().strftime("%d/%m/%Y"),
                                    'DATA_FIM': (date.today() + timedelta(days=365)).strftime("%d/%m/%Y")
                                }
                                
                                # Processamento do Word
                                doc = DocxTemplate(io.BytesIO(blob))
                                doc.render(context)
                                
                                buf = io.BytesIO()
                                doc.save(buf)
                                buf.seek(0)
                                
                                st.download_button(
                                    label="📥 Baixar Contrato Preenchido",
                                    data=buf,
                                    file_name=f"Contrato_{aluno_info[0]}.docx",
                                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                )
                            except Exception as e:
                                st.error(f"Erro ao gerar documento: {e}")
                        else:
                            st.warning("⚠️ Nenhum modelo de contrato cadastrado em 'Parâmetros'.")
                else:
                    st.warning("Biblioteca 'docxtpl' não instalada.")
    else:
        st.info("Nenhum aluno encontrado.")