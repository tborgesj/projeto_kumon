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
from typing import Dict, Tuple, List, Any, Optional
from conectDB.conexao import conectar
import pandas as pd
from datetime import date, datetime
from calendar import monthrange
import database as db


def buscar_dados_financeiros_anuais(unidade_id: int, ano: int) -> pd.DataFrame:
    conn = conectar()
    try:
        termo_busca = f"%{ano}"
        query = """
            SELECT mes_referencia, tipo, SUM(total) as total FROM (
                SELECT mes_referencia, 'Receita' as tipo, valor_pago as total FROM pagamentos WHERE unidade_id=? AND mes_referencia LIKE ? AND id_status=2
                UNION ALL
                SELECT mes_referencia, 'Despesa' as tipo, valor as total FROM despesas WHERE unidade_id=? AND mes_referencia LIKE ? AND id_status=2
            ) GROUP BY mes_referencia, tipo
        """
        return pd.read_sql(query, conn, params=(unidade_id, termo_busca, unidade_id, termo_busca))
    finally:
        conn.close()


def buscar_despesas_por_categoria(unidade_id: int, ano: int) -> pd.DataFrame:
    conn = conectar()
    try:
        termo = f"%{ano}"
        query = """
            SELECT c.nome_categoria, SUM(valor) as total 
            FROM despesas d
            INNER JOIN categorias_despesas c ON (c.id = d.id_categoria)
            WHERE unidade_id=? AND mes_referencia LIKE ? AND id_status=2
            GROUP BY c.nome_categoria
        """
        return pd.read_sql_query(query, conn, params=(unidade_id, termo))
    finally:
        conn.close()


def buscar_distribuicao_matriculas(unidade_id: int) -> pd.DataFrame:
    conn = conectar()
    try:
        query = """
            SELECT d.nome as disciplina, COUNT(*) as qtd 
            FROM matriculas m
            INNER JOIN disciplinas d ON m.id_disciplina = d.id
            WHERE m.ativo=1 AND m.unidade_id=? 
            GROUP BY d.nome
        """
        return pd.read_sql_query(query, conn, params=(unidade_id,))
    finally:
        conn.close()


def buscar_indicadores_inadimplencia(unidade_id: int, ano: int) -> pd.DataFrame:
    conn = conectar()
    try:
        termo = f"%{ano}"
        query = """
            SELECT 
                SUM(valor_pago) as valor_total,
                SUM(CASE WHEN id_status=1 AND data_vencimento < DATE('now') THEN valor_pago ELSE 0 END) as valor_atrasado
            FROM pagamentos
            WHERE unidade_id=? AND mes_referencia LIKE ?
        """
        return pd.read_sql_query(query, conn, params=(unidade_id, termo))
    finally:
        conn.close()


def buscar_custo_rh_anual(unidade_id: int, ano: int) -> float:
    conn = conectar()
    try:
        termo = f"%{ano}"
        query = """
            SELECT SUM(valor) FROM despesas 
            WHERE unidade_id=? 
            AND mes_referencia LIKE ? 
            AND (id_categoria = 1 OR id_categoria = 2)
            AND id_status=2
        """
        resultado = conn.execute(query, (unidade_id, termo)).fetchone()[0]
        return db.from_cents(resultado) if resultado else 0
    finally:
        conn.close()


def contar_funcionarios_ativos(unidade_id: int) -> int:
    conn = conectar()
    try:
        query = "SELECT COUNT(*) as cnt FROM funcionarios WHERE ativo=1 AND unidade_id=?"
        return int(conn.execute(query, (unidade_id,)).fetchone()['cnt'] or 0)
    finally:
        conn.close()


def contar_meses_com_faturamento(unidade_id: int, ano: int) -> int:
    conn = conectar()
    try:
        termo = f"%{ano}"
        query = """
            SELECT COUNT(DISTINCT mes_referencia) as cnt
            FROM pagamentos 
            WHERE unidade_id=? AND mes_referencia LIKE ? AND valor_pago > 0
        """
        count = conn.execute(query, (unidade_id, termo)).fetchone()['cnt']
        return int(count or 0)
    finally:
        conn.close()

