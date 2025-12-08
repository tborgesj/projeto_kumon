import streamlit as st
import pandas as pd
import database as db
import auth
from datetime import datetime, date, timedelta
import calendar

st.set_page_config(page_title="Financeiro", layout="wide", page_icon="💰")
if not auth.validar_sessao(): auth.tela_login(); st.stop()
auth.barra_lateral()

unidade_atual = st.session_state.get('unidade_ativa')
if not unidade_atual: st.error("Erro Unidade"); st.stop()

# --- FUNÇÕES AUXILIARES ---
def format_brl(val): 
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if val else "R$ 0,00"

def get_valid_date(year, month, day): 
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))

def get_visual_status(dt_str):
    try:
        d = datetime.strptime(str(dt_str), '%Y-%m-%d').date() if isinstance(dt_str, str) else dt_str
        hoje = date.today()
        s = d.strftime('%d/%m')
        if d < hoje: return f"🚨 :red[**{s}**]"
        elif d == hoje: return f"⚠️ :orange[**{s}**]"
        return s
    except: return "-"

def get_meses_disponiveis(uid):
    conn = db.conectar()
    df = pd.read_sql_query('SELECT distinct mes_referencia FROM pagamentos WHERE unidade_id=? UNION SELECT distinct mes_referencia FROM despesas WHERE unidade_id=?', conn, params=(uid, uid))
    conn.close()
    lista = df['mes_referencia'].unique().tolist()
    atual = datetime.now().strftime("%m/%Y")
    if atual not in lista: lista.append(atual)
    try:
        prox = (datetime.now().replace(day=1)+pd.DateOffset(months=1)).strftime("%m/%Y")
        if prox not in lista: lista.append(prox)
    except: pass
    lista.sort(key=lambda x: datetime.strptime(x, "%m/%Y") if x else datetime.now(), reverse=True)
    return lista

# --- POPUPS (DIALOGS) ---
@st.dialog("Receber Mensalidade")
def popup_receber(id_pagamento, valor_bruto, nome_aluno):
    st.write(f"**Aluno:** {nome_aluno}")
    st.write(f"**Valor a Receber:** {format_brl(valor_bruto)}")
    st.markdown("---")
    
    with st.form("form_recebimento"):
        forma = st.selectbox("Forma de Pagamento", ["Dinheiro", "Pix", "Boleto", "Débito", "Crédito"])
        st.caption("Se houver taxa de maquininha, informe abaixo para lançar como despesa.")
        taxa = st.number_input("Valor da Taxa (R$)", min_value=0.0, step=0.50)
        
        if st.form_submit_button("💰 Confirmar Recebimento"):
            conn = db.conectar()
            try:
                hoje = date.today()
                conn.execute("UPDATE pagamentos SET status='PAGO', data_pagamento=?, forma_pagamento=? WHERE id=?", (hoje, forma, id_pagamento))
                
                if taxa > 0:
                    mes_ref = hoje.strftime("%m/%Y")
                    desc_despesa = f"Taxa Maquininha ({forma}) - {nome_aluno}"
                    conn.execute("INSERT INTO despesas (unidade_id, categoria, descricao, valor, data_vencimento, mes_referencia, data_pagamento, status) VALUES (?, 'Taxas Financeiras', ?, ?, ?, ?, ?, 'PAGO')", 
                                 (unidade_atual, desc_despesa, taxa, hoje, mes_ref, hoje))
                
                conn.commit()
                st.toast(f"Recebimento de {nome_aluno} confirmado!")
                st.rerun()
            except Exception as e: st.error(f"Erro: {e}")
            finally: conn.close()

@st.dialog("Confirmar Estorno")
def popup_estorno(id_item, tipo_item, descricao):
    st.warning(f"Estornar {descricao}?")
    st.caption("O status voltará para 'PENDENTE'.")
    col_sim, col_nao = st.columns(2)
    if col_sim.button("✅ Sim, Estornar", type="primary"):
        conn = db.conectar()
        try:
            if tipo_item == 'Entrada':
                conn.execute("UPDATE pagamentos SET status='PENDENTE', data_pagamento=NULL, forma_pagamento=NULL WHERE id=?", (id_item,))
            else:
                conn.execute("UPDATE despesas SET status='PENDENTE', data_pagamento=NULL WHERE id=?", (id_item,))
            conn.commit()
            st.toast("Estornado!")
            st.rerun()
        finally: conn.close()
    if col_nao.button("Cancelar"): st.rerun()

# --- ROBÔ FINANCEIRO (MENSALIDADES + BOLSAS + DESPESAS) ---
def run_robos(uid):
    conn = db.conectar()
    mes_str = datetime.now().strftime("%m/%Y")
    hj = datetime.now()
    cnt_d, cnt_r, cnt_p = 0, 0, 0
    
    # 1. DESPESAS RECORRENTES
    regras = conn.execute("SELECT id, categoria, descricao, valor, dia_vencimento FROM despesas_recorrentes WHERE ativo=1 AND unidade_id=?", (uid,)).fetchall()
    for r in regras:
        rid, cat, desc, val, dia = r
        if not conn.execute("SELECT id FROM despesas WHERE recorrente_id=? AND mes_referencia=? AND unidade_id=?", (rid, mes_str, uid)).fetchone():
            conn.execute("INSERT INTO despesas (unidade_id, recorrente_id, categoria, descricao, valor, data_vencimento, mes_referencia, status) VALUES (?,?,?,?,?,?,?, 'PENDENTE')",
                         (uid, rid, cat, desc, val, get_valid_date(hj.year, hj.month, dia), mes_str))
            cnt_d += 1
            
    # 2. MENSALIDADES (COM LÓGICA DE BOLSA)
    # Define data alvo: se hoje > dia 20, gera para o próximo mês
    target = hj if hj.day < 21 else hj + pd.DateOffset(days=32)
    m_ref = target.strftime("%m/%Y")
    
    # Busca Matrículas + Dados de Bolsa
    mats = conn.execute("SELECT id, valor_acordado, aluno_id, dia_vencimento, bolsa_ativa, bolsa_meses_restantes FROM matriculas WHERE ativo=1 AND unidade_id=?", (uid,)).fetchall()
    
    for mid, val_base, aid, dia, b_ativa, b_meses in mats:
        # Verifica se JÁ existe boleto para esse mês/matrícula
        if not conn.execute("SELECT id FROM pagamentos WHERE matricula_id=? AND mes_referencia=? AND unidade_id=?", (mid, m_ref, uid)).fetchone():
            
            valor_final = val_base
            
            # --- LÓGICA DE BOLSA ---
            if b_ativa and b_meses > 0:
                valor_final = val_base * 0.50 # Aplica 50% de desconto
                
                # Consome 1 mês do saldo
                novo_saldo = b_meses - 1
                novo_status_bolsa = 1 if novo_saldo > 0 else 0 # Desativa bolsa se zerar
                
                # Atualiza matrícula
                conn.execute("UPDATE matriculas SET bolsa_meses_restantes=?, bolsa_ativa=? WHERE id=?", (novo_saldo, novo_status_bolsa, mid))
            # -----------------------

            conn.execute("INSERT INTO pagamentos (unidade_id, matricula_id, aluno_id, mes_referencia, data_vencimento, valor_pago, status) VALUES (?,?,?,?,?,?,'PENDENTE')",
                         (uid, mid, aid, m_ref, get_valid_date(target.year, target.month, dia), valor_final))
            cnt_r += 1

    # 3. RH (Salários Fixos + Custos Extras)
    funcs = conn.execute("SELECT id, nome, salario_base, dia_pagamento_salario FROM funcionarios WHERE ativo=1 AND unidade_id=?", (uid,)).fetchall()
    for f in funcs:
        fid, fnome, fsal, fdia = f
        desc_sal = f"Salário - {fnome}"
        # Salário Base
        if not conn.execute("SELECT id FROM despesas WHERE descricao=? AND mes_referencia=? AND unidade_id=?", (desc_sal, mes_str, uid)).fetchone():
            if fsal > 0:
                conn.execute("INSERT INTO despesas (unidade_id, categoria, descricao, valor, data_vencimento, mes_referencia, status) VALUES (?, 'Pessoal', ?, ?, ?, ?, 'PENDENTE')",
                             (uid, desc_sal, fsal, get_valid_date(hj.year, hj.month, fdia), mes_str))
                cnt_p += 1
        
        # Custos Extras (Benefícios/Impostos)
        custos = conn.execute("SELECT tipo_item, nome_item, valor, dia_vencimento FROM custos_pessoal WHERE funcionario_id=?", (fid,)).fetchall()
        for c in custos:
            ctipo, cnome, cval, cdia = c
            desc_item = f"{cnome} - {fnome}"
            cat = "Impostos" if ctipo == "IMPOSTO" else "Pessoal"
            if not conn.execute("SELECT id FROM despesas WHERE descricao=? AND mes_referencia=? AND unidade_id=?", (desc_item, mes_str, uid)).fetchone():
                if cval > 0:
                    conn.execute("INSERT INTO despesas (unidade_id, categoria, descricao, valor, data_vencimento, mes_referencia, status) VALUES (?, ?, ?, ?, ?, ?, 'PENDENTE')",
                                 (uid, cat, desc_item, cval, get_valid_date(hj.year, hj.month, cdia), mes_str))
                    cnt_p += 1

    conn.commit()
    conn.close()
    
    if cnt_d+cnt_r+cnt_p > 0:
        st.toast(f"🤖 Robô executado: {cnt_r} Boletos, {cnt_d} Despesas, {cnt_p} RH gerados.")

run_robos(unidade_atual)

# --- INTERFACE PRINCIPAL ---
st.title("💰 Controle Financeiro")
lista_meses = get_meses_disponiveis(unidade_atual)
tab_in, tab_out, tab_fluxo = st.tabs(["🟢 Entradas (Receber)", "🔴 Saídas (Pagar)", "📊 Fluxo de Caixa"])

# ABA ENTRADAS
with tab_in:
    c1, c2 = st.columns([1,3])
    filtro_in = c1.selectbox("Mês (Entradas)", ["Todos"]+lista_meses, index=1)
    conn = db.conectar()
    q = "SELECT p.id, p.data_vencimento, a.nome, m.disciplina, p.valor_pago FROM pagamentos p LEFT JOIN matriculas m ON p.matricula_id=m.id JOIN alunos a ON COALESCE(p.aluno_id, m.aluno_id)=a.id WHERE p.status='PENDENTE' AND p.unidade_id=?"
    p = [unidade_atual]
    if filtro_in != "Todos": q += " AND p.mes_referencia=?"; p.append(filtro_in)
    q += " ORDER BY p.data_vencimento"
    df = pd.read_sql(q, conn, params=p)
    conn.close()
    if not df.empty:
        st.markdown("**Vencimento | Aluno | Valor | Ação**")
        for i, r in df.iterrows():
            c1,c2,c3,c4 = st.columns([1.5, 4, 1.5, 1.5])
            c1.markdown(get_visual_status(r['data_vencimento']))
            c2.text(f"{r['nome']} ({r['disciplina'] if r['disciplina'] else 'Taxa'})")
            c3.text(format_brl(r['valor_pago']))
            if c4.button("Receber", key=f"r_{r['id']}"): popup_receber(r['id'], r['valor_pago'], r['nome'])
            st.markdown("<hr style='margin:0; opacity:0.1'>", unsafe_allow_html=True)
    else: st.info("Nada pendente.")

# ABA SAÍDAS
with tab_out:
    c1, c2 = st.columns([1,3])
    filtro_out = c1.selectbox("Mês (Saídas)", ["Todos"]+lista_meses, index=1)
    conn = db.conectar()
    q = "SELECT id, data_vencimento, categoria, descricao, valor FROM despesas WHERE status='PENDENTE' AND unidade_id=?"
    p = [unidade_atual]
    if filtro_out != "Todos": q += " AND mes_referencia=?"; p.append(filtro_out)
    q += " ORDER BY data_vencimento"
    df = pd.read_sql(q, conn, params=p)
    conn.close()
    if not df.empty:
        st.markdown("**Vencimento | Descrição | Valor | Ação**")
        for i, r in df.iterrows():
            c1,c2,c3,c4 = st.columns([1.5, 4, 1.5, 1.5])
            c1.markdown(get_visual_status(r['data_vencimento']))
            c2.text(f"{r['categoria']} - {r['descricao']}")
            c3.text(format_brl(r['valor']))
            if c4.button("Pagar", key=f"p_{r['id']}"):
                cn=db.conectar(); cn.execute("UPDATE despesas SET status='PAGO', data_pagamento=DATE('now') WHERE id=?",(r['id'],)); cn.commit(); cn.close(); st.rerun()
            st.markdown("<hr style='margin:0; opacity:0.1'>", unsafe_allow_html=True)
    else: st.info("Nada a pagar.")

# ABA FLUXO
with tab_fluxo:
    c1, c2 = st.columns([1,3])
    f_fluxo = c1.selectbox("Mês (Fluxo)", lista_meses, index=0)
    conn = db.conectar()
    
    q_rec = '''SELECT p.id, p.data_pagamento, 'Entrada' as Tipo, p.valor_pago, p.forma_pagamento, a.nome || ' - ' || COALESCE(m.disciplina, 'Taxa') as Descricao 
               FROM pagamentos p LEFT JOIN matriculas m ON p.matricula_id = m.id JOIN alunos a ON COALESCE(p.aluno_id, m.aluno_id) = a.id 
               WHERE p.status='PAGO' AND p.unidade_id=? AND p.mes_referencia=?'''
    q_des = '''SELECT d.id, d.data_pagamento, 'Saída' as Tipo, d.valor as valor_pago, '' as forma_pagamento, d.categoria || ' - ' || d.descricao as Descricao 
               FROM despesas d WHERE d.status='PAGO' AND d.unidade_id=? AND d.mes_referencia=?'''
    
    rec = pd.read_sql(q_rec, conn, params=(unidade_atual, f_fluxo))
    des = pd.read_sql(q_des, conn, params=(unidade_atual, f_fluxo))
    conn.close()
    
    geral = pd.concat([rec, des], ignore_index=True)
    if not geral.empty:
        geral['data_pagamento'] = pd.to_datetime(geral['data_pagamento'])
        geral = geral.sort_values('data_pagamento', ascending=False)
        
        h1, h2, h3, h4, h5, h6 = st.columns([1.2, 1, 4, 1.5, 1.5, 1.2])
        h1.markdown("**Data**"); h2.markdown("**Tipo**"); h3.markdown("**Descrição**"); h4.markdown("**Valor**"); h5.markdown("**Forma**"); h6.markdown("**Ação**")
        st.divider()
        
        tr, td = 0, 0
        for i, row in geral.iterrows():
            if row['Tipo'] == 'Entrada': tr += row['valor_pago']
            else: td += row['valor_pago']
            c1, c2, c3, c4, c5, c6 = st.columns([1.2, 1, 4, 1.5, 1.5, 1.2])
            c1.text(row['data_pagamento'].strftime('%d/%m'))
            c2.markdown(f"<span style='color:{'green' if row['Tipo']=='Entrada' else 'red'}'>{row['Tipo']}</span>", unsafe_allow_html=True)
            c3.text(row['Descricao'])
            c4.text(format_brl(row['valor_pago']))
            c5.text(row['forma_pagamento'] if row['forma_pagamento'] else "-")
            if c6.button("↩️", key=f"est_{row['Tipo']}_{row['id']}", help="Estornar"):
                popup_estorno(row['id'], row['Tipo'], row['Descricao'])
            st.markdown("<hr style='margin: 0px 0px 10px 0px; opacity: 0.1'>", unsafe_allow_html=True)
            
        st.divider()
        k1, k2, k3 = st.columns(3)
        k1.metric("Entradas", format_brl(tr))
        k2.metric("Saídas", format_brl(td))
        k3.metric("Saldo", format_brl(tr - td), delta_color="normal")
    else: st.info("Sem movimento.")