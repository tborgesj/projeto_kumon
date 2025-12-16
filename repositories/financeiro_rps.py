from typing import List, Optional
from conectDB.conexao import conectar
import pandas as pd
from datetime import date
from calendar import monthrange
import database as db

def buscar_meses_com_movimento(unidade_id: int) -> List[str]:
    conn = conectar()
    try:
        query = """
            SELECT distinct mes_referencia FROM pagamentos WHERE unidade_id=? 
            UNION 
            SELECT distinct mes_referencia FROM despesas WHERE unidade_id=?
        """
        df = pd.read_sql_query(query, conn, params=(unidade_id, unidade_id))
        if 'mes_referencia' in df.columns:
            return df['mes_referencia'].dropna().unique().tolist()
        return []
    finally:
        conn.close()

def registrar_recebimento(unidade_id: int, pagamento_id: int, id_forma: int, taxa: float, nome_aluno: str) -> None:
    taxa_cents = db.to_cents(taxa)
    conn = conectar()
    try:
        with conn:
            hoje = date.today()
            # 1. Atualiza o Pagamento (Entrada)
            conn.execute("""
                UPDATE pagamentos 
                SET id_status=2, data_pagamento=?, id_forma_pagamento=? 
                WHERE id=?
            """, (hoje, id_forma, pagamento_id)) 
            
            # 2. Cria a Despesa de Taxa (Se houver) - AGORA VINCULADA
            if taxa_cents > 0:
                mes_ref = hoje.strftime("%m/%Y")
                
                # Busca nome da forma apenas para a descrição visual
                nome_forma = conn.execute("SELECT nome FROM formas_pagamento WHERE id=?", (id_forma,)).fetchone()[0]
                desc_despesa = f"({nome_forma}) - {nome_aluno}"
                ID_CAT_TAXAS = 3 
                
                conn.execute("""
                    INSERT INTO despesas 
                    (unidade_id, id_categoria, descricao, valor, data_vencimento, mes_referencia, data_pagamento, id_status, id_pagamento_origem) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, 2, ?)
                """, (unidade_id, ID_CAT_TAXAS, desc_despesa, taxa_cents, hoje, mes_ref, hoje, pagamento_id))
    finally:
        conn.close()


def estornar_operacao(id_item: int, tipo_item: str) -> None:
    conn = conectar()
    try:
        with conn:
            if tipo_item == 'Entrada':
                # 1. Estorna a Entrada (Pagamento)
                conn.execute("""
                    UPDATE pagamentos 
                    SET id_status=1, data_pagamento=NULL, id_forma_pagamento=NULL 
                    WHERE id=?
                """, (id_item,))
                
                # 2. Estorna AUTOMATICAMENTE a Taxa vinculada (Despesa)
                # Procura qualquer despesa que tenha nascido deste pagamento
                conn.execute("""
                    DELETE FROM despesas 
                    WHERE id_pagamento_origem=?
                """, (id_item,))
                # Obs: Optei por DELETE porque se estornou a entrada, a taxa "nunca existiu".
                # Se preferir manter histórico, use UPDATE despesas SET id_status=1...

            else:
                # Lógica para estorno de Despesa manual (sem vínculo de origem)
                conn.execute("""
                    UPDATE despesas 
                    SET id_status=1, data_pagamento=NULL 
                    WHERE id=?
                """, (id_item,))
    finally:
        conn.close()


def buscar_recebimentos_pendentes(unidade_id: int, filtro_mes: Optional[str]=None) -> pd.DataFrame:
    conn = conectar()
    try:
        query = """
            SELECT p.id, p.data_vencimento, a.nome, d.nome as disciplina, p.valor_pago 
            FROM pagamentos p 
            LEFT JOIN matriculas m ON p.matricula_id=m.id 
            LEFT JOIN disciplinas d ON m.id_disciplina=d.id
            JOIN alunos a ON COALESCE(p.aluno_id, m.aluno_id)=a.id 
            WHERE p.id_status=1 AND p.unidade_id=?
        """
        params = [unidade_id]
        if filtro_mes and filtro_mes != "Todos": 
            query += " AND p.mes_referencia=?"
            params.append(filtro_mes)
        query += " ORDER BY p.data_vencimento"
        return pd.read_sql(query, conn, params=params)
    finally:
        conn.close()


def buscar_despesas_pendentes(unidade_id: int, filtro_mes: Optional[str]=None) -> pd.DataFrame:
    conn = conectar()
    try:
        query = """
            SELECT d.id, d.data_vencimento, d.id_categoria, c.nome_categoria, descricao, valor 
            FROM despesas d
            INNER JOIN categorias_despesas c ON (c.id = d.id_categoria)
            WHERE id_status=1 AND unidade_id=?
        """
        params = [unidade_id]
        if filtro_mes and filtro_mes != "Todos":
            query += " AND mes_referencia=?"
            params.append(filtro_mes)
        query += " ORDER BY data_vencimento"
        return pd.read_sql(query, conn, params=params)
    finally:
        conn.close()


def buscar_fluxo_caixa(unidade_id: int, mes_referencia: str) -> pd.DataFrame:
    conn = conectar()
    try:
        q_rec = '''
            SELECT p.id, p.data_pagamento, 'Entrada' as Tipo, p.valor_pago, 
            fp.nome as forma_pagamento, 
            a.nome || ' - ' || COALESCE(d.nome, 'Taxa') as Descricao 
            FROM pagamentos p 
            LEFT JOIN matriculas m ON p.matricula_id = m.id 
            LEFT JOIN disciplinas d ON m.id_disciplina = d.id
            JOIN alunos a ON COALESCE(p.aluno_id, m.aluno_id) = a.id 
            LEFT JOIN formas_pagamento fp ON p.id_forma_pagamento = fp.id
            WHERE p.id_status=2 AND p.unidade_id=? AND p.mes_referencia=?
        '''
        q_des = '''
            SELECT d.id, d.data_pagamento, 'Saída' as Tipo, d.valor as valor_pago, '' as forma_pagamento, 
            c.nome_categoria || ' - ' || d.descricao as Descricao 
            FROM despesas d 
            INNER JOIN categorias_despesas c ON (c.id = d.id_categoria)
            WHERE d.id_status=2 AND d.unidade_id=? AND d.mes_referencia=?
        '''
        rec = pd.read_sql(q_rec, conn, params=(unidade_id, mes_referencia))
        des = pd.read_sql(q_des, conn, params=(unidade_id, mes_referencia))
        geral = pd.concat([rec, des], ignore_index=True) if not rec.empty or not des.empty else pd.DataFrame()
        if not geral.empty and 'data_pagamento' in geral.columns:
            geral['data_pagamento'] = pd.to_datetime(geral['data_pagamento'])
            geral = geral.sort_values('data_pagamento', ascending=False)
        return geral
    finally:
        conn.close()



def pagar_despesa(despesa_id: int) -> None:
    conn = conectar()
    try:
        with conn:
            conn.execute("UPDATE despesas SET id_status=2, data_pagamento=DATE('now') WHERE id=?", (despesa_id,))
    finally:
        conn.close()

