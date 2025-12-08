import streamlit as st
import pandas as pd
import database as db
import auth
from datetime import datetime, date
import calendar

st.set_page_config(page_title="Gestão de Despesas", layout="wide", page_icon="💸")
if not auth.validar_sessao(): auth.tela_login(); st.stop()
auth.barra_lateral()

# --- SEGURANÇA MULTI-UNIDADE ---
unidade_atual = st.session_state.get('unidade_ativa')
nome_unidade = st.session_state.get('unidade_nome', 'Unidade')

if not unidade_atual:
    st.error("Erro de Unidade. Faça login novamente.")
    st.stop()

st.title(f"💸 Gestão de Despesas - {nome_unidade}")

# --- HELPER FUNCTIONS ---
def format_brl(val): 
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def get_valid_date(year, month, day):
    last_day_of_month = calendar.monthrange(year, month)[1]
    safe_day = min(day, last_day_of_month)
    return date(year, month, safe_day)

@st.dialog("Sucesso!")
def show_success(msg):
    st.success(msg)
    if st.button("OK"):
        st.rerun()

# Carrega Categorias
conn = db.conectar()
cats_df = pd.read_sql("SELECT nome_categoria FROM categorias_despesas ORDER BY nome_categoria", conn)
categorias = cats_df['nome_categoria'].tolist()
conn.close()

tab1, tab2 = st.tabs(["➕ Nova Despesa", "🔄 Gerenciar Recorrências (Fixas)"])

# ==============================================================================
# ABA 1: LANÇAMENTO DE NOVA DESPESA
# ==============================================================================
with tab1:
    st.subheader("Lançar Conta a Pagar")
    st.caption("Use para contas que chegam todo mês (Recorrente) ou gastos únicos (Avulsa).")
    
    with st.container():
        tipo_lancamento = st.radio("Tipo:", ["Avulsa (Única)", "Recorrente (Todo Mês)"], horizontal=True)
        
        with st.form("form_nova_despesa", clear_on_submit=True):
            c1, c2 = st.columns(2)
            desc = c1.text_input("Descrição (Ex: Manutenção Ar Condicionado)")
            cat = c2.selectbox("Categoria", categorias)
            
            c3, c4 = st.columns(2)
            valor = c3.number_input("Valor (R$)", min_value=0.0, step=10.0)
            
            dia_venc = 10
            dt_avulsa = date.today()
            
            if tipo_lancamento == "Recorrente (Todo Mês)":
                dia_venc = c4.number_input("Dia de Vencimento Mensal", 1, 31, 10)
                st.info(f"ℹ️ O sistema gerará automaticamente uma conta todo dia {dia_venc}.")
            else:
                dt_avulsa = c4.date_input("Data de Vencimento", value=date.today())
            
            if st.form_submit_button("💾 Salvar Despesa"):
                if not desc:
                    st.error("A descrição é obrigatória.")
                else:
                    conn = db.conectar()
                    try:
                        if tipo_lancamento == "Recorrente (Todo Mês)":
                            # 1. Cria a Regra Recorrente
                            cur = conn.execute('''
                                INSERT INTO despesas_recorrentes (unidade_id, categoria, descricao, valor, dia_vencimento, limite_meses, data_criacao, ativo) 
                                VALUES (?, ?, ?, ?, ?, 0, DATE('now'), 1)
                            ''', (unidade_atual, cat, desc, valor, dia_venc))
                            rid = cur.lastrowid
                            
                            # 2. Gera a PRIMEIRA cobranca (deste mês) para não esperar o robô
                            hj = datetime.now()
                            m_ref = f"{hj.month:02d}/{hj.year}"
                            dt_venc_atual = get_valid_date(hj.year, hj.month, dia_venc)
                            
                            # Verifica se o vencimento já passou muito (ex: hoje é dia 25 e vence dia 5 -> joga pro mês que vem?)
                            # Regra simplificada: Gera pro mês atual independente, usuário ajusta se quiser.
                            
                            conn.execute('''
                                INSERT INTO despesas (unidade_id, recorrente_id, categoria, descricao, valor, data_vencimento, mes_referencia, status) 
                                VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDENTE')
                            ''', (unidade_atual, rid, cat, desc, valor, dt_venc_atual, m_ref))
                            
                            msg = "Despesa Fixa criada! A primeira conta já está no Financeiro."
                            
                        else:
                            # Despesa Avulsa
                            m_ref = dt_avulsa.strftime("%m/%Y")
                            conn.execute('''
                                INSERT INTO despesas (unidade_id, categoria, descricao, valor, data_vencimento, mes_referencia, status) 
                                VALUES (?, ?, ?, ?, ?, ?, 'PENDENTE')
                            ''', (unidade_atual, cat, desc, valor, dt_avulsa, m_ref))
                            
                            msg = "Despesa Avulsa lançada no Financeiro."
                        
                        conn.commit()
                        show_success(msg)
                        
                    except Exception as e:
                        st.error(f"Erro ao salvar: {e}")
                    finally:
                        conn.close()

# ==============================================================================
# ABA 2: GERENCIAR RECORRÊNCIAS
# ==============================================================================
with tab2:
    st.subheader("Gerenciar Contas Fixas")
    
    conn = db.conectar()
    
    # Lista apenas as ATIVAS por padrão
    filtro_ativo = st.checkbox("Mostrar apenas regras ativas?", value=True)
    
    q = "SELECT id, categoria, descricao, valor, dia_vencimento, ativo FROM despesas_recorrentes WHERE unidade_id=?"
    if filtro_ativo: q += " AND ativo=1"
    q += " ORDER BY descricao"
    
    df = pd.read_sql_query(q, conn, params=(unidade_atual,))
    
    if not df.empty:
        # Layout de Lista
        col_list, col_edit = st.columns([1, 2])
        
        with col_list:
            st.markdown("##### Selecione para Editar:")
            rec_id_sel = st.radio(
                "Lista:", 
                df['id'].tolist(), 
                format_func=lambda x: f"{df[df['id']==x]['descricao'].values[0]} ({format_brl(df[df['id']==x]['valor'].values[0])})",
                label_visibility="collapsed"
            )

        with col_edit:
            if rec_id_sel:
                # Pega dados frescos do banco
                r_data = conn.execute("SELECT * FROM despesas_recorrentes WHERE id=?", (rec_id_sel,)).fetchone()
                # indices: 0:id, 1:uid, 2:cat, 3:desc, 4:val, 5:dia, 6:limite, 7:criacao, 8:ativo
                
                st.markdown(f"### ✏️ Editando: {r_data[3]}")
                
                with st.form(key=f"edit_rec_{rec_id_sel}"):
                    ec1, ec2 = st.columns(2)
                    n_cat = ec1.selectbox("Categoria", categorias, index=categorias.index(r_data[2]) if r_data[2] in categorias else 0)
                    n_desc = ec2.text_input("Descrição", value=r_data[3])
                    
                    ec3, ec4 = st.columns(2)
                    n_val = ec3.number_input("Valor Mensal (R$)", value=float(r_data[4]), step=10.0)
                    n_dia = ec4.number_input("Dia Vencimento", 1, 31, int(r_data[5]))
                    
                    is_ativo = bool(r_data[8])
                    n_ativo = st.checkbox("Despesa Ativa (Gerando cobranças)?", value=is_ativo)
                    
                    if st.form_submit_button("Atualizar Regra"):
                        try:
                            # 1. Atualiza a Regra
                            conn.execute('''
                                UPDATE despesas_recorrentes 
                                SET categoria=?, descricao=?, valor=?, dia_vencimento=?, ativo=? 
                                WHERE id=?
                            ''', (n_cat, n_desc, n_val, n_dia, 1 if n_ativo else 0, rec_id_sel))
                            
                            # 2. PROPAGAÇÃO (ATUALIZAR BOLETO PENDENTE)
                            # Se o valor ou descrição mudou, atualizamos a conta que está PENDENTE no financeiro
                            # (Apenas as pendentes geradas por esta regra)
                            if is_ativo: # Só propaga se estava ativo
                                conn.execute('''
                                    UPDATE despesas 
                                    SET valor=?, descricao=?, categoria=? 
                                    WHERE recorrente_id=? AND status='PENDENTE' AND unidade_id=?
                                ''', (n_val, n_desc, n_cat, rec_id_sel, unidade_atual))
                            
                            conn.commit()
                            show_success("Regra atualizada e contas pendentes ajustadas!")
                        except Exception as e:
                            st.error(f"Erro: {e}")
                            
                st.markdown("---")
                if is_ativo:
                    if st.button("🗑️ Encerrar Recorrência (Parar de gerar)", type="primary"):
                        conn.execute("UPDATE despesas_recorrentes SET ativo=0 WHERE id=?", (rec_id_sel,))
                        conn.commit()
                        show_success("Recorrência encerrada com sucesso.")
                else:
                    st.info("Esta despesa já está inativa.")

    else:
        st.info("Nenhuma despesa recorrente encontrada.")
    
    conn.close()