import streamlit as st
import pandas as pd
import database as db
import auth
from datetime import datetime, date, timedelta
import calendar
import time

st.set_page_config(page_title="Financeiro", layout="wide", page_icon="💰")
if not auth.validar_sessao(): auth.tela_login(); st.stop()
auth.barra_lateral()

unidade_atual = st.session_state.get('unidade_ativa')
if not unidade_atual: st.error("Erro Unidade"); st.stop()

# --- ROBÔ AUTOMÁTICO (Executa ao abrir a tela) ---
try:
    # Chama a função blindada do banco silenciosamente
    c_desp, c_rec, c_rh = db.executar_robo_financeiro(unidade_atual)
    
    total_gerado = c_desp + c_rec + c_rh
    
    # Só avisa e recarrega SE houve alguma novidade
    if total_gerado > 0:
        st.toast(f"🤖 Robô: {c_rec} Boletos, {c_desp} Despesas e {c_rh} RH gerados.", icon="✅")
        time.sleep(1.5) # Pausa rápida para ler o toast
        st.rerun()      # Recarrega a página para exibir os novos dados nas tabelas abaixo
        
except Exception as e:
    # Se der erro no robô, mostramos um aviso discreto mas não travamos a tela inteira
    st.error(f"Alerta: O Robô Financeiro encontrou um problema: {e}")



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
    # 1. Busca o histórico real do banco (backend)
    lista = db.buscar_meses_com_movimento(uid)
    
    # 2. Lógica de Apresentação (Frontend)
    # Garante que o mês atual e o próximo apareçam na lista, mesmo sem dados
    atual = datetime.now().strftime("%m/%Y")
    if atual not in lista: 
        lista.append(atual)
    
    # 3. Ordenação Decrescente (Data mais recente primeiro)
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
            try:
                # Recupera a unidade da sessão
                unidade = st.session_state.get('unidade_ativa')
                
                # Chama a função blindada do backend
                db.registrar_recebimento(
                    unidade_id=unidade,
                    pagamento_id=id_pagamento,
                    forma=forma,
                    taxa=taxa,
                    nome_aluno=nome_aluno
                )
                
                st.toast(f"Recebimento de {nome_aluno} confirmado!")
                time.sleep(1)
                st.rerun()
                
            except Exception as e:
                st.error(f"Erro ao processar recebimento: {e}")

@st.dialog("Confirmar Estorno")
def popup_estorno(id_item, tipo_item, descricao):
    st.warning(f"Deseja realmente estornar: **{descricao}**?")
    st.caption("O status voltará para 'PENDENTE' e a data de pagamento será apagada.")
    
    col_sim, col_nao = st.columns(2)
    
    if col_sim.button("✅ Sim, Estornar", type="primary"):
        try:
            # Chama a função blindada do backend
            db.estornar_operacao(id_item, tipo_item)
            
            st.toast("Operação estornada com sucesso!")
            time.sleep(0.5) # Pausa rápida para ler o toast
            st.rerun()
            
        except Exception as e:
            st.error(f"Erro ao estornar: {e}")
            
    if col_nao.button("Cancelar"):
        st.rerun()



# --- INTERFACE PRINCIPAL ---
st.title("💰 Controle Financeiro")
lista_meses = get_meses_disponiveis(unidade_atual)
tab_in, tab_out, tab_fluxo = st.tabs(["🟢 Entradas (Receber)", "🔴 Saídas (Pagar)", "📊 Fluxo de Caixa"])

# ABA ENTRADAS
with tab_in:
    c1, c2 = st.columns([1,3])
    filtro_in = c1.selectbox("Mês (Entradas)", ["Todos"]+lista_meses, index=1)
    
    # 1. Busca Segura (Sem SQL na tela)
    df = db.buscar_recebimentos_pendentes(unidade_atual, filtro_in)
    
    if not df.empty:
        st.markdown("**Vencimento | Aluno | Valor | Ação**")
        for i, r in df.iterrows():
            c1,c2,c3,c4 = st.columns([1.5, 4, 1.5, 1.5])
            
            # Formatação Visual
            c1.markdown(get_visual_status(r['data_vencimento']))
            
            # Tratamento de nome de disciplina (lógica de apresentação)
            disciplina = r['disciplina'] if r['disciplina'] else 'Taxa'
            c2.text(f"{r['nome']} ({disciplina})")
            
            c3.text(format_brl(db.from_cents(r['valor_pago'])))
            
            # Botão de Ação chamando o Popup (que já arrumamos antes)
            if c4.button("Receber", key=f"r_{r['id']}"): 
                popup_receber(r['id'], r['valor_pago'], r['nome'])
                
            st.markdown("<hr style='margin:0; opacity:0.1'>", unsafe_allow_html=True)
    else:
        st.info("Nada pendente para receber.")

# ABA SAÍDAS
with tab_out:
    c1, c2 = st.columns([1,3])
    filtro_out = c1.selectbox("Mês (Saídas)", ["Todos"] + lista_meses, index=1)
    
    # 1. Busca os dados usando a função nova
    df = db.buscar_despesas_pendentes(unidade_atual, filtro_out)
    
    if not df.empty:
        st.markdown("**Vencimento | Descrição | Valor | Ação**")
        
        for i, r in df.iterrows():
            c1, c2, c3, c4 = st.columns([1.5, 4, 1.5, 1.5])
            
            # Funções visuais (assumindo que já existem no seu código)
            c1.markdown(get_visual_status(r['data_vencimento']))
            c2.text(f"{r['nome_categoria']} - {r['descricao']}")
            c3.text(format_brl(db.from_cents(r['valor'])))
            
            # 2. Lógica do Botão Segura
            if c4.button("Pagar", key=f"p_{r['id']}"):
                try:
                    db.pagar_despesa(r['id'])
                    st.toast("Conta paga com sucesso!")
                    time.sleep(0.5)
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao pagar: {e}")
            
            st.markdown("<hr style='margin:0; opacity:0.1'>", unsafe_allow_html=True)
    else:
        st.info("Nada a pagar neste período.")

# ABA FLUXO

with tab_fluxo:
    c1, c2 = st.columns([1,3])
    f_fluxo = c1.selectbox("Mês (Fluxo)", lista_meses, index=0)
    
    # 1. Busca os dados prontos do Backend
    geral = db.buscar_fluxo_caixa(unidade_atual, f_fluxo)
    
    if not geral.empty:
        # Cabeçalho da Tabela
        h1, h2, h3, h4, h5, h6 = st.columns([1.2, 1, 4, 1.5, 1.5, 1.2])
        h1.markdown("**Data**"); h2.markdown("**Tipo**"); h3.markdown("**Descrição**")
        h4.markdown("**Valor**"); h5.markdown("**Forma**"); h6.markdown("**Ação**")
        st.divider()
        
        # Loop de Exibição
        for i, row in geral.iterrows():
            c1, c2, c3, c4, c5, c6 = st.columns([1.2, 1, 4, 1.5, 1.5, 1.2])
            
            # Formatação de data segura
            data_fmt = row['data_pagamento'].strftime('%d/%m') if pd.notnull(row['data_pagamento']) else "-"
            c1.text(data_fmt)
            
            # Badge colorido para Tipo
            cor = 'green' if row['Tipo'] == 'Entrada' else 'red'
            c2.markdown(f":{cor}[{row['Tipo']}]")
            
            c3.text(row['Descricao'])
            c4.text(format_brl(db.from_cents(row['valor_pago'])))
            c5.text(row['forma_pagamento'] if row['forma_pagamento'] else "-")
            
            # Botão de Estorno
            if c6.button("↩️", key=f"est_{row['Tipo']}_{row['id']}", help="Estornar Lançamento"):
                popup_estorno(row['id'], row['Tipo'], row['Descricao'])
                
            st.markdown("<hr style='margin: 0px 0px 10px 0px; opacity: 0.1'>", unsafe_allow_html=True)
            
        st.divider()
        
        # Cálculo de Totais (Otimizado com Pandas)
        total_entradas = db.from_cents(geral[geral['Tipo'] == 'Entrada']['valor_pago'].sum())
        total_saidas = db.from_cents(geral[geral['Tipo'] == 'Saída']['valor_pago'].sum())
        saldo = total_entradas - total_saidas
        
        k1, k2, k3 = st.columns(3)
        k1.metric("Total Entradas", format_brl(total_entradas))
        k2.metric("Total Saídas", format_brl(total_saidas))
        k3.metric("Saldo do Período", format_brl(saldo), delta_color="normal")
        
    else:
        st.info("Sem movimentação financeira neste mês.")
