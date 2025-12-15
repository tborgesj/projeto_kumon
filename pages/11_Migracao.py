import sys
import os

# 1. Pega o caminho absoluto de onde o arquivo '1_Aluno.py' está
diretorio_atual = os.path.dirname(os.path.abspath(__file__))

# 2. Sobe um nível para chegar na raiz do projeto (o pai do diretorio_atual)
diretorio_raiz = os.path.dirname(diretorio_atual)

# 3. Adiciona a raiz à lista de lugares onde o Python procura arquivos
sys.path.append(diretorio_raiz)

from repositories import migracao_rps as rps

import streamlit as st
import pandas as pd
import database as db
import auth
from datetime import datetime, date
import calendar

st.set_page_config(page_title="Migração de Dados", layout="wide", page_icon="🚚")
if not auth.validar_sessao(): auth.tela_login(); st.stop()
auth.barra_lateral()

unidade_atual = st.session_state.get('unidade_ativa')
if not unidade_atual: st.error("Erro Unidade"); st.stop()

# --- TRAVA DE SEGURANÇA (BACKEND) ---
unidade_limpa, n_alunos, n_matriculas = rps.verificar_status_migracao(unidade_atual)

if not unidade_limpa:
    st.error(f"""
        🚫 **Migração Bloqueada**
        
        Esta unidade já possui dados operacionais e não pode receber migração em massa para evitar duplicidade.
        
        **Registros encontrados:**
        - Alunos: {n_alunos}
        - Matrículas: {n_matriculas}
        
        Para realizar uma nova migração, é necessário que a unidade esteja completamente vazia.
    """)
    st.info("💡 Dica: Se isso for um erro e você precisa reiniciar a unidade, contate o suporte.")
    st.stop()

# --- INTERFACE DE MIGRAÇÃO ---

st.title("🚚 Migração de Dados")
st.info("Use esta ferramenta para importar sua base antiga (Excel/CSV).")

# Funções Auxiliares de Tratamento (Frontend)
def limpar_cpf(cpf_str):
    if pd.isna(cpf_str): return ""
    return ''.join(filter(str.isdigit, str(cpf_str)))

def formatar_cpf(cpf_limpo):
    if len(cpf_limpo) != 11: return cpf_limpo 
    return f"{cpf_limpo[:3]}.{cpf_limpo[3:6]}.{cpf_limpo[6:9]}-{cpf_limpo[9:]}"

# Download Modelo
colunas_modelo = ["Aluno", "Responsavel", "CPF Responsavel", "Disciplina", "Valor", "Dia Vencimento", "Canal"]
st.download_button(
    "📥 Baixar Modelo Atualizado (com CPF)", 
    pd.DataFrame(columns=colunas_modelo).to_csv(index=False, sep=';').encode('latin-1'), 
    "modelo_migracao.csv"
)

st.divider()

# Upload
arquivo = st.file_uploader("Upload CSV/XLSX", type=['xlsx','csv'])

if arquivo:
    try:
        # Leitura do Arquivo
        if arquivo.name.endswith('.csv'):
            try: df = pd.read_csv(arquivo, sep=None, engine='python')
            except: arquivo.seek(0); df = pd.read_csv(arquivo, sep=None, engine='python', encoding='latin-1')
        else: df = pd.read_excel(arquivo)
        
        df.columns = [c.strip().title() for c in df.columns]
        
        colunas_obrigatorias = {"Aluno", "Responsavel", "Disciplina", "Valor", "Dia Vencimento"}
        
        if colunas_obrigatorias.issubset(set(df.columns)):
            st.success(f"Arquivo lido! {len(df)} registros encontrados.")
            st.dataframe(df.head())
            
            if st.button("🚀 Iniciar Importação", type="primary"):
                # PREPARAÇÃO DOS DADOS (Frontend)
                registros_preparados = []
                
                try:
                    with st.spinner("Processando dados e enviando para o banco..."):
                        for idx, row in df.iterrows():
                            # Limpeza e Tratamento
                            nome = str(row['Aluno']).strip()
                            resp = str(row['Responsavel']).strip()
                            disc = str(row['Disciplina']).strip()
                            dia = int(row['Dia Vencimento'])
                            
                            # Valor
                            try: valor = float(str(row['Valor']).replace("R$","").replace(".","").replace(",","."))
                            except: valor = float(str(row['Valor']).replace(",", "."))
                            
                            # CPF
                            cpf_raw = row['Cpf Responsavel'] if 'Cpf Responsavel' in df.columns else ""
                            cpf_final = formatar_cpf(limpar_cpf(cpf_raw))
                            
                            canal = row['Canal'] if 'Canal' in df.columns else 'Importacao'
                            
                            # Adiciona ao pacote
                            registros_preparados.append({
                                'nome': nome,
                                'responsavel': resp,
                                'disciplina': disc,
                                'dia_vencimento': dia,
                                'valor': valor,
                                'cpf': cpf_final,
                                'canal': canal
                            })
                        
                        # EXECUÇÃO (Backend)
                        rps.importar_dados_migracao(unidade_atual, registros_preparados)
                        
                        st.success("Importação concluída com sucesso!")
                        st.balloons()
                        
                except Exception as e:
                    st.error(f"Erro durante o processo: {e}")
        else: 
            st.error("Colunas obrigatórias faltando.")
            st.write(f"Esperado: {colunas_obrigatorias}")
            
    except Exception as e: st.error(f"Erro ao ler arquivo: {e}")