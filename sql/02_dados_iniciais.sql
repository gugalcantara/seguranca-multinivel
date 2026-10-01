-- Dados de referência: níveis e taxonomia da camada causal (Camada Causal v1.0).
-- Os 9 itens do acervo mínimo NÃO entram aqui: são importados de
-- acervo/itens/metadados.json por  python -m ferramentas importar-acervo
SET NAMES utf8mb4;   -- sem isto o cliente mysql lê o arquivo como latin1 e corrompe os acentos
USE aps_pivc;

INSERT INTO nivel (id, nome, descricao, fatores_exigidos) VALUES
(1, 'Consulta pública assistida', 'Dados agregados, sem localização; regiões sensíveis suprimidas', 'FACE (1:N)'),
(2, 'Consulta restrita',          'Registro individual íntegro da própria região, com marca d''água', 'SENHA + FACE (1:1)'),
(3, 'Custódia',                   'Visão consolidada nacional; sem exportação', 'SENHA + SENHA_FORTE + FACE (1:1) + VIVACIDADE + REGRA_DOIS');

INSERT INTO atividade_geradora (codigo, descricao, cnae, observacao) VALUES
('AG-01', 'Postos de combustível e serviços automotivos', '47.31-8', 'Tanques subterrâneos; ~70% do cadastro estadual de SP'),
('AG-02', 'Indústria química e petroquímica',             '20',      'Solventes clorados, borras oleosas, catalisadores usados'),
('AG-03', 'Metalurgia e galvanoplastia',                  '25.39-0', 'Lodo galvânico, cianetos, cromo hexavalente'),
('AG-04', 'Serviços de saúde',                            '86',      'Fontes seladas de radioterapia; caso Césio-137, Goiânia, 1987'),
('AG-05', 'Mineração e beneficiamento',                   '07',      'Rejeito com radioatividade natural, drenagem ácida'),
('AG-06', 'Armazenagem e transporte',                     '52.11-7', 'Carga apreendida, resíduo de limpeza de tanque'),
('AG-07', 'Agropecuária',                                 '01',      'Embalagens de agrotóxico, produto vencido ou proibido'),
('AG-08', 'Instalação nuclear e pesquisa',                '72.10-0', 'Rejeito de baixa e média atividade; controle setorial próprio');
-- TODO (Integrante 3): conferir os códigos CNAE na tabela oficial do IBGE/CONCLA.

INSERT INTO motivo_permanencia (codigo, descricao, base_legal, acao_institucional) VALUES
('MP-01', 'Encerramento ou falência do gerador',
 'Obrigação propter rem: alcança proprietário atual e sucessor (Lei 6.938/81, art. 14, §1º)',
 'Identificar sucessor ou proprietário atual e notificar'),
('MP-02', 'Disputa sobre a responsabilidade',
 'Solidariedade entre os envolvidos (Súmula 623 do STJ)',
 'Acompanhamento processual; medida cautelar de contenção'),
('MP-03', 'Custo da destinação',
 'Resíduo Classe I exige tratamento licenciado (ABNT NBR 10004; Lei 12.305/2010)',
 'Cronograma de regularização com prazos; autuação em caso de descumprimento'),
('MP-04', 'Ausência de destinador licenciado',
 'Lei 12.305/2010',
 'Mapear capacidade instalada e identificar o vazio de infraestrutura'),
('MP-05', 'Ausência de destino final no país',
 'Destino final de rejeito radioativo atribuído à União/CNEN (Lei 10.308/2001)',
 'Priorizar na fila do depósito intermediário; acompanhar o definitivo'),
('MP-06', 'Material órfão, sem responsável identificado',
 'Custo recai sobre o poder público',
 'Inclusão em programa público de remediação, com priorização por risco'),
('MP-07', 'Passivo não identificado à época',
 'Responsabilidade imprescritível (Súmula 629 do STJ)',
 'Caracterização técnica e abertura de processo de regularização'),
('MP-08', 'Manifesto emitido sem baixa do destinador',
 'Ausência de baixa no prazo é irregularidade sujeita a autuação (SINIR/MTR)',
 'Rastrear a carga na cadeia gerador -> transportador -> destinador');
