"""
Improved database module for the Kumon system.
Goals:
- Keep existing public API (function names and signatures) so front-end doesn't need to change.
- Improve safety: consistent connection handling, transactions, input validation, logging.
- Preserve backwards compatibility for password verification (existing sha256 hashes), but recommend migration to bcrypt.
- Add small helpers to reduce repetition and to make code easier to test.
"""

import sqlite3
import hashlib
import logging
from datetime import date, datetime
from calendar import monthrange
from typing import Dict, Tuple, List, Any, Optional
import pandas as pd

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


# --- 2. CONEXÃO ---
DB_PATH = 'kumon.db'
_DEFAULT_TIMEOUT = 10

def conectar() -> sqlite3.Connection:
    """Retorna uma nova conexão SQLite configurada com segurança para uso em app web (check_same_thread=False).
    A função preserva a API original (retorna sqlite3.Connection).
    """
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=_DEFAULT_TIMEOUT)
    # Usar row factory facilita leitura por nome em alguns pontos
    conn.row_factory = sqlite3.Row
    return conn


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
    """Verifica credenciais. Compatível com hashes SHA256 existentes.
    Retorna (ok, nome_completo, is_admin).
    OBS: recomendamos migrar para bcrypt/argon2; esta função mantém compatibilidade com SHA256.
    """
    conn = conectar()
    try:
        senha_hash = hashlib.sha256(senha_digitada.encode()).hexdigest()
        row = conn.execute("SELECT nome_completo, admin, password_hash FROM usuarios WHERE username = ? AND ativo=1", (usuario,)).fetchone()
        if not row:
            return False, None, False

        stored = row['password_hash']
        # Se o stored for um algoritmo diferente no futuro, adapte aqui
        if stored == senha_hash:
            return True, row['nome_completo'], bool(row['admin'])

        # Se quiser implementar troca incremental: verificar outros esquemas aqui (ex: bcrypt)
        return False, None, False
    finally:
        conn.close()


def get_unidades_usuario(usuario: str) -> List[Tuple[int, str]]:
    conn = conectar()
    try:
        rows = conn.execute(
            'SELECT u.id AS id, u.nome AS nome FROM unidades u JOIN usuario_unidades uu ON u.id = uu.unidade_id WHERE uu.usuario_username = ? ORDER BY u.id',
            (usuario,)
        ).fetchall()
        return [(r['id'], r['nome']) for r in rows]
    finally:
        conn.close()


def get_parametros_unidade(unidade_id: int) -> Dict[str, Any]:
    conn = conectar()
    try:
        row = conn.execute("SELECT em_campanha_matricula, valor_taxa_matricula, valor_mensalidade_padrao FROM parametros WHERE unidade_id=?", (unidade_id,)).fetchone()
        if not row:
            return {"campanha": False, "taxa_matr": 0, "mensalidade": 0}
        return {"campanha": bool(row[0]), "taxa_matr": from_cents(row[1]), "mensalidade": from_cents(row[2])}
    finally:
        conn.close()


def get_parametros_unidade(unidade_id):
    """
    Busca as configurações globais da unidade (mensalidade padrão, taxa, campanha).
    Retorna um dicionário.
    """
    conn = conectar()
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
                INSERT INTO alunos (unidade_id, nome, responsavel_nome, cpf_responsavel, canal_aquisicao) 
                VALUES (?, ?, ?, ?, ?)
            """, (unidade_id, dados_aluno['nome'], dados_aluno['responsavel'], dados_aluno['cpf'], dados_aluno['canal']))
            aid = cur.lastrowid
            
            # 2. Processa Disciplinas
            for item in lista_disciplinas:
                # Cria Matrícula
                cur.execute("""
                    INSERT INTO matriculas (unidade_id, aluno_id, disciplina, valor_acordado, dia_vencimento, justificativa_desconto, data_inicio, ativo) 
                    VALUES (?,?,?,?,?,?,DATE('now'),1)
                """, (unidade_id, aid, item['disc'], to_cents(item['val']), dia_vencimento, item['just']))
                mid = cur.lastrowid
                
                # Gera 1ª Mensalidade
                cur.execute("""
                    INSERT INTO pagamentos (unidade_id, matricula_id, aluno_id, mes_referencia, data_vencimento, valor_pago, status, tipo) 
                    VALUES (?,?,?,?,?,?, 'PENDENTE', 'MENSALIDADE')
                """, (unidade_id, mid, aid, mes_ref, dt_venc_mensal, to_cents(item['val'])))
            
            # 3. Taxa de Matrícula (Se não for isento/campanha)
            if not campanha_ativa and valor_taxa > 0:
                dt_tx = date.today() + pd.Timedelta(days=1) # Vence amanhã
                mes_ref_tx = dt_tx.strftime("%m/%Y")
                
                conn.execute("""
                    INSERT INTO pagamentos (unidade_id, aluno_id, mes_referencia, data_vencimento, valor_pago, status, tipo) 
                    VALUES (?,?,?,?,?, 'PENDENTE', 'TAXA_MATRICULA')
                """, (unidade_id, aid, mes_ref_tx, dt_tx, to_cents(valor_taxa)))
                
    except Exception as e:
        raise e
    finally:
        conn.close()


def atualizar_aluno(aluno_id: int, nome: str, responsavel: str, cpf: str, canal: str) -> None:
    conn = conectar()
    try:
        with conn:
            conn.execute("""
                UPDATE alunos 
                SET nome=?, responsavel_nome=?, cpf_responsavel=?, canal_aquisicao=? 
                WHERE id=?
            """, (nome, responsavel, cpf, canal, aluno_id))
    finally:
        conn.close()

# --- GESTÃO DE ALUNOS E MATRÍCULAS ---

def buscar_alunos_por_nome(unidade_id, termo_busca=""):
    """
    Busca alunos para o seletor. Se termo_busca vazio, traz últimos 50.
    """
    conn = conectar()
    try:
        if termo_busca:
            query = "SELECT id, nome FROM alunos WHERE unidade_id=? AND nome LIKE ? ORDER BY nome LIMIT 50"
            return pd.read_sql_query(query, conn, params=(unidade_id, f"%{termo_busca}%"))
        else:
            query = "SELECT id, nome FROM alunos WHERE unidade_id=? ORDER BY id DESC LIMIT 50"
            return pd.read_sql_query(query, conn, params=(unidade_id,))
    finally:
        conn.close()

def buscar_dados_aluno_completo(aluno_id):
    """Retorna dados cadastrais do aluno."""
    conn = conectar()
    try:
        return conn.execute("SELECT * FROM alunos WHERE id=?", (aluno_id,)).fetchone()
    finally:
        conn.close()

def atualizar_dados_aluno(aluno_id, nome, resp, cpf, canal):
    """Atualiza cadastro básico."""
    conn = conectar()
    try:
        with conn:
            conn.execute("""
                UPDATE alunos SET nome=?, responsavel_nome=?, cpf_responsavel=?, canal_aquisicao=? 
                WHERE id=?
            """, (nome, resp, cpf, canal, aluno_id))
    except Exception as e:
        raise e
    finally:
        conn.close()

def buscar_matriculas_aluno(aluno_id, unidade_id):
    """Retorna lista de matrículas (disciplinas) do aluno."""
    conn = conectar()
    try:
        return conn.execute("""
            SELECT id, disciplina, valor_acordado, dia_vencimento, ativo, bolsa_ativa, bolsa_meses_restantes 
            FROM matriculas WHERE aluno_id=? AND unidade_id=?
        """, (aluno_id, unidade_id)).fetchall()
    finally:
        conn.close()

def adicionar_nova_matricula_aluno_existente(unidade_id, aluno_id, disciplina, valor, dia_venc, just):
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
                INSERT INTO matriculas (unidade_id, aluno_id, disciplina, valor_acordado, dia_vencimento, justificativa_desconto, data_inicio, ativo) 
                VALUES (?,?,?,?,?,?,DATE('now'),1)
            """, (unidade_id, aluno_id, disciplina, to_cents(valor), dia_venc, just))
            mid = cur.lastrowid
            
            # 2. Financeiro
            conn.execute("""
                INSERT INTO pagamentos (unidade_id, matricula_id, aluno_id, mes_referencia, data_vencimento, valor_pago, status, tipo) 
                VALUES (?,?,?,?,?,?, 'PENDENTE', 'MENSALIDADE')
            """, (unidade_id, mid, aluno_id, mes_ref, dt_venc, to_cents(valor)))
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
                WHERE matricula_id=? AND status='PENDENTE' AND unidade_id=?
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
        return pd.read_sql_query("""
            SELECT mes_referencia, valor_pago, status, tipo 
            FROM pagamentos 
            WHERE aluno_id=? AND unidade_id=? 
            ORDER BY id DESC
        """, conn, params=(aluno_id, unidade_id))
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
            'taxa': from_cents(param[0]) if param else 0
        }
    finally:
        conn.close()

def buscar_recebimentos_pendentes(unidade_id: int, filtro_mes: Optional[str]=None) -> pd.DataFrame:
    conn = conectar()
    try:
        query = """
            SELECT p.id, p.data_vencimento, a.nome, m.disciplina, p.valor_pago 
            FROM pagamentos p 
            LEFT JOIN matriculas m ON p.matricula_id=m.id 
            JOIN alunos a ON COALESCE(p.aluno_id, m.aluno_id)=a.id 
            WHERE p.status='PENDENTE' AND p.unidade_id=?
        """
        params = [unidade_id]
        if filtro_mes and filtro_mes != "Todos": 
            query += " AND p.mes_referencia=?"
            params.append(filtro_mes)
        query += " ORDER BY p.data_vencimento"
        return pd.read_sql(query, conn, params=params)
    finally:
        conn.close()


def registrar_recebimento(unidade_id: int, pagamento_id: int, forma: str, taxa: float, nome_aluno: str) -> None:

    taxa_cents = to_cents(taxa)

    conn = conectar()
    try:
        with conn:
            hoje = date.today()
            # Atualiza pagamento
            conn.execute("""
                UPDATE pagamentos 
                SET status='PAGO', data_pagamento=?, forma_pagamento=? 
                WHERE id=?
            """, (hoje, forma, pagamento_id))
            # Lança despesa de taxa, se aplicável
            if taxa_cents > 0:
                mes_ref = hoje.strftime("%m/%Y")
                desc_despesa = f"({forma}) - {nome_aluno}"
                
                # CORREÇÃO: Usar id_categoria (3 = Taxas Financeiras)
                # Se não tiver a cat 3, troque por 2 (Impostos)
                ID_CAT_TAXAS = 3 
                
                conn.execute("""
                    INSERT INTO despesas 
                    (unidade_id, id_categoria, descricao, valor, data_vencimento, mes_referencia, data_pagamento, status) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'PAGO')
                """, (unidade_id, ID_CAT_TAXAS, desc_despesa, taxa_cents, hoje, mes_ref, hoje))
    finally:
        conn.close()


def buscar_despesas_pendentes(unidade_id: int, filtro_mes: Optional[str]=None) -> pd.DataFrame:
    conn = conectar()
    try:
        query = """
            SELECT d.id, d.data_vencimento, d.id_categoria, c.nome_categoria, descricao, valor 
            FROM despesas d
            INNER JOIN categorias_despesas c ON (c.id = d.id_categoria)
            WHERE status='PENDENTE' AND unidade_id=?
        """
        params = [unidade_id]
        if filtro_mes and filtro_mes != "Todos":
            query += " AND mes_referencia=?"
            params.append(filtro_mes)
        query += " ORDER BY data_vencimento"
        return pd.read_sql(query, conn, params=params)
    finally:
        conn.close()


def pagar_despesa(despesa_id: int) -> None:
    conn = conectar()
    try:
        with conn:
            conn.execute("UPDATE despesas SET status='PAGO', data_pagamento=DATE('now') WHERE id=?", (despesa_id,))
    finally:
        conn.close()


def estornar_operacao(id_item: int, tipo_item: str) -> None:
    conn = conectar()
    try:
        with conn:
            if tipo_item == 'Entrada':
                conn.execute("""
                    UPDATE pagamentos 
                    SET status='PENDENTE', data_pagamento=NULL, forma_pagamento=NULL 
                    WHERE id=?
                """, (id_item,))
            else:
                conn.execute("""
                    UPDATE despesas 
                    SET status='PENDENTE', data_pagamento=NULL 
                    WHERE id=?
                """, (id_item,))
    finally:
        conn.close()


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
        target = hj if hj.day < 21 else (hj + pd.DateOffset(days=32))
        m_ref_boletos = target.strftime("%m/%Y")

        with conn:
            regras = conn.execute("""
                                    SELECT d.id, c.nome_categoria, d.id_categoria, descricao, valor, dia_vencimento 
                                        FROM despesas_recorrentes d
                                        INNER JOIN categorias_despesas c ON (c.id = d.id_categoria)
                                        WHERE ativo=1 AND unidade_id=?""", (unidade_id,)).fetchall()
            for r in regras:
                rid, cat, desc, val, dia = r['id'], r['id_categoria'], r['descricao'], r['valor'], r['dia_vencimento']
                existe = conn.execute("SELECT id FROM despesas WHERE recorrente_id=? AND mes_referencia=? AND unidade_id=?", (rid, mes_str, unidade_id)).fetchone()
                if not existe:
                    conn.execute("""
                        INSERT INTO despesas (unidade_id, recorrente_id, categoria, descricao, valor, data_vencimento, mes_referencia, status) 
                        VALUES (?,?,?,?,?,?,?, 'PENDENTE')
                    """, (unidade_id, rid, cat, desc, to_cents(val), _get_valid_date_local(hj.year, hj.month, dia), mes_str))
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
                        conn.execute("UPDATE matriculas SET bolsa_meses_restantes=?, bolsa_ativa=? WHERE id=?", (to_cents(novo_saldo), novo_status, mid))
                    conn.execute("""
                        INSERT INTO pagamentos (unidade_id, matricula_id, aluno_id, mes_referencia, data_vencimento, valor_pago, status) 
                        VALUES (?,?,?,?,?,?,'PENDENTE')
                    """, (unidade_id, mid, aid, m_ref_boletos, _get_valid_date_local(target.year, target.month, dia), to_cents(valor_final)))
                    cnt_r += 1

            funcs = conn.execute("SELECT id, nome, salario_base, dia_pagamento_salario FROM funcionarios WHERE ativo=1 AND unidade_id=?", (unidade_id,)).fetchall()
            for f in funcs:
                fid = f['id']; fnome = f['nome']; fsal = f['salario_base']; fdia = f['dia_pagamento_salario']
                desc_sal = f"Salário - {fnome}"
                if fsal and fsal > 0:
                    existe_sal = conn.execute("SELECT id FROM despesas WHERE descricao=? AND mes_referencia=? AND unidade_id=?", (desc_sal, mes_str, unidade_id)).fetchone()
                    if not existe_sal:
                        conn.execute("""
                            INSERT INTO despesas (unidade_id, categoria, descricao, valor, data_vencimento, mes_referencia, status) 
                            VALUES (?, 'Pessoal', ?, ?, ?, ?, 'PENDENTE')
                        """, (unidade_id, desc_sal, fsal, _get_valid_date_local(hj.year, hj.month, fdia), mes_str))
                        cnt_p += 1

                custos = conn.execute("SELECT tipo_item, nome_item, valor, dia_vencimento FROM custos_pessoal WHERE funcionario_id=?", (fid,)).fetchall()
                for c in custos:
                    ctipo = c['tipo_item']; cnome = c['nome_item']; cval = c['valor']; cdia = c['dia_vencimento']
                    desc_item = f"{cnome} - {fnome}"
                    cat = "Impostos" if ctipo == "IMPOSTO" else "Pessoal"
                    if cval and cval > 0:
                        existe_custo = conn.execute("SELECT id FROM despesas WHERE descricao=? AND mes_referencia=? AND unidade_id=?", (desc_item, mes_str, unidade_id)).fetchone()
                        if not existe_custo:
                            conn.execute("""
                                INSERT INTO despesas (unidade_id, categoria, descricao, valor, data_vencimento, mes_referencia, status) 
                                VALUES (?, ?, ?, ?, ?, ?, 'PENDENTE')
                            """, (unidade_id, cat, desc_item, to_cents(cval), _get_valid_date_local(hj.year, hj.month, cdia), mes_str))
                            cnt_p += 1
        return cnt_d, cnt_r, cnt_p
    finally:
        conn.close()


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


def buscar_fluxo_caixa(unidade_id: int, mes_referencia: str) -> pd.DataFrame:
    conn = conectar()
    try:
        q_rec = '''
            SELECT p.id, p.data_pagamento, 'Entrada' as Tipo, p.valor_pago, p.forma_pagamento, 
            a.nome || ' - ' || COALESCE(m.disciplina, 'Taxa') as Descricao 
            FROM pagamentos p 
            LEFT JOIN matriculas m ON p.matricula_id = m.id 
            JOIN alunos a ON COALESCE(p.aluno_id, m.aluno_id) = a.id 
            WHERE p.status='PAGO' AND p.unidade_id=? AND p.mes_referencia=?
        '''
        q_des = '''
            SELECT d.id, d.data_pagamento, 'Saída' as Tipo, d.valor as valor_pago, '' as forma_pagamento, 
            c.nome_categoria || ' - ' || d.descricao as Descricao 
            FROM despesas d 
            INNER JOIN categorias_despesas c ON (c.id = d.id_categoria)
            WHERE d.status='PAGO' AND d.unidade_id=? AND d.mes_referencia=?
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


def adicionar_royalty(unidade_id: int, valor: float, inicio: str) -> None:
    conn = conectar()
    try:
        with conn:
            conn.execute("INSERT INTO config_royalties (unidade_id, valor, ano_mes_inicio) VALUES (?, ?, ?)", (unidade_id, to_cents(valor), inicio))
    finally:
        conn.close()


def excluir_royalty(id_regra: int) -> None:
    conn = conectar()
    try:
        with conn:
            conn.execute("DELETE FROM config_royalties WHERE id=?", (id_regra,))
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
    
    valor_cents = to_cents(valor)

    conn = conectar()
    try:
        with conn:
            conn.execute('''
                UPDATE despesas_recorrentes 
                SET id_categoria=?, descricao=?, valor=?, dia_vencimento=?, ativo=? 
                WHERE id=?
            ''', (categoria, descricao, valor_cents, dia, _bool_to_int(ativo), id_rec))
            if ativo:
                conn.execute('''
                    UPDATE despesas 
                    SET valor=?, descricao=?, id_categoria=? 
                    WHERE recorrente_id=? AND status='PENDENTE' AND unidade_id=?
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


def adicionar_despesa_avulsa(unidade_id: int, categoria: str, descricao: str, valor: float, data_vencimento: date) -> None:

    valor_cents = to_cents(valor)

    conn = conectar()
    try:
        with conn:
            mes_ref = data_vencimento.strftime("%m/%Y")
            conn.execute('''
                INSERT INTO despesas (unidade_id, id_categoria, descricao, valor, data_vencimento, mes_referencia, status) 
                VALUES (?, ?, ?, ?, ?, ?, 'PENDENTE')
            ''', (unidade_id, categoria, descricao, valor_cents, data_vencimento, mes_ref))
    finally:
        conn.close()


def adicionar_despesa_recorrente(unidade_id: int, categoria: str, descricao: str, valor: int, dia_vencimento: int) -> None:

    valor_cents = to_cents(valor)

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
            dt_venc_atual = _get_valid_date(hj.year, hj.month, dia_vencimento)
            conn.execute('''
                INSERT INTO despesas (unidade_id, recorrente_id, id_categoria, descricao, valor, data_vencimento, mes_referencia, status) 
                VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDENTE')
            ''', (unidade_id, rid, categoria, descricao, valor_cents, dt_venc_atual, m_ref))
    finally:
        conn.close()


def buscar_dados_financeiros_anuais(unidade_id: int, ano: int) -> pd.DataFrame:
    conn = conectar()
    try:
        termo_busca = f"%{ano}"
        query = """
            SELECT mes_referencia, tipo, SUM(total) as total FROM (
                SELECT mes_referencia, 'Receita' as tipo, valor_pago as total FROM pagamentos WHERE unidade_id=? AND mes_referencia LIKE ? AND status='PAGO'
                UNION ALL
                SELECT mes_referencia, 'Despesa' as tipo, valor as total FROM despesas WHERE unidade_id=? AND mes_referencia LIKE ? AND status='PAGO'
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
            WHERE unidade_id=? AND mes_referencia LIKE ? AND status='PAGO'
            GROUP BY c.nome_categoria
        """
        return pd.read_sql_query(query, conn, params=(unidade_id, termo))
    finally:
        conn.close()


def buscar_distribuicao_matriculas(unidade_id: int) -> pd.DataFrame:
    conn = conectar()
    try:
        query = """
            SELECT disciplina, COUNT(*) as qtd 
            FROM matriculas 
            WHERE ativo=1 AND unidade_id=? 
            GROUP BY disciplina
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
                SUM(CASE WHEN status='PENDENTE' AND data_vencimento < DATE('now') THEN valor_pago ELSE 0 END) as valor_atrasado
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
            AND status='PAGO'
        """
        resultado = conn.execute(query, (unidade_id, termo)).fetchone()[0]
        return from_cents(resultado) if resultado else 0
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
                """, (to_cents(valor), cofre_id, unidade_id))
                if cur.rowcount == 0:
                    raise ValueError(f"Cofre {cofre_id} não existe para a unidade {unidade_id}")
                conn.execute("""
                    INSERT INTO cofres_movimentacao 
                    (unidade_id, cofre_id, data_movimentacao, valor, tipo, descricao) 
                    VALUES (?, ?, ?, ?, 'ENTRADA', 'Distribuição de Lucro')
                """, (unidade_id, cofre_id, hoje, to_cents(valor)))
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
            """, (to_cents(valor), cofre_id, unidade_id))
            if cur.rowcount == 0:
                raise ValueError("Cofre não encontrado ou relação com unidade incorreta.")
            conn.execute("""
                INSERT INTO cofres_movimentacao 
                (unidade_id, cofre_id, data_movimentacao, valor, tipo, descricao) 
                VALUES (?, ?, DATE('now'), ?, 'SAIDA', ?)
            """, (unidade_id, cofre_id, to_cents(valor), motivo))
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
        rec = conn.execute("SELECT SUM(valor_pago) as total FROM pagamentos WHERE mes_referencia=? AND status='PAGO' AND unidade_id=?", (mes_referencia, unidade_id)).fetchone()['total'] or 0.0
        des = conn.execute("SELECT SUM(valor) as total FROM despesas WHERE mes_referencia=? AND status='PAGO' AND unidade_id=?", (mes_referencia, unidade_id)).fetchone()['total'] or 0.0
        lucro = from_cents(rec) - from_cents(des)
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

def buscar_bolsas_ativas(unidade_id):
    """
    Retorna um DataFrame com todos os alunos que possuem bolsa ativa na unidade.
    Traz: Nome, Disciplina, Valor Original e Meses Restantes.
    """
    conn = conectar()
    try:
        query = '''
            SELECT 
                a.nome, 
                m.disciplina, 
                m.valor_acordado as valor_original,
                m.bolsa_meses_restantes
            FROM matriculas m
            JOIN alunos a ON m.aluno_id = a.id
            WHERE m.unidade_id = ? AND m.bolsa_ativa = 1 AND m.ativo = 1
            ORDER BY m.bolsa_meses_restantes ASC
        '''
        return pd.read_sql_query(query, conn, params=(unidade_id,))
    finally:
        conn.close()

def buscar_lista_alunos_periodo(unidade_id, data_inicio, data_fim):
    """
    Busca alunos que tiveram matrícula ativa em algum momento dentro do período informado.
    Regra: Data Início da matrícula <= Fim do Mês E (Ativo ou Data Fim >= Início do Mês).
    """
    conn = conectar()
    try:
        query = '''
            SELECT 
                a.nome as Aluno,
                m.disciplina as Disciplina
            FROM matriculas m
            JOIN alunos a ON m.aluno_id = a.id
            WHERE m.unidade_id = ?
              AND a.nome IS NOT NULL 
              AND m.aluno_id IS NOT NULL
              AND m.data_inicio <= ? 
              AND (m.ativo = 1 OR m.data_fim >= ?)
            ORDER BY a.nome, m.disciplina
        '''
        return pd.read_sql_query(query, conn, params=(unidade_id, data_fim, data_inicio))
    finally:
        conn.close()

def buscar_todas_unidades():
    """
    Retorna lista de tuplas (id, nome) de todas as unidades cadastradas.
    """
    conn = conectar()
    try:
        return conn.execute("SELECT id, nome FROM unidades ORDER BY nome").fetchall()
    finally:
        conn.close()

def buscar_lista_usuarios():
    """
    Retorna DataFrame com dados básicos dos usuários para listagem.
    """
    conn = conectar()
    try:
        return pd.read_sql("SELECT username, nome_completo, admin, ativo FROM usuarios ORDER BY nome_completo", conn)
    finally:
        conn.close()

def buscar_ids_unidades_usuario(username):
    """
    Retorna uma lista de IDs das unidades que o usuário tem acesso.
    """
    conn = conectar()
    try:
        res = conn.execute("SELECT unidade_id FROM usuario_unidades WHERE usuario_username=?", (username,)).fetchall()
        return [r[0] for r in res]
    finally:
        conn.close()

def criar_usuario_completo(username, password_hash, nome, is_admin, lista_unidades_ids):
    """
    Cria o usuário e vincula as unidades em uma TRANSAÇÃO ÚNICA.
    """
    conn = conectar()
    try:
        with conn:
            # 1. Insere Usuário
            conn.execute("""
                INSERT INTO usuarios (username, password_hash, nome_completo, admin, ativo) 
                VALUES (?, ?, ?, ?, 1)
            """, (username, password_hash, nome, 1 if is_admin else 0))
            
            # 2. Vincula Unidades
            for uid in lista_unidades_ids:
                conn.execute("INSERT INTO usuario_unidades (usuario_username, unidade_id) VALUES (?,?)", (username, uid))
    except Exception as e:
        raise e
    finally:
        conn.close()

def atualizar_usuario_completo(username, nome, is_admin, is_ativo, lista_unidades_ids, nova_password_hash=None):
    """
    Atualiza dados, permissões e (opcionalmente) senha do usuário.
    Recria os vínculos de unidade de forma atômica.
    """
    conn = conectar()
    try:
        with conn:
            # 1. Atualiza Dados Básicos
            conn.execute("""
                UPDATE usuarios 
                SET nome_completo=?, admin=?, ativo=? 
                WHERE username=?
            """, (nome, 1 if is_admin else 0, 1 if is_ativo else 0, username))
            
            # 2. Atualiza Senha (Se fornecida)
            if nova_password_hash:
                conn.execute("UPDATE usuarios SET password_hash=? WHERE username=?", (nova_password_hash, username))
            
            # 3. Atualiza Unidades (Remove todas e recria)
            conn.execute("DELETE FROM usuario_unidades WHERE usuario_username=?", (username,))
            for uid in lista_unidades_ids:
                conn.execute("INSERT INTO usuario_unidades (usuario_username, unidade_id) VALUES (?,?)", (username, uid))
    except Exception as e:
        raise e
    finally:
        conn.close()

def cadastrar_funcionario_completo(unidade_id, nome, tipo, salario, dia_pag, lista_custos_iniciais):
    """
    Cadastra funcionário e seus custos iniciais em transação única.
    lista_custos_iniciais = [{tipo, nome, valor, dia}, ...]
    """
    conn = conectar()
    try:
        with conn:
            # 1. Funcionário
            cur = conn.execute('''
                INSERT INTO funcionarios (unidade_id, nome, tipo_contratacao, salario_base, data_contratacao, dia_pagamento_salario, ativo)
                VALUES (?, ?, ?, ?, DATE('now'), ?, 1)
            ''', (unidade_id, nome, tipo, to_cents(salario), dia_pag))
            fid = cur.lastrowid
            
            # 2. Custos
            for item in lista_custos_iniciais:
                conn.execute('''
                    INSERT INTO custos_pessoal (unidade_id, funcionario_id, tipo_item, nome_item, valor, dia_vencimento)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (unidade_id, fid, item['tipo'], item['nome'], to_cents(item['valor']), item['dia']))
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
        query = "SELECT id, nome, tipo_contratacao, salario_base, ativo FROM funcionarios WHERE unidade_id=?"
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
        return conn.execute("SELECT * FROM funcionarios WHERE id=?", (func_id,)).fetchone()
    finally:
        conn.close()

def atualizar_funcionario_completo(func_id, nome_novo, tipo, salario, dia, ativo, data_demissao, unidade_id, nome_antigo):
    """
    Atualiza cadastro E propaga alterações para o Financeiro (Salário e Benefícios Pendentes).
    """
    conn = conectar()
    try:
        with conn:
            # 1. Update Cadastro
            conn.execute('''
                UPDATE funcionarios 
                SET nome=?, tipo_contratacao=?, salario_base=?, dia_pagamento_salario=?, ativo=?, data_demissao=?
                WHERE id=?
            ''', (nome_novo, tipo, to_cents(salario), dia, 1 if ativo else 0, data_demissao, func_id))
            
            # 2. Propagação Financeira (Sincronizar Salário Pendente)
            desc_sal_antiga = f"Salário - {nome_antigo}"
            desc_sal_nova = f"Salário - {nome_novo}"
            
            # Atualiza valor e descrição da despesa de salário pendente
            conn.execute('''
                UPDATE despesas SET valor=?, descricao=? 
                WHERE descricao=? AND status='PENDENTE' AND unidade_id=?
            ''', (to_cents(salario), desc_sal_nova, desc_sal_antiga, unidade_id))

            # Atualiza nome nos benefícios pendentes (se mudou de nome)
            if nome_antigo != nome_novo:
                # Ex: "Vale - João" vira "Vale - João Silva"
                conn.execute("""
                    UPDATE despesas 
                    SET descricao = REPLACE(descricao, ?, ?) 
                    WHERE descricao LIKE ? AND status='PENDENTE' AND unidade_id=?
                """, (f" - {nome_antigo}", f" - {nome_novo}", f"% - {nome_antigo}", unidade_id))

            # Se demitiu, apaga TUDO que estava pendente para ele
            if not ativo:
                conn.execute("""
                    DELETE FROM despesas 
                    WHERE descricao LIKE ? AND status='PENDENTE' AND unidade_id=?
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
            conn.execute("DELETE FROM despesas WHERE descricao=? AND status='PENDENTE' AND unidade_id=?", 
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
            ''', (unidade_id, func_id, tipo_item, nome_item, to_cents(valor), dia_venc))
            
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
                    VALUES (?, ?, ?, ?, ?, ?, 'PENDENTE')
                ''', (unidade_id, cat_item, desc_item, to_cents(valor), dt_venc, mes_ref))
    except Exception as e:
        raise e
    finally:
        conn.close()

def verificar_status_migracao(unidade_id):
    """
    Verifica se a unidade está apta a receber migração (deve estar vazia).
    Retorna: (pode_migrar, qtd_alunos, qtd_matriculas)
    """
    conn = conectar()
    try:
        qa = conn.execute("SELECT COUNT(*) FROM alunos WHERE unidade_id = ?", (unidade_id,)).fetchone()[0]
        qm = conn.execute("SELECT COUNT(*) FROM matriculas WHERE unidade_id = ?", (unidade_id,)).fetchone()[0]
        
        estah_limpa = (qa == 0 and qm == 0)
        return estah_limpa, qa, qm
    finally:
        conn.close()

def importar_dados_migracao(unidade_id, lista_registros):
    """
    Processa a importação em lote de forma ATÔMICA.
    lista_registros: lista de dicionários contendo os dados limpos.
    """
    conn = conectar()
    try:
        # Helper de data para calcular vencimento
        def get_valid_date(year, month, day):
            try:
                return date(year, month, day)
            except ValueError:
                if month == 12: return date(year, 12, 31)
                return date(year, month + 1, 1) - pd.Timedelta(days=1)

        hj = datetime.now()
        mes_ref = hj.strftime("%m/%Y")
        
        # Cache local para evitar duplicidade dentro do próprio arquivo
        cache_alunos = {} 
        
        with conn: # Início da Transação
            for row in lista_registros:
                nome = row['nome']
                
                # 1. Busca/Cria Aluno
                # Verifica no cache da transação
                aid = cache_alunos.get(nome)
                
                if not aid:
                    # Verifica no banco (caso existam alunos de outra importação manual, 
                    # embora a trava de segurança evite isso, é bom garantir)
                    exist = conn.execute("SELECT id FROM alunos WHERE nome=? AND unidade_id=?", (nome, unidade_id)).fetchone()
                    if exist:
                        aid = exist[0]
                    else:
                        cur = conn.execute("""
                            INSERT INTO alunos (unidade_id, nome, responsavel_nome, cpf_responsavel, canal_aquisicao) 
                            VALUES (?,?,?,?,?)""", 
                            (unidade_id, nome, row['responsavel'], row['cpf'], row['canal']))
                        aid = cur.lastrowid
                    cache_alunos[nome] = aid
                
                # 2. Cria Matrícula
                cur = conn.execute("""
                    INSERT INTO matriculas (unidade_id, aluno_id, disciplina, valor_acordado, dia_vencimento, data_inicio, ativo, justificativa_desconto) 
                    VALUES (?,?,?,?,?,DATE('now'),1, 'Migracao')""",
                    (unidade_id, aid, row['disciplina'], to_cents(row['valor']), row['dia_vencimento']))
                mid = cur.lastrowid
                
                # 3. Gera Mensalidade do Mês Atual
                dt_venc = get_valid_date(hj.year, hj.month, row['dia_vencimento'])
                
                conn.execute("""
                    INSERT INTO pagamentos (unidade_id, matricula_id, aluno_id, mes_referencia, data_vencimento, valor_pago, status) 
                    VALUES (?,?,?,?,?,?,'PENDENTE')""",
                    (unidade_id, mid, aid, mes_ref, dt_venc, to_cents(row['valor'])))
                    
    except Exception as e:
        raise e
    finally:
        conn.close()

def buscar_resumo_operacional_mes(unidade_id):
    """
    Calcula os totais financeiros (Receitas/Despesas) e contagem de alunos
    para alimentar os Cards da Home.
    """
    conn = conectar()
    try:
        hoje = datetime.now()
        mes_ref = hoje.strftime("%m/%Y")     # Para pagamentos/despesas
        mes_anomes = hoje.strftime('%Y-%m')  # Para filtro de data_fim (sqlite)

        cursor = conn.cursor()

        # 1. Receitas
        cursor.execute("SELECT SUM(valor_pago) FROM pagamentos WHERE mes_referencia = ? AND unidade_id = ?", (mes_ref, unidade_id))
        rec_total = cursor.fetchone()[0] or 0.0

        cursor.execute("SELECT SUM(valor_pago) FROM pagamentos WHERE mes_referencia = ? AND status='PENDENTE' AND unidade_id = ?", (mes_ref, unidade_id))
        rec_pendente = cursor.fetchone()[0] or 0.0

        # 2. Despesas
        cursor.execute("SELECT SUM(valor) FROM despesas WHERE mes_referencia = ? AND unidade_id = ?", (mes_ref, unidade_id))
        desp_total = cursor.fetchone()[0] or 0.0

        cursor.execute("SELECT SUM(valor) FROM despesas WHERE mes_referencia = ? AND status='PENDENTE' AND unidade_id = ?", (mes_ref, unidade_id))
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
            "desp_total": desp_total,
            "desp_pendente": desp_pendente,
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
    conn = conectar()
    try:
        query = '''
            SELECT a.nome, p.data_vencimento, p.valor_pago
            FROM pagamentos p JOIN alunos a ON p.aluno_id = a.id
            WHERE p.status='PENDENTE' AND p.mes_referencia = ? AND p.unidade_id = ?
            ORDER BY p.data_vencimento
        '''
        return pd.read_sql_query(query, conn, params=(mes_ref, unidade_id))
    finally:
        conn.close()

def buscar_pendencias_pagamento(unidade_id, mes_ref):
    """
    Lista as contas (despesas) que vencem no mês atual e ainda não foram pagas.
    """
    conn = conectar()
    try:
        query = '''
            SELECT descricao, data_vencimento, valor
            FROM despesas
            WHERE status='PENDENTE' AND mes_referencia = ? AND unidade_id = ?
            ORDER BY data_vencimento
        '''
        return pd.read_sql_query(query, conn, params=(mes_ref, unidade_id))
    finally:
        conn.close()