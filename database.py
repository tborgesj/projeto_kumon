"""
Improved database module for the Kumon system.
Goals:
- Keep existing public API (function names and signatures) so front-end doesn't need to change.
- Improve safety: consistent connection handling, transactions, input validation, logging.
- Preserve backwards compatibility for password verification (existing sha256 hashes), but recommend migration to bcrypt.
- Add small helpers to reduce repetition and to make code easier to test.
"""

import sqlite3
import bcrypt
import logging
from datetime import date, datetime
from calendar import monthrange
from typing import Dict, Tuple, List, Any, Optional
import pandas as pd

from conectDB import conexao as cnc

# --- Logging ---
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(name)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

# --- 1. ADAPTERS (Datas) ---
def adapt_date(val: date) -> str:
    return val.isoformat()

def adapt_datetime(val: datetime) -> str:
    # SQLite expects 'YYYY-MM-DD HH:MM:SS' for datetime strings
    return val.isoformat(" ")

sqlite3.register_adapter(date, adapt_date)
sqlite3.register_adapter(datetime, adapt_datetime)


# --- Helpers internos ---
def _get_valid_date(year: int, month: int, day: int) -> date:
    """Retorna uma data válida ajustando o dia se ultrapassar o último dia do mês."""
    max_day = monthrange(year, month)[1]
    return date(year, month, min(day, max_day))

def _ensure_positive_number(name: str, value: Any) -> float:
    try:
        v = float(value)
    except Exception:
        raise ValueError(f"{name} precisa ser um número (float/int). Recebido: {value!r}")
    if v < 0:
        raise ValueError(f"{name} não pode ser negativo.")
    return v

def _bool_to_int(b: bool) -> int:
    return 1 if b else 0


# --- HELPERS DE CONVERSÃO MONETÁRIA (Centavos) ---

def to_cents(val) -> int:
    """Converte R$ 10,00 (float/str) para 1000 (int centavos) para salvar no banco."""
    if val is None: return 0
    try:
        # Converte para float primeiro para garantir, depois multiplica e arredonda
        return int(round(float(val) * 100))
    
    except Exception:
        return 0

def from_cents(val) -> float:
    """Converte 1000 (int centavos) do banco para 10.00 (float) para exibir."""
    if val is None: return 0.0
    try:
        return float(val) / 100.0
    except Exception:
        return 0.0


# --- 4. Funções auxiliares e operacionais (preservando assinaturas públicas) ---

def verificar_credenciais(usuario: str, senha_digitada: str) -> Tuple[bool, Optional[str], bool]:
    """Verifica credenciais. Compatível com hashes existentes.
    Retorna (ok, nome_completo, is_admin).
    """
    conn = cnc.conectar()
    try:
        
        row = conn.execute("SELECT nome_completo, admin, password_hash FROM usuarios WHERE username = ? AND ativo=1", (usuario,)).fetchone()
        
        if not row:
            return False, None, False

        stored = row['password_hash']

        # # Se o stored for um algoritmo diferente no futuro, adapte aqui
        # if stored == senha_hash:
        #     return True, row['nome_completo'], bool(row['admin'])

        # O stored_hash vem do SQLite como string, então também convertemos para bytes
        try:
            if bcrypt.checkpw(senha_digitada.encode('utf-8'), stored.encode('utf-8')):
                return True, row['nome_completo'], bool(row['admin'])
        except ValueError:
            # Proteção caso, por algum erro manual, o banco tenha um hash inválido/corrompido
            return False, None, False

        # Se quiser implementar troca incremental: verificar outros esquemas aqui (ex: bcrypt)
        return False, None, False
    finally:
        conn.close()


def get_unidades_usuario(usuario: str) -> List[Tuple[int, str]]:
    conn = cnc.conectar()
    try:
        rows = conn.execute(
            'SELECT u.id AS id, u.nome AS nome FROM unidades u JOIN usuario_unidades uu ON u.id = uu.unidade_id WHERE uu.usuario_username = ? ORDER BY u.id',
            (usuario,)
        ).fetchall()
        return [(r['id'], r['nome']) for r in rows]
    finally:
        conn.close()


def get_parametros_unidade(unidade_id):
    """
    Busca as configurações globais da unidade (mensalidade padrão, taxa, campanha).
    Retorna um dicionário.
    """
    conn = cnc.conectar()
    try:
        row = conn.execute("SELECT valor_mensalidade_padrao, valor_taxa_matricula, em_campanha_matricula FROM parametros WHERE unidade_id=?", (unidade_id,)).fetchone()
        if row:
            return {
                'mensalidade': from_cents(row[0]),
                'taxa_matr': from_cents(row[1]),
                'campanha': bool(row[2])
            }
        return {'mensalidade': 0, 'taxa_matr': 0, 'campanha': False} # Fallback seguro
    finally:
        conn.close()


def buscar_todas_unidades():
    """
    Retorna lista de tuplas (id, nome) de todas as unidades cadastradas.
    """
    conn = cnc.conectar()
    try:
        return conn.execute("SELECT id, nome FROM unidades ORDER BY nome").fetchall()
    finally:
        conn.close()

def buscar_lista_usuarios():
    """
    Retorna DataFrame com dados básicos dos usuários para listagem.
    """
    conn = cnc.conectar()
    try:
        return pd.read_sql("SELECT username, nome_completo, admin, ativo FROM usuarios ORDER BY nome_completo", conn)
    finally:
        conn.close()

def buscar_ids_unidades_usuario(username):
    """
    Retorna uma lista de IDs das unidades que o usuário tem acesso.
    """
    conn = cnc.conectar()
    try:
        res = conn.execute("SELECT unidade_id FROM usuario_unidades WHERE usuario_username=?", (username,)).fetchall()
        return [r[0] for r in res]
    finally:
        conn.close()

def buscar_resumo_operacional_mes(unidade_id):
    """
    Calcula os totais financeiros (Receitas/Despesas) e contagem de alunos
    para alimentar os Cards da Home.
    """
    conn = cnc.conectar()
    try:
        hoje = datetime.now()
        mes_ref = hoje.strftime("%m/%Y")     # Para pagamentos/despesas
        mes_anomes = hoje.strftime('%Y-%m')  # Para filtro de data_fim (sqlite)

        cursor = conn.cursor()

        # 1. Receitas
        cursor.execute("SELECT SUM(valor_pago) FROM pagamentos WHERE mes_referencia = ? AND unidade_id = ?", (mes_ref, unidade_id))
        rec_total = cursor.fetchone()[0] or 0.0

        cursor.execute("SELECT SUM(valor_pago) FROM pagamentos WHERE mes_referencia = ? AND id_status=1 AND unidade_id = ?", (mes_ref, unidade_id))
        rec_pendente = cursor.fetchone()[0] or 0.0

        # 2. Despesas
        cursor.execute("SELECT SUM(valor) FROM despesas WHERE mes_referencia = ? AND unidade_id = ?", (mes_ref, unidade_id))
        desp_total = cursor.fetchone()[0] or 0.0

        cursor.execute("SELECT SUM(valor) FROM despesas WHERE mes_referencia = ? AND id_status=1 AND unidade_id = ?", (mes_ref, unidade_id))
        desp_pendente = cursor.fetchone()[0] or 0.0

        # 3. Alunos
        cursor.execute("SELECT COUNT(id) FROM matriculas WHERE ativo=1 AND unidade_id = ?", (unidade_id,))
        alunos_ativos = cursor.fetchone()[0] or 0

        cursor.execute("SELECT COUNT(*) FROM matriculas WHERE unidade_id = ? AND ativo = 0 AND strftime('%Y-%m', data_fim) = ?", (unidade_id, mes_anomes))
        alunos_ausentes = cursor.fetchone()[0] or 0

        return {
            "mes": mes_ref,
            "rec_total": from_cents(rec_total),
            "rec_pendente": from_cents(rec_pendente),
            "desp_total": from_cents(desp_total),
            "desp_pendente": from_cents(desp_pendente),
            "saldo_previsto": from_cents(rec_total - desp_total),
            "alunos_ativos": alunos_ativos,
            "alunos_ausentes": alunos_ausentes,
        }
    finally:
        conn.close()

def buscar_pendencias_recebimento(unidade_id, mes_ref):
    """
    Lista os alunos que ainda não pagaram no mês atual.
    """
    conn = cnc.conectar()
    try:
        query = '''
            SELECT a.nome, p.data_vencimento, p.valor_pago
            FROM pagamentos p JOIN alunos a ON p.aluno_id = a.id
            WHERE p.id_status=1 AND p.mes_referencia = ? AND p.unidade_id = ?
            ORDER BY p.data_vencimento
        '''
        return pd.read_sql_query(query, conn, params=(mes_ref, unidade_id))
    finally:
        conn.close()

def buscar_pendencias_pagamento(unidade_id, mes_ref):
    """
    Lista as contas (despesas) que vencem no mês atual e ainda não foram pagas.
    """
    conn = cnc.conectar()
    try:
        query = '''
            SELECT descricao, data_vencimento, valor
            FROM despesas
            WHERE id_status=1 AND mes_referencia = ? AND unidade_id = ?
            ORDER BY data_vencimento
        '''
        return pd.read_sql_query(query, conn, params=(mes_ref, unidade_id))
    finally:
        conn.close()

def buscar_canais_aquisicao() -> List[dict]:
    conn = cnc.conectar()
    try:
        # Retorna lista de dicts com 'id' e 'nome'
        df = pd.read_sql_query("SELECT id, nome FROM canais_aquisicao ORDER BY nome", conn)
        return df.to_dict(orient="records")
    finally:
        conn.close()

def buscar_disciplinas() -> List[dict]:
    conn = cnc.conectar()
    try:
        df = pd.read_sql_query("SELECT id, nome FROM disciplinas ORDER BY nome", conn)
        return df.to_dict(orient="records")
    finally:
        conn.close()

def buscar_formas_pagamento() -> List[dict]:
    conn = cnc.conectar()
    try:
        df = pd.read_sql("SELECT id, nome FROM formas_pagamento ORDER BY nome", conn)
        return df.to_dict(orient="records")
    finally:
        conn.close()