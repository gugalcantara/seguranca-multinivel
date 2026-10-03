-- =============================================================================
-- Esquema do banco — APS PIVC 2026/2 — MySQL 8.0
-- Executar como administrador:  mysql -u root -p < sql/01_schema.sql
-- Depois: sql/02_dados_iniciais.sql e sql/03_usuarios.sql (nesta ordem)
--
-- Diferenças em relação ao rascunho do Handoff (ver README, "Decisões"):
--  * pendencia, item_acervo e regiao_sensivel criadas (a camada causal e o
--    acervo dependiam delas, mas não existiam);
--  * log_acesso.momento é gravado pela APLICAÇÃO com microssegundos, não pelo
--    DEFAULT do banco — o momento entra no hash e precisa ser o mesmo gravado;
--  * distancia/qualidade em DECIMAL: FLOAT perde precisão na volta e quebra a
--    recomputação do hash;
--  * log_acesso ganhou usuario2_id (regra dos dois), motivo, evento e item_id
--    (consultas e exportações também entram na cadeia — RF-12, S-07);
--  * limiar_distancia saiu de `nivel`: a fonte única é o config.ini.
-- =============================================================================

SET NAMES utf8mb4;   -- sem isto o cliente mysql lê o arquivo como latin1 e corrompe os acentos
CREATE DATABASE IF NOT EXISTS aps_pivc
    CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE aps_pivc;

-- ---------------------------------------------------------------- Acesso
CREATE TABLE nivel (
    id               TINYINT      PRIMARY KEY,           -- 1, 2, 3
    nome             VARCHAR(50)  NOT NULL,
    descricao        VARCHAR(200) NOT NULL,
    fatores_exigidos VARCHAR(200) NOT NULL
);

CREATE TABLE usuario (
    id         INT          PRIMARY KEY AUTO_INCREMENT,  -- = rótulo no LBPH
    matricula  VARCHAR(20)  NOT NULL UNIQUE,
    nome       VARCHAR(100) NOT NULL,
    nivel_id   TINYINT      NOT NULL,
    uf         CHAR(2),                                  -- região do diretor (N2)
    senha_hash CHAR(60)     NOT NULL,                    -- bcrypt, custo 12
    ativo      BOOLEAN      NOT NULL DEFAULT TRUE,
    criado_em  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (nivel_id) REFERENCES nivel(id)
);

-- Metadado das amostras. A IMAGEM não fica aqui: é apagada após o treino.
CREATE TABLE amostra (
    id         INT          PRIMARY KEY AUTO_INCREMENT,
    usuario_id INT          NOT NULL,
    sessao     TINYINT      NOT NULL,                    -- base da divisão treino/teste
    origem     VARCHAR(50),
    qualidade  DECIMAL(6,4),
    criada_em  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (usuario_id) REFERENCES usuario(id)
);

CREATE TABLE bloqueio (
    matricula     VARCHAR(20) PRIMARY KEY,
    tentativas    INT         NOT NULL DEFAULT 0,
    bloqueado_ate DATETIME
);

-- Consentimento para tratamento de dado biométrico (LGPD art. 11, I).
-- O hash do texto fica gravado porque o ônus de provar o consentimento é do
-- controlador (art. 8º, §2º): registrar "aceitou a v1.0" não provaria nada se o
-- texto da v1.0 mudasse depois. A revogação (art. 8º, §5º) é marcada aqui, não
-- apagada — a baixa também precisa de evidência.
CREATE TABLE consentimento (
    id            INT          PRIMARY KEY AUTO_INCREMENT,
    usuario_id    INT,                                    -- nulo até o cadastro concluir
    titular_nome  VARCHAR(100) NOT NULL,
    versao_termo  VARCHAR(10)  NOT NULL,
    hash_termo    CHAR(64)     NOT NULL,                  -- SHA-256 do texto apresentado
    finalidade    VARCHAR(200) NOT NULL,
    momento       DATETIME(6)  NOT NULL,
    revogado_em   DATETIME(6),
    FOREIGN KEY (usuario_id) REFERENCES usuario(id)
);

-- ---------------------------------------------------------------- Camada causal
CREATE TABLE atividade_geradora (
    id         INT          PRIMARY KEY AUTO_INCREMENT,
    codigo     VARCHAR(10)  NOT NULL UNIQUE,             -- AG-01 a AG-08
    descricao  VARCHAR(200) NOT NULL,
    cnae       VARCHAR(20),
    observacao TEXT
);

CREATE TABLE motivo_permanencia (
    id                 INT          PRIMARY KEY AUTO_INCREMENT,
    codigo             VARCHAR(10)  NOT NULL UNIQUE,     -- MP-01 a MP-08
    descricao          VARCHAR(200) NOT NULL,
    base_legal         TEXT,
    acao_institucional TEXT
);

-- ---------------------------------------------------------------- Acervo
CREATE TABLE pendencia (
    id                INT           PRIMARY KEY AUTO_INCREMENT,
    codigo            VARCHAR(20)   NOT NULL UNIQUE,
    substancia        VARCHAR(200)  NOT NULL,
    classe_risco      VARCHAR(50)   NOT NULL,            -- ex.: Classe I (NBR 10004), rejeito radioativo
    quantidade        DECIMAL(12,3),
    unidade           VARCHAR(10),
    uf                CHAR(2)       NOT NULL,
    municipio         VARCHAR(100),
    latitude          DECIMAL(9,6),
    longitude         DECIMAL(9,6),
    prazo_coleta      DATE,
    situacao          VARCHAR(50)   NOT NULL,
    atividade_id      INT           NOT NULL,            -- RF-19: nenhuma aceita nulo
    motivo_id         INT           NOT NULL,
    sintetico         BOOLEAN       NOT NULL DEFAULT TRUE,
    fonte             VARCHAR(300),
    data_acesso_fonte DATE,
    FOREIGN KEY (atividade_id) REFERENCES atividade_geradora(id),
    FOREIGN KEY (motivo_id)    REFERENCES motivo_permanencia(id)
);

-- Cadeia de responsabilidade — nomeia pessoas e empresas: só a partir do N2 (RF-21)
CREATE TABLE responsavel (
    id                 INT          PRIMARY KEY AUTO_INCREMENT,
    pendencia_id       INT          NOT NULL,
    nome               VARCHAR(200) NOT NULL,
    vinculo            ENUM('GERADOR_ORIGINAL','SUCESSOR','PROPRIETARIO_ATUAL',
                            'TRANSPORTADOR','DESTINADOR') NOT NULL,
    situacao_cadastral VARCHAR(50),
    nivel_minimo       TINYINT      NOT NULL DEFAULT 2,
    CHECK (nivel_minimo BETWEEN 2 AND 3),
    FOREIGN KEY (pendencia_id) REFERENCES pendencia(id)
);

CREATE TABLE item_acervo (
    id                INT          PRIMARY KEY AUTO_INCREMENT,
    codigo            VARCHAR(20)  NOT NULL UNIQUE,
    titulo            VARCHAR(200) NOT NULL,
    tipo              ENUM('DOCUMENTO','MAPA','FOTO') NOT NULL,
    arquivo           VARCHAR(300) NOT NULL,             -- relativo a [caminhos] acervo
    nivel_minimo      TINYINT      NOT NULL,             -- abaixo disso o item nem é listado
    regioes_revisadas BOOLEAN      NOT NULL DEFAULT FALSE,  -- FALSE = totalmente sensível (só N3)
    sintetico         BOOLEAN      NOT NULL DEFAULT TRUE,   -- RF-18
    uf                CHAR(2),
    pendencia_id      INT,
    fonte             VARCHAR(300),
    data_acesso_fonte DATE,
    CHECK (nivel_minimo BETWEEN 1 AND 3),
    FOREIGN KEY (pendencia_id) REFERENCES pendencia(id)
);

-- Região que só aparece íntegra para quem tem nível >= nivel_minimo
CREATE TABLE regiao_sensivel (
    id           INT         PRIMARY KEY AUTO_INCREMENT,
    item_id      INT         NOT NULL,
    x            INT         NOT NULL,
    y            INT         NOT NULL,
    largura      INT         NOT NULL,
    altura       INT         NOT NULL,
    rotulo       VARCHAR(50),                            -- ENDERECO, RESPONSAVEL, COORDENADA...
    nivel_minimo TINYINT     NOT NULL,
    CHECK (nivel_minimo BETWEEN 2 AND 3),
    FOREIGN KEY (item_id) REFERENCES item_acervo(id)
);

-- ---------------------------------------------------------------- Auditoria
-- Trilha encadeada por SHA-256 (D-05). A conta da aplicação só tem
-- SELECT e INSERT aqui (ver 03_usuarios.sql): não consegue alterar o passado.
CREATE TABLE log_acesso (
    id                INT          PRIMARY KEY AUTO_INCREMENT,
    momento           DATETIME(6)  NOT NULL,             -- definido pela aplicação, entra no hash
    evento            ENUM('AUTENTICACAO','CONSULTA','EXPORTACAO','CADASTRO','VERIFICACAO') NOT NULL,
    usuario_id        INT,
    usuario2_id       INT,                               -- segunda pessoa da regra dos dois
    matricula_informada VARCHAR(20),
    nivel_solicitado  TINYINT      NOT NULL,
    item_id           INT,
    fatores_avaliados VARCHAR(200),
    resultado         ENUM('CONCEDIDO','NEGADO') NOT NULL,
    motivo            VARCHAR(40)  NOT NULL,
    distancia         DECIMAL(10,4),
    qualidade         DECIMAL(6,4),
    hash_anterior     CHAR(64)     NOT NULL,             -- 64 zeros no primeiro registro
    hash_registro     CHAR(64)     NOT NULL UNIQUE,
    FOREIGN KEY (usuario_id)  REFERENCES usuario(id),
    FOREIGN KEY (usuario2_id) REFERENCES usuario(id),
    FOREIGN KEY (item_id)     REFERENCES item_acervo(id)
);

-- Foto apenas de tentativas NEGADAS, cifrada (Fernet) e com prazo de expiração
CREATE TABLE tentativa_negada (
    id        INT        PRIMARY KEY AUTO_INCREMENT,
    log_id    INT        NOT NULL,
    imagem    MEDIUMBLOB NOT NULL,
    expira_em DATETIME   NOT NULL,
    FOREIGN KEY (log_id) REFERENCES log_acesso(id)
);

-- ---------------------------------------------------------------- Visões do nível 1
-- Agregadas, sem endereço, coordenada nem responsável (RF-20)
CREATE VIEW vw_n1_por_atividade AS
SELECT p.uf, a.codigo AS atividade, a.descricao, COUNT(*) AS pendencias
FROM pendencia p JOIN atividade_geradora a ON a.id = p.atividade_id
GROUP BY p.uf, a.codigo, a.descricao;

CREATE VIEW vw_n1_por_motivo AS
SELECT m.codigo AS motivo, m.descricao, COUNT(*) AS pendencias,
       SUM(p.prazo_coleta < CURRENT_DATE) AS vencidas
FROM pendencia p JOIN motivo_permanencia m ON m.id = p.motivo_id
GROUP BY m.codigo, m.descricao;
