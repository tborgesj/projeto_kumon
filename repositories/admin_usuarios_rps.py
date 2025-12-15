
from conectDB.conexao import conectar

import bcrypt

def _gerar_hash_bcrypt(senha_plana: str) -> str:
    """Gera um hash seguro usando Bcrypt com Salt automático."""
    # Bcrypt trabalha com bytes, então codificamos a string
    # E decodificamos o resultado para salvar como TEXT no banco SQLite
    salt = bcrypt.gensalt()
    hash_bytes = bcrypt.hashpw(senha_plana.encode('utf-8'), salt)
    return hash_bytes.decode('utf-8')

def _verificar_senha_bcrypt(senha_plana: str, hash_banco: str) -> bool:
    """Verifica se a senha bate com o hash Bcrypt."""
    try:
        return bcrypt.checkpw(senha_plana.encode('utf-8'), hash_banco.encode('utf-8'))
    except ValueError:
        return False

def verifica_usuario_existe(username):
    """
    Cria o usuário e vincula as unidades em uma TRANSAÇÃO ÚNICA.
    """
    conn = conectar()
    try:
        row = conn.execute("SELECT 1 FROM usuarios WHERE username = ?", (username,)).fetchone()

        if row:
            return True
        else:
            return False

    except Exception as e:
        print(f"Erro ao verificar usuário: {e}")
        return False # Em caso de erro, assumimos False ou tratamos conforme necessidade
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
