import streamlit as st
import pandas as pd
import database as db
import auth

# Configuração da Página
st.set_page_config(page_title="Gestão de Bolsas", layout="wide", page_icon="🎓")
if not auth.validar_sessao(): auth.tela_login(); st.stop()
auth.barra_lateral()

unidade_atual = st.session_state.get('unidade_ativa')
if not unidade_atual: st.error("Erro Unidade"); st.stop()

st.title(f"🎓 Gestão de Bolsas - {st.session_state.get('unidade_nome')}")
st.markdown("Acompanhe a vigência dos descontos ativos e o impacto financeiro na unidade.")

# 1. Busca Dados no Backend (Seguro)
df = db.buscar_bolsas_ativas(unidade_atual)

if not df.empty:
    # --- MÉTRICAS GERAIS ---
    total_bolsas = len(df)
    
    # Cálculo do impacto: Soma dos valores originais * 50% (Regra visual)
    impacto_mensal = df['valor_original'].sum() * 0.5 
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total de Bolsistas", total_bolsas)
    
    # Formatação manual BRL (ou use sua função format_brl se tiver importado)
    str_impacto = f"R$ {impacto_mensal:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    col2.metric("Impacto Mensal (Descontos)", str_impacto, delta="- Receita", delta_color="inverse")
    
    st.divider()
    
    # --- TABELA VISUAL ---
    st.subheader("Prazos de Vigência")
    st.caption("Quando o contador chegar a zero, o desconto será removido automaticamente pelo robô financeiro.")
    
    st.dataframe(
        df,
        column_config={
            "nome": "Aluno",
            "disciplina": "Disciplina",
            "valor_original": st.column_config.NumberColumn(
                "Valor Cheio", 
                format="R$ %.2f"
            ),
            "bolsa_meses_restantes": st.column_config.ProgressColumn(
                "Meses Restantes",
                help="Tempo até a bolsa expirar",
                format="%d meses",
                min_value=0,
                max_value=12, # Teto visual para barra de progresso
            ),
        },
        hide_index=True,
        use_container_width=True
    )

else:
    st.info("ℹ️ Nenhuma bolsa de estudos ativa no momento.")
    st.markdown("""
    Para conceder uma bolsa:
    1. Vá em **Gerenciar Alunos**.
    2. Selecione o aluno e localize a disciplina.
    3. Clique no botão **🎓 Conceder Bolsa**.
    """)