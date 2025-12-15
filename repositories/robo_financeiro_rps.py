import sys
import os

# 1. Pega o caminho absoluto de onde o arquivo '1_Aluno.py' está
diretorio_atual = os.path.dirname(os.path.abspath(__file__))

# 2. Sobe um nível para chegar na raiz do projeto (o pai do diretorio_atual)
diretorio_raiz = os.path.dirname(diretorio_atual)

# 3. Adiciona a raiz à lista de lugares onde o Python procura arquivos
sys.path.append(diretorio_raiz)

# --- FIM DA CONFIGURAÇÃO DE CAMINHO ---

from typing import Tuple, List, Optional
from conectDB.conexao import conectar
import pandas as pd
from datetime import date, datetime
from calendar import monthrange
import database as db

def executar_robo_financeiro(unidade_id: int) -> Tuple[int, int, int]:
    conn = conectar()
    try:
        def _get_valid_date_local(year, month, day):
            try:
                return date(year, month, day)
            except ValueError:
                max_d = monthrange(year, month)[1]
                return date(year, month, max_d)

        cnt_d, cnt_r, cnt_p = 0, 0, 0
        mes_str = datetime.now().strftime("%m/%Y")
        hj = datetime.now()

        # Define se gera boleto para este mês ou próximo (regra do dia 21)
        target = hj if hj.day < 21 else (hj + pd.DateOffset(days=32))
        m_ref_boletos = target.strftime("%m/%Y")

        with conn:
            
            # --- 1. DESPESAS RECORRENTES (Água, Luz, Internet) ---
            regras = conn.execute("""
                                    SELECT d.id, c.nome_categoria, d.id_categoria, descricao, valor, dia_vencimento 
                                        FROM despesas_recorrentes d
                                        INNER JOIN categorias_despesas c ON (c.id = d.id_categoria)
                                        WHERE ativo=1 AND unidade_id=?""", (unidade_id,)).fetchall()
            
            # print(f"DEBUG: Regras Encontradas = {[dict(r) for r in regras]}")

            for r in regras:
                rid, cat, desc, val, dia = r['id'], r['id_categoria'], r['descricao'], r['valor'], r['dia_vencimento']
                existe_bol = conn.execute("SELECT id FROM despesas WHERE recorrente_id=? AND mes_referencia=? AND unidade_id=?", (rid, mes_str, unidade_id)).fetchone()
                
                if not existe_bol:
                    # Nota: val já vem do banco em centavos (despesas_recorrentes), não precisa de to_cents novamente se já estiver salvo certo.
                    # Se na tabela 'despesas_recorrentes' o valor é float, use to_cents. Se é int, use direto.
                    # Vou assumir que 'despesas_recorrentes' guarda centavos (int). Se guardar reais, coloque db.to_cents(val).
                    val_insert = val 
                    
                    conn.execute("""
                        INSERT INTO despesas (unidade_id, recorrente_id, id_categoria, descricao, valor, data_vencimento, mes_referencia, id_status) 
                        VALUES (?,?,?,?,?,?,?, 1)
                    """, (unidade_id, rid, cat, desc, val_insert, _get_valid_date_local(hj.year, hj.month, dia), mes_str))
                    cnt_d += 1
                
            mats = conn.execute("SELECT id, valor_acordado, aluno_id, dia_vencimento, bolsa_ativa, bolsa_meses_restantes FROM matriculas WHERE ativo=1 AND unidade_id=?", (unidade_id,)).fetchall()
            for row in mats:
                mid = row['id']; val_base = row['valor_acordado']; aid = row['aluno_id']; dia = row['dia_vencimento']; b_ativa = row['bolsa_ativa']; b_meses = row['bolsa_meses_restantes']
                existe_bol = conn.execute("SELECT id FROM pagamentos WHERE matricula_id=? AND mes_referencia=? AND unidade_id=?", (mid, m_ref_boletos, unidade_id)).fetchone()
                if not existe_bol:
                    valor_final = val_base
                    if b_ativa and b_meses and b_meses > 0:
                        valor_final = float(val_base) * 0.50
                        novo_saldo = b_meses - 1
                        novo_status = 1 if novo_saldo > 0 else 0
                        conn.execute("UPDATE matriculas SET bolsa_meses_restantes=?, bolsa_ativa=? WHERE id=?", (novo_saldo, novo_status, mid))
                    conn.execute("""
                        INSERT INTO pagamentos (unidade_id, matricula_id, aluno_id, mes_referencia, data_vencimento, valor_pago, id_status, id_tipo) 
                        VALUES (?,?,?,?,?,?, 1, 1)
                    """, (unidade_id, mid, aid, m_ref_boletos, _get_valid_date_local(target.year, target.month, dia), valor_final))
                    cnt_r += 1

            funcs = conn.execute("SELECT id, nome, salario_base, dia_pagamento_salario FROM funcionarios WHERE ativo=1 AND unidade_id=?", (unidade_id,)).fetchall()
            for f in funcs:
                fid = f['id']; fnome = f['nome']; fsal = f['salario_base']; fdia = f['dia_pagamento_salario']
                desc_sal = f"Salário - {fnome}"
                if fsal and fsal > 0:
                    existe_sal = conn.execute("SELECT id FROM despesas WHERE descricao=? AND mes_referencia=? AND unidade_id=?", (desc_sal, mes_str, unidade_id)).fetchone()
                    if not existe_sal:
                        conn.execute("""
                            INSERT INTO despesas (unidade_id, id_categoria, descricao, valor, data_vencimento, mes_referencia, id_status) 
                            VALUES (?, 1, ?, ?, ?, ?, 1)
                        """, (unidade_id, desc_sal, fsal, _get_valid_date_local(hj.year, hj.month, fdia), mes_str))
                        cnt_p += 1

                custos = conn.execute("SELECT tipo_item, nome_item, valor, dia_vencimento FROM custos_pessoal WHERE funcionario_id=?", (fid,)).fetchall()
                for c in custos:
                    ctipo = c['tipo_item']; cnome = c['nome_item']; cval = c['valor']; cdia = c['dia_vencimento']
                    desc_item = f"{cnome} - {fnome}"
                    cat = 2 if ctipo == "IMPOSTO" else 1
                    if cval and cval > 0:
                        existe_custo = conn.execute("SELECT id FROM despesas WHERE descricao=? AND mes_referencia=? AND unidade_id=?", (desc_item, mes_str, unidade_id)).fetchone()
                        if not existe_custo:
                            conn.execute("""
                                INSERT INTO despesas (unidade_id, id_categoria, descricao, valor, data_vencimento, mes_referencia, id_status) 
                                VALUES (?, ?, ?, ?, ?, ?, 1)
                            """, (unidade_id, cat, desc_item, db.to_cents(cval), _get_valid_date_local(hj.year, hj.month, cdia), mes_str))
                            cnt_p += 1
        return cnt_d, cnt_r, cnt_p
    finally:
        conn.close()
