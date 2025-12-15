from typing import Dict, Tuple, List, Any, Optional
from conectDB.conexao import conectar
import pandas as pd
from datetime import date, datetime
from calendar import monthrange
import database as db


def realizar_distribuicao_lucro(unidade_id: int, mapa_distribuicao: Dict[int, float]) -> None:
    conn = conectar()
    try:
        with conn:
            hoje = date.today()
            for cofre_id, valor in mapa_distribuicao.items():
                if not isinstance(cofre_id, int):
                    raise TypeError("cofre_id deve ser int")
                valor = float(valor)
                if valor <= 0:
                    continue
                cur = conn.execute("""
                    UPDATE cofres_saldo 
                    SET saldo_atual = saldo_atual + ? 
                    WHERE cofre_id=? AND unidade_id=?
                """, (db.to_cents(valor), cofre_id, unidade_id))
                if cur.rowcount == 0:
                    raise ValueError(f"Cofre {cofre_id} não existe para a unidade {unidade_id}")
                conn.execute("""
                    INSERT INTO cofres_movimentacao 
                    (unidade_id, cofre_id, data_movimentacao, valor, tipo, descricao) 
                    VALUES (?, ?, ?, ?, 'ENTRADA', 'Distribuição de Lucro')
                """, (unidade_id, cofre_id, hoje, db.to_cents(valor)))
    finally:
        conn.close()


def realizar_saque_cofre(unidade_id: int, cofre_id: int, valor: float, motivo: str) -> None:
    conn = conectar()
    try:
        with conn:
            valor = float(valor)
            if valor <= 0:
                raise ValueError("Valor do saque deve ser maior que zero.")
            cur = conn.execute("""
                UPDATE cofres_saldo 
                SET saldo_atual = saldo_atual - ? 
                WHERE cofre_id=? AND unidade_id=?
            """, (db.to_cents(valor), cofre_id, unidade_id))
            if cur.rowcount == 0:
                raise ValueError("Cofre não encontrado ou relação com unidade incorreta.")
            conn.execute("""
                INSERT INTO cofres_movimentacao 
                (unidade_id, cofre_id, data_movimentacao, valor, tipo, descricao) 
                VALUES (?, ?, DATE('now'), ?, 'SAIDA', ?)
            """, (unidade_id, cofre_id, db.to_cents(valor), motivo))
    finally:
        conn.close()


def buscar_cofres_com_saldo(unidade_id: int) -> pd.DataFrame:
    conn = conectar()
    try:
        query = '''
            SELECT c.id, c.nome, c.percentual_padrao, c.descricao, s.saldo_atual 
            FROM cofres c 
            JOIN cofres_saldo s ON c.id = s.cofre_id 
            WHERE c.unidade_id = ?
        '''
        return pd.read_sql_query(query, conn, params=(unidade_id,))
    finally:
        conn.close()


def calcular_lucro_realizado(unidade_id: int, mes_referencia: str) -> float:
    conn = conectar()
    try:
        rec = conn.execute("SELECT SUM(valor_pago) as total FROM pagamentos WHERE mes_referencia=? AND id_status=2 AND unidade_id=?", (mes_referencia, unidade_id)).fetchone()['total'] or 0.0
        des = conn.execute("SELECT SUM(valor) as total FROM despesas WHERE mes_referencia=? AND id_status=2 AND unidade_id=?", (mes_referencia, unidade_id)).fetchone()['total'] or 0.0
        lucro = db.from_cents(rec) - db.from_cents(des)
        return lucro if lucro > 0 else 0.0
    finally:
        conn.close()


def atualizar_percentuais_cofres(mapa_novos_percentuais: Dict[int, float]) -> bool:
    if not mapa_novos_percentuais:
        raise ValueError("Nenhum percentual informado para atualização.")
    for cofre_id, percentual in mapa_novos_percentuais.items():
        if not isinstance(cofre_id, int):
            raise TypeError(f"ID do cofre inválido: {cofre_id}")
        if not isinstance(percentual, (int, float)):
            raise TypeError(f"Percentual inválido para o cofre {cofre_id}: {percentual}")
        if percentual < 0 or percentual > 100:
            raise ValueError(f"Percentual fora do intervalo permitido (0–100): {percentual}")
    conn = conectar()
    try:
        with conn:
            for cofre_id, percentual in mapa_novos_percentuais.items():
                cur = conn.execute("UPDATE cofres SET percentual_padrao = ? WHERE id = ?", (percentual, cofre_id))
                if cur.rowcount == 0:
                    raise ValueError(f"Cofre com ID {cofre_id} não encontrado.")
        return True
    finally:
        conn.close()

def buscar_historico_movimentacoes_cofres(unidade_id):
    """
    Retorna o histórico completo de entradas e saídas dos cofres,
    com join para pegar o nome do cofre.
    """
    conn = conectar()
    try:
        query = '''
            SELECT m.data_movimentacao, c.nome, m.tipo, m.valor, m.descricao 
            FROM cofres_movimentacao m 
            JOIN cofres c ON m.cofre_id = c.id 
            WHERE m.unidade_id = ? 
            ORDER BY m.id DESC
        '''
        return pd.read_sql_query(query, conn, params=(unidade_id,))
    finally:
        conn.close()
