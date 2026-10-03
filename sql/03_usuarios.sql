-- Conta da APLICAÇÃO, separada da administrativa (ETP 6.4).
-- Executar como root, trocando a senha pela mesma colocada em DB_SENHA no .env.
--
-- Ponto de segurança demonstrável: a aplicação NÃO tem UPDATE nem DELETE em
-- log_acesso. Para adulterar a trilha é preciso a conta administrativa — e
-- mesmo assim a cadeia de hash denuncia a alteração (RF-13).

SET NAMES utf8mb4;   -- sem isto o cliente mysql lê o arquivo como latin1 e corrompe os acentos
CREATE USER IF NOT EXISTS 'aps_app'@'localhost' IDENTIFIED BY 'troque-esta-senha';
CREATE USER IF NOT EXISTS 'aps_app'@'%'         IDENTIFIED BY 'troque-esta-senha';

GRANT SELECT                  ON aps_pivc.nivel              TO 'aps_app'@'localhost', 'aps_app'@'%';
GRANT SELECT, INSERT, UPDATE  ON aps_pivc.usuario            TO 'aps_app'@'localhost', 'aps_app'@'%';
GRANT SELECT, INSERT          ON aps_pivc.amostra            TO 'aps_app'@'localhost', 'aps_app'@'%';
-- UPDATE permitido para vincular o usuário criado e para marcar a revogação;
-- sem DELETE: a evidência do consentimento não se apaga (LGPD art. 8º, §2º).
GRANT SELECT, INSERT, UPDATE  ON aps_pivc.consentimento      TO 'aps_app'@'localhost', 'aps_app'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON aps_pivc.bloqueio    TO 'aps_app'@'localhost', 'aps_app'@'%';
GRANT SELECT                  ON aps_pivc.atividade_geradora TO 'aps_app'@'localhost', 'aps_app'@'%';
GRANT SELECT                  ON aps_pivc.motivo_permanencia TO 'aps_app'@'localhost', 'aps_app'@'%';
GRANT SELECT, INSERT, UPDATE  ON aps_pivc.pendencia          TO 'aps_app'@'localhost', 'aps_app'@'%';
GRANT SELECT, INSERT, UPDATE  ON aps_pivc.responsavel        TO 'aps_app'@'localhost', 'aps_app'@'%';
GRANT SELECT, INSERT, UPDATE  ON aps_pivc.item_acervo        TO 'aps_app'@'localhost', 'aps_app'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON aps_pivc.regiao_sensivel TO 'aps_app'@'localhost', 'aps_app'@'%';
GRANT SELECT, INSERT          ON aps_pivc.log_acesso         TO 'aps_app'@'localhost', 'aps_app'@'%';
GRANT SELECT, INSERT, DELETE  ON aps_pivc.tentativa_negada   TO 'aps_app'@'localhost', 'aps_app'@'%';
GRANT SELECT                  ON aps_pivc.vw_n1_por_atividade TO 'aps_app'@'localhost', 'aps_app'@'%';
GRANT SELECT                  ON aps_pivc.vw_n1_por_motivo    TO 'aps_app'@'localhost', 'aps_app'@'%';

-- Banco DESCARTÁVEL dos testes de integração (testes/test_integracao_banco.py).
-- Privilégio total AQUI de propósito: o teste precisa criar e apagar o próprio
-- schema a cada execução. No banco de demonstração acima a conta continua sem
-- UPDATE nem DELETE em log_acesso — é lá que a propriedade do RF-13 vale.
-- O banco em si é criado pela suíte, a partir de sql/01 e sql/02.
GRANT ALL PRIVILEGES ON `aps_pivc_teste`.* TO 'aps_app'@'localhost', 'aps_app'@'%';
FLUSH PRIVILEGES;
