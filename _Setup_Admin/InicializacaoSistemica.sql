
CREATE TABLE IF NOT EXISTS unidades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS usuarios (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            nome_completo TEXT,
            admin BOOLEAN DEFAULT 0,
            ativo BOOLEAN DEFAULT 1);

CREATE TABLE IF NOT EXISTS usuario_unidades (
            usuario_username TEXT,
            unidade_id INTEGER,
            PRIMARY KEY (usuario_username, unidade_id),
            FOREIGN KEY (usuario_username) REFERENCES usuarios (username),
            FOREIGN KEY (unidade_id) REFERENCES unidades (id));

CREATE TABLE IF NOT EXISTS parametros (
            unidade_id INTEGER PRIMARY KEY,
            em_campanha_matricula BOOLEAN DEFAULT 0,
            valor_taxa_matricula DECIMAL(10,2) DEFAULT 0.00,
            valor_mensalidade_padrao DECIMAL(10,2) DEFAULT 350.00,
            FOREIGN KEY (unidade_id) REFERENCES unidades (id));

CREATE TABLE IF NOT EXISTS categorias_despesas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            nome_categoria TEXT UNIQUE);

CREATE TABLE IF NOT EXISTS config_royalties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unidade_id INTEGER NOT NULL,
            valor DECIMAL(10,2),
            ano_mes_inicio TEXT,
            ano_mes_fim TEXT,
            FOREIGN KEY (unidade_id) REFERENCES unidades (id));

CREATE TABLE IF NOT EXISTS docs_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unidade_id INTEGER NOT NULL,
            nome_arquivo TEXT,
            arquivo_binario BLOB,
            tipo TEXT DEFAULT 'CONTRATO',
            FOREIGN KEY (unidade_id) REFERENCES unidades (id));

CREATE TABLE IF NOT EXISTS alunos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unidade_id INTEGER NOT NULL,
            nome TEXT NOT NULL,
            responsavel_nome TEXT,
            cpf_responsavel TEXT, 
            canal_aquisicao TEXT,
            data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (unidade_id) REFERENCES unidades (id));

CREATE TABLE IF NOT EXISTS matriculas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unidade_id INTEGER NOT NULL,
            aluno_id INTEGER,
            disciplina TEXT NOT NULL,
            data_inicio DATE,
            valor_acordado DECIMAL(10,2) NOT NULL,
            dia_vencimento INTEGER DEFAULT 10,
            justificativa_desconto TEXT,
            ativo BOOLEAN DEFAULT 1,
            bolsa_ativa BOOLEAN DEFAULT 0,
            bolsa_meses_restantes INTEGER DEFAULT 0,
            data_fim DATE,
            FOREIGN KEY (aluno_id) REFERENCES alunos (id));

CREATE TABLE IF NOT EXISTS pagamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unidade_id INTEGER NOT NULL,
            matricula_id INTEGER,
            aluno_id INTEGER,
            mes_referencia TEXT,
            valor_pago DECIMAL(10,2),
            data_vencimento DATE,
            data_pagamento DATE,
            status TEXT,
            tipo TEXT DEFAULT 'MENSALIDADE',
            forma_pagamento TEXT,
            FOREIGN KEY (matricula_id) REFERENCES matriculas (id));

CREATE TABLE IF NOT EXISTS despesas_recorrentes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unidade_id INTEGER NOT NULL,
            categoria TEXT,
            descricao TEXT,
            valor DECIMAL(10,2),
            dia_vencimento INTEGER,
            limite_meses INTEGER,
            data_criacao DATE,
            ativo BOOLEAN DEFAULT 1);

CREATE TABLE IF NOT EXISTS despesas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unidade_id INTEGER NOT NULL,
            recorrente_id INTEGER,
            categoria TEXT,
            descricao TEXT,
            valor DECIMAL(10,2),
            data_vencimento DATE,
            mes_referencia TEXT,
            data_pagamento DATE,
            status TEXT DEFAULT 'PENDENTE');

CREATE TABLE IF NOT EXISTS funcionarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unidade_id INTEGER NOT NULL,
            nome TEXT NOT NULL,
            tipo_contratacao TEXT,
            salario_base DECIMAL(10,2),
            data_contratacao DATE,
            dia_pagamento_salario INTEGER,
            ativo BOOLEAN DEFAULT 1,
            data_demissao DATE);

CREATE TABLE IF NOT EXISTS custos_pessoal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unidade_id INTEGER NOT NULL,
            funcionario_id INTEGER,
            tipo_item TEXT, 
            nome_item TEXT,
            valor DECIMAL(10,2),
            dia_vencimento INTEGER);

CREATE TABLE IF NOT EXISTS cofres (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unidade_id INTEGER NOT NULL,
            nome TEXT NOT NULL,
            percentual_padrao DECIMAL(5,2) DEFAULT 0.00,
            descricao TEXT,
            FOREIGN KEY (unidade_id) REFERENCES unidades (id));

CREATE TABLE IF NOT EXISTS cofres_saldo (
            unidade_id INTEGER NOT NULL,
            cofre_id INTEGER NOT NULL,
            saldo_atual DECIMAL(10,2) DEFAULT 0.00,
            PRIMARY KEY (unidade_id, cofre_id),
            FOREIGN KEY (cofre_id) REFERENCES cofres (id));

CREATE TABLE IF NOT EXISTS cofres_movimentacao (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unidade_id INTEGER NOT NULL,
            cofre_id INTEGER,
            data_movimentacao DATE,
            valor DECIMAL(10,2),
            tipo TEXT, 
            descricao TEXT,
            FOREIGN KEY (cofre_id) REFERENCES cofres (id));

INSERT OR IGNORE INTO unidades (id, nome) VALUES (1, 'Kumon - Matriz')
INSERT OR IGNORE INTO unidades (id, nome) VALUES (2, 'Kumon - Filial Centro')

def criar_tabelas() -> None:

        cursor.execute("SELECT * FROM usuarios WHERE username = 'admin'")
        if not cursor.fetchone():
            senha_hash = hashlib.sha256("Asdke1234".encode()).hexdigest()
            cursor.execute("INSERT INTO usuarios (username, password_hash, nome_completo, admin, ativo) VALUES (?, ?, ?, 1, 1)", 
                           ('admin', senha_hash, 'Administrador Master'))
            cursor.execute("INSERT OR IGNORE INTO usuario_unidades (usuario_username, unidade_id) VALUES ('admin', 1)")
            cursor.execute("INSERT OR IGNORE INTO usuario_unidades (usuario_username, unidade_id) VALUES ('admin', 2)")
            
            cursor.execute("INSERT OR IGNORE INTO parametros (unidade_id, em_campanha_matricula, valor_taxa_matricula, valor_mensalidade_padrao) VALUES (1, 0, 50.00, 350.00)")
            cursor.execute("INSERT OR IGNORE INTO parametros (unidade_id, em_campanha_matricula, valor_taxa_matricula, valor_mensalidade_padrao) VALUES (2, 0, 0.00, 320.00)")
            
            for uid in [1, 2]:
                cofres_padrao = [
                    ("13º Salário e Férias", 15.00, "Provisão Trabalhista Obrigatória"),
                    ("Fundo de Emergência", 10.00, "Reserva para crises"),
                    ("Capital de Giro", 15.00, "Dinheiro para rodar o mês"),
                    ("Investimentos", 10.00, "Marketing, Reformas"),
                    ("Lucro Livre (Sócios)", 50.00, "Disponível para retirada")
                ]
                for nome, perc, desc in cofres_padrao:
                    cursor.execute("INSERT INTO cofres (unidade_id, nome, percentual_padrao, descricao) VALUES (?, ?, ?, ?)", (uid, nome, perc, desc))
                    cid = cursor.lastrowid
                    cursor.execute("INSERT OR IGNORE INTO cofres_saldo (unidade_id, cofre_id, saldo_atual) VALUES (?, ?, 0.00)", (uid, cid))

        conn.commit()
    except Exception as e:
        logger.exception("Erro ao criar tabelas")
        raise
    finally:
        conn.close()