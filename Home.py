import streamlit as st
import pandas as pd
import database as db
import auth
from datetime import datetime, date

# 1. Configuração Inicial da Página (Deve ser sempre a primeira linha)
st.set_page_config(page_title="Visão Operacional", layout="wide", page_icon="🏠")

# 2. Inicialização e Autenticação
db.criar_tabelas() 

if not auth.validar_sessao():
    auth.tela_login()
    st.stop()

auth.barra_lateral()

# 3. Verificação de Segurança (Unidade)
unidade_atual = st.session_state.get('unidade_ativa')
if not unidade_atual:
    st.warning("⚠️ Nenhuma unidade selecionada. Por favor, selecione uma unidade na barra lateral.")
    st.stop()

# 4. Estilos CSS Personalizados
st.markdown("""
    <style>
        div[data-testid="stMetricValue"] { font-size: 1.8rem; }
        hr { margin: 5px 0px; opacity: 0.1; }
    </style>
""", unsafe_allow_html=True)

# --- FUNÇÕES AUXILIARES ---

def format_brl(val):
    """Formata valores float para moeda brasileira."""
    if pd.isnull(val): return "R$ 0,00"
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def get_status_visual(data_vencimento):
    """Gera o alerta visual baseado na data de vencimento."""
    try:
        # Garante que temos um objeto date
        if isinstance(data_vencimento, str):
            dt_venc = datetime.strptime(data_vencimento, '%Y-%m-%d').date()
        elif isinstance(data_vencimento, datetime):
            dt_venc = data_vencimento.date()
        else:
            dt_venc = data_vencimento
            
        hoje = date.today()
        dt_fmt = dt_venc.strftime('%d/%m')
        
        if dt_venc < hoje:
            return f"🚨 :red[**{dt_fmt}**]" # Atrasado
        elif dt_venc == hoje:
            return f"⚠️ :orange[**{dt_fmt}**]" # Vence hoje
        else:
            return dt_fmt # No prazo
    except Exception:
        return "-"

def get_dados_mes_atual(unidade_id):
    """Busca os totais financeiros e de alunos para os Cards."""
    conn = db.conectar()
    cursor = conn.cursor()
    
    try:
        hoje = datetime.now()
        mes_atual = hoje.strftime("%m/%Y")
        mes_atual_str = hoje.strftime('%Y-%m') # Formato AAAA-MM para comparação no banco
        
        # Consultas otimizadas
        # 1. Receitas
        cursor.execute("SELECT SUM(valor_pago) FROM pagamentos WHERE mes_referencia = ? AND unidade_id = ?", (mes_atual, unidade_id))
        rec_total = cursor.fetchone()[0] or 0.0
        
        cursor.execute("SELECT SUM(valor_pago) FROM pagamentos WHERE mes_referencia = ? AND status='PENDENTE' AND unidade_id = ?", (mes_atual, unidade_id))
        rec_pendente = cursor.fetchone()[0] or 0.0
        
        # 2. Despesas
        cursor.execute("SELECT SUM(valor) FROM despesas WHERE mes_referencia = ? AND unidade_id = ?", (mes_atual, unidade_id))
        desp_total = cursor.fetchone()[0] or 0.0
        
        cursor.execute("SELECT SUM(valor) FROM despesas WHERE mes_referencia = ? AND status='PENDENTE' AND unidade_id = ?", (mes_atual, unidade_id))
        desp_pendente = cursor.fetchone()[0] or 0.0
        
        # 3. Alunos Ativos
        cursor.execute("SELECT COUNT(id) FROM matriculas WHERE ativo=1 AND unidade_id = ?", (unidade_id,))
        alunos_ativos = cursor.fetchone()[0] or 0

        # 4. Alunos Inativos
        cursor.execute("SELECT COUNT(*) FROM matriculas WHERE unidade_id = ? AND ativo = 0 AND strftime('%Y-%m', data_fim) = ?", (unidade_id, mes_atual_str))
        alunos_ausentes = cursor.fetchone()[0] or 0
        
        return {
            "mes": mes_atual,
            "rec_total": rec_total,
            "rec_pendente": rec_pendente,
            "desp_total": desp_total,
            "desp_pendente": desp_pendente,
            "saldo_previsto": rec_total - desp_total,
            "alunos_ativos": alunos_ativos,
            "alunos_ausentes": alunos_ausentes,
        }
    except Exception as e:
        st.error(f"Erro ao buscar dados: {e}")
        return {} # Retorna dict vazio para não quebrar a UI
    finally:
        conn.close()

# --- INTERFACE PRINCIPAL ---

# Carregar dados
dados = get_dados_mes_atual(unidade_atual)

# Cabeçalho
st.title(f"🏠 Visão Operacional ({dados.get('mes', '-')})")
st.caption(f"Resumo financeiro: {st.session_state.get('unidade_nome', 'Unidade')}")
st.markdown("---")

# Cards (Métricas)
if dados:
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Alunos Ativos", dados['alunos_ativos'], delta="Base Atual")
    c2.metric("Alunos Ausentes", dados['alunos_ausentes'], delta="Base Atual")
    c3.metric("Receita (Mês)", format_brl(dados['rec_total']), delta="Entradas Previstas")
    c4.metric("Despesa (Mês)", format_brl(dados['desp_total']), delta="Saídas Previstas", delta_color="inverse")
    
    cor_saldo = "normal" if dados['saldo_previsto'] >= 0 else "inverse"
    c5.metric("Resultado (Previsto)", format_brl(dados['saldo_previsto']), delta="Lucro/Prejuízo", delta_color=cor_saldo)

# Listas de Pendências
st.markdown("### 📅 Próximos Vencimentos (Ainda não pagos)")
col_l, col_r = st.columns(2)

# Abrir conexão única para as listas (Performance)
conn = db.conectar()

try:
    # --- COLUNA ESQUERDA: A RECEBER ---
    with col_l:
        st.markdown(f"**A Receber (Alunos): {format_brl(dados.get('rec_pendente', 0))}**")
        st.divider()
        
        query_rec = '''
            SELECT a.nome, p.data_vencimento, p.valor_pago
            FROM pagamentos p JOIN alunos a ON p.aluno_id = a.id
            WHERE p.status='PENDENTE' AND p.mes_referencia = ? AND p.unidade_id = ?
            ORDER BY p.data_vencimento
        '''
        df_rec = pd.read_sql_query(query_rec, conn, params=(dados['mes'], unidade_atual))
        
        if not df_rec.empty:
            # Cabeçalho da tabela manual
            h1, h2, h3 = st.columns([1.5, 3, 2])
            h1.caption("Vencimento")
            h2.caption("Aluno")
            h3.caption("Valor")
            
            # Linhas da tabela
            for _, row in df_rec.iterrows():
                visual_date = get_status_visual(row['data_vencimento'])
                
                r1, r2, r3 = st.columns([1.5, 3, 2])
                r1.markdown(visual_date)
                r2.write(row['nome'])
                r3.write(format_brl(row['valor_pago']))
                st.markdown("<hr>", unsafe_allow_html=True)
        else:
            st.success("Tudo recebido neste mês!")

    # --- COLUNA DIREITA: A PAGAR ---
    with col_r:
        st.markdown(f"**A Pagar (Despesas): {format_brl(dados.get('desp_pendente', 0))}**")
        st.divider()
        
        query_pag = '''
            SELECT descricao, data_vencimento, valor
            FROM despesas
            WHERE status='PENDENTE' AND mes_referencia = ? AND unidade_id = ?
            ORDER BY data_vencimento
        '''
        df_pag = pd.read_sql_query(query_pag, conn, params=(dados['mes'], unidade_atual))
        
        if not df_pag.empty:
            # Cabeçalho da tabela manual
            h1, h2, h3 = st.columns([1.5, 3, 2])
            h1.caption("Vencimento")
            h2.caption("Descrição")
            h3.caption("Valor")
            
            # Linhas da tabela
            for _, row in df_pag.iterrows():
                visual_date = get_status_visual(row['data_vencimento'])
                
                r1, r2, r3 = st.columns([1.5, 3, 2])
                r1.markdown(visual_date)
                r2.write(row['descricao'])
                r3.write(format_brl(row['valor']))
                st.markdown("<hr>", unsafe_allow_html=True)
        else:
            st.success("Tudo pago neste mês!")

finally:
    # Garante que a conexão feche mesmo se der erro no SQL
    conn.close()