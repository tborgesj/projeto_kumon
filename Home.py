from services import geral_svc as g_svc

import streamlit as st
import pandas as pd
import database as db
import auth
from datetime import datetime, date

# 1. Configuração Inicial
st.set_page_config(page_title="Visão Operacional", layout="wide", page_icon="🏠")

if not auth.validar_sessao():
    auth.tela_login()
    st.stop()

auth.barra_lateral()

# 3. Verificação de Segurança
unidade_atual = st.session_state.get('unidade_ativa')
if not unidade_atual:
    st.warning("⚠️ Nenhuma unidade selecionada. Por favor, selecione uma unidade na barra lateral.")
    st.stop()

# 4. Estilos CSS
st.markdown("""
    <style>
        div[data-testid="stMetricValue"] { font-size: 1.8rem; }
        hr { margin: 5px 0px; opacity: 0.1; }
    </style>
""", unsafe_allow_html=True)

# --- FUNÇÕES AUXILIARES VISUAIS ---

# --- INTERFACE PRINCIPAL ---

# 1. Busca os Totais (Cards) no Backend
dados = db.buscar_resumo_operacional_mes(unidade_atual)

# Cabeçalho
st.title(f"🏠 Visão Operacional ({dados.get('mes', '-')})")
st.caption(f"Resumo financeiro: {st.session_state.get('unidade_nome', 'Unidade')}")
st.markdown("---")

# Cards (Métricas)
if dados:
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Alunos Ativos", dados['alunos_ativos'], delta="Base Atual")
    c2.metric("Alunos Ausentes", dados['alunos_ausentes'], delta="Base Atual")
    c3.metric("Receita (Mês)", g_svc.format_brl(dados['rec_total']), delta="Entradas Previstas")
    c4.metric("Despesa (Mês)", g_svc.format_brl(dados['desp_total']), delta="Saídas Previstas", delta_color="inverse")
    
    cor_saldo = "normal" if dados['saldo_previsto'] >= 0 else "inverse"
    c5.metric("Resultado (Previsto)", g_svc.format_brl(dados['saldo_previsto']), delta="Lucro/Prejuízo", delta_color=cor_saldo)

# Listas de Pendências
st.markdown("### 📅 Próximos Vencimentos (Ainda não pagos)")
col_l, col_r = st.columns(2)

# --- COLUNA ESQUERDA: A RECEBER ---
with col_l:
    st.markdown(f"**A Receber (Alunos): {g_svc.format_brl(dados.get('rec_pendente', 0))}**")
    st.divider()
    
    # Busca Lista no Backend
    df_rec = db.buscar_pendencias_recebimento(unidade_atual, dados['mes'])
    
    if not df_rec.empty:
        h1, h2, h3 = st.columns([1.5, 3, 2])
        h1.caption("Vencimento")
        h2.caption("Aluno")
        h3.caption("Valor")
        
        for _, row in df_rec.iterrows():
            visual_date = g_svc.get_status_visual(row['data_vencimento'])
            r1, r2, r3 = st.columns([1.5, 3, 2])
            r1.markdown(visual_date)
            r2.write(row['nome'])
            r3.write(g_svc.format_brl(db.from_cents(row['valor_pago'])))
            st.markdown("<hr>", unsafe_allow_html=True)
    else:
        st.success("Tudo recebido neste mês!")

# --- COLUNA DIREITA: A PAGAR ---
with col_r:
    st.markdown(f"**A Pagar (Despesas): {g_svc.format_brl(dados.get('desp_pendente', 0))}**")
    st.divider()
    
    # Busca Lista no Backend
    df_pag = db.buscar_pendencias_pagamento(unidade_atual, dados['mes'])
    
    if not df_pag.empty:
        h1, h2, h3 = st.columns([1.5, 3, 2])
        h1.caption("Vencimento")
        h2.caption("Descrição")
        h3.caption("Valor")
        
        for _, row in df_pag.iterrows():
            visual_date = g_svc.get_status_visual(row['data_vencimento'])
            r1, r2, r3 = st.columns([1.5, 3, 2])
            r1.markdown(visual_date)
            r2.write(row['descricao'])
            r3.write(g_svc.format_brl(db.from_cents(row['valor'])))
            st.markdown("<hr>", unsafe_allow_html=True)
    else:
        st.success("Tudo pago neste mês!")