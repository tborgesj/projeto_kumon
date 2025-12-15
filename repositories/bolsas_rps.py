# import sqlite3
from typing import Dict, Tuple, List, Any, Optional
from conectDB.conexao import conectar
import pandas as pd
from datetime import date, datetime
from calendar import monthrange
import database as db


def buscar_bolsas_ativas(unidade_id):
    """
    Retorna um DataFrame com todos os alunos que possuem bolsa ativa na unidade.
    Traz: Nome, Disciplina, Valor Original e Meses Restantes.
    """
    conn = conectar()
    try:
        query = '''
            SELECT 
                a.nome, 
                d.nome disciplina, 
                m.valor_acordado as valor_original,
                m.bolsa_meses_restantes
            FROM matriculas m
            INNER JOIN disciplinas d ON d.id = m.id_disciplina
            JOIN alunos a ON m.aluno_id = a.id
            WHERE m.unidade_id = ? AND m.bolsa_ativa = 1 AND m.ativo = 1
            ORDER BY m.bolsa_meses_restantes ASC
        '''
        return pd.read_sql_query(query, conn, params=(unidade_id,))
    finally:
        conn.close()

