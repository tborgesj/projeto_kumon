import sys
import os

# 1. Pega o caminho absoluto de onde o arquivo '1_Aluno.py' está
diretorio_atual = os.path.dirname(os.path.abspath(__file__))

# 2. Sobe um nível para chegar na raiz do projeto (o pai do diretorio_atual)
diretorio_raiz = os.path.dirname(diretorio_atual)

# 3. Adiciona a raiz à lista de lugares onde o Python procura arquivos
sys.path.append(diretorio_raiz)

from repositories import cofres_rps as rps

import streamlit as st
import pandas as pd
import database as db
import auth
from datetime import datetime, date
import time

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
    
    with st.form("form_dist"):
        # Interface de Cálculo
        for index, row in df_cofres.iterrows():
            perc = row['percentual_padrao']
            # Calcula sugestão baseado no % cadastrado
            valor_sugerido = (lucro_disponivel * perc) / 100
            
            c1, c2 = st.columns([3, 2])
            c1.write(f"**{row['nome']}** ({perc}%)")
            
            # Coleta o input do usuário (que pode alterar a sugestão)
            input_vals[row['id']] = c2.number_input(
                f"Valor (R$)", 
                value=float(valor_sugerido), 
                step=10.0, 
                key=f"d_{row['id']}"
            )
        
        # Mostra total visualmente
        total_alocado = sum(input_vals.values())
        st.divider()
        st.markdown(f"**Total Alocado:** {format_brl(total_alocado)}")
        
        if total_alocado > lucro_disponivel:
            st.warning("⚠️ Atenção: Você está alocando mais do que o lucro disponível.")
        
        if st.form_submit_button("✅ Confirmar Distribuição"):
            try:
                # Chama a função de lote do backend
                rps.realizar_distribuicao_lucro(st.session_state['unidade_ativa'], input_vals)
                
                st.success("Lucro guardado nos cofres com sucesso!")
                time.sleep(1)
                st.rerun()
                
            except Exception as e:
                st.error(f"Erro ao distribuir: {e}")

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
                st.error("Informe o motivo da utilização do recurso.")
            else:
                try:
                    # Recupera ID da unidade da sessão para segurança
                    unidade_atual = st.session_state.get('unidade_ativa')
                    
                    # Chama a função segura do backend
                    rps.realizar_saque_cofre(unidade_atual, cofre_id, valor, motivo)
                    
                    st.success("Saque registrado com sucesso!")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao realizar saque: {e}")

# --- LÓGICA PRINCIPAL (Separada) ---

# 1. Busca Dados dos Cofres (Backend)
df_cofres = rps.buscar_cofres_com_saldo(unidade_atual)

# 2. Calcula Lucro do Mês Anterior (Lógica de Data + Backend)
hj = datetime.now()
# Pega o primeiro dia deste mês e volta um dia para cair no mês anterior
mes_ant_date = (hj.replace(day=1) - pd.DateOffset(days=1))
mes_ant_str = mes_ant_date.strftime("%m/%Y")

# Chama a "Fórmula Oficial" do lucro
lucro_sugerido = rps.calcular_lucro_realizado(unidade_atual, mes_ant_str)

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
        # Usamos 'lucro_sugerido', que já calculamos logo acima usando a função do banco
        st.info(f"Lucro Realizado do mês passado ({mes_ant_str}): **{format_brl(lucro_sugerido)}**")
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
        # Dicionário para guardar os inputs do usuário
        novos_percs = {}
        total_perc = 0.0
        
        # Itera sobre os dados carregados anteriormente (df_cofres)
        if not df_cofres.empty:
            for index, row in df_cofres.iterrows():
                c1, c2 = st.columns([3, 1])
                c1.markdown(f"**{row['nome']}**")
                c1.caption(row['descricao'])
                
                val = c2.number_input(
                    f"% Alocação", 
                    value=float(row['percentual_padrao']), 
                    min_value=0.0, 
                    max_value=100.0, 
                    step=1.0, 
                    key=f"cfg_{row['id']}"
                )
                
                novos_percs[row['id']] = val
                total_perc += val
                st.markdown("---")
        
        # Feedback Visual do Total
        cor_total = "green" if total_perc == 100 else "orange"
        st.markdown(f"**Total Configurado:** :{cor_total}[{total_perc:.1f}%]")
        
        if total_perc != 100:
            st.warning("⚠️ A soma não é 100%. Verifique se é intencional.")
            
        if st.form_submit_button("💾 Salvar Novas Regras"):
            try:
                # Chama a função segura do backend
                rps.atualizar_percentuais_cofres(novos_percs)
                
                st.success("Regras atualizadas com sucesso!")
                time.sleep(1)
                st.rerun()
                
            except Exception as e:
                st.error(f"Erro ao salvar: {e}")

# ==============================================================================
# TAB 3: EXTRATO
# ==============================================================================
with tab3:
    st.subheader("Histórico de Movimentações")
    
    # 1. Busca Segura (Backend)
    hist = rps.buscar_historico_movimentacoes_cofres(unidade_atual)
    
    if not hist.empty:
        # 2. Formatação Visual (Frontend)
        # Trabalhamos numa cópia para não afetar os dados brutos caso precise usar depois
        hist_visual = hist.copy()
        
        hist_visual['valor'] = hist_visual['valor'].apply(format_brl)
        
        # Estilização condicional (Verde/Vermelho)
        st.dataframe(
            hist_visual.style.map(
                lambda x: f'color: {"green" if x=="ENTRADA" else "red"}', 
                subset=['tipo']
            ), 
            width='stretch'
        )
    else:
        st.info("Nenhuma movimentação registrada ainda.")