import streamlit as st
import pandas as pd
import database as db
import auth
from datetime import datetime, date
import calendar
import re

st.set_page_config(page_title="Migração de Dados", layout="wide", page_icon="🚚")
if not auth.validar_sessao(): auth.tela_login(); st.stop()
auth.barra_lateral()

unidade_atual = st.session_state.get('unidade_ativa')
if not unidade_atual: st.error("Erro Unidade"); st.stop()

# --- TRAVA DE SEGURANÇA DA MIGRAÇÃO ---
# Objetivo: Impedir importação se a unidade já tiver dados (Alunos ou Matrículas)

def verificar_unidade_limpa(id_unidade):
    """
    Retorna False se a unidade já tiver alunos ou matrículas cadastrados.
    Retorna True se estiver limpa (pode migrar).
    """
    conn_check = db.conectar()
    cursor_check = conn_check.cursor()
    try:
        # 1. Checa Alunos
        cursor_check.execute("SELECT COUNT(*) FROM alunos WHERE unidade_id = ?", (id_unidade,))
        qtd_alunos = cursor_check.fetchone()[0]

        # 2. Checa Matrículas
        cursor_check.execute("SELECT COUNT(*) FROM matriculas WHERE unidade_id = ?", (id_unidade,))
        qtd_matriculas = cursor_check.fetchone()[0]
        
        # Se tiver qualquer registro, retorna False (Não está limpa)
        if qtd_alunos > 0 or qtd_matriculas > 0:
            return False, qtd_alunos, qtd_matriculas
        
        return True, 0, 0
    finally:
        conn_check.close()

# Executa a verificação
unidade_limpa, n_alunos, n_matriculas = verificar_unidade_limpa(unidade_atual)

if not unidade_limpa:
    st.error(f"""
        🚫 **Migração Bloqueada**
        
        Esta unidade já possui dados operacionais e não pode receber migração em massa para evitar duplicidade.
        
        **Registros encontrados:**
        - Alunos: {n_alunos}
        - Matrículas: {n_matriculas}
        
        Para realizar uma nova migração, é necessário que a unidade esteja completamente vazia.
        Caso precise incluir um aluno novo, utilize a tela de **Cadastro Manual**.
    """)
    st.info("💡 Dica: Se isso for um erro e você precisa reiniciar a unidade, contate o suporte para limpar os dados.")
    st.stop() # <--- ISSO AQUI PARA A EXECUÇÃO DO CÓDIGO ABAIXO

# --- FIM DA TRAVA ---

# ... O resto do seu código de upload de CSV/Excel vem aqui embaixo ...

st.title("🚚 Migração de Dados")
st.info("Use esta ferramenta para importar sua base antiga (Excel/CSV).")

# --- FUNÇÕES AUXILIARES ---
def get_valid_date(y, m, d): 
    return date(y, m, min(d, calendar.monthrange(y, m)[1]))

def limpar_cpf(cpf_str):
    """Mantém apenas números"""
    if pd.isna(cpf_str): return ""
    return ''.join(filter(str.isdigit, str(cpf_str)))

def formatar_cpf(cpf_limpo):
    """Formata para o padrão do banco XXX.XXX.XXX-XX"""
    if len(cpf_limpo) != 11: return cpf_limpo # Retorna limpo se não tiver 11 dígitos
    return f"{cpf_limpo[:3]}.{cpf_limpo[3:6]}.{cpf_limpo[6:9]}-{cpf_limpo[9:]}"

# --- DOWNLOAD DO MODELO ---
colunas_modelo = ["Aluno", "Responsavel", "CPF Responsavel", "Disciplina", "Valor", "Dia Vencimento", "Canal"]

st.download_button(
    "📥 Baixar Modelo Atualizado (com CPF)", 
    pd.DataFrame(columns=colunas_modelo).to_csv(index=False, sep=';').encode('latin-1'), 
    "modelo_migracao.csv"
)

st.divider()

# --- UPLOAD ---
arquivo = st.file_uploader("Upload CSV/XLSX", type=['xlsx','csv'])

if arquivo:
    try:
        if arquivo.name.endswith('.csv'):
            try: df = pd.read_csv(arquivo, sep=None, engine='python')
            except: arquivo.seek(0); df = pd.read_csv(arquivo, sep=None, engine='python', encoding='latin-1')
        else: df = pd.read_excel(arquivo)
        
        # Padroniza colunas
        df.columns = [c.strip().title() for c in df.columns]
        
        # Verifica colunas obrigatórias (CPF é opcional na validação para não travar, mas ideal ter)
        colunas_obrigatorias = {"Aluno", "Responsavel", "Disciplina", "Valor", "Dia Vencimento"}
        
        if colunas_obrigatorias.issubset(set(df.columns)):
            st.success(f"Arquivo lido! {len(df)} registros.")
            st.dataframe(df.head())
            
            if st.button("🚀 Iniciar Importação", type="primary"):
                conn = db.conectar()
                bar = st.progress(0)
                cache_alunos = {} # Evita duplicar aluno se ele tiver 2 disciplinas no arquivo
                
                try:
                    for idx, row in df.iterrows():
                        # 1. Dados Básicos
                        nome = str(row['Aluno']).strip()
                        resp = str(row['Responsavel']).strip()
                        disc = str(row['Disciplina']).strip()
                        dia = int(row['Dia Vencimento'])
                        
                        # 2. Tratamento de Valor
                        try: valor = float(str(row['Valor']).replace("R$","").replace(".","").replace(",","."))
                        except: valor = float(str(row['Valor']).replace(",", "."))
                        
                        # 3. Tratamento de CPF (NOVO)
                        # Verifica se a coluna existe, se não, fica vazio
                        cpf_raw = row['Cpf Responsavel'] if 'Cpf Responsavel' in df.columns else ""
                        cpf_final = formatar_cpf(limpar_cpf(cpf_raw))
                        
                        canal = row['Canal'] if 'Canal' in df.columns else 'Importacao'

                        # 4. Cria ou Busca Aluno
                        if nome in cache_alunos: 
                            aid = cache_alunos[nome]
                        else:
                            # Verifica se já existe no banco (pelo nome)
                            exist = conn.execute("SELECT id FROM alunos WHERE nome=? AND unidade_id=?", (nome, unidade_atual)).fetchone()
                            if exist: 
                                aid = exist[0]
                                # Opcional: Atualizar o CPF se estiver vazio no banco?
                                # Por segurança na migração, melhor não sobrescrever dados existentes sem avisar.
                            else:
                                cur = conn.execute("INSERT INTO alunos (unidade_id, nome, responsavel_nome, cpf_responsavel, canal_aquisicao) VALUES (?,?,?,?,?)", 
                                                   (unidade_atual, nome, resp, cpf_final, canal))
                                aid = cur.lastrowid
                            cache_alunos[nome] = aid
                        
                        # 5. Cria Matrícula
                        cur = conn.execute("INSERT INTO matriculas (unidade_id, aluno_id, disciplina, valor_acordado, dia_vencimento, data_inicio, ativo, justificativa_desconto) VALUES (?,?,?,?,?,DATE('now'),1, 'Migracao')", 
                                           (unidade_atual, aid, disc, valor, dia))
                        mid = cur.lastrowid
                        
                        # 6. Gera Mensalidade (Mês Atual)
                        hj = datetime.now()
                        conn.execute("INSERT INTO pagamentos (unidade_id, matricula_id, aluno_id, mes_referencia, data_vencimento, valor_pago, status) VALUES (?,?,?,?,?,?,'PENDENTE')",
                                     (unidade_atual, mid, aid, hj.strftime("%m/%Y"), get_valid_date(hj.year, hj.month, dia), valor))
                        
                        bar.progress((idx+1)/len(df))
                    
                    conn.commit()
                    st.success("Importação concluída com sucesso!")
                    st.balloons()
                    
                except Exception as e:
                    st.error(f"Erro na linha {idx+1}: {e}")
                finally:
                    conn.close()
        else: 
            st.error("Colunas obrigatórias faltando.")
            st.write(f"Esperado: {colunas_obrigatorias}")
            st.write(f"Encontrado: {list(df.columns)}")
            
    except Exception as e: st.error(f"Erro ao ler arquivo: {e}")