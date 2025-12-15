# import sqlite3
from typing import Dict, Tuple, List, Any, Optional
from conectDB.conexao import conectar
import pandas as pd
from datetime import date, datetime
from calendar import monthrange
import database as db


def realizar_matricula_completa(unidade_id, dados_aluno, lista_disciplinas, dia_vencimento, valor_taxa, campanha_ativa):
    """
    Realiza todo o processo de matrícula em uma única transação atômica.
    - Cria Aluno
    - Cria Matrículas
    - Gera 1ª Mensalidade
    - Gera Taxa de Matrícula (se houver)
    """
    conn = conectar()
    try:
        # Helper de data para calcular vencimentos
        def get_valid_date_local(year, month, day):
            try:
                return date(year, month, day)
            except ValueError:
                if month == 12: return date(year, 12, 31)
                return date(year, month + 1, 1) - pd.Timedelta(days=1)

        hj = datetime.now()
        
        # Regra de Negócio: Se dia > 20, cobra só no próximo mês
        mes_cob = hj.month if hj.day <= 20 else hj.month + 1
        ano_cob = hj.year
        if mes_cob > 12: 
            mes_cob = 1; ano_cob += 1
            
        mes_ref = f"{mes_cob:02d}/{ano_cob}"
        dt_venc_mensal = get_valid_date_local(ano_cob, mes_cob, dia_vencimento)

        with conn: # INÍCIO DA TRANSAÇÃO (Tudo ou Nada)
            # 1. Cria Aluno
            cur = conn.execute("""
                INSERT INTO alunos (unidade_id, nome, responsavel_nome, cpf_responsavel, id_canal_aquisicao, data_cadastro)
                VALUES (?, ?, ?, ?, ?, DATE('now'))
            """, (unidade_id, dados_aluno['nome'], dados_aluno['responsavel'], dados_aluno['cpf'], dados_aluno['id_canal'])) # Note: dados_aluno['id_canal']
            aid = cur.lastrowid
            
            # 2. Processa Disciplinas
            for item in lista_disciplinas:
                # Cria Matrícula
                cur.execute("""
                    INSERT INTO matriculas (unidade_id, aluno_id, id_disciplina, valor_acordado, dia_vencimento, justificativa_desconto, data_inicio, ativo) 
                    VALUES (?,?,?,?,?,?,DATE('now'),1)
                """, (unidade_id, aid, item['id_disc'], db.to_cents(item['val']), dia_vencimento, item['just']))
                mid = cur.lastrowid
                
                # Gera 1ª Mensalidade
                cur.execute("""
                    INSERT INTO pagamentos (unidade_id, matricula_id, aluno_id, mes_referencia, data_vencimento, valor_pago, id_status, id_tipo) 
                    VALUES (?,?,?,?,?,?, 1, 1)
                """, (unidade_id, mid, aid, mes_ref, dt_venc_mensal, db.to_cents(item['val'])))
            
            # 3. Taxa de Matrícula (id_status=1 Pendente, id_tipo=2 Taxa Matrícula)
            if not campanha_ativa and valor_taxa > 0:
                dt_tx = date.today() + pd.Timedelta(days=1) # Vence amanhã
                mes_ref_tx = dt_tx.strftime("%m/%Y")
                
                conn.execute("""
                    INSERT INTO pagamentos (unidade_id, aluno_id, mes_referencia, data_vencimento, valor_pago, id_status, id_tipo) 
                    VALUES (?,?,?,?,?, 1, 2)
                """, (unidade_id, aid, mes_ref_tx, dt_tx, db.to_cents(valor_taxa)))
                
    except Exception as e:
        raise e
    finally:
        conn.close()

# def buscar_alunos_por_nome(unidade_id, termo_busca=""):
#     """
#     Busca alunos para o seletor. Se termo_busca vazio, traz últimos 50.
#     """
#     conn = conectar()
#     try:
#         if termo_busca:
#             query = "SELECT id, nome FROM alunos WHERE unidade_id=? AND nome LIKE ? ORDER BY nome LIMIT 50"
#             return pd.read_sql_query(query, conn, params=(unidade_id, f"%{termo_busca}%"))
#         else:
#             query = "SELECT id, nome FROM alunos WHERE unidade_id=? ORDER BY id DESC LIMIT 50"
#             return pd.read_sql_query(query, conn, params=(unidade_id,))
#     finally:
#         conn.close()

def buscar_dados_aluno_completo(aluno_id: int):
    """Retorna dados cadastrais do aluno."""
    conn = conectar()
    try:
        query = """ 
        SELECT id, unidade_id, nome, responsavel_nome, cpf_responsavel, id_canal_aquisicao 
            FROM alunos 
            WHERE id=?
        """
        df = pd.read_sql_query(query, conn, params=(aluno_id,))
        return df.iloc[0] if not df.empty else None
    finally:
        conn.close()

def atualizar_dados_aluno(aluno_id, nome, resp, cpf, id_canal: int):
    """Atualiza cadastro básico."""
    conn = conectar()
    try:
        with conn:
            conn.execute("""
                UPDATE alunos SET nome=?, responsavel_nome=?, cpf_responsavel=?, id_canal_aquisicao=? 
                WHERE id=?
            """, (nome, resp, cpf, id_canal, aluno_id))
    except Exception as e:
        raise e
    finally:
        conn.close()

def buscar_matriculas_aluno(aluno_id, unidade_id):
    """Retorna lista de matrículas (disciplinas) do aluno."""
    conn = conectar()
    try:
        return conn.execute("""
            SELECT m.id, d.nome as disciplina, m.valor_acordado, m.dia_vencimento, m.ativo, m.bolsa_ativa, m.bolsa_meses_restantes 
            FROM matriculas m
            INNER JOIN disciplinas d ON m.id_disciplina = d.id
            WHERE m.aluno_id=? AND m.unidade_id=?
        """, (aluno_id, unidade_id)).fetchall()
    finally:
        conn.close()

def adicionar_nova_matricula_aluno_existente(unidade_id, aluno_id, id_disciplina, valor, dia_venc, just):
    """
    Adiciona uma nova matéria para um aluno que já existe.
    Gera a matrícula E a cobrança do mês atual.
    """
    conn = conectar()
    try:
        # Helper de data
        def get_valid_date(y, m, d):
            try: return date(y, m, d)
            except: return date(y, m + 1, 1) - pd.Timedelta(days=1)

        hj = datetime.now()
        mes_cob = hj.month if hj.day <= 20 else hj.month + 1
        ano_cob = hj.year
        if mes_cob > 12: mes_cob=1; ano_cob+=1
        
        mes_ref = f"{mes_cob:02d}/{ano_cob}"
        dt_venc = get_valid_date(ano_cob, mes_cob, dia_venc)

        with conn:
            # 1. Matrícula
            cur = conn.execute("""
                INSERT INTO matriculas (unidade_id, aluno_id, id_disciplina, valor_acordado, dia_vencimento, justificativa_desconto, data_inicio, ativo) 
                VALUES (?,?,?,?,?,?,DATE('now'),1)
            """, (unidade_id, aluno_id, id_disciplina, db.to_cents(valor), dia_venc, just))
            mid = cur.lastrowid
            
            # 2. Financeiro
            conn.execute("""
                INSERT INTO pagamentos (unidade_id, matricula_id, aluno_id, mes_referencia, data_vencimento, valor_pago, id_status, id_tipo) 
                VALUES (?,?,?,?,?,?, 1, 1)
            """, (unidade_id, mid, aluno_id, mes_ref, dt_venc, db.to_cents(valor)))
    except Exception as e:
        raise e
    finally:
        conn.close()

def aplicar_bolsa_desconto(matricula_id, meses_duracao, unidade_id):
    """
    Aplica bolsa de 50% na matrícula E atualiza o boleto pendente atual se houver.
    """
    conn = conectar()
    try:
        with conn:
            # 1. Atualiza Matrícula
            conn.execute("""
                UPDATE matriculas 
                SET bolsa_ativa=1, bolsa_meses_restantes=? 
                WHERE id=?
            """, (meses_duracao, matricula_id))
            
            # 2. Atualiza Boleto Pendente (Aplica 50% no valor atual)
            # Nota: O SQL calcula direto: valor_pago * 0.5
            conn.execute("""
                UPDATE pagamentos 
                SET valor_pago = valor_pago * 0.5 
                WHERE matricula_id=? AND id_status=1 AND unidade_id=?
            """, (matricula_id, unidade_id))
    except Exception as e:
        raise e
    finally:
        conn.close()

def inativar_matricula(matricula_id):
    """Desativa uma disciplina específica e define data fim."""
    conn = conectar()
    try:
        with conn:
            conn.execute("UPDATE matriculas SET ativo=0, data_fim=DATE('now') WHERE id=?", (matricula_id,))
    except Exception as e:
        raise e
    finally:
        conn.close()

def inativar_aluno_completo(aluno_id):
    """Desativa TODAS as matrículas do aluno."""
    conn = conectar()
    try:
        with conn:
            conn.execute("UPDATE matriculas SET ativo=0, data_fim=DATE('now') WHERE aluno_id=?", (aluno_id,))
    except Exception as e:
        raise e
    finally:
        conn.close()

def buscar_historico_financeiro_aluno(aluno_id, unidade_id):
    """Retorna DataFrame de pagamentos do aluno."""
    # conn = conectar()
    # try:
    #     return pd.read_sql_query("""
    #         SELECT p.mes_referencia, p.valor_pago, s.nome as status, t.nome as tipo 
    #         FROM pagamentos p
    #         JOIN status_pagamentos s ON p.id_status = s.id
    #         JOIN tipos_pagamento t ON p.id_tipo = t.id
    #         WHERE p.aluno_id=? AND p.unidade_id=? 
    #         ORDER BY p.id DESC
    #     """, conn, params=(aluno_id, unidade_id))
    # finally:
    #     conn.close()
    conn = conectar()
    try:
        query = """
            SELECT p.mes_referencia, p.valor_pago, s.nome as status, t.nome as tipo 
             FROM pagamentos p
             JOIN status_pagamentos s ON p.id_status = s.id
             JOIN tipos_pagamento t ON p.id_tipo = t.id
             WHERE p.aluno_id=? AND p.unidade_id=? 
             ORDER BY p.id DESC
        """
        params = [aluno_id, unidade_id]
        
        return pd.read_sql(query, conn, params=params)
    finally:
        conn.close()



def buscar_binario_contrato(unidade_id):
    """Retorna o arquivo .docx template salvo no banco."""
    conn = conectar()
    try:
        row = conn.execute("SELECT arquivo_binario FROM docs_templates WHERE unidade_id=? AND tipo='CONTRATO'", (unidade_id,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()

def buscar_dados_para_doc_word(aluno_id, unidade_id):
    """
    Retorna um dicionário com dados do aluno e da matrícula mais recente
    para preencher o contrato automaticamente.
    """
    conn = conectar()
    try:
        # Busca Aluno
        aluno = conn.execute("SELECT nome, responsavel_nome, cpf_responsavel FROM alunos WHERE id=?", (aluno_id,)).fetchone()
        # Busca Matrícula Recente (Pega a primeira ativa ou última criada)
        mat = conn.execute("""
            SELECT valor_acordado, dia_vencimento 
            FROM matriculas 
            WHERE aluno_id=? AND unidade_id=? 
            ORDER BY ativo DESC, id DESC LIMIT 1
        """, (aluno_id, unidade_id)).fetchone()
        
        # Busca Taxa (Parâmetros)
        param = conn.execute("SELECT valor_taxa_matricula FROM parametros WHERE unidade_id=?", (unidade_id,)).fetchone()
        
        return {
            'aluno': aluno,
            'matricula': mat,
            'taxa': db.from_cents(param[0]) if param else 0
        }
    finally:
        conn.close()

# No arquivo repositories/alunos_rps.py

def listar_alunos_grid(unidade_id: int, termo: str = "", filtro_status: str = "Ativos"):
    """
    Busca alunos otimizada para Dataframe com cálculo de status.
    filtro_status: "Ativos", "Inativos", "Todos"
    """
    conn = conectar()
    try:
        # 1. Base da Query: Trazemos o status calculado com base na existência de matrículas ativas
        # O CASE WHEN verifica se existe pelo menos uma matrícula com ativo=1 para aquele aluno
        sql = """
            SELECT 
                a.id, 
                CASE 
                    WHEN EXISTS (SELECT 1 FROM matriculas m WHERE m.aluno_id = a.id AND m.ativo = 1) THEN 'Ativo' 
                    ELSE 'Inativo' 
                END as status,
                a.nome, 
                a.responsavel_nome,
                a.cpf_responsavel
            FROM alunos a
            WHERE a.unidade_id = ?
        """
        params = [unidade_id]

        # 2. Aplica Filtro de Texto (Nome ou CPF)
        if termo:
            sql += " AND (a.nome LIKE ? OR a.cpf_responsavel LIKE ?)"
            termo_like = f"%{termo}%"
            params.extend([termo_like, termo_like])

        # 3. Ordenação (Ativos primeiro, depois ordem alfabética)
        sql += " ORDER BY status ASC, a.nome ASC"

        # Carrega no Pandas
        df = pd.read_sql_query(sql, conn, params=params)

        # 4. Filtragem do DataFrame (Mais prático fazer no Pandas do que complicar o SQL dinâmico agora)
        if filtro_status == "Ativos":
            df = df[df['status'] == 'Ativo']
        elif filtro_status == "Inativos":
            df = df[df['status'] == 'Inativo']
        
        return df

    finally:
        conn.close()

# No arquivo repositories/alunos_rps.py

def atualizar_valor_matricula(matricula_id: int, novo_valor: float, unidade_id: int):
    """
    Atualiza o valor acordado da matrícula e recalcula a mensalidade pendente (se houver).
    """
    conn = conectar()
    try:
        with conn:
            # 1. Atualiza o valor base na matrícula
            valor_cents = db.to_cents(novo_valor)
            conn.execute("UPDATE matriculas SET valor_acordado=? WHERE id=?", (valor_cents, matricula_id))
            
            # 2. Verifica se tem bolsa ativa para calcular o valor líquido correto
            row = conn.execute("SELECT bolsa_ativa FROM matriculas WHERE id=?", (matricula_id,)).fetchone()
            tem_bolsa = row[0] if row else 0
            
            # Se tiver bolsa, aplica os 50% (regra do seu sistema)
            novo_valor_final = valor_cents
            if tem_bolsa:
                novo_valor_final = int(valor_cents * 0.5)
            
            # 3. Atualiza apenas boletos PENDENTES (id_status=1) desta matrícula
            # Isso garante que o boleto deste mês já venha com o valor corrigido
            conn.execute("""
                UPDATE pagamentos 
                SET valor_pago=? 
                WHERE matricula_id=? AND id_status=1 AND unidade_id=?
            """, (novo_valor_final, matricula_id, unidade_id))
            
    except Exception as e:
        raise e
    finally:
        conn.close()