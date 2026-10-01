# O que falta fazer — APS PIVC 2026/2

Situação em **01/10/2026**. Legenda: ✅ feito · 🟡 parcial / precisa validar · ⬜ não iniciado.
Responsáveis conforme a ETP 9.1: **G** = Gustavo · **I2** = Integrante 2 · **I3** = Integrante 3.

---

## Marcos

| Data | Marco | Situação |
|---|---|---|
| 22/09 | ETP aprovada | conferir com o professor (ETP v3.2 pendente, ver abaixo) |
| 29/09 | Base facial + acervo mínimo | 🟡 acervo **sintético** pronto; base facial a confirmar com I3 — **marco já passou** |
| **13/10** | **Protótipo ponta a ponta + parcial no Teams** | 🟡 código pronto, falta rodar com câmera real |
| 27/10 | Experimentos concluídos | ⬜ scripts prontos, faltam dados |
| 03/11 | Dissertação final | ⬜ |
| 10/11 | Ensaio da apresentação | ⬜ |
| 12/11 | Entrega no site da UNIP | ⬜ |

---

## 1. Caminho crítico até 13/10 (nesta ordem)

- [ ] **G + I2** — Rodar `python verificar_ambiente.py` (com câmera) nas duas máquinas e colar o resultado no grupo.
- [ ] **G** — Limpar os usuários `TESTE-*` legados (resíduo das execuções anteriores à separação dos bancos):
      `python -m ferramentas limpar-operacao --confirmar`. Preserva o acervo; pede a senha do root do MySQL
      (no Docker, a padrão é `raiz-somente-local`).
- [ ] **G** — Em algum momento, recriar o container (`docker compose down -v && docker compose up -d`) para que
      o `GRANT` do banco de teste no `sql/03` fique permanente — hoje foi aplicado só na instância em execução.
- [ ] **G** — `git init`, criar o repositório no GitHub (combinar com o grupo se privado ou público), conferir o `.gitignore` e fazer o primeiro commit.
      Antes do commit: `git status` não pode listar `.env`, `modelo/`, `dados_faciais/` nem `*.yml` (R-07).
- [ ] **I2** — `python esqueleto.py SeuNome` com uma pessoa e depois com três. É a prova das 5 fases (passo 3 do Handoff).
      Anotar FPS, ms por frame e as distâncias típicas (mesma pessoa × outra pessoa).
- [ ] **I2** — Calibrar `[qualidade]` no `config.ini` com a câmera real. Os limiares de nitidez, brilho, contraste e
      ruído são palpites; se rejeitarem frames bons, o cadastro não termina.
- [ ] **G** — Subir o MySQL (`docker compose up -d`), preencher o `.env`, `importar-acervo`, e cadastrar pela
      **Administração** um usuário de cada nível + um segundo N3.
- [ ] **G** — Rodar os cenários N1 e N2 ao vivo, incluindo as negações (senha errada 3×, credencial alheia, nível insuficiente).
- [ ] **I2 + G** — Testar ao vivo o **desafio de vivacidade** (piscar e mover) e a **regra dos dois** no N3. Ajustar
      `[vivacidade]` se necessário. Esse fluxo ainda **não foi exercitado com câmera**.
- [ ] **G** — Ajustar os limiares provisórios de `[limiares]` só o suficiente para a demonstração (os definitivos vêm da curva DET).
- [ ] **Todos** — Gerar o relatório de linhas de código e postar a parcial no Teams (CA-06).

---

## 2. Por integrante

### Gustavo — arquitetura, banco, multifator, acervo, trilha, relatórios

| | Tarefa |
|---|---|
| ✅ | Estrutura de módulos, `config.ini`, `.env.exemplo`, `requirements.txt`, `.gitignore` |
| ✅ | Schema MySQL com camada causal, contas separadas (aplicação sem UPDATE/DELETE na trilha) |
| ✅ | Motor multifator, política de níveis, bcrypt, bloqueio, sessão N3 com tempo-limite |
| ✅ | Trilha encadeada SHA-256 + verificador (testado com adulteração real) |
| ✅ | Tarja, entrega, política de exportação, marca d'água LSB/DCT |
| ✅ | Interface Tkinter (inicial, autenticação, consulta, administração) |
| ✅ | Camada de tema (`interface/tema.py`): paleta, estilos ttk, `Cartao` e `Tabela` (Treeview ordenável) |
| ✅ | **Painel de gerenciamento** (`interface/painel.py`): visão geral com 6 indicadores, tabela de usuários com ativar/desativar auditado na trilha, motivos de negação. 10 testes em `testes/test_painel.py` |
| ✅ | **Cadastro por arquivos de imagem** (`JanelaImportarImagens` + `visao.coleta.coletar_de_arquivos`), com laudo por foto e `amostra.origem='imagem'`. 9 testes em `testes/test_coleta_imagens.py` |
| 🟡 | Migrar S-01 a S-07 da aba antiga de administração para o painel, em `Tabela`; depois remover `JanelaAdministracao` |
| ⚠️ | **A senha do administrador está como `123APS`**, por decisão de desenvolvimento (01/10/2026). Não cumpre a política do próprio sistema (12+ caracteres, maiúscula, minúscula, dígito e símbolo) e o hash foi gerado contornando o `ferramentas hash-admin`. **Regenerar antes da entrega** |
| ✅ | Testes de integração isolados em banco descartável (`DB_NOME_TESTE`), recriado de `sql/01`+`sql/02` a cada execução — o banco de demonstração não recebe mais usuários nem trilha de teste |
| ✅ | Matrícula gerada pelo sistema (`gerar_codigo_matricula`, 7 testes) e UF habilitada só no nível 2 |
| ✅ | Testes da vivacidade, do pipeline/segmentação e da máquina de estados do motor (43 testes novos; 140 no total) |
| ✅ | **Falha corrigida:** rosto saindo do quadro era contado como piscada no desafio do N3 (Haar devolve "sem olhos" para recorte vazio, sem erro). Novo parâmetro `[vivacidade] fracao_minima_rosto_visivel` |
| ⬜ | Calibrar `[qualidade]` também para FOTOS: os limiares são de webcam e podem recusar imagens boas de celular (ou aceitar demais). Vale medir com as fotos reais dos voluntários |
| 🟡 | Validar todo o fluxo da interface com câmera real (item 1) |
| ⬜ | **Relatórios gerados do banco.** Hoje os itens do acervo são imagens estáticas geradas uma vez. Os relatórios do catálogo (A1-02, A2-02, A3-01…) deveriam ser **renderizados do banco no momento da consulta** e então passar pela tarja: renderizar → regiões → tarja → marca d'água |
| ⬜ | Relatórios ainda ausentes: A1-03 Série histórica, A1-04 Ficha de substância, A2-02 Vencidas por região (hoje só como texto na aba Indicadores), A2-03 Dossiê do gerador, A2-05 Laudo, A3-03 Mapa de calor, A3-04 Projeção de capacidade |
| ⬜ | **Mapa A1-05 no nível 1:** os pontos continuam visíveis e revelam a localização aproximada, o que contradiz "sem localização". Trocar por densidade agregada por UF no N1, ou suprimir a área do mapa inteira |
| ⬜ | S-02: tela para ver a foto (decifrada) de uma tentativa negada, com acesso só do administrador — entra como aba do painel |
| ⬜ | Restringir o painel ao desenvolvedor (hoje usa a senha de administrador). O portão é `exigir_administrador()`, em `interface/comum.py` |
| ⬜ | Aplicar o tema às telas de autenticação e de consulta ao acervo (hoje só a inicial, o painel e o cadastro) |
| ⬜ | Fallback SQLite (contingência do Handoff 15) — só se o MySQL falhar em alguma máquina |
| ⬜ | Capítulo de projeto do programa na dissertação (arquitetura, modelo de dados, decisões do README) |
| ⬜ | Manual de operação (INC-16), incluindo o procedimento de **revisão humana** de negações (ETP 12.3) |

### Integrante 2 — visão, qualidade, vivacidade, inspeção, experimentos

| | Tarefa |
|---|---|
| ✅ | Módulos das 5 fases, portão de qualidade, KCF, LBPH 1:N/1:1 com `update()` |
| ✅ | Vivacidade (piscar / mover), inspeção ORB + SSIM, métricas e protocolo |
| 🟡 | Calibrar `[qualidade]`, `[vivacidade]` e `[rastreamento]` com câmera real |
| ⬜ | Capturar a base experimental (`python -m experimentos.capturar`) junto com o I3 |
| ⬜ | Rodar `python -m experimentos.executar`, levantar a **curva DET** e copiar os limiares sugeridos para `[limiares]` (princípio 9) |
| ⬜ | Linha de base Eigenfaces: já está no `executar.py`; analisar e comentar no capítulo de resultados |
| ⬜ | **Experimento da marca d'água** (ETP 7.2): escrever o script que aplica JPEG em 3 qualidades, redimensionamento, recorte e captura de tela, e mede a taxa de recuperação LSB × DCT. Hoje só há teste unitário com JPEG 75–95 |
| ⬜ | **Experimento de inspeção:** gerar os 20 pares (metade alterada) e medir a taxa de detecção. Há só um par em `acervo/itens/inspecao/` |
| ⬜ | Vivacidade: 10 tentativas com foto no celular (ETP 7.2) e registro dos resultados |
| ⬜ | Cronometrar 30 tentativas (RNF-01: ≤ 2 s; prévia ≥ 10 FPS) |
| ⬜ | Capítulo de fundamentos (5 fases do PDI, Haar, LBP, DCT, SSIM) |

### Integrante 3 — dados, acervo, dissertação

| | Tarefa |
|---|---|
| ⬜ | **Termo de autorização de uso de imagem** (LGPD art. 11), assinado **antes** de qualquer captura |
| ⬜ | Sessões de captura: 6–8 identidades + impostores. Ver a observação sobre sessões no item 4 |
| ⬜ | **Acervo real dos níveis 1 e 2** a partir das fontes públicas (SINIR, CETESB, CNEN, IBAMA), substituindo os itens sintéticos desses níveis. Editar `acervo/itens/metadados.json` com regiões em pixels, `sintetico: false`, `fonte` e `data_acesso_fonte` |
| ⬜ | Preencher AG e MP de cada pendência real (Camada Causal, passo 1) |
| ⬜ | Conferir os códigos CNAE em `sql/02_dados_iniciais.sql` (estão aproximados) |
| ⬜ | Seção do **ciclo do passivo** no capítulo de fundamentos (geração → manifesto → destinação → interrupção) |
| ⬜ | Introdução, objetivos, plano de desenvolvimento, ética e LGPD, formatação ABNT |
| ⬜ | Matriz de rastreabilidade completa (ETP 5.3). O README tem uma versão resumida para partir dela |
| ⬜ | Atas semanais; ata de **descarte** ao final (banco, modelo, `dados_faciais/`) |

---

## 3. Documentação: ETP v3.2

O que mudou desde a v3.1 e precisa entrar na ETP, com nova versão e registro em 11.1:

- [ ] **MC-03** — Camada causal, por exigência do professor: RF-19, RF-20 e RF-21; tabelas `atividade_geradora`,
      `motivo_permanencia`, `responsavel`, `pendencia`.
- [ ] **Renumerar o risco da Camada Causal:** o documento cria um "R-06" que já existe na ETP; deve virar **R-12**.
- [ ] **Modelo de dados:** decisões 1 a 6 do README (tabelas novas, `momento` pela aplicação, `DECIMAL`,
      `usuario2_id`/`evento`/`item_id`, limiar só no `config.ini`, `GET_LOCK`).
- [ ] **Exportação em PNG**, não PDF (decisão 7 do README); o catálogo e o Handoff falam em PDF.
- [ ] **6.4 Ferramentas:** registrar o `uv` como forma de obter o Python 3.11 e o Docker como opção de MySQL.
- [ ] **4.7 Divisão treino/teste:** com **duas** sessões por identidade, a divisão por sessão dá 50/50, não 70/30.
      Ou se capturam **três sessões** (→ 67/33, recomendado), ou a ETP passa a dizer 50/50.
- [ ] **12.2 / EXC-06:** declarar as limitações da vivacidade (item 4).

---

## 4. Limitações conhecidas (para declarar, não necessariamente corrigir)

- **Vivacidade:** o desafio de movimento barra fotos, mas um vídeo da pessoa fazendo o gesto pedido passaria (EXC-06).
  O piscar via Haar de olhos é instável com óculos e pode gerar falsa rejeição; documentar no capítulo de resultados.
- **DCT × redimensionamento/recorte:** a marca depende da grade 8×8; redimensionar ou recortar desalinha a grade e
  a extração deve falhar. É resultado experimental esperado (R-09), não defeito a esconder.
- **Nível 1 é 1:N sobre toda a galeria:** qualquer usuário cadastrado, de qualquer nível, entra no N1. Está correto
  pela regra "cada nível vê o que os de baixo veem", mas vale explicar na apresentação.
- **Foto de tentativa negada** só é guardada se `CHAVE_CIFRAGEM` estiver no `.env`; sem a chave, a foto é descartada
  (falha segura de privacidade).
- **Teste de integração** (`testes/test_integracao_banco.py`) grava registros `TESTE-*` no banco configurado. Use só em
  banco de desenvolvimento e rode `docker compose down -v` antes da demonstração para começar limpo.
- **Limiares provisórios:** enquanto não houver curva DET, qualquer número de FAR/FRR citado é inválido.
