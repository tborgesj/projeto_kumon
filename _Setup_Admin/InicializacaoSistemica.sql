
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
            valor_taxa_matricula INTEGER DEFAULT 0,
            valor_mensalidade_padrao INTEGER DEFAULT 350,
            FOREIGN KEY (unidade_id) REFERENCES unidades (id));

CREATE TABLE IF NOT EXISTS config_royalties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unidade_id INTEGER NOT NULL,
            valor INTEGER,
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
    id_canal_aquisicao INTEGER, -- Alterado de TEXT para FK
    data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (unidade_id) REFERENCES unidades (id),
    FOREIGN KEY (id_canal_aquisicao) REFERENCES canais_aquisicao (id)
);

CREATE TABLE IF NOT EXISTS matriculas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unidade_id INTEGER NOT NULL,
            aluno_id INTEGER,
            id_disciplina INTEGER NOT NULL, -- Alterado de TEXT para FK
            data_inicio DATE,
            valor_acordado INTEGER NOT NULL,
            dia_vencimento INTEGER DEFAULT 10,
            justificativa_desconto TEXT,
            ativo BOOLEAN DEFAULT 1,
            bolsa_ativa BOOLEAN DEFAULT 0,
            bolsa_meses_restantes INTEGER DEFAULT 0,
            data_fim DATE,
            FOREIGN KEY (unidade_id) REFERENCES unidades (id),
            FOREIGN KEY (aluno_id) REFERENCES alunos (id),
            FOREIGN KEY (id_disciplina) REFERENCES disciplinas (id)
);

CREATE TABLE IF NOT EXISTS pagamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unidade_id INTEGER NOT NULL,
            matricula_id INTEGER,
            aluno_id INTEGER,
            mes_referencia TEXT,
            valor_pago INTEGER,
            data_vencimento DATE,
            data_pagamento DATE,
            id_status INTEGER DEFAULT 1,          -- FK: Pendente
            id_tipo INTEGER DEFAULT 1,            -- FK: Mensalidade
            id_forma_pagamento INTEGER,           -- Alterado de TEXT para FK
            FOREIGN KEY (unidade_id) REFERENCES unidades (id),
            FOREIGN KEY (matricula_id) REFERENCES matriculas (id),
            FOREIGN KEY (aluno_id) REFERENCES alunos (id),
            FOREIGN KEY (id_status) REFERENCES status_pagamentos (id),
            FOREIGN KEY (id_tipo) REFERENCES tipos_pagamento (id),
            FOREIGN KEY (id_forma_pagamento) REFERENCES formas_pagamento (id)
);

CREATE TABLE IF NOT EXISTS categorias_despesas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            nome_categoria TEXT UNIQUE);

CREATE TABLE IF NOT EXISTS despesas_recorrentes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unidade_id INTEGER NOT NULL,
            id_categoria INTEGER,
            descricao TEXT,
            valor INTEGER,
            dia_vencimento INTEGER,
            limite_meses INTEGER,
            data_criacao DATE,
            ativo BOOLEAN DEFAULT 1,
            FOREIGN KEY (id_categoria) REFERENCES categorias_despesas (id));

CREATE TABLE IF NOT EXISTS despesas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    unidade_id INTEGER NOT NULL,
    recorrente_id INTEGER,
    id_categoria INTEGER,
    descricao TEXT,
    valor INTEGER,
    data_vencimento DATE,
    mes_referencia TEXT,
    data_pagamento DATE,
    id_status INTEGER DEFAULT 1,
    id_pagamento_origem INTEGER REFERENCES pagamentos(id),
    FOREIGN KEY (id_categoria) REFERENCES categorias_despesas (id),
    FOREIGN KEY (id_status) REFERENCES status_despesas (id)
);

CREATE TABLE IF NOT EXISTS funcionarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unidade_id INTEGER NOT NULL,
            nome TEXT NOT NULL,
            id_tipo_contratacao INTEGER, -- Alterado de TEXT para FK
            salario_base INTEGER,
            data_contratacao DATE,
            dia_pagamento_salario INTEGER,
            ativo BOOLEAN DEFAULT 1,
            data_demissao DATE,
            FOREIGN KEY (unidade_id) REFERENCES unidades (id),
            FOREIGN KEY (id_tipo_contratacao) REFERENCES tipos_contratacao (id)
);

CREATE TABLE IF NOT EXISTS custos_pessoal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unidade_id INTEGER NOT NULL,
            funcionario_id INTEGER,
            tipo_item TEXT, 
            nome_item TEXT,
            valor INTEGER,
            dia_vencimento INTEGER);

CREATE TABLE IF NOT EXISTS cofres (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unidade_id INTEGER NOT NULL,
            nome TEXT NOT NULL,
            percentual_padrao INTEGER DEFAULT 0,
            descricao TEXT,
            FOREIGN KEY (unidade_id) REFERENCES unidades (id));

CREATE TABLE IF NOT EXISTS cofres_saldo (
            unidade_id INTEGER NOT NULL,
            cofre_id INTEGER NOT NULL,
            saldo_atual INTEGER DEFAULT 0,
            PRIMARY KEY (unidade_id, cofre_id),
            FOREIGN KEY (cofre_id) REFERENCES cofres (id));

CREATE TABLE IF NOT EXISTS cofres_movimentacao (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unidade_id INTEGER NOT NULL,
            cofre_id INTEGER,
            data_movimentacao DATE,
            valor INTEGER,
            tipo TEXT, 
            descricao TEXT,
            FOREIGN KEY (cofre_id) REFERENCES cofres (id));

CREATE TABLE IF NOT EXISTS status_despesas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE
);



INSERT OR IGNORE INTO unidades (id, nome) VALUES (1, 'Kumon - Matriz');
INSERT OR IGNORE INTO unidades (id, nome) VALUES (2, 'Kumon - Filial Centro');

INSERT INTO cofres (unidade_id, nome, percentual_padrao, descricao) VALUES (1, '13º Salário e Férias', 15, 'Provisão Trabalhista Obrigatória');
INSERT INTO cofres (unidade_id, nome, percentual_padrao, descricao) VALUES (1, 'Fundo de Emergência', 10, 'Reserva para crises');
INSERT INTO cofres (unidade_id, nome, percentual_padrao, descricao) VALUES (1, 'Capital de Giro', 15, 'Dinheiro para rodar o mês');
INSERT INTO cofres (unidade_id, nome, percentual_padrao, descricao) VALUES (1, 'Investimentos', 10, 'Marketing, Reformas');
INSERT INTO cofres (unidade_id, nome, percentual_padrao, descricao) VALUES (1, 'Lucro Livre (Sócios)', 50, 'Disponível para retirada');

-- Carga inicial de dados para referência
INSERT OR IGNORE INTO status_despesas (id, nome) VALUES (1, 'PENDENTE');
INSERT OR IGNORE INTO status_despesas (id, nome) VALUES (2, 'PAGO');
INSERT OR IGNORE INTO status_despesas (id, nome) VALUES (3, 'ATRASADO');
INSERT OR IGNORE INTO status_despesas (id, nome) VALUES (4, 'CANCELADO');

INSERT INTO categorias_despesas (id,nome_categoria) values (1,'Pessoal');
INSERT INTO categorias_despesas (id,nome_categoria) values (2,'Impostos');
INSERT INTO categorias_despesas (id,nome_categoria) values (3,'Taxas Financeiras');

INSERT OR IGNORE INTO cofres_saldo (unidade_id, cofre_id, saldo_atual) VALUES (1, 1, 0);

-- CAMPO STATUS TABELA DESPESAS FIM --

-- CAMPO CANAL AQUISIÇÃO TABELA ALUNOS INICIO --

CREATE TABLE IF NOT EXISTS canais_aquisicao (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE
);

-- Carga inicial de dados sugerida
INSERT OR IGNORE INTO canais_aquisicao (id, nome) VALUES (1, 'Indicação');
INSERT OR IGNORE INTO canais_aquisicao (id, nome) VALUES (2, 'Redes Sociais (Instagram/Facebook)');
INSERT OR IGNORE INTO canais_aquisicao (id, nome) VALUES (3, 'Fachada / Passou na Frente');
INSERT OR IGNORE INTO canais_aquisicao (id, nome) VALUES (4, 'Panfletagem / Escola');
INSERT OR IGNORE INTO canais_aquisicao (id, nome) VALUES (5, 'Google / Site');
INSERT OR IGNORE INTO canais_aquisicao (id, nome) VALUES (6, 'Outros');



-- CAMPO CANAL AQUISIÇÃO TABELA ALUNOS FIM --


-- CAMPO TIPO CONTRATAÇÃO TABELA FUNCIONÁRIOS INICIO --

CREATE TABLE IF NOT EXISTS tipos_contratacao (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE
);

-- Carga inicial de dados
INSERT OR IGNORE INTO tipos_contratacao (id, nome) VALUES (1, 'CLT (Efetivo)');
INSERT OR IGNORE INTO tipos_contratacao (id, nome) VALUES (2, 'PJ (Prestador de Serviço)');
INSERT OR IGNORE INTO tipos_contratacao (id, nome) VALUES (3, 'Estágio');
INSERT OR IGNORE INTO tipos_contratacao (id, nome) VALUES (4, 'Temporário');
INSERT OR IGNORE INTO tipos_contratacao (id, nome) VALUES (5, 'Jovem Aprendiz');
INSERT OR IGNORE INTO tipos_contratacao (id, nome) VALUES (6, 'Freelancer / Autônomo');



-- CAMPO TIPO CONTRATAÇÃO TABELA FUNCIONÁRIOS FIM --


-- CAMPO DISCIPLINA TABELA MATRICULAS INICIO --

CREATE TABLE IF NOT EXISTS disciplinas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE
);

-- Carga inicial de dados (Baseada no portfólio padrão do Kumon)
INSERT OR IGNORE INTO disciplinas (id, nome) VALUES (1, 'Matemática');
INSERT OR IGNORE INTO disciplinas (id, nome) VALUES (2, 'Português');
INSERT OR IGNORE INTO disciplinas (id, nome) VALUES (3, 'Inglês');
-- INSERT OR IGNORE INTO disciplinas (id, nome) VALUES (4, 'Japonês');
-- INSERT OR IGNORE INTO disciplinas (id, nome) VALUES (5, 'Kokugo'); -- Para alunos fluentes em japonês, se aplicável



-- CAMPO DISCIPLINA TABELA MATRICULAS FIM --

-- CAMPO STATUS/TIPO TABELA PAGAMENTOS INICIO --

CREATE TABLE IF NOT EXISTS status_pagamentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE
);

INSERT OR IGNORE INTO status_pagamentos (id, nome) VALUES (1, 'PENDENTE');
INSERT OR IGNORE INTO status_pagamentos (id, nome) VALUES (2, 'PAGO');
INSERT OR IGNORE INTO status_pagamentos (id, nome) VALUES (3, 'ATRASADO');
INSERT OR IGNORE INTO status_pagamentos (id, nome) VALUES (4, 'CANCELADO');
INSERT OR IGNORE INTO status_pagamentos (id, nome) VALUES (5, 'ESTORNADO');

CREATE TABLE IF NOT EXISTS tipos_pagamento (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE
);

-- Carga inicial sugerida para o contexto Kumon/Escola
INSERT OR IGNORE INTO tipos_pagamento (id, nome) VALUES (1, 'Mensalidade');
INSERT OR IGNORE INTO tipos_pagamento (id, nome) VALUES (2, 'Taxa de Matrícula');
INSERT OR IGNORE INTO tipos_pagamento (id, nome) VALUES (3, 'Material Didático');
INSERT OR IGNORE INTO tipos_pagamento (id, nome) VALUES (4, 'Multa / Juros');
INSERT OR IGNORE INTO tipos_pagamento (id, nome) VALUES (5, 'Outros');

CREATE TABLE IF NOT EXISTS formas_pagamento (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE
);

-- Carga inicial de dados
INSERT OR IGNORE INTO formas_pagamento (id, nome) VALUES (1, 'Boleto Bancário');
INSERT OR IGNORE INTO formas_pagamento (id, nome) VALUES (2, 'Pix');
INSERT OR IGNORE INTO formas_pagamento (id, nome) VALUES (3, 'Dinheiro / Espécie');
INSERT OR IGNORE INTO formas_pagamento (id, nome) VALUES (4, 'Cartão de Crédito');
INSERT OR IGNORE INTO formas_pagamento (id, nome) VALUES (5, 'Cartão de Débito');
INSERT OR IGNORE INTO formas_pagamento (id, nome) VALUES (6, 'Transferência / DOC / TED');
INSERT OR IGNORE INTO formas_pagamento (id, nome) VALUES (7, 'Cheque');



-- CAMPO STATUS/TIPO TABELA PAGAMENTOS FIM --

-- Executar inserção após inserir usuário ADM

-- INSERT OR IGNORE INTO usuario_unidades (usuario_username, unidade_id) VALUES ('admin', 1);
-- INSERT OR IGNORE INTO usuario_unidades (usuario_username, unidade_id) VALUES ('admin', 2)


-- ============================================================
-- ÍNDICES DE PERFORMANCE (OTIMIZAÇÃO)
-- ============================================================

-- 1. Tabela PAGAMENTOS (A mais crítica para o Dashboard)
-- Cenário: "Quanto recebi este mês na unidade X?"
-- Cobre: WHERE unidade_id=? AND mes_referencia=? AND id_status=?
CREATE INDEX IF NOT EXISTS idx_pagamentos_dashboard 
ON pagamentos (unidade_id, mes_referencia, id_status);

-- Cenário: "Quem está devendo?" ou "Próximos vencimentos"
-- Cobre: WHERE unidade_id=? AND id_status=1 ORDER BY data_vencimento
CREATE INDEX IF NOT EXISTS idx_pagamentos_cobranca 
ON pagamentos (unidade_id, id_status, data_vencimento);

-- Cenário: Histórico financeiro do aluno (Aba 2 de Alunos)
-- Cobre: JOINs e buscas por aluno específico
CREATE INDEX IF NOT EXISTS idx_pagamentos_aluno 
ON pagamentos (aluno_id);


-- 2. Tabela DESPESAS
-- Cenário: Fluxo de Caixa e Resumo Operacional
-- Cobre: WHERE unidade_id=? AND mes_referencia=?
CREATE INDEX IF NOT EXISTS idx_despesas_dashboard 
ON despesas (unidade_id, mes_referencia, id_status);


-- 3. Tabela ALUNOS
-- Cenário: Busca rápida no Selectbox e listagens
-- Cobre: WHERE unidade_id=? AND nome LIKE '...'
CREATE INDEX IF NOT EXISTS idx_alunos_busca 
ON alunos (unidade_id, nome);

-- Cenário: JOINs (Chave Estrangeira nem sempre cria índice automático no SQLite para busca reversa)
CREATE INDEX IF NOT EXISTS idx_alunos_cpf 
ON alunos (cpf_responsavel);


-- 4. Tabela MATRÍCULAS
-- Cenário: Robô Financeiro (Gerar mensalidades para ativos)
-- Cobre: WHERE unidade_id=? AND ativo=1
CREATE INDEX IF NOT EXISTS idx_matriculas_geracao 
ON matriculas (unidade_id, ativo);

-- Cenário: Vínculo com Aluno (JOINs)
CREATE INDEX IF NOT EXISTS idx_matriculas_aluno 
ON matriculas (aluno_id);