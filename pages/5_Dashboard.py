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

conn = db.conectar()

# --- CARREGAMENTO DE DADOS FINANCEIROS ---

# A. Dados Financeiros por Mês (Para Gráficos)
q_fin = f'''
    SELECT mes_referencia, tipo, SUM(valor) as total
    FROM (
        SELECT mes_referencia, 'Receita' as tipo, valor_pago as valor FROM pagamentos WHERE mes_referencia LIKE '%{ano_sel}'
        UNION ALL
        SELECT mes_referencia, 'Despesa' as tipo, valor FROM despesas WHERE mes_referencia LIKE '%{ano_sel}'
    )
    GROUP BY mes_referencia, tipo
'''
df_fin = pd.read_sql_query(q_fin, conn)

# B. Dados de Categoria (Para Pizza)
q_cat = f'''
    SELECT categoria, SUM(valor) as total 
    FROM despesas 
    WHERE mes_referencia LIKE '%{ano_sel}' 
    GROUP BY categoria
'''
df_cat = pd.read_sql_query(q_cat, conn)

# C. Dados de Matrículas (Alunos Ativos HOJE)
q_mat = '''SELECT disciplina, COUNT(*) as qtd FROM matriculas WHERE ativo=1 GROUP BY disciplina'''
df_mat = pd.read_sql_query(q_mat, conn)
total_alunos_ativos = df_mat['qtd'].sum()

# D. Inadimplência
q_inad = f'''
    SELECT 
        SUM(valor_pago) as valor_total,
        SUM(CASE WHEN status='PENDENTE' AND data_vencimento < DATE('now') THEN valor_pago ELSE 0 END) as valor_atrasado
    FROM pagamentos
    WHERE mes_referencia LIKE '%{ano_sel}'
'''
df_inad = pd.read_sql_query(q_inad, conn)

# E. Dados de RH (Pessoal)
# Custo Total com Pessoal no Ano (Categoria 'Pessoal' + Custos associados na tabela despesas)
# Nota: Assumimos que o Robô de RH lança na categoria 'Pessoal' ou 'Impostos' mas com descrição clara. 
# Para simplificar e ser robusto, vamos somar a categoria 'Pessoal' que é onde lançamos salários e benefícios.
q_rh_custo = f'''
    SELECT SUM(valor) FROM despesas 
    WHERE mes_referencia LIKE '%{ano_sel}' 
    AND (categoria = 'Pessoal' OR categoria = 'Impostos')
'''
custo_pessoal_ano = conn.execute(q_rh_custo).fetchone()[0] or 0.0

# Contagem de Funcionários Ativos
qtd_funcionarios = conn.execute("SELECT COUNT(*) FROM funcionarios WHERE ativo=1").fetchone()[0] or 0

# F. Contagem de Meses com Faturamento (Para o Ticket Médio correto)
q_meses = f'''SELECT COUNT(DISTINCT mes_referencia) FROM pagamentos WHERE mes_referencia LIKE '%{ano_sel}' AND valor_pago > 0'''
meses_faturados = conn.execute(q_meses).fetchone()[0]
if meses_faturados == 0: meses_faturados = 1 # Evita divisão por zero

conn.close()

# --- CÁLCULO DE KPIS GERAIS ---
receita_ano = df_fin[df_fin['tipo']=='Receita']['total'].sum()
despesa_ano = df_fin[df_fin['tipo']=='Despesa']['total'].sum()
lucro_ano = receita_ano - despesa_ano

# TICKET MÉDIO CORRIGIDO
# Fórmula: (Faturamento Total / Meses com Faturamento) / Alunos Ativos Hoje
media_faturamento_mensal = receita_ano / meses_faturados
ticket_medio = media_faturamento_mensal / total_alunos_ativos if total_alunos_ativos > 0 else 0

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
c3.metric("Ticket Médio Real", format_brl(ticket_medio), help=f"Média mensal ({meses_faturados} meses) dividido por alunos ativos.")
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
        st.plotly_chart(fig_evolucao, use_container_width=True)
    else:
        st.info("Sem dados financeiros para o gráfico neste ano.")

col_g1, col_g2 = st.columns(2)

with col_g1:
    st.subheader("💸 Detalhamento de Custos")
    if not df_cat.empty:
        # Destaca a fatia de Pessoal
        fig_pizza = px.pie(df_cat, values='total', names='categoria', hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
        st.plotly_chart(fig_pizza, use_container_width=True)
    else:
        st.info("Sem despesas cadastradas.")

with col_g2:
    st.subheader("📚 Alunos por Disciplina")
    if not df_mat.empty:
        fig_donut = px.pie(df_mat, values='qtd', names='disciplina', hole=0.4)
        st.plotly_chart(fig_donut, use_container_width=True)
    else:
        st.info("Sem matrículas ativas.")