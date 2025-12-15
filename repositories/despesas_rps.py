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

def buscar_categorias_despesas() -> List[dict]:
    conn = conectar()
    try:
        df = pd.read_sql("""
            SELECT id, nome_categoria 
            FROM categorias_despesas 
            ORDER BY nome_categoria
        """, conn)
        return df.to_dict(orient="records")
    finally:
        conn.close()


def adicionar_despesa_avulsa(unidade_id: int, categoria: str, descricao: str, valor: float, data_vencimento: date) -> None:
    valor_cents = db.to_cents(valor)
    conn = conectar()
    try:
        with conn:
            mes_ref = data_vencimento.strftime("%m/%Y")
            # AQUI A MUDANÇA: id_status = 1
            conn.execute('''
                INSERT INTO despesas (unidade_id, id_categoria, descricao, valor, data_vencimento, mes_referencia, id_status) 
                VALUES (?, ?, ?, ?, ?, ?, 1)
            ''', (unidade_id, categoria, descricao, valor_cents, data_vencimento, mes_ref))
    finally:
        conn.close()


def adicionar_despesa_recorrente(unidade_id: int, categoria: str, descricao: str, valor: int, dia_vencimento: int) -> None:

    valor_cents = db.to_cents(valor)

    conn = conectar()
    try:
        with conn:
            cur = conn.execute('''
                INSERT INTO despesas_recorrentes (unidade_id, id_categoria, descricao, valor, dia_vencimento, limite_meses, data_criacao, ativo) 
                VALUES (?, ?, ?, ?, ?, 0, DATE('now'), 1)
            ''', (unidade_id, categoria, descricao, valor_cents, dia_vencimento))
            rid = cur.lastrowid
            hj = datetime.now()
            m_ref = f"{hj.month:02d}/{hj.year}"
            dt_venc_atual = db._get_valid_date(hj.year, hj.month, dia_vencimento)
            conn.execute('''
                INSERT INTO despesas (unidade_id, recorrente_id, id_categoria, descricao, valor, data_vencimento, mes_referencia, id_status) 
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            ''', (unidade_id, rid, categoria, descricao, valor_cents, dt_venc_atual, m_ref))
    finally:
        conn.close()


def buscar_recorrencias(unidade_id: int, apenas_ativas: bool=True) -> pd.DataFrame:
    conn = conectar()
    try:
        query = """
            SELECT 
                d.id, 
                d.id_categoria, 
                c.nome_categoria,
                d.descricao, 
                d.valor, 
                d.dia_vencimento, 
                d.ativo
            FROM 
                despesas_recorrentes d
            INNER JOIN
                categorias_despesas c 
                    ON (d.id_categoria = c.id)
            WHERE 
                unidade_id=?"""
        params = [unidade_id]
        if apenas_ativas:
            query += " AND ativo=1"
        query += " ORDER BY descricao"
        return pd.read_sql_query(query, conn, params=params)
    finally:
        conn.close()


def buscar_detalhe_recorrencia(id_recorrencia: int):
    conn = conectar()
    try:
        return conn.execute("SELECT * FROM despesas_recorrentes WHERE id=?", (id_recorrencia,)).fetchone()
    finally:
        conn.close()


def atualizar_recorrencia_completa(id_rec: int, categoria: int, descricao: str, valor: float, dia: int, ativo: bool, unidade_id: int) -> None:
    
    valor_cents = db.to_cents(valor)

    conn = conectar()
    try:
        with conn:
            conn.execute('''
                UPDATE despesas_recorrentes 
                SET id_categoria=?, descricao=?, valor=?, dia_vencimento=?, ativo=? 
                WHERE id=?
            ''', (categoria, descricao, valor_cents, dia, db._bool_to_int(ativo), id_rec))
            if ativo:
                conn.execute('''
                    UPDATE despesas 
                    SET valor=?, descricao=?, id_categoria=? 
                    WHERE recorrente_id=? AND id_status=1 AND unidade_id=?
                ''', (valor_cents, descricao, categoria, id_rec, unidade_id))
    finally:
        conn.close()


def encerrar_recorrencia(id_rec: int) -> None:
    conn = conectar()
    try:
        with conn:
            conn.execute("UPDATE despesas_recorrentes SET ativo=0 WHERE id=?", (id_rec,))
    finally:
        conn.close()

