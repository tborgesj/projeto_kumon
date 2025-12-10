import streamlit as st
import pandas as pd
import database as db
import auth
from datetime import datetime
import time

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
    # Carrega os dados atuais
    params = db.get_parametros_unidade(unidade_atual)
    
    with st.form("form_parametros"):
        c1, c2 = st.columns(2)
        nova_mensalidade = c1.number_input("Mensalidade Padrão (R$)", value=float(params['mensalidade']), step=5.0)
        nova_taxa = c2.number_input("Taxa de Matrícula (R$)", value=float(params['taxa_matr']), step=5.0)
        
        st.markdown("---")
        # Garante que o valor venha como booleano para o checkbox
        campanha_ativa = True if params['campanha'] == 1 else False
        campanha = st.checkbox("Ativar Campanha (Taxa de Matrícula Grátis)", value=campanha_ativa)
        st.caption("Se ativado, novos alunos cadastrados terão a taxa zerada automaticamente.")
        
        if st.form_submit_button("💾 Salvar Valores"):
            try:
                # Chama a função blindada do backend
                db.atualizar_parametros_unidade(
                    unidade_id=unidade_atual,
                    mensalidade=nova_mensalidade,
                    taxa=nova_taxa,
                    em_campanha=campanha
                )
                
                st.success("Parâmetros salvos com sucesso!")
                time.sleep(1)
                st.rerun()
                
            except Exception as e:
                st.error(f"Erro ao salvar: {e}")

# ==============================================================================
# ABA 2: ROYALTIES
# ==============================================================================
with tab2:
    st.subheader("Configuração de Royalties")
    st.caption("Configure aqui os valores fixos pagos à franquia para que o robô financeiro lance automaticamente.")
    
    # 1. Busca Segura (Backend)
    df_roy = db.buscar_royalties(unidade_atual)
    
    if not df_roy.empty:
        # Cria uma cópia para formatar o visual sem estragar os dados originais
        df_visual = df_roy.copy()
        df_visual['valor'] = df_visual['valor'].apply(format_brl)
        st.dataframe(df_visual, width='stretch')
        
        st.write("Excluir regra antiga:")
        for index, row in df_roy.iterrows():
            # 2. Ação de Excluir (Backend)
            if st.button(f"🗑️ Apagar regra de {row['ano_mes_inicio']}", key=f"del_roy_{row['id']}"):
                try:
                    db.excluir_royalty(row['id'])
                    st.success("Regra removida.")
                    time.sleep(0.5)
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao excluir: {e}")
    else:
        st.info("Nenhum royalty configurado.")
    
    st.divider()
    
    # 3. Form de Inclusão
    with st.form("form_royalties"):
        st.markdown("#### Adicionar Nova Regra")
        r1, r2 = st.columns(2)
        r_val = r1.number_input("Valor Mensal (R$)", step=10.0, min_value=0.0)
        r_ini = r2.text_input("Mês Início (MM/AAAA)", placeholder="Ex: 01/2025")
        
        if st.form_submit_button("➕ Adicionar Regra"):
            if not r_ini or r_val <= 0:
                st.error("Preencha o valor e o mês de início corretamente.")
            else:
                try:
                    # Chama função segura do backend
                    db.adicionar_royalty(unidade_atual, r_val, r_ini)
                    st.success("Regra adicionada com sucesso!")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao salvar: {e}")

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
    
    # 1. Verifica estado atual (Somente Leitura)
    nome_arquivo = db.buscar_info_modelo_contrato(unidade_atual)
    
    if nome_arquivo:
        st.success(f"✅ Modelo Atual: **{nome_arquivo}**")
        
        # 2. Botão de Exclusão
        if st.button("🗑️ Remover Modelo Atual"):
            try:
                db.excluir_modelo_contrato(unidade_atual)
                st.success("Modelo removido.")
                time.sleep(0.5)
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao remover: {e}")
    else:
        st.warning("Nenhum modelo de contrato cadastrado.")

    st.divider()
    
    # 3. Upload e Salvamento
    uploaded_file = st.file_uploader("Enviar novo arquivo (.docx)", type=['docx'])
    
    if uploaded_file and st.button("💾 Salvar Modelo no Sistema"):
        try:
            # Prepara os dados binários
            blob_data = uploaded_file.getvalue()
            
            # Envia para o backend salvar (Atomicamente)
            db.salvar_modelo_contrato(
                unidade_id=unidade_atual, 
                nome_arquivo=uploaded_file.name, 
                dados_binarios=blob_data
            )
            
            st.success("Modelo salvo com sucesso!")
            time.sleep(1)
            st.rerun()
            
        except Exception as e:
            st.error(f"Erro ao salvar arquivo: {e}")