# Controle de acesso multinível por reconhecimento facial

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![OpenCV](https://img.shields.io/badge/OpenCV-contrib%204.10-5C3EE8?logo=opencv&logoColor=white)
![MySQL](https://img.shields.io/badge/MySQL-8.0-4479A1?logo=mysql&logoColor=white)
![Testes](https://img.shields.io/badge/testes-140%20passando-1f7a4d)

Aplicação desktop em Python que protege um cadastro **fictício** de materiais perigosos ainda não recolhidos —
resíduo químico Classe I, rejeito radioativo, áreas contaminadas. O acesso combina **senha e reconhecimento
facial ao vivo**, com exigência crescente em três níveis, e o conteúdo é entregue com **tarja adaptativa** e
**marca d'água invisível**. Toda tentativa, consulta e exportação entra numa **trilha de auditoria encadeada por
hash**.

> A ideia central não é "reconhecer rostos". É que **o grau de confiança que a visão computacional entrega
> determina quanta informação o pixel pode revelar.**

<p align="center">
  <img src="docs/imagens/01-tela-inicial.png" width="560" alt="Tela inicial com os três níveis de acesso">
</p>

---

## Os três níveis

| Nível | Quem | Fatores exigidos | Modo facial | O que vê | Exporta |
|---|---|---|---|---|---|
| **1** | Servidores | face | **1:N** | agregados, sem localização | livre |
| **2** | Diretores | matrícula + senha → face | **1:1** | registros da própria UF | com marca d'água |
| **3** | Ministro | + senha forte + desafio na câmera + **segunda pessoa** | **1:1** (limiar mais duro) | visão nacional | **bloqueado** |

O mesmo item do acervo é servido de formas diferentes conforme o nível: no `A1-05 Mapa de Densidade`, as
coordenadas aparecem borradas no nível 1, legíveis no 2, e a instalação de custódia só no 3 — e a supressão é
aplicada **antes** de a imagem chegar à interface, não como um retângulo desenhado por cima.

---

## As cinco fases do processamento de imagens

```
Aquisição  →  Pré-processamento  →  Segmentação  →  Extração  →  Classificação
 (thread +     (cinza, CLAHE,       (Haar + KCF)    (LBPH)       (distância ao
  fila 1)       ruído, 200×200)                                   modelo + limiar)
                          ↓
                 portão de qualidade  (nitidez, brilho, contraste, ruído)
```

- **Aquisição** roda em thread com fila de tamanho 1: o frame antigo é descartado quando chega um novo, então a
  latência nunca se acumula mesmo se o reconhecimento for mais lento que a câmera.
- **Qualidade é medida no recorte cru**, antes do CLAHE — o realce mascara justamente a imagem escura e sem
  contraste que o portão existe para barrar.
- **LBPH devolve distância, não similaridade**: aceita-se quando `distancia <= limiar`. Inverter esse sinal
  inverteria a política de segurança inteira, e há teste dedicado a isso.
- **Haar roda a cada N frames**; entre duas detecções o **KCF** acompanha a ROI, que custa uma fração do custo.

---

## Painel de gerenciamento

<p align="center">
  <img src="docs/imagens/02-painel-visao-geral.png" width="760" alt="Painel com indicadores de monitoramento">
</p>

Acompanha o estado do sistema sem abrir o banco na mão: usuários por nível, amostras, negativas nas últimas 24 h,
bloqueios ativos, integridade da cadeia de hash e — o indicador mais útil — a **divergência entre o modelo LBPH
em memória e as amostras registradas no banco**, que denuncia modelo perdido, recriado com outra chave ou
cadastro interrompido.

<p align="center">
  <img src="docs/imagens/03-painel-usuarios.png" width="760" alt="Aba de usuários com ficha e ações">
</p>

Desativar um usuário **não** apaga amostras nem retira a face do modelo: a política passa a negar pelo motivo
`USUARIO_INATIVO`, e o ato entra na mesma cadeia de hash dos acessos — é decisão auditável, não configuração
silenciosa.

---

## Cadastro

<p align="center">
  <img src="docs/imagens/04-novo-usuario.png" width="520" alt="Formulário de novo usuário">
  <img src="docs/imagens/05-cadastro-por-imagens.png" width="520" alt="Cadastro a partir de arquivos de imagem">
</p>

A matrícula é **gerada pelo sistema**, nunca escolhida: o alfabeto exclui `I`, `O`, `0` e `1` — os caracteres que
mais se confundem ao ler de um crachá — porque ela é digitada no login dos níveis 2 e 3.

As faces podem vir da **webcam** (duas sessões, com iluminações distintas) ou de **arquivos de imagem**. As fotos
passam pelo mesmo Haar e pelo mesmo portão de qualidade da captura ao vivo; a tela devolve um laudo por foto
dizendo *por que* cada uma foi recusada (*muito escura*, *fora de foco*, *mais de um rosto na foto*).

---

## Instalação

**Requisitos:** Python 3.11, MySQL 8 (ou Docker) e uma webcam.

```bash
# 1. ambiente — o uv baixa o 3.11 sem mexer no Python do sistema
uv venv --python 3.11 .venv
uv pip install --python .venv/Scripts/python.exe -r requirements.txt

# 2. banco
docker compose up -d        # sobe o MySQL na porta 3307 e cria o schema

# 3. credenciais
cp .env.exemplo .env
python -m ferramentas gerar-chave     # cole em CHAVE_CIFRAGEM
python -m ferramentas hash-admin      # cole em ADMIN_SENHA_HASH

# 4. acervo de exemplo
python -m ferramentas importar-acervo

# 5. conferir o ambiente (webcam, FPS, LBPH, KCF)
python verificar_ambiente.py
```

> ⚠️ **A armadilha nº 1 do projeto:** é preciso `opencv-contrib-python`. O `opencv-python` comum **não tem
> `cv2.face`** (LBPH), e os dois no mesmo ambiente conflitam em silêncio. O `requirements.txt` já está correto —
> não instale outro OpenCV por cima.

Sem Docker, execute `sql/01_schema.sql`, `sql/02_dados_iniciais.sql` e `sql/03_usuarios.sql` como root, nessa ordem.

---

## Como usar

| Comando | O que faz |
|---|---|
| `python main.py` | Aplicação completa. Comece pelo **Painel de gerenciamento** e cadastre os usuários |
| `python esqueleto.py Gustavo Ana` | **Prova das 5 fases sem banco**: captura, treina em memória e reconhece ao vivo mostrando nome, distância, ms e FPS |
| `python -m pytest` | Os 140 testes |
| `python -m ferramentas verificar-trilha` | Verifica a cadeia de hash e aponta onde ela foi rompida |
| `python -m ferramentas extrair-marca ARQ.png` | Recupera quem exportou um arquivo, e quando |
| `python -m ferramentas inspecionar REF ATUAL` | Compara duas fotos de acondicionamento (ORB + SSIM) |
| `python -m experimentos.executar` | Gera curva DET, matriz de confusão e os limiares sugeridos |

O `esqueleto.py` é o caminho mais rápido para ver o projeto funcionando: não precisa de banco nenhum.

### Roteiro de demonstração

1. **Painel** → cadastrar um N1, um N2 com UF `SP` e **dois** N3 (a regra dos dois exige duas identidades).
2. **Nível 1** → só a face → abrir `A1-05`: coordenadas e custódia borradas.
3. **Nível 2** → mesmo mapa com as coordenadas visíveis → exportar → `extrair-marca` recupera quem exportou.
4. **Nível 3** → senha forte + face + desafio + segunda pessoa → mapa completo, exportação bloqueada, sessão com
   tempo-limite.
5. **Negações:** senha errada 3× (bloqueio), face de outra pessoa com a senha certa (credencial alheia), N1
   tentando o N2.
6. **Adulteração:** alterar um registro de `log_acesso` como root → `verificar-trilha` aponta o `id` exato.

---

## Arquitetura

```
visao/         aquisicao · preprocessamento · segmentacao · qualidade · extracao · pipeline · coleta
autenticacao/  politica (decisão pura) · senha (bcrypt) · vivacidade (desafio) · motor (orquestração)
dados/         conexao · repositorio · auditoria (cadeia SHA-256) · relatorios_sistema · manutencao
acervo/        tarja · marca_dagua (LSB/DCT) · inspecao (ORB/SSIM) · entrega · repositorio_acervo
interface/     tema (paleta, Cartao, Tabela) · painel · autenticacao · relatorios · cadastro
experimentos/  protocolo (divisão por sessão) · metricas (FAR/FRR/EER/DET) · executar · capturar
sql/           schema com camada causal · dados de referência · contas separadas
```

Três escolhas que sustentam o resto:

**A decisão de acesso é uma função pura.** `autenticacao/politica.py` recebe as evidências já coletadas e devolve
concedido/negado. Não toca em câmera nem em banco — por isso tem 20 testes isolados. A regra que a governa é a
falha segura: evidência ausente (`None`) conta como fator **não** cumprido, e não existe caminho em que a falta
de informação conceda acesso.

**A aplicação não consegue reescrever o passado.** A conta `aps_app` tem apenas `SELECT` e `INSERT` em
`log_acesso` — sem `UPDATE` nem `DELETE`. O encadeamento usa `GET_LOCK` em vez de `SELECT … FOR UPDATE`
justamente para não precisar desse privilégio. Adulterar a trilha exige a conta administrativa, e mesmo assim a
cadeia de hash denuncia e **localiza** a alteração.

**A supressão acontece antes da entrega.** `acervo/tarja.py` aplica filtro gaussiano de núcleo grande sobre uma
cópia; a interface nunca recebe o pixel original de uma região que o nível não autoriza.

---

## Decisões de projeto

Pontos em que a implementação divergiu do plano inicial, e por quê:

1. **`log_acesso.momento` é gravado pela aplicação**, em `DATETIME(6)`. Com `DEFAULT CURRENT_TIMESTAMP`, o momento
   que entra no hash poderia diferir do gravado e a verificação falharia.
2. **`distancia` e `qualidade` em `DECIMAL`.** `FLOAT` perde precisão na volta do banco e quebra a recomputação do hash.
3. **A verificação 1:1 usa o `StandardCollector`** do OpenCV, filtrando pela identidade informada. É verificação de
   fato, não um `predict()` com o rótulo comparado depois.
4. **A divisão treino/teste é por sessão de captura, não por frame.** Frames da mesma sessão são quase idênticos;
   espalhá-los entre treino e teste infla a acurácia. Implementada à mão, equivalente ao `GroupShuffleSplit`.
5. **A marca DCT comprime a luminância em ±12 níveis antes da inserção.** Sem isso o fundo branco dos documentos
   satura em 255 e apaga a marca.
6. **O painel dimensiona tabelas pela métrica da fonte, não em pixels.** Largura e altura fixas truncam o texto em
   monitor com escala de DPI — 100% na máquina de quem desenvolve, 150% na de quem apresenta.
7. **Os testes de integração têm banco próprio**, recriado a cada execução. Antes sujavam o banco de demonstração,
   e limpar depois era impossível sem quebrar a cadeia: `usuario_id` entra no hash e a FK prende o usuário.
8. **A exportação gera PNG, não PDF.** LSB e DCT marcam pixels; um PDF exigiria rasterizar.

### Uma falha encontrada pelos testes

Quando o rosto encosta na borda do quadro, o KCF devolve retângulo com coordenada negativa, e a fatia da metade
superior sai **vazia**. O Haar de olhos responde "nenhum olho" para imagem vazia **sem levantar erro** — então os
frames eram contados como olhos fechados, e bastava aparecer e sair de cena para o sistema dar a piscada por
vista, cumprindo o desafio de vivacidade sem piscar.

A correção limita o recorte à imagem e exige que ao menos 60% dele esteja dentro do quadro; abaixo disso o frame é
*inconclusivo*, não "olhos fechados". É um caso concreto de detector que falha em silêncio — e de por que testar
função de segurança exige cobrir a entrada degenerada, não só o caminho feliz.

---

## Privacidade e LGPD

- Imagens faciais **nunca vão para disco** no fluxo da aplicação: ficam em memória, treinam o modelo e são
  descartadas. O modelo é salvo **cifrado** (Fernet) em `modelo/lbph.yml.enc`.
- Fotos de tentativas negadas são guardadas **cifradas** e com prazo de expiração.
- Todo o conteúdo do acervo é **sintético** — empresas, municípios e coordenadas inventados — e aparece com a
  faixa permanente "DADO FICTÍCIO".
- O `.gitignore` bloqueia `.env`, `modelo/`, `dados_faciais/`, `*.yml` e dumps do banco.
- Captura de rostos só mediante **termo de autorização de uso de imagem** assinado (LGPD art. 11).

---

## Estado atual e limitações

**Funciona e está testado:** política de níveis, trilha encadeada com adulteração localizada, tarja, marca d'água
LSB/DCT, inspeção ORB+SSIM, métricas FAR/FRR/EER, painel, cadastro por webcam e por imagens.

**Ainda não validado com câmera real:** o reconhecimento ao vivo, o desafio de vivacidade e a regra dos dois ponta
a ponta. O código existe e tem testes, mas com imagens sintéticas.

**Os limiares são provisórios.** Enquanto a curva DET não for levantada com a base real, qualquer número de
FAR/FRR citado é inválido — os valores em `[limiares]` são palpites conservadores.

**A vivacidade não é anti-spoofing robusto.** O desafio barra fotografia estática, mas um vídeo da pessoa fazendo
o gesto pedido passaria. A piscada via Haar de olhos é instável com óculos.

---

## Contexto

Trabalho da disciplina de **Processamento de Imagens e Visão Computacional** — UNIP, 2026/2.

Todos os parâmetros ficam em [`config.ini`](config.ini); nenhum valor fixo no código. As pendências e os próximos
passos estão em [`TAREFAS.md`](TAREFAS.md).
