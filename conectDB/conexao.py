import sqlite3

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