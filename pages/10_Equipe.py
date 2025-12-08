import streamlit as st
import pandas as pd
import database as db
import auth
from datetime import datetime, date
import calendar

st.set_page_config(page_title="Gestão de Equipe", layout="wide", page_icon="👥")
if not auth.validar_sessao(): auth.tela_login(); st.stop()
auth.barra_lateral()

# --- SEGURANÇA: VERIFICA UNIDADE ---
unidade_atual = st.session_state.get('unidade_ativa')
nome_unidade = st.session_state.get('unidade_nome', 'Unidade')
if not unidade_atual:
    st.error("Erro de Unidade. Faça login novamente.")
    st.stop()

st.title(f"👥 Gestão de Funcionários - {nome_unidade}")

def format_brl(val): 
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def get_valid_date(year, month, day):
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last_day))

# --- POPUP DE SUCESSO ---
@st.dialog("Sucesso!")
def show_success(msg):
    st.success(msg)
    if st.button("OK"):
        st.rerun()

tab1, tab2 = st.tabs(["Novo Funcionário", "Gerenciar Equipe"])

# ==============================================================================
# ABA 1: NOVO CADASTRO (COM LIMPEZA E UNIDADE)
# ==============================================================================
with tab1:
    st.subheader("Cadastrar Colaborador")
    
    if 'temp_custos' not in st.session_state: st.session_state['temp_custos'] = []
    
    # Função para limpar session state do form
    def clear_form():
        st.session_state['temp_custos'] = []
        keys = ['n_nome', 'n_tipo', 'n_sal', 'n_dia', 'add_tipo', 'add_nome_sel', 'add_nome_txt', 'add_val', 'add_dia']
        for k in keys:
            if k in st.session_state: del st.session_state[k]

    with st.container():
        c1, c2 = st.columns(2)
        nome = c1.text_input("Nome Completo", key="n_nome")
        tipo = c2.selectbox("Contratação", ["CLT", "Horista", "Estagiário", "Jovem Aprendiz", "Temporário", "Autônomo (PJ)"], key="n_tipo")
        
        c3, c4 = st.columns(2)
        salario = c3.number_input("Salário Base (R$)", min_value=0.0, step=100.0, key="n_sal")
        dia_pag = c4.number_input("Dia Pagamento", 1, 31, 5, key="n_dia")

        st.divider()
        st.markdown("#### ➕ Benefícios e Impostos Iniciais")
        
        col_tipo, col_nome, col_val, col_dia, col_btn = st.columns([1.5, 2, 1.5, 1, 1])
        tipo_item = col_tipo.selectbox("Tipo", ["Benefício (Despesa)", "Imposto"], key="add_tipo")
        
        sugestoes = ["Vale Alimentação", "Vale Transporte", "Plano de Saúde"] if "Benefício" in tipo_item else ["FGTS", "INSS", "IRRF", "DAS (Simples)"]
        nome_sel = col_nome.selectbox("Descrição", sugestoes + ["Outro..."], key="add_nome_sel")
        nome_final = nome_sel
        if nome_sel == "Outro...": 
            nome_final = col_nome.text_input("Digite o nome", key="add_nome_txt")
            
        val_item = col_val.number_input("Valor (R$)", min_value=0.0, step=10.0, key="add_val")
        dia_item = col_dia.number_input("Dia Venc.", 1, 31, 7 if "Imposto" in tipo_item else dia_pag, key="add_dia")
        
        if col_btn.button("Incluir Item"):
            if nome_final:
                st.session_state['temp_custos'].append({
                    "tipo": "BENEFICIO" if "Benefício" in tipo_item else "IMPOSTO",
                    "nome": nome_final,
                    "valor": val_item,
                    "dia": dia_item
                })

        # Lista visual
        if st.session_state['temp_custos']:
            st.caption("Itens a cadastrar:")
            for i, item in enumerate(st.session_state['temp_custos']):
                ic = "🍔" if item['tipo'] == "BENEFICIO" else "🏛️"
                cols = st.columns([4, 2, 1])
                cols[0].text(f"{ic} {item['nome']}")
                cols[1].text(f"{format_brl(item['valor'])} (Dia {item['dia']})")
                if cols[2].button("🗑️", key=f"del_temp_{i}"):
                    st.session_state['temp_custos'].pop(i)
                    st.rerun()

    st.divider()
    
    if st.button("💾 Salvar Funcionário", type="primary"):
        if not nome:
            st.error("Nome é obrigatório.")
        else:
            conn = db.conectar()
            try:
                # 1. INSERT FUNCIONARIO (Com Unidade ID)
                cur = conn.execute('''
                    INSERT INTO funcionarios (unidade_id, nome, tipo_contratacao, salario_base, data_contratacao, dia_pagamento_salario, ativo)
                    VALUES (?, ?, ?, ?, DATE('now'), ?, 1)
                ''', (unidade_atual, nome, tipo, salario, dia_pag))
                fid = cur.lastrowid
                
                # 2. INSERT CUSTOS (Com Unidade ID)
                for item in st.session_state['temp_custos']:
                    conn.execute('''
                        INSERT INTO custos_pessoal (unidade_id, funcionario_id, tipo_item, nome_item, valor, dia_vencimento)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (unidade_atual, fid, item['tipo'], item['nome'], item['valor'], item['dia']))
                
                conn.commit()
                clear_form()
                show_success(f"{nome} cadastrado com sucesso!")
                
            except Exception as e:
                st.error(f"Erro: {e}")
            finally:
                conn.close()

# ==============================================================================
# ABA 2: GERENCIAR (RECUPERADA A FUNCIONALIDADE DE EDIÇÃO COMPLETA)
# ==============================================================================
with tab2:
    conn = db.conectar()
    
    # Filtro e Seleção
    cf1, cf2 = st.columns([1, 3])
    filtro_status = cf1.radio("Exibir:", ["Ativos", "Inativos", "Todos"], horizontal=True)
    
    query = "SELECT id, nome, tipo_contratacao, salario_base, ativo FROM funcionarios WHERE unidade_id=?"
    if filtro_status == "Ativos": query += " AND ativo=1"
    elif filtro_status == "Inativos": query += " AND ativo=0"
    
    df = pd.read_sql_query(query, conn, params=(unidade_atual,))
    
    if not df.empty:
        col_esq, col_dir = st.columns([1, 2])
        
        with col_esq:
            st.markdown("### Lista de Colaboradores")
            func_id_sel = st.radio("Selecione:", df['id'].tolist(), format_func=lambda x: df[df['id']==x]['nome'].values[0])
        
        with col_dir:
            st.markdown("### 📝 Edição e Custos")
            if func_id_sel:
                # Busca dados do funcionário selecionado
                f_data = conn.execute("SELECT * FROM funcionarios WHERE id=?", (func_id_sel,)).fetchone()
                # indices: 0:id, 1:uid, 2:nome, 3:tipo, 4:salario, 5:dt, 6:dia, 7:ativo, 8:demissao
                
                # --- BLOCO 1: DADOS BÁSICOS E SALÁRIO ---
                with st.form(key=f"edit_func_{func_id_sel}"):
                    ce1, ce2 = st.columns(2)
                    n_nome = ce1.text_input("Nome", value=f_data[2])
                    n_tipo = ce2.selectbox("Contrato", ["CLT", "Horista", "Estagiário", "Jovem Aprendiz", "Temporário", "Autônomo (PJ)"], index=["CLT", "Horista", "Estagiário", "Jovem Aprendiz", "Temporário", "Autônomo (PJ)"].index(f_data[3]) if f_data[3] in ["CLT", "Horista", "Estagiário", "Jovem Aprendiz", "Temporário", "Autônomo (PJ)"] else 0)
                    
                    ce3, ce4 = st.columns(2)
                    n_sal = ce3.number_input("Salário (R$)", value=float(f_data[4]), step=100.0)
                    n_dia = ce4.number_input("Dia Pagamento", value=int(f_data[6]), min_value=1, max_value=31)
                    
                    is_ativo = f_data[7] == 1
                    novo_status = st.checkbox("Funcionário Ativo?", value=is_ativo)
                    
                    dt_demissao = None
                    if not novo_status:
                        val_date = datetime.strptime(f_data[8], '%Y-%m-%d').date() if f_data[8] else date.today()
                        dt_demissao = st.date_input("Data de Demissão", value=val_date)
                    
                    if st.form_submit_button("Atualizar Dados Básicos"):
                        try:
                            dem_str = dt_demissao if not novo_status else None
                            # 1. Update Funcionário
                            conn.execute('''
                                UPDATE funcionarios SET nome=?, tipo_contratacao=?, salario_base=?, dia_pagamento_salario=?, ativo=?, data_demissao=?
                                WHERE id=?
                            ''', (n_nome, n_tipo, n_sal, n_dia, 1 if novo_status else 0, dem_str, func_id_sel))
                            
                            # 2. PROPAGAÇÃO FINANCEIRA (Sincronizar Salário Pendente)
                            nome_antigo = f_data[2]
                            desc_sal_antiga = f"Salário - {nome_antigo}"
                            desc_sal_nova = f"Salário - {n_nome}"
                            
                            # Atualiza valor e nome na tabela despesas (se estiver pendente)
                            conn.execute('''
                                UPDATE despesas SET valor=?, descricao=? 
                                WHERE descricao=? AND status='PENDENTE' AND unidade_id=?
                            ''', (n_sal, desc_sal_nova, desc_sal_antiga, unidade_atual))

                            # Atualiza nome nos benefícios pendentes (se mudou de nome)
                            if nome_antigo != n_nome:
                                conn.execute("UPDATE despesas SET descricao = REPLACE(descricao, ?, ?) WHERE descricao LIKE ? AND status='PENDENTE' AND unidade_id=?", 
                                             (f" - {nome_antigo}", f" - {n_nome}", f"% - {nome_antigo}", unidade_atual))

                            # Se demitiu, apaga as pendências
                            if not novo_status:
                                conn.execute("DELETE FROM despesas WHERE descricao LIKE ? AND status='PENDENTE' AND unidade_id=?", 
                                             (f"% - {n_nome}", unidade_atual))

                            conn.commit()
                            show_success("Dados atualizados!")
                        except Exception as e:
                            st.error(f"Erro: {e}")

                st.divider()
                st.markdown("#### 💲 Custos Adicionais (Benefícios/Impostos)")
                
                # --- BLOCO 2: LISTA DE CUSTOS EXISTENTES (COM EXCLUSÃO) ---
                custos = conn.execute("SELECT id, tipo_item, nome_item, valor, dia_vencimento FROM custos_pessoal WHERE funcionario_id=?", (func_id_sel,)).fetchall()
                
                if custos:
                    for c in custos:
                        cid, ctipo, cnome, cval, cdia = c
                        cc1, cc2, cc3, cc4 = st.columns([3, 2, 2, 1])
                        cc1.text(f"{cnome} ({ctipo})")
                        cc2.text(format_brl(cval))
                        cc3.text(f"Dia {cdia}")
                        
                        if cc4.button("🗑️", key=f"del_cost_{cid}"):
                            # 1. Remove da tabela de custos
                            conn.execute("DELETE FROM custos_pessoal WHERE id=?", (cid,))
                            
                            # 2. PROPAGAÇÃO: Remove a conta a pagar pendente do financeiro
                            desc_pendente = f"{cnome} - {f_data[2]}" # Nome atual do func
                            conn.execute("DELETE FROM despesas WHERE descricao=? AND status='PENDENTE' AND unidade_id=?", 
                                         (desc_pendente, unidade_atual))
                            conn.commit()
                            st.toast("Custo removido e despesa cancelada.")
                            st.rerun()
                        st.markdown("<hr style='margin:0; opacity:0.1'>", unsafe_allow_html=True)
                else:
                    st.info("Nenhum custo adicional cadastrado.")
                
                # --- BLOCO 3: ADICIONAR NOVO CUSTO (FUNCIONALIDADE RECUPERADA) ---
                with st.expander("➕ Adicionar Novo Custo (Para este funcionário)", expanded=False):
                    with st.form(key=f"add_cost_exist_{func_id_sel}", clear_on_submit=True):
                        ac1, ac2, ac3, ac4 = st.columns([2, 2, 1.5, 1])
                        ntipo = ac1.selectbox("Tipo", ["Benefício", "Imposto"])
                        nnome = ac2.text_input("Nome (Ex: Vale Refeição)")
                        nval = ac3.number_input("Valor", min_value=0.0, step=10.0)
                        ndia = ac4.number_input("Dia", 1, 31, 5)
                        
                        if st.form_submit_button("Adicionar"):
                            if not nnome:
                                st.error("Preencha o nome.")
                            else:
                                try:
                                    tipo_bd = "BENEFICIO" if ntipo == "Benefício" else "IMPOSTO"
                                    # 1. Insere Custo
                                    conn.execute('''
                                        INSERT INTO custos_pessoal (unidade_id, funcionario_id, tipo_item, nome_item, valor, dia_vencimento) 
                                        VALUES (?,?,?,?,?,?)
                                    ''', (unidade_atual, func_id_sel, tipo_bd, nnome, nval, ndia))
                                    
                                    # 2. PROPAGAÇÃO IMEDIATA: Gera a despesa deste mês
                                    # Para o usuário não ter que esperar o robô rodar
                                    hj = datetime.now()
                                    mes_ref = hj.strftime("%m/%Y")
                                    desc_item = f"{nnome} - {f_data[2]}" # Nome do func
                                    cat_item = "Impostos" if tipo_bd == "IMPOSTO" else "Pessoal"
                                    dt_venc = get_valid_date(hj.year, hj.month, ndia)
                                    
                                    # Verifica se já existe para não duplicar
                                    existe = conn.execute("SELECT id FROM despesas WHERE descricao=? AND mes_referencia=? AND unidade_id=?", 
                                                          (desc_item, mes_ref, unidade_atual)).fetchone()
                                    
                                    if not existe:
                                        conn.execute('''
                                            INSERT INTO despesas (unidade_id, categoria, descricao, valor, data_vencimento, mes_referencia, status) 
                                            VALUES (?, ?, ?, ?, ?, ?, 'PENDENTE')
                                        ''', (unidade_atual, cat_item, desc_item, nval, dt_venc, mes_ref))
                                    
                                    conn.commit()
                                    st.success("Custo adicionado e lançamento financeiro gerado!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Erro: {e}")

    else:
        st.warning("Nenhum funcionário encontrado nesta unidade.")
    
    conn.close()