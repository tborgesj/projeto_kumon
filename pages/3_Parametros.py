import streamlit as st
import pandas as pd
import database as db
import auth
from datetime import datetime

st.set_page_config(page_title="Configurações", layout="wide", page_icon="⚙️")
if not auth.validar_sessao(): auth.tela_login(); st.stop()
auth.barra_lateral()

unidade_atual = st.session_state.get('unidade_ativa')
if not unidade_atual:
    st.error("Selecione uma unidade.")
    st.stop()

st.title(f"⚙️ Configurações - {st.session_state.get('unidade_nome')}")

def format_brl(val): 
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

tab1, tab2, tab3 = st.tabs(["💰 Valores & Matrícula", "👑 Royalties", "📄 Contratos"])

# ==============================================================================
# ABA 1: VALORES GERAIS
# ==============================================================================
with tab1:
    st.subheader("Definição de Preços")
    params = db.get_parametros_unidade(unidade_atual)
    
    with st.form("form_parametros"):
        c1, c2 = st.columns(2)
        nova_mensalidade = c1.number_input("Mensalidade Padrão (R$)", value=float(params['mensalidade']), step=5.0)
        nova_taxa = c2.number_input("Taxa de Matrícula (R$)", value=float(params['taxa_matr']), step=5.0)
        
        st.markdown("---")
        campanha = st.checkbox("Ativar Campanha (Taxa de Matrícula Grátis)", value=params['campanha'])
        st.caption("Se ativado, novos alunos cadastrados terão a taxa zerada automaticamente.")
        
        if st.form_submit_button("💾 Salvar Valores"):
            conn = db.conectar()
            try:
                conn.execute('''
                    UPDATE parametros 
                    SET em_campanha_matricula=?, valor_taxa_matricula=?, valor_mensalidade_padrao=? 
                    WHERE unidade_id=?
                ''', (1 if campanha else 0, nova_taxa, nova_mensalidade, unidade_atual))
                conn.commit()
                st.success("Parâmetros salvos com sucesso!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro: {e}")
            finally:
                conn.close()

# ==============================================================================
# ABA 2: ROYALTIES
# ==============================================================================
with tab2:
    st.subheader("Configuração de Royalties")
    st.caption("Configure aqui os valores fixos pagos à franquia para que o robô financeiro lance automaticamente.")
    conn = db.conectar()
    
    # Lista
    df_roy = pd.read_sql_query("SELECT id, valor, ano_mes_inicio, ano_mes_fim FROM config_royalties WHERE unidade_id=? ORDER BY ano_mes_inicio DESC", conn, params=(unidade_atual,))
    
    if not df_roy.empty:
        df_roy['valor'] = df_roy['valor'].apply(format_brl)
        st.dataframe(df_roy, use_container_width=True)
        
        st.write("Excluir regra antiga:")
        for index, row in df_roy.iterrows():
            if st.button(f"🗑️ Apagar regra de {row['ano_mes_inicio']}", key=f"del_roy_{row['id']}"):
                conn.execute("DELETE FROM config_royalties WHERE id=?", (row['id'],))
                conn.commit()
                st.rerun()
    else:
        st.info("Nenhum royalty configurado.")
    
    st.divider()
    
    # Form Inclusão
    with st.form("form_royalties"):
        st.markdown("#### Adicionar Nova Regra")
        r1, r2 = st.columns(2)
        r_val = r1.number_input("Valor Mensal (R$)", step=10.0, min_value=0.0)
        r_ini = r2.text_input("Mês Início (MM/AAAA)", placeholder="Ex: 01/2025")
        
        if st.form_submit_button("➕ Adicionar Regra"):
            if not r_ini or r_val <= 0:
                st.error("Preencha o valor e o mês de início.")
            else:
                conn.execute("INSERT INTO config_royalties (unidade_id, valor, ano_mes_inicio) VALUES (?, ?, ?)", (unidade_atual, r_val, r_ini))
                conn.commit()
                st.success("Regra adicionada!")
                st.rerun()
    conn.close()

# ==============================================================================
# ABA 3: CONTRATOS (UPLOAD TEMPLATE)
# ==============================================================================
with tab3:
    st.subheader("Modelo de Contrato (Word)")
    st.markdown("""
    Faça o upload do seu contrato padrão em formato **.docx**.
    O sistema substituirá automaticamente as seguintes tags no texto:
    
    * `{{NOME_ALUNO}}` - Nome do Aluno
    * `{{RESPONSAVEL}}` - Nome do Responsável Financeiro
    * `{{CPF_RESPONSAVEL}}` - CPF Formatado
    * `{{VALOR_MENSALIDADE}}` - Valor da parcela mensal
    * `{{TAXA_MATRICULA}}` - Valor da taxa paga (ou R$ 0,00)
    * `{{DIA_VENCIMENTO}}` - Dia escolhido para pagamento
    * `{{DATA_INICIO}}` - Data de hoje
    * `{{DATA_FIM}}` - Data daqui a 12 meses
    """)
    
    conn = db.conectar()
    
    # Verifica modelo atual
    tem_contrato = conn.execute("SELECT nome_arquivo FROM docs_templates WHERE unidade_id=? AND tipo='CONTRATO'", (unidade_atual,)).fetchone()
    
    if tem_contrato:
        st.success(f"✅ Modelo Atual: **{tem_contrato[0]}**")
        if st.button("🗑️ Remover Modelo Atual"):
            conn.execute("DELETE FROM docs_templates WHERE unidade_id=? AND tipo='CONTRATO'", (unidade_atual,))
            conn.commit()
            st.rerun()
    else:
        st.warning("Nenhum modelo de contrato cadastrado.")

    st.divider()
    uploaded_file = st.file_uploader("Enviar novo arquivo (.docx)", type=['docx'])
    
    if uploaded_file and st.button("💾 Salvar Modelo no Sistema"):
        blob_data = uploaded_file.getvalue()
        # Remove anterior se houver
        conn.execute("DELETE FROM docs_templates WHERE unidade_id=? AND tipo='CONTRATO'", (unidade_atual,))
        # Insere novo
        conn.execute("INSERT INTO docs_templates (unidade_id, nome_arquivo, arquivo_binario, tipo) VALUES (?, ?, ?, 'CONTRATO')", 
                     (unidade_atual, uploaded_file.name, blob_data))
        conn.commit()
        st.success("Modelo salvo com sucesso!")
        st.rerun()
        
    conn.close()