import sys
import os

# 1. Pega o caminho absoluto de onde o arquivo '1_Aluno.py' está
diretorio_atual = os.path.dirname(os.path.abspath(__file__))

# 2. Sobe um nível para chegar na raiz do projeto (o pai do diretorio_atual)
diretorio_raiz = os.path.dirname(diretorio_atual)

# 3. Adiciona a raiz à lista de lugares onde o Python procura arquivos
sys.path.append(diretorio_raiz)

from repositories import dashboard_rps as rps

import streamlit as st
import pandas as pd
import database as db
import auth
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

st.set_page_config(page_title="Dashboard Estratégico", layout="wide", page_icon="📈")
if not auth.validar_sessao(): auth.tela_login(); st.stop()
auth.barra_lateral()

# --- SEGURANÇA MULTI-UNIDADE ---
unidade_atual = st.session_state.get('unidade_ativa')
if not unidade_atual:
    st.error("Erro de Unidade. Faça login novamente.")
    st.stop()

st.title("📈 Dashboard Estratégico")

def format_brl(val): return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# 1. FILTRO DE ANO
anos_disponiveis = [str(datetime.now().year), str(datetime.now().year - 1)]
ano_sel = st.selectbox("Selecione o Ano de Análise:", anos_disponiveis)

# --- CARREGAMENTO DE DADOS FINANCEIROS ---

# A. Dados Financeiros por Mês (Para Gráficos)
df_fin = rps.buscar_dados_financeiros_anuais(unidade_atual, ano_sel)

# (O restante do código que usa df_fin para criar o gráfico continua igual...)

# B. Dados de Categoria (Backend)
df_cat = rps.buscar_despesas_por_categoria(unidade_atual, ano_sel)

# C. Dados de Matrículas (Backend)
df_mat = rps.buscar_distribuicao_matriculas(unidade_atual)
# O cálculo de soma continua sendo feito com o DataFrame retornado
total_alunos_ativos = df_mat['qtd'].sum() if not df_mat.empty else 0

# D. Inadimplência (Backend)
df_inad = rps.buscar_indicadores_inadimplencia(unidade_atual, ano_sel)

# ... (O restante do código que gera os gráficos continua igual) ...


# E. Dados de RH (Pessoal)
# Custo Total com Pessoal no Ano (Categoria 'Pessoal' + Custos associados na tabela despesas)
# Nota: Assumimos que o Robô de RH lança na categoria 'Pessoal' ou 'Impostos' mas com descrição clara. 
# Para simplificar e ser robusto, vamos somar a categoria 'Pessoal' que é onde lançamos salários e benefícios.
# 1. Custo RH (Pessoal + Impostos) - Backend
custo_pessoal_ano = rps.buscar_custo_rh_anual(unidade_atual, ano_sel)

# 2. Contagem de Funcionários - Backend
qtd_funcionarios = rps.contar_funcionarios_ativos(unidade_atual)

# 3. Meses Faturados (Para Ticket Médio) - Backend
meses_faturados = rps.contar_meses_com_faturamento(unidade_atual, ano_sel)
# Proteção contra divisão por zero (Lógica de Interface)
if meses_faturados == 0: 
    meses_faturados = 1

# --- CÁLCULO DE KPIS GERAIS ---

# 1. Busca contagem de alunos únicos (PESSOAS)
total_alunos_unicos = rps.contar_alunos_unicos_ativos(unidade_atual)

# 2. Busca total de matrículas (DISCIPLINAS)
total_matriculas_ativas = df_mat['qtd'].sum() if not df_mat.empty else 0

receita_ano = db.from_cents(df_fin[df_fin['tipo']=='Receita']['total'].sum())
despesa_ano = db.from_cents(df_fin[df_fin['tipo']=='Despesa']['total'].sum())
lucro_ano = receita_ano - despesa_ano

# TICKET MÉDIO CORRIGIDO
# Fórmula: (Faturamento Total / Meses com Faturamento) / Alunos Ativos Hoje
media_faturamento_mensal = receita_ano / meses_faturados
# ticket_medio = media_faturamento_mensal / total_alunos_ativos if total_alunos_ativos > 0 else 0

# Ticket por Aluno (Quanto cada família paga em média)
ticket_por_aluno = media_faturamento_mensal / total_alunos_unicos if total_alunos_unicos > 0 else 0

# Ticket por Matrícula (Preço médio da disciplina)
ticket_por_materia = media_faturamento_mensal / total_matriculas_ativas if total_matriculas_ativas > 0 else 0

# INADIMPLÊNCIA
taxa_inad = 0
if not df_inad.empty and df_inad['valor_total'].iloc[0] and df_inad['valor_total'].iloc[0] > 0:
    taxa_inad = (df_inad['valor_atrasado'].iloc[0] / df_inad['valor_total'].iloc[0]) * 100

# --- CÁLCULO DE KPIS DE RH (Inteligência de Equipe) ---
# 1. Capacidade: Alunos por Funcionário
alunos_por_func = total_alunos_ativos / qtd_funcionarios if qtd_funcionarios > 0 else 0

# 2. Custo Folha %: Quanto da receita vai para a equipe
folha_percentual = (custo_pessoal_ano / receita_ano) * 100 if receita_ano > 0 else 0

# 3. ROI Humano: Quanto 1 real de salário gera de receita
roi_humano = receita_ano / custo_pessoal_ano if custo_pessoal_ano > 0 else 0

# ==============================================================================
# VISUALIZAÇÃO - SEÇÃO 1: FINANCEIRO MACRO
# ==============================================================================
st.markdown("### 🏦 Saúde Financeira")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Faturamento Anual", format_brl(receita_ano))
c2.metric("Lucro Líquido", format_brl(lucro_ano), delta_color="normal" if lucro_ano >=0 else "inverse")
# c3.metric("Ticket Médio Real", format_brl(ticket_medio), help=f"Média mensal ({meses_faturados} meses) dividido por alunos ativos.")
c3.metric(
    "Ticket Médio (Aluno)", 
    format_brl(ticket_por_aluno), 
    help=f"Média por aluno único. Por matéria: {format_brl(ticket_por_materia)}"
)   
c4.metric("Inadimplência", f"{taxa_inad:.1f}%", delta_color="inverse")

st.markdown("---")

# ==============================================================================
# VISUALIZAÇÃO - SEÇÃO 2: INTELIGÊNCIA DE EQUIPE (NOVO!)
# ==============================================================================
st.markdown("### 👥 Eficiência da Equipe")
st.caption("Indicadores de produtividade e custo-benefício dos colaboradores.")

k1, k2, k3, k4 = st.columns(4)

k1.metric(
    "Equipe Ativa", 
    f"{qtd_funcionarios} Colab.", 
    help="Total de funcionários com contrato ativo."
)

# Indicador 1: Capacidade
k2.metric(
    "Carga Operacional", 
    f"{alunos_por_func:.1f} Alunos/Func.", 
    delta="Ideal: 8 a 15" if 8 <= alunos_por_func <= 15 else "Atenção",
    delta_color="normal" if 8 <= alunos_por_func <= 15 else "inverse",
    help="Quantos alunos (matrículas) cada funcionário atende em média."
)

# Indicador 2: Peso da Folha
k3.metric(
    "Peso da Folha", 
    f"{folha_percentual:.1f}% da Receita", 
    delta="Ideal: < 40%",
    delta_color="inverse", # Se subir é ruim
    help="Porcentagem do faturamento que é gasta com salários e encargos."
)

# Indicador 3: ROI Humano
k4.metric(
    "Retorno sobre Pessoal", 
    f"{roi_humano:.2f}x", 
    help="Para cada R$ 1,00 gasto com equipe, quanto a empresa faturou."
)

st.markdown("---")

# ==============================================================================
# VISUALIZAÇÃO - SEÇÃO 3: GRÁFICOS
# ==============================================================================
col_graph_main, _ = st.columns([1, 0.01])
with col_graph_main:
    st.subheader("📊 Evolução: Receita vs. Despesas")
    if not df_fin.empty:
        df_fin['total'] = df_fin['total'].astype(float) / 100
        df_fin['Data'] = pd.to_datetime(df_fin['mes_referencia'], format='%m/%Y')
        df_fin = df_fin.sort_values('Data')
        
        fig_evolucao = px.bar(
            df_fin, 
            x="mes_referencia", 
            y="total", 
            color="tipo", 
            barmode="group",
            color_discrete_map={"Receita": "#28a745", "Despesa": "#dc3545"},
            labels={"total": "Valor (R$)", "mes_referencia": "Mês", "tipo": "Tipo"}
        )
        fig_evolucao.update_layout(width=None)
        st.plotly_chart(fig_evolucao)
    else:
        st.info("Sem dados financeiros para o gráfico neste ano.")

col_g1, col_g2 = st.columns(2)

with col_g1:
    st.subheader("💸 Detalhamento de Custos")
    if not df_cat.empty:
        # Destaca a fatia de Pessoal
        df_cat['total'] = df_cat['total'].astype(float) / 100
        fig_pizza = px.pie(df_cat, values='total', names='nome_categoria', hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
        fig_pizza.update_layout(width=None)
        st.plotly_chart(fig_pizza)
    else:
        st.info("Sem despesas cadastradas.")

# with col_g2:
#     st.subheader("📚 Alunos por Disciplina")
#     if not df_mat.empty:
#         fig_donut = px.pie(df_mat, values='qtd', names='disciplina', hole=0.4)
#         fig_donut.update_layout(width=None)
#         st.plotly_chart(fig_donut)
#     else:
#         st.info("Sem matrículas ativas.")

with col_g2:
    st.subheader("📚 Alunos por Disciplina")
    
    if not df_mat.empty:
        # --- MAPA DE CORES OFICIAIS KUMON ---
        # Se aparecer uma disciplina nova, ela fica cinza padrão ('#DDDDDD')
        cores_kumon_map = {
            "Matemática": "#0037FF",  # Azul Oficial (Pantone 2915 C)
            "Português": "#FFF700",   # Cinza Oficial (Pantone 430 C) - Para contraste
            "Inglês": "#FF0000",      # Preto Oficial - Para destaque
            "Japonês": "#00FF4C",     # Azul Claro (Tom sobre tom harmonioso)
            "Kokugo": "#22FF00"      # Cinza Claro (Caso tenha)
        }

        fig_donut = px.pie(
            df_mat, 
            values='qtd', 
            names='disciplina', 
            hole=0.4,
            color='disciplina',                 # Informa que a cor segue o nome da disciplina
            color_discrete_map=cores_kumon_map  # Aplica o mapa definido acima
        )
        
        # Ajustes visuais para ficar clean
        fig_donut.update_traces(
            textinfo='value',           # Mostra o número (ex: 45)
            hoverinfo='label+percent',  # Ao passar o mouse mostra %
            textfont_size=14
        )
        
        # # Remove margens para o gráfico aproveitar o espaço
        # fig_donut.update_layout(
        #     width=None, 
        #     margin=dict(t=0, b=0, l=0, r=0),
        #     legend=dict(orientation="h", y=-0.1) # Legenda horizontal embaixo
        # )
        
        st.plotly_chart(fig_donut, use_container_width=True)
        
    else:
        st.info("Sem matrículas ativas.")