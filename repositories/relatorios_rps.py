from conectDB.conexao import conectar
import pandas as pd


def buscar_lista_alunos_periodo(unidade_id, data_inicio, data_fim):
    """
    Busca alunos que tiveram matrícula ativa em algum momento dentro do período informado.
    Regra: Data Início da matrícula <= Fim do Mês E (Ativo ou Data Fim >= Início do Mês).
    """
    conn = conectar()
    try:
        query = '''
            SELECT 
                a.nome as Aluno,
                d.nome as Disciplina
            FROM matriculas m
            INNER JOIN disciplinas d ON d.id = m.id_disciplina
            JOIN alunos a ON m.aluno_id = a.id
            WHERE m.unidade_id = ?
              AND a.nome IS NOT NULL 
              AND m.aluno_id IS NOT NULL
              AND m.data_inicio <= ? 
              AND (m.ativo = 1 OR m.data_fim >= ?)
            ORDER BY a.nome, m.id_disciplina
        '''
        return pd.read_sql_query(query, conn, params=(unidade_id, data_fim, data_inicio))
    finally:
        conn.close()
