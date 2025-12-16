# import sqlite3
from typing import Dict, Tuple, List, Any, Optional
from conectDB.conexao import conectar
import pandas as pd
from datetime import date, datetime
from calendar import monthrange
import database as db


def realizar_matricula_completa(unidade_id, dados_aluno, lista_disciplinas, dia_vencimento, valor_taxa, campanha_ativa, data_matricula_dt):
    """
    Realiza todo o processo de matrícula em uma única transação atômica.
    - Cria Aluno
    - Cria Matrículas
    - Gera 1ª Mensalidade
    - Gera Taxa de Matrícula (se houver)
    
    Realiza a matrícula considerando a data de referência para cálculo do pro-rata.
    Regras:
    - 01 a 10: 100% valor (Mês Atual)
    - 11 a 20: 50% valor (Mês Atual)
    - 21 a 31: 100% valor (Próximo Mês)
    """
    conn = conectar()
    try:
        # Helper simples para garantir dia útil (pula fds)
        def _proximo_dia_util(d):
            wd = d.weekday() # 5=Sábado, 6=Domingo
            if wd == 5: return d + pd.Timedelta(days=2)
            if wd == 6: return d + pd.Timedelta(days=1)
            return d

        # 1. Definição do Cenário Financeiro
        dia_ref = data_matricula_dt.day
        mes_ref = data_matricula_dt.month
        ano_ref = data_matricula_dt.year
        
        fator_pagamento = 1.0 # 100%
        
        # Data base do vencimento (no mês da matrícula)
        # Tenta criar a data, se dia 31 não existir em Fev, ajusta.
        try:
            dt_venc_base = date(ano_ref, mes_ref, dia_vencimento)
        except ValueError:
             # Pega o último dia do mês se o dia escolhido não existir (ex: 30 de fev)
            max_day = monthrange(ano_ref, mes_ref)[1]
            dt_venc_base = date(ano_ref, mes_ref, max_day)

        # LÓGICA DAS 3 FAIXAS
        if 21 <= dia_ref <= 31:
            # Cenário 3: Joga para o próximo mês
            dt_venc_real = dt_venc_base + pd.DateOffset(months=1)
            # Recalcula string MM/YYYY
            mes_str = dt_venc_real.strftime("%m/%Y")
            # Fator continua 1.0
            
        elif 11 <= dia_ref <= 20:
            # Cenário 2: Mês atual, 50%
            fator_pagamento = 0.5
            mes_str = data_matricula_dt.strftime("%m/%Y")
            
            # Se o dia do vencimento já passou em relação à data da matrícula
            if dt_venc_base < data_matricula_dt:
                # Vence no dia seguinte da matrícula (ou próximo útil)
                dt_venc_real = _proximo_dia_util(data_matricula_dt + pd.Timedelta(days=1))
            else:
                dt_venc_real = _proximo_dia_util(dt_venc_base)
                
        else: # 01 a 10
            # Cenário 1: Mês atual, 100%
            fator_pagamento = 1.0
            mes_str = data_matricula_dt.strftime("%m/%Y")
            
            if dt_venc_base < data_matricula_dt:
                dt_venc_real = _proximo_dia_util(data_matricula_dt + pd.Timedelta(days=1))
            else:
                dt_venc_real = _proximo_dia_util(dt_venc_base)

        # ---------------------------------------------------------

        with conn: # INÍCIO DA TRANSAÇÃO
            # 1. Cria Aluno (Usando a data de matrícula informada, não 'now')
            cur = conn.execute("""
                INSERT INTO alunos (unidade_id, nome, responsavel_nome, cpf_responsavel, id_canal_aquisicao, data_cadastro)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (unidade_id, dados_aluno['nome'], dados_aluno['responsavel'], dados_aluno['cpf'], dados_aluno['id_canal'], data_matricula_dt))
            aid = cur.lastrowid
            
            # 2. Processa Disciplinas
            for item in lista_disciplinas:
                valor_cheio_cents = db.to_cents(item['val'])
                
                # Cria Matrícula
                cur.execute("""
                    INSERT INTO matriculas (unidade_id, aluno_id, id_disciplina, valor_acordado, dia_vencimento, justificativa_desconto, data_inicio, ativo) 
                    VALUES (?,?,?,?,?,?,?,1)
                """, (unidade_id, aid, item['id_disc'], valor_cheio_cents, dia_vencimento, item['just'], data_matricula_dt))
                mid = cur.lastrowid
                
                # Gera 1ª Mensalidade (Com fator aplicado)
                valor_primeira_parc = int(valor_cheio_cents * fator_pagamento)
                
                cur.execute("""
                    INSERT INTO pagamentos (unidade_id, matricula_id, aluno_id, mes_referencia, data_vencimento, valor_pago, id_status, id_tipo) 
                    VALUES (?,?,?,?,?,?, 1, 1)
                """, (unidade_id, mid, aid, mes_str, dt_venc_real, valor_primeira_parc))
            
            # 3. Taxa de Matrícula (Essa geralmente não tem desconto pro-rata, segue cheia)
            if not campanha_ativa and valor_taxa > 0:
                # Vence junto com a primeira mensalidade para facilitar
                dt_tx = dt_venc_real 
                mes_ref_tx = mes_str
                
                conn.execute("""
                    INSERT INTO pagamentos (unidade_id, aluno_id, mes_referencia, data_vencimento, valor_pago, id_status, id_tipo) 
                    VALUES (?,?,?,?,?, 1, 2)
                """, (unidade_id, aid, mes_ref_tx, dt_tx, db.to_cents(valor_taxa)))
                
    except Exception as e:
        raise e
    finally:
        conn.close()


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

    conn = conectar()
    try:
        query = """
            SELECT p.mes_referencia, data_vencimento, p.valor_pago, s.nome as status, t.nome as tipo 
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