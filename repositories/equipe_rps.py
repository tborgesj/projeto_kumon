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


def buscar_tipos_contratacao() -> List[dict]:
    conn = conectar()
    try:
        df = pd.read_sql_query("SELECT id, nome FROM tipos_contratacao ORDER BY nome", conn)
        return df.to_dict(orient="records")
    finally:
        conn.close()


def cadastrar_funcionario_completo(unidade_id, nome, id_tipo, salario, dia_pag, lista_custos_iniciais):
    """
    Cadastra funcionário e seus custos iniciais em transação única.
    lista_custos_iniciais = [{tipo, nome, valor, dia}, ...]
    """
    conn = conectar()
    try:
        with conn:
            # 1. Funcionário
            cur = conn.execute('''
                INSERT INTO funcionarios (unidade_id, nome, id_tipo_contratacao, salario_base, data_contratacao, dia_pagamento_salario, ativo)
                VALUES (?, ?, ?, ?, DATE('now'), ?, 1)
            ''', (unidade_id, nome, id_tipo, db.to_cents(salario), dia_pag))
            fid = cur.lastrowid
            
            # 2. Custos
            for item in lista_custos_iniciais:
                conn.execute('''
                    INSERT INTO custos_pessoal (unidade_id, funcionario_id, tipo_item, nome_item, valor, dia_vencimento)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (unidade_id, fid, item['tipo'], item['nome'], db.to_cents(item['valor']), item['dia']))
    except Exception as e:
        raise e
    finally:
        conn.close()

def buscar_funcionarios(unidade_id, filtro_status="Ativos"):
    """
    Retorna DataFrame de funcionários filtrado por status.
    """
    conn = conectar()
    try:
        query = "SELECT id, nome, id_tipo_contratacao, salario_base, ativo FROM funcionarios WHERE unidade_id=?"
        if filtro_status == "Ativos": query += " AND ativo=1"
        elif filtro_status == "Inativos": query += " AND ativo=0"
        
        return pd.read_sql_query(query, conn, params=(unidade_id,))
    finally:
        conn.close()

def buscar_detalhe_funcionario(func_id):
    """
    Retorna tupla com dados completos do funcionário.
    """
    conn = conectar()
    try:
        return conn.execute("SELECT id, unidade_id, nome, id_tipo_contratacao, salario_base, data_contratacao, dia_pagamento_salario, ativo, data_demissao FROM funcionarios WHERE id=?", (func_id,)).fetchone()
    finally:
        conn.close()

def atualizar_funcionario_completo(func_id, nome_novo, id_tipo, salario, dia, ativo, data_demissao, unidade_id, nome_antigo):
    """
    Atualiza cadastro E propaga alterações para o Financeiro (Salário e Benefícios Pendentes).
    """
    conn = conectar()
    try:
        with conn:
            # 1. Update Cadastro
            conn.execute('''
                UPDATE funcionarios 
                SET nome=?, id_tipo_contratacao=?, salario_base=?, dia_pagamento_salario=?, ativo=?, data_demissao=?
                WHERE id=?
            ''', (nome_novo, id_tipo, db.to_cents(salario), dia, 1 if ativo else 0, data_demissao, func_id))
            
            # 2. Propagação Financeira (Sincronizar Salário Pendente)
            desc_sal_antiga = f"Salário - {nome_antigo}"
            desc_sal_nova = f"Salário - {nome_novo}"
            
            # Atualiza valor e descrição da despesa de salário pendente
            conn.execute('''
                UPDATE despesas SET valor=?, descricao=? 
                WHERE descricao=? AND id_status=1 AND unidade_id=?
            ''', (db.to_cents(salario), desc_sal_nova, desc_sal_antiga, unidade_id))

            # Atualiza nome nos benefícios pendentes (se mudou de nome)
            if nome_antigo != nome_novo:
                # Ex: "Vale - João" vira "Vale - João Silva"
                conn.execute("""
                    UPDATE despesas 
                    SET descricao = REPLACE(descricao, ?, ?) 
                    WHERE descricao LIKE ? AND id_status=1 AND unidade_id=?
                """, (f" - {nome_antigo}", f" - {nome_novo}", f"% - {nome_antigo}", unidade_id))

            # Se demitiu, apaga TUDO que estava pendente para ele
            if not ativo:
                conn.execute("""
                    DELETE FROM despesas 
                    WHERE descricao LIKE ? AND id_status=1 AND unidade_id=?
                """, (f"% - {nome_novo}", unidade_id))
    except Exception as e:
        raise e
    finally:
        conn.close()

def buscar_custos_funcionario(func_id):
    """
    Lista benefícios e impostos extras do funcionário.
    """
    conn = conectar()
    try:
        return conn.execute("SELECT id, tipo_item, nome_item, valor, dia_vencimento FROM custos_pessoal WHERE funcionario_id=?", (func_id,)).fetchall()
    finally:
        conn.close()

def excluir_custo_pessoal(custo_id, nome_item, nome_funcionario, unidade_id):
    """
    Remove custo do cadastro e cancela a despesa pendente correspondente.
    """
    conn = conectar()
    try:
        with conn:
            # 1. Remove da tabela de custos
            conn.execute("DELETE FROM custos_pessoal WHERE id=?", (custo_id,))
            
            # 2. Remove conta a pagar pendente
            desc_pendente = f"{nome_item} - {nome_funcionario}"
            conn.execute("DELETE FROM despesas WHERE descricao=? AND id_status=1 AND unidade_id=?", 
                         (desc_pendente, unidade_id))
    except Exception as e:
        raise e
    finally:
        conn.close()

def adicionar_custo_extra_funcionario(unidade_id, func_id, tipo_item, nome_item, valor, dia_venc, nome_funcionario):
    """
    Adiciona novo custo e já gera a despesa do mês atual (Propagação Imediata).
    """
    conn = conectar()
    try:
        # Helper de data local para esta função
        def get_valid_date(year, month, day):
            try:
                return date(year, month, day)
            except ValueError:
                if month == 12: return date(year, 12, 31)
                return date(year, month + 1, 1) - pd.Timedelta(days=1)

        with conn:
            # 1. Insere Custo no Cadastro
            conn.execute('''
                INSERT INTO custos_pessoal (unidade_id, funcionario_id, tipo_item, nome_item, valor, dia_vencimento) 
                VALUES (?,?,?,?,?,?)
            ''', (unidade_id, func_id, tipo_item, nome_item, db.to_cents(valor), dia_venc))
            
            # 2. Gera Despesa Financeira (Mês Atual)
            hj = datetime.now()
            mes_ref = hj.strftime("%m/%Y")
            desc_item = f"{nome_item} - {nome_funcionario}"
            cat_item = "Impostos" if tipo_item == "IMPOSTO" else "Pessoal"
            dt_venc = get_valid_date(hj.year, hj.month, dia_venc)
            
            # Verifica duplicidade antes de inserir
            existe = conn.execute("SELECT id FROM despesas WHERE descricao=? AND mes_referencia=? AND unidade_id=?", 
                                  (desc_item, mes_ref, unidade_id)).fetchone()
            
            if not existe:
                conn.execute('''
                    INSERT INTO despesas (unidade_id, categoria, descricao, valor, data_vencimento, mes_referencia, status) 
                    VALUES (?, ?, ?, ?, ?, ?, 1)
                ''', (unidade_id, cat_item, desc_item, db.to_cents(valor), dt_venc, mes_ref))
    except Exception as e:
        raise e
    finally:
        conn.close()
