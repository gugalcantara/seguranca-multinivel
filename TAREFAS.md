# O que falta fazer — APS PIVC 2026/2

Situação em **03/10/2026**. Legenda: ✅ feito · 🟡 parcial / precisa validar · ⬜ não iniciado.
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
- [x] **G** — ~~Recriar o banco~~ — feito em 04/10, durante a auditoria: o banco de demonstração não tinha a
      tabela `consentimento`, o que tornava IMPOSSÍVEL cadastrar alguém. Recriado com o schema atual (inclui a
      restrição `ck_usuario_n2_tem_uf`), privilégios e acervo corrigido do A1-05. Antes, backup do banco antigo
      (0 usuários, 3 registros de trilha de teste).
- [x] **G** — ~~Limpar os usuários `TESTE-*` legados~~ — feito em 01/10 com `limpar-operacao --confirmar`;
      o banco ficou com 0 usuários e o acervo preservado.
- [x] **G** — ~~Tornar permanente o `GRANT` do banco de teste~~ — resolvido com a recriação acima.
- [x] **G** — ~~`git init` e primeiro commit no GitHub~~ — feito: `gugalcantara/seguranca-multinivel`.
- [ ] **G** — **Commitar o trabalho desde então.** Há um único commit no repositório e dezenas de arquivos
      alterados desde ele (LGPD, responsividade, correções de retenção de imagem, 107 testes novos).
      Antes do commit: `git status` não pode listar `.env`, `modelo/`, `dados_faciais/` nem `*.yml` (R-07).
- [ ] **I2** — `python esqueleto.py SeuNome` com uma pessoa e depois com três. É a prova das 5 fases (passo 3 do Handoff).
      Anotar FPS, ms por frame e as distâncias típicas (mesma pessoa × outra pessoa).
- [ ] **I2** — Calibrar `[qualidade]` no `config.ini` com a câmera real. Os limiares de nitidez, brilho, contraste e
      ruído são palpites; se rejeitarem frames bons, o cadastro não termina.
- [ ] **G** — Subir o MySQL (`docker compose up -d`), preencher o `.env`, `importar-acervo`, e cadastrar pela
      **Painel de gerenciamento** um usuário de cada nível + um segundo N3.
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
| ✅ | Interface Tkinter (inicial, autenticação, consulta, cadastro, termo de consentimento) |
| ✅ | Camada de tema (`interface/tema.py`): paleta, estilos ttk, `Cartao` e `Tabela` (Treeview ordenável) |
| ✅ | **Painel de gerenciamento** (`interface/painel.py`): visão geral com 6 indicadores, tabela de usuários com ativar/desativar auditado na trilha, motivos de negação. 10 testes em `testes/test_painel.py` |
| ✅ | **Cadastro por arquivos de imagem** (`JanelaImportarImagens` + `visao.coleta.coletar_de_arquivos`), com laudo por foto e `amostra.origem='imagem'`. 9 testes em `testes/test_coleta_imagens.py` |
| ✅ | S-01 a S-07 e as Ferramentas migrados para o painel em `Tabela` ordenável; `JanelaAdministracao` removida e a tela inicial passou a ter um caminho administrativo único |
| ⚠️ | **A senha do administrador está como `123APS`**, por decisão de desenvolvimento (01/10/2026). Não cumpre a política do próprio sistema (12+ caracteres, maiúscula, minúscula, dígito e símbolo) e o hash foi gerado contornando o `ferramentas hash-admin`. **Regenerar antes da entrega** |
| ✅ | Testes de integração isolados em banco descartável (`DB_NOME_TESTE`), recriado de `sql/01`+`sql/02` a cada execução — o banco de demonstração não recebe mais usuários nem trilha de teste |
| ✅ | Matrícula gerada pelo sistema (`gerar_codigo_matricula`, 7 testes) e UF habilitada só no nível 2 |
| ✅ | Testes da vivacidade, do pipeline/segmentação e da máquina de estados do motor (43 testes novos) |
| ✅ | **Suíte de fluxo de uso** (`testes/test_fluxos_de_uso.py`, 38 testes): o cadastro do começo ao fim, no caminho certo e nos caminhos de quem desiste, fecha a janela errada ou clica duas vezes. Cobre `_concluir`, que grava o usuário, treina o modelo e apaga a biometria — e não tinha nenhum teste. **246 testes no total** |
| ✅ | **Raiz Tk única para a sessão de testes** (`testes/conftest.py`). Três módulos criavam e destruíam o próprio `Tk()`; o terceiro encontrava o interpretador Tcl quebrado e caía num `skip`. A suíte de telas sumia do relatório **sem acusar falha** — o pior desfecho possível para testes de regressão |
| ✅ | **Falha corrigida:** rosto saindo do quadro era contado como piscada no desafio do N3 (Haar devolve "sem olhos" para recorte vazio, sem erro). Novo parâmetro `[vivacidade] fracao_minima_rosto_visivel` |
| ⬜ | Calibrar `[qualidade]` também para FOTOS: os limiares são de webcam e podem recusar imagens boas de celular (ou aceitar demais). Vale medir com as fotos reais dos voluntários |
| 🟡 | Validar todo o fluxo da interface com câmera real (item 1) |
| ⬜ | **Relatórios gerados do banco.** Hoje os itens do acervo são imagens estáticas geradas uma vez. Os relatórios do catálogo (A1-02, A2-02, A3-01…) deveriam ser **renderizados do banco no momento da consulta** e então passar pela tarja: renderizar → regiões → tarja → marca d'água |
| ⬜ | Relatórios ainda ausentes: A1-03 Série histórica, A1-04 Ficha de substância, A2-02 Vencidas por região (hoje só como texto na aba Indicadores), A2-03 Dossiê do gerador, A2-05 Laudo, A3-03 Mapa de calor, A3-04 Projeção de capacidade |
| ✅ | **Mapa A1-05 no nível 1** corrigido: a área de plotagem virou região sensível de nível 2. Descoberto no caminho que o borrão gaussiano preserva o centroide (pico do resíduo a 0 px do ponto real), então rótulos de posição passaram a usar supressão sólida — ver `[tarja] rotulos_supressao_total` |
| ✅ | `importar-acervo --recriar` troca o acervo do banco. Recusa quando a trilha já tem consultas apontando para os itens — apagá-los seria reescrever o passado; nesse caso o caminho é `limpar-operacao` antes |
| ✅ | **Adequação à LGPD:** termo de consentimento prévio antes da captura (`lgpd/termo.py` + `interface/termo.py`), com via para salvar/imprimir; tabela `consentimento` guardando o hash do texto aceito (art. 8º, §2º); revogação no painel (art. 8º, §5º); relatório de consentimentos. 14 testes em `testes/test_lgpd.py` e no de integração |
| ✅ | **Correções da auditoria de 04/10.** (1) Consentimento passou a ser fator da decisão de acesso, e "Reativar" recusa quem revogou — antes, dois cliques devolviam o acesso a um rosto ainda presente no modelo, sem base legal. (3) Nível 2 sem UF falhava ABERTO (via todas as regiões); agora o filtro vale sempre e o schema recusa o estado com `CHECK`. (4) Fotos de tentativas negadas são eliminadas sozinhas ao abrir o programa e de hora em hora — o prazo de 7 dias era só um rótulo. (2) Banco de demonstração recriado. Todas as correções verificadas por mutação (10/10) |
| ⬜ | **Pendências da auditoria ainda abertas:** senha `123APS` publicada neste repositório e no README; privilégio excessivo da conta da aplicação sobre o acervo (pode apagar `regiao_sensivel`); dependências com vulnerabilidades conhecidas (cryptography, Pillow, mysql-connector, python-dotenv, pytest — versões fixadas pela ETP); log de erros com id e distância biométrica, sem rotação; 7 importações sem uso |
| ✅ | **Orientação ao usuário (RNF-02):** checklist antes da captura, moldura de enquadramento desenhada no vídeo, aviso de distância e centralização, mensagens de qualidade acionáveis ("acenda uma luz à sua frente" em vez de "imagem escura"), erros de câmera e de inicialização com o que verificar. 8 testes em `testes/test_orientacao.py` |
| ✅ | **Vazamento corrigido:** a mensagem de `CREDENCIAL_ALHEIA` confirmava que a senha estava certa. Agora falha de identidade responde sempre igual na tela; a distinção fica só no motivo gravado na trilha |
| ✅ | **Regra dos dois virou configurável** (`[autenticacao] exigir_segunda_pessoa`). Desligada no repositório: o N3 passa a bastar UMA pessoa, porque exigir duas presentes trava cada teste. Desligada, o fator sai da exigência, da faixa de etapas e dos fatores gravados na trilha — não vira fator "cumprido" que não foi. O resto do N3 (senha forte, 1:1 com limiar duro, vivacidade, sessão com prazo) continua valendo, com testes que garantem isso |
| ⚠️ | **Decidir se a regra dos dois volta ligada na entrega.** A ETP a descreve como requisito do N3 (RF-08). Se for demonstrá-la, basta `exigir_segunda_pessoa = true` no `config.ini` e cadastrar DOIS usuários de nível 3. Se ficar desligada, declarar isso na dissertação como decisão de implementação, não como ausência |
| ✅ | **Otimização guiada por medição.** O gargalo não era a detecção (Haar 12 ms, só a cada 5 quadros) nem o acervo (≤ 47 ms por item), e sim o LBPH: modelo de 215 MB levando ~4 s para gravar e carregar, e 1:1 de 42 ms/quadro crescendo com a galeria (150 ms com 30 pessoas, abaixo dos 10 FPS do RNF-01). Agora: 18,7 MB, ~1,3 s / ~1,4 s, e 1:1 de ~11 ms constante, com distâncias idênticas às do OpenCV. A medição anterior de "~9 ms/quadro, sem gargalo" foi feita sem modelo treinado e não valia para o uso real |
| ✅ | **Interface mais agradável**, a partir de capturas de cada tela: códigos do banco exibidos como texto legível ("Credencial alheia" em vez de CREDENCIAL_ALHEIA — só na tela; trilha e ordenação seguem com o código); formulário de cadastro com campos alinhados, nível com nome, checklist de senha ao vivo e "Mostrar senha"; "Tentar novamente" também quando a webcam falha; ficha causal somente leitura e "Exportar" habilitado só com item aberto; orientação nos espaços vazios da consulta; atalhos 1/2/3, Ctrl+P e Esc em todas as janelas; uma autenticação aberta por vez |
| ✅ | **Instalação em dois cliques** (`instalar.bat` e `executar.bat`), a pedido do grupo. Antes: 3 programas, 8 comandos e 2 edições à mão no `.env`. O instalador acha um Python 3.11 cujo `tkinter` carrega (evita o bloqueio do Smart App Control), cria o `.venv`, abre o Docker e espera o banco, gera a chave e pede a senha validando a política, corrige `DB_PORTA` 3306→3307 e detecta banco de versão antiga. Testado numa cópia limpa do projeto: instalação do zero em 34 s, janela aberta pelo `executar.bat`. Lógica em `preparacao.py`, 13 testes |
| ⬜ | S-02: tela para ver a foto (decifrada) de uma tentativa negada, com acesso só do administrador — entra como aba do painel |
| ⬜ | Restringir o painel ao desenvolvedor (hoje usa a senha de administrador). O portão é `exigir_administrador()`, em `interface/comum.py` |
| ✅ | **Portão administrativo equiparado ao login comum:** senha errada conta para o mesmo contador de bloqueio e entra na trilha (`ADMIN_SENHA_INCORRETA` / `ADMIN_AUTENTICADO` / `ADMIN_BLOQUEADO`). Era a única porta do sistema que podia ser tentada infinitas vezes sem travar e sem rastro. Cancelar o diálogo não conta como tentativa |
| ✅ | **Retenção de imagem facial corrigida em três caminhos** (LGPD art. 6º, III e V; ETP 4.3): fechar a importação de imagens pelo X, fechar o formulário de cadastro durante a captura, e falhar no meio do cadastro. O descarte saiu do botão e foi para o evento `<Destroy>`, por onde toda saída passa |
| ✅ | **Cadastro ficou atômico:** se o modelo não puder ser salvo depois de o usuário já existir no banco, ele é **desativado**. Antes ficava ativo sem rosto no modelo salvo, e isso só apareceria na próxima tentativa de acesso dele |
| ✅ | **Regra dos dois não fica mais em aberto:** desistir com a primeira pessoa já autenticada registra o desfecho na trilha. Na auditoria, acesso em aberto é indistinguível de acesso concedido |
| ✅ | **Duplo clique em «Concordo e autorizo»** abria duas janelas de captura para a mesma pessoa; `_aceitar` ganhou a guarda que `_recusar` já tinha |
| ✅ | **Revogação de consentimento em ordem segura:** desativa o cadastro ANTES de revogar. Na ordem inversa, uma falha no meio deixaria o cadastro ativo com o consentimento baixado — tratamento de dado sensível sem base legal |
| ✅ | **Responsividade:** o botão de avançar entre as sessões de captura saía da tela em monitor com escala de DPI. Controles passaram a ser ancorados na base antes do vídeo, que recebe a sobra **medida**. Vale para as cinco janelas; há testes que recusam janela maior que a tela ou botão fora do quadro |
| ✅ | **Verificação por mutação** das correções acima: cada bug foi reintroduzido de propósito e a suíte tinha de acusar. 14/14 detectadas; duas revelaram testes que passavam com e sem o bug, e foram reescritos |
| ✅ | **Experiência do reconhecimento:** medidor com quadros confirmados, distância × limiar e tempo restante na autenticação; barra de progresso e diagnóstico dos descartes ("7 repetidas, 3 desfocadas") na captura do cadastro; Esc fecha as janelas |
| ✅ | Tema aplicado a TODAS as telas. A autenticação ganhou faixa de etapas derivada de `FATORES_POR_NIVEL`; a consulta ao acervo passou a usar `Tabela` na lista de itens e nos indicadores |
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
| ✅ | **Experimento da marca d'água** (`experimentos/marca.py`): 15 degradações, LSB × DCT, CSV e gráfico. DCT 100% sob JPEG até q=50 e sob captura de tela; recorte derruba ambos. Dois achados contrariaram a previsão — ver README |
| ✅ | **Experimento de inspeção** (`experimentos/inspecao_pares.py`): 20 pares, 4 tipos de alteração. Sensibilidade 100%, falso positivo 0%. Achado: o SSIM global não dispara nenhuma detecção — quem acusa é a análise de regiões, e o limiar de SSIM está folgado demais para alterações localizadas |
| ⬜ | **Recalibrar `[inspecao] limiar_ssim`** ou trocar a métrica por SSIM mínimo local: medido 0,98 nos pares alterados contra limiar 0,90, ou seja, ele nunca age |
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
- **Teste de integração** (`testes/test_integracao_banco.py`) usa o banco descartável `DB_NOME_TESTE`, recriado a
  cada execução. O banco de demonstração não é mais tocado por `pytest`.
- **Limiares provisórios:** enquanto não houver curva DET, qualquer número de FAR/FRR citado é inválido.
- **A sessão de captura não tem prazo.** É proposital — ninguém deve ser barrado por demorar — mas significa que
  em condição ruim a contagem pode ficar parada indefinidamente. A mitigação é orientar: passados alguns
  segundos sem amostra aceita, a tela sugere o ajuste conforme o descarte dominante. Se na prática com câmera
  real isso não bastar, o passo seguinte é oferecer "encerrar a sessão com o que já foi coletado".
- **Um lote de imagens em que nada é aceito consome o número da sessão** (grava 2 e 3 em vez de 1 e 2). Não
  corrigido de propósito: numerar de novo criaria dois lotes com o mesmo rótulo na tabela, e a divisão
  treino/teste da ETP 4.7 só exige que as sessões sejam distintas, não contíguas.
