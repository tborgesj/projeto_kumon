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
from typing import Optional
from conectDB.conexao import conectar
import pandas as pd
from calendar import monthrange


def atualizar_parametros_unidade(unidade_id: int, mensalidade: float, taxa: float, em_campanha: bool) -> None:
    conn = conectar()
    try:
        with conn:
            conn.execute('''
                INSERT INTO parametros (unidade_id, em_campanha_matricula, valor_taxa_matricula, valor_mensalidade_padrao)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(unidade_id) DO UPDATE SET em_campanha_matricula=excluded.em_campanha_matricula,
                    valor_taxa_matricula=excluded.valor_taxa_matricula, valor_mensalidade_padrao=excluded.valor_mensalidade_padrao
            ''', (unidade_id, _bool_to_int(em_campanha), to_cents(taxa), to_cents(mensalidade)))
    finally:
        conn.close()


def buscar_royalties(unidade_id: int) -> pd.DataFrame:
    conn = conectar()
    try:
        return pd.read_sql_query("""
            SELECT id, valor, ano_mes_inicio, ano_mes_fim 
            FROM config_royalties 
            WHERE unidade_id=? 
            ORDER BY ano_mes_inicio DESC
        """, conn, params=(unidade_id,))
    finally:
        conn.close()


def excluir_royalty(id_regra: int) -> None:
    conn = conectar()
    try:
        with conn:
            conn.execute("DELETE FROM config_royalties WHERE id=?", (id_regra,))
    finally:
        conn.close()


def adicionar_royalty(unidade_id: int, valor: float, inicio: str) -> None:
    conn = conectar()
    try:
        with conn:
            conn.execute("INSERT INTO config_royalties (unidade_id, valor, ano_mes_inicio) VALUES (?, ?, ?)", (unidade_id, to_cents(valor), inicio))
    finally:
        conn.close()


def buscar_info_modelo_contrato(unidade_id: int) -> Optional[str]:
    conn = conectar()
    try:
        row = conn.execute("SELECT nome_arquivo FROM docs_templates WHERE unidade_id=? AND tipo='CONTRATO'", (unidade_id,)).fetchone()
        return row['nome_arquivo'] if row else None
    finally:
        conn.close()


def excluir_modelo_contrato(unidade_id: int) -> None:
    conn = conectar()
    try:
        with conn:
            conn.execute("DELETE FROM docs_templates WHERE unidade_id=? AND tipo='CONTRATO'", (unidade_id,))
    finally:
        conn.close()


def salvar_modelo_contrato(unidade_id: int, nome_arquivo: str, dados_binarios: bytes) -> None:
    conn = conectar()
    try:
        with conn:
            conn.execute("DELETE FROM docs_templates WHERE unidade_id=? AND tipo='CONTRATO'", (unidade_id,))
            conn.execute("INSERT INTO docs_templates (unidade_id, nome_arquivo, arquivo_binario, tipo) VALUES (?, ?, ?, 'CONTRATO')", (unidade_id, nome_arquivo, dados_binarios))
    finally:
        conn.close()

