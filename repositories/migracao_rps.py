import sys
import os

# 1. Pega o caminho absoluto de onde o arquivo '1_Aluno.py' está
diretorio_atual = os.path.dirname(os.path.abspath(__file__))

# 2. Sobe um nível para chegar na raiz do projeto (o pai do diretorio_atual)
diretorio_raiz = os.path.dirname(diretorio_atual)

# 3. Adiciona a raiz à lista de lugares onde o Python procura arquivos
sys.path.append(diretorio_raiz)

# --- FIM DA CONFIGURAÇÃO DE CAMINHO ---

# import sqlite3
from conectDB.conexao import conectar
import pandas as pd
from datetime import date, datetime
from calendar import monthrange
import database as db


def verificar_status_migracao(unidade_id):
    """
    Verifica se a unidade está apta a receber migração (deve estar vazia).
    Retorna: (pode_migrar, qtd_alunos, qtd_matriculas)
    """
    conn = conectar()
    try:
        qa = conn.execute("SELECT COUNT(*) FROM alunos WHERE unidade_id = ?", (unidade_id,)).fetchone()[0]
        qm = conn.execute("SELECT COUNT(*) FROM matriculas WHERE unidade_id = ?", (unidade_id,)).fetchone()[0]
        
        estah_limpa = (qa == 0 and qm == 0)
        return estah_limpa, qa, qm
    finally:
        conn.close()

def importar_dados_migracao(unidade_id, lista_registros):
    """
    Processa a importação em lote de forma ATÔMICA.
    lista_registros: lista de dicionários contendo os dados limpos.
    """
    conn = conectar()
    try:
        # Helper de data para calcular vencimento
        def get_valid_date(year, month, day):
            try:
                return date(year, month, day)
            except ValueError:
                if month == 12: return date(year, 12, 31)
                return date(year, month + 1, 1) - pd.Timedelta(days=1)

        hj = datetime.now()
        mes_ref = hj.strftime("%m/%Y")
        
        # Cache local para evitar duplicidade dentro do próprio arquivo
        cache_alunos = {} 

        # Cria dict: {'Matemática': 1, 'Inglês': 3...}
        df_disc = pd.read_sql("SELECT id, nome FROM disciplinas", conn)
        mapa_disc = dict(zip(df_disc['nome'], df_disc['id']))
        
        with conn: # Início da Transação
            for row in lista_registros:
                nome = row['nome']
                
                # 1. Busca/Cria Aluno
                # Verifica no cache da transação
                aid = cache_alunos.get(nome)
                
                if not aid:
                    # Verifica no banco (caso existam alunos de outra importação manual, 
                    # embora a trava de segurança evite isso, é bom garantir)
                    exist = conn.execute("SELECT id FROM alunos WHERE nome=? AND unidade_id=?", (nome, unidade_id)).fetchone()
                    if exist:
                        aid = exist[0]
                    else:
                        cur = conn.execute("""
                            INSERT INTO alunos (unidade_id, nome, responsavel_nome, cpf_responsavel, canal_aquisicao) 
                            VALUES (?,?,?,?,?)""", 
                            (unidade_id, nome, row['responsavel'], row['cpf'], row['canal']))
                        aid = cur.lastrowid
                    cache_alunos[nome] = aid

                # Resolve ID da disciplina
                nome_disc = row['disciplina']
                id_disc = mapa_disc.get(nome_disc)
                if not id_disc:
                    raise ValueError(f"Disciplina '{nome_disc}' não cadastrada no sistema.")
                
                # 2. Cria Matrícula
                cur = conn.execute("""
                    INSERT INTO matriculas (unidade_id, aluno_id, id_disciplina, valor_acordado, dia_vencimento, data_inicio, ativo, justificativa_desconto) 
                    VALUES (?,?,?,?,?,DATE('now'),1, 'Migracao')""",
                    (unidade_id, aid, id_disc, db.to_cents(row['valor']), row['dia_vencimento']))
                mid = cur.lastrowid
                
                # 3. Gera Mensalidade do Mês Atual
                dt_venc = get_valid_date(hj.year, hj.month, row['dia_vencimento'])
                
                conn.execute("""
                    INSERT INTO pagamentos (unidade_id, matricula_id, aluno_id, mes_referencia, data_vencimento, valor_pago, status) 
                    VALUES (?,?,?,?,?,?,1)""",
                    (unidade_id, mid, aid, mes_ref, dt_venc, db.to_cents(row['valor'])))
                    
    except Exception as e:
        raise e
    finally:
        conn.close()
