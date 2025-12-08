import streamlit as st
import pandas as pd
import database as db
import auth
from datetime import datetime, date

st.set_page_config(page_title="Cofres Inteligentes", layout="wide", page_icon="🏦")
if not auth.validar_sessao(): auth.tela_login(); st.stop()
auth.barra_lateral()

# --- SEGURANÇA ---
unidade_atual = st.session_state.get('unidade_ativa')
nome_unidade = st.session_state.get('unidade_nome', 'Unidade')

if not unidade_atual:
    st.error("Selecione uma unidade.")
    st.stop()

st.title(f"🏦 Cofres Inteligentes - {nome_unidade}")
st.markdown("Gestão de Tesouraria: Separe o lucro em 'potes' virtuais para garantir o futuro da empresa.")

def format_brl(val): 
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# --- POPUP DE DISTRIBUIÇÃO ---
@st.dialog("Distribuir Lucros")
def popup_distribuir(lucro_disponivel, df_cofres):
    st.write(f"**Lucro a Distribuir:** {format_brl(lucro_disponivel)}")
    st.caption("Ajuste os valores se necessário. O padrão segue suas regras de %.")
    
    input_vals = {}
    total_alocado = 0.0
    
    with st.form("form_dist"):
        for index, row in df_cofres.iterrows():
            perc = row['percentual_padrao']
            valor_sugerido = (lucro_disponivel * perc) / 100
            
            c1, c2 = st.columns([3, 2])
            c1.write(f"**{row['nome']}** ({perc}%)")
            input_vals[row['id']] = c2.number_input(f"Valor (R$)", value=float(valor_sugerido), step=10.0, key=f"d_{row['id']}")
            total_alocado += input_vals[row['id']]
        
        st.divider()
        st.markdown(f"**Total Alocado:** {format_brl(sum(input_vals.values()))}")
        
        if st.form_submit_button("✅ Confirmar Distribuição"):
            conn = db.conectar()
            try:
                hoje = date.today()
                for cid, val in input_vals.items():
                    if val > 0:
                        # 1. Atualiza Saldo
                        conn.execute("UPDATE cofres_saldo SET saldo_atual = saldo_atual + ? WHERE cofre_id=? AND unidade_id=?", 
                                     (val, cid, unidade_atual))
                        # 2. Registra Histórico
                        conn.execute("INSERT INTO cofres_movimentacao (unidade_id, cofre_id, data_movimentacao, valor, tipo, descricao) VALUES (?, ?, ?, ?, 'ENTRADA', 'Distribuição de Lucro')", 
                                     (unidade_atual, cid, hoje, val))
                conn.commit()
                st.success("Lucro guardado nos cofres com sucesso!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro: {e}")
            finally:
                conn.close()

# --- POPUP DE SAQUE/USO ---
@st.dialog("Utilizar Recurso do Cofre")
def popup_saque(cofre_id, nome_cofre, saldo_atual):
    st.subheader(f"Sacar de: {nome_cofre}")
    st.info(f"Saldo Disponível: {format_brl(saldo_atual)}")
    
    with st.form("form_saque"):
        valor = st.number_input("Valor a Utilizar (R$)", min_value=0.01, max_value=float(saldo_atual), step=10.0)
        motivo = st.text_input("Motivo (Ex: Pagamento 1ª parc 13º)")
        
        if st.form_submit_button("📉 Confirmar Uso"):
            if not motivo:
                st.error("Informe o motivo.")
            else:
                conn = db.conectar()
                try:
                    # 1. Debita Saldo
                    conn.execute("UPDATE cofres_saldo SET saldo_atual = saldo_atual - ? WHERE cofre_id=? AND unidade_id=?", 
                                 (valor, cofre_id, unidade_atual))
                    # 2. Histórico
                    conn.execute("INSERT INTO cofres_movimentacao (unidade_id, cofre_id, data_movimentacao, valor, tipo, descricao) VALUES (?, ?, DATE('now'), ?, 'SAIDA', ?)", 
                                 (unidade_atual, cofre_id, valor, motivo))
                    conn.commit()
                    st.success("Saque registrado!")
                    st.rerun()
                except Exception as e: st.error(e)
                finally: conn.close()

# --- LÓGICA PRINCIPAL ---
conn = db.conectar()

# 1. Busca Dados dos Cofres
q_cofres = '''
    SELECT c.id, c.nome, c.percentual_padrao, c.descricao, s.saldo_atual 
    FROM cofres c 
    JOIN cofres_saldo s ON c.id = s.cofre_id 
    WHERE c.unidade_id = ?
'''
df_cofres = pd.read_sql_query(q_cofres, conn, params=(unidade_atual,))

# 2. Calcula Lucro do Mês Anterior (Para sugestão)
hj = datetime.now()
mes_ant_date = (hj.replace(day=1) - pd.DateOffset(days=1))
mes_ant_str = mes_ant_date.strftime("%m/%Y")

# Receita PAGA
rec = conn.execute("SELECT SUM(valor_pago) FROM pagamentos WHERE mes_referencia=? AND status='PAGO' AND unidade_id=?", (mes_ant_str, unidade_atual)).fetchone()[0] or 0.0
# Despesa PAGA
des = conn.execute("SELECT SUM(valor) FROM despesas WHERE mes_referencia=? AND status='PAGO' AND unidade_id=?", (mes_ant_str, unidade_atual)).fetchone()[0] or 0.0
lucro_sugerido = rec - des
if lucro_sugerido < 0: lucro_sugerido = 0.0

conn.close()

tab1, tab2, tab3 = st.tabs(["📊 Dashboard & Distribuição", "⚙️ Configurar Regras", "📜 Extrato"])

# ==============================================================================
# TAB 1: DASHBOARD
# ==============================================================================
with tab1:
    # A. PAINEL DE SALDOS
    st.subheader("Saldos Acumulados")
    cols = st.columns(len(df_cofres)) if not df_cofres.empty else [st.container()]
    
    total_guardado = 0
    for i, row in df_cofres.iterrows():
        total_guardado += row['saldo_atual']
        with cols[i % 4]: # Quebra linha a cada 4
            st.metric(label=row['nome'], value=format_brl(row['saldo_atual']))
            if st.button("Sacar", key=f"btn_saque_{row['id']}"):
                popup_saque(row['id'], row['nome'], row['saldo_atual'])
    
    st.divider()
    
    # B. SIMULADOR E DISTRIBUIÇÃO
    st.markdown("### 💸 Distribuir Lucros")
    
    c_sim1, c_sim2 = st.columns([2, 1])
    with c_sim1:
        st.info(f"Lucro Realizado do mês passado ({mes_ant_str}): **{format_brl(rec - des)}**")
        val_dist = st.number_input("Quanto deseja distribuir agora?", value=float(lucro_sugerido), min_value=0.0, step=100.0)
    
    with c_sim2:
        st.write("##") # Spacer
        if st.button("🚀 Distribuir nos Cofres", type="primary"):
            if val_dist > 0:
                popup_distribuir(val_dist, df_cofres)
            else:
                st.warning("Informe um valor maior que zero.")

# ==============================================================================
# TAB 2: CONFIGURAÇÃO
# ==============================================================================
with tab2:
    st.subheader("Definir Regras de Porcentagem")
    st.caption("A soma das porcentagens deve ser idealmente 100%.")
    
    with st.form("config_cofres"):
        conn = db.conectar()
        # Input editável para cada cofre
        novos_percs = {}
        total_perc = 0
        
        for index, row in df_cofres.iterrows():
            c1, c2 = st.columns([3, 1])
            c1.markdown(f"**{row['nome']}**")
            c1.caption(row['descricao'])
            val = c2.number_input(f"% Alocação", value=float(row['percentual_padrao']), min_value=0.0, max_value=100.0, step=1.0, key=f"cfg_{row['id']}")
            novos_percs[row['id']] = val
            total_perc += val
            st.markdown("---")
            
        st.markdown(f"**Total Configurado: {total_perc:.1f}%**")
        if total_perc != 100:
            st.warning("Atenção: A soma não é 100%. Verifique se é intencional.")
            
        if st.form_submit_button("💾 Salvar Novas Regras"):
            try:
                for cid, perc in novos_percs.items():
                    conn.execute("UPDATE cofres SET percentual_padrao=? WHERE id=?", (perc, cid))
                conn.commit()
                st.success("Regras atualizadas!")
                st.rerun()
            except Exception as e: st.error(e)
            finally: conn.close()

# ==============================================================================
# TAB 3: EXTRATO
# ==============================================================================
with tab3:
    st.subheader("Histórico de Movimentações")
    conn = db.conectar()
    hist = pd.read_sql_query('''
        SELECT m.data_movimentacao, c.nome, m.tipo, m.valor, m.descricao 
        FROM cofres_movimentacao m 
        JOIN cofres c ON m.cofre_id = c.id 
        WHERE m.unidade_id = ? 
        ORDER BY m.id DESC
    ''', conn, params=(unidade_atual,))
    conn.close()
    
    if not hist.empty:
        # Formatação
        hist['valor'] = hist['valor'].apply(format_brl)
        st.dataframe(hist.style.map(lambda x: f'color: {"green" if x=="ENTRADA" else "red"}', subset=['tipo']), use_container_width=True)
    else:
        st.info("Nenhuma movimentação registrada ainda.")