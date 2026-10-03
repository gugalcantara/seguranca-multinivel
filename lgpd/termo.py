"""Termo de consentimento para tratamento de dado biométrico (LGPD).

Imagem de rosto é dado pessoal **sensível** (Lei 13.709/2018, art. 5º, II), e o
tratamento de dado sensível exige consentimento **específico e destacado** para
finalidades determinadas (art. 11, I). Genérico não serve: a pessoa precisa saber
exatamente o que será coletado, para quê, por quanto tempo e como pedir a
exclusão.

Dois pontos sustentam o desenho deste módulo:

- **O ônus da prova é do controlador** (art. 8º, §2º): cabe a quem trata o dado
  demonstrar que obteve consentimento. Por isso o aceite é gravado com o HASH do
  texto — prova qual versão exata a pessoa leu, não apenas que clicou em algo.
- **O consentimento pode ser revogado a qualquer momento** (art. 8º, §5º), por
  procedimento gratuito e facilitado. Daí o módulo registrar a revogação em vez
  de simplesmente apagar a linha.

A ETP (4.5 e 12.3) exige termo assinado. Esta tela não substitui a assinatura:
ela informa, registra o aceite eletrônico e produz o documento para impressão.
"""
import hashlib
from datetime import datetime

VERSAO = "1.0"

CONTROLADOR = ("Grupo de Atividades Práticas Supervisionadas — Processamento de Imagens e "
               "Visão Computacional, Universidade Paulista (UNIP), 2026/2")

TITULO = "Termo de consentimento para uso de imagem facial"

SECOES = [
    ("1. Quem trata os seus dados", [
        f"Controlador: {CONTROLADOR}.",
        "Este é um trabalho acadêmico. Não há finalidade comercial, nem compartilhamento com "
        "terceiros, nem transferência internacional de dados.",
    ]),
    ("2. Que dado é coletado", [
        "Imagens do seu rosto, captadas pela webcam em duas sessões curtas, ou enviadas por você "
        "em arquivos de imagem.",
        "Do seu rosto é extraído e guardado apenas um MODELO MATEMÁTICO (histograma LBPH). "
        "As fotos originais NÃO são gravadas em disco: elas treinam o modelo na memória e são "
        "descartadas em seguida.",
        "São gravados também: seu nome, a matrícula gerada pelo sistema, o nível de acesso e a "
        "quantidade de amostras — nunca a imagem em si.",
    ]),
    ("3. Por que é coletado (finalidade específica)", [
        "Exclusivamente para desenvolver e avaliar este trabalho acadêmico: autenticar o acesso a "
        "um cadastro FICTÍCIO e medir o desempenho do reconhecimento facial.",
        "O dado não será usado para vigilância, controle de ponto, avaliação de desempenho ou "
        "qualquer finalidade diferente da descrita aqui.",
    ]),
    ("4. Base legal", [
        "Imagem de rosto é dado pessoal sensível (LGPD, art. 5º, II). O tratamento se apoia no seu "
        "CONSENTIMENTO específico e destacado (art. 11, I), manifestado neste termo.",
    ]),
    ("5. Por quanto tempo", [
        "Até a entrega e avaliação do trabalho, prevista para 12/11/2026.",
        "Depois disso, o modelo facial e o banco de dados são eliminados, com registro em ata.",
    ]),
    ("6. Como o dado é protegido", [
        "O modelo facial fica cifrado em disco (Fernet). A senha é guardada como hash bcrypt, "
        "nunca em texto legível.",
        "Tudo é local: nenhuma imagem sai desta máquina, não há nuvem nem serviço externo de "
        "reconhecimento.",
        "Uma tentativa de acesso NEGADA pode guardar a foto do momento, cifrada e com prazo de "
        "expiração, apenas para conferência de segurança.",
    ]),
    ("7. Seus direitos (LGPD, art. 18)", [
        "Confirmar que existe tratamento e acessar os seus dados.",
        "Corrigir dados incompletos ou desatualizados.",
        "Pedir a eliminação dos dados tratados com base no seu consentimento.",
        "Saber com quem os dados foram compartilhados — neste projeto, com ninguém.",
        "REVOGAR este consentimento a qualquer momento, por procedimento gratuito e simples "
        "(art. 8º, §5º). Basta comunicar um integrante do grupo: o cadastro é desativado e o "
        "modelo, regenerado sem as suas amostras.",
        "Recusar o consentimento sem qualquer prejuízo — a participação é voluntária.",
    ]),
    ("8. Limitações que você deve conhecer", [
        "Este é um protótipo acadêmico, com taxa de erro conhecida e não desprezível. Ele pode "
        "não reconhecer você (falsa rejeição) ou, menos provável, confundir você com outra pessoa.",
        "A base é pequena (6 a 8 pessoas) e pouco diversa, o que torna o desempenho desigual entre "
        "diferentes aparências. Isso está declarado no relatório.",
        "Toda negação de acesso pode ser conferida por um responsável humano. Nenhuma decisão é "
        "definitiva sem essa possibilidade de revisão.",
        "Biometria é irrevogável: senha vazada se troca, rosto não. Por isso o rosto nunca é fator "
        "único nos níveis 2 e 3, e o modelo fica cifrado.",
    ]),
]

ACEITE = ("Declaro que li e compreendi as informações acima, que tive oportunidade de esclarecer "
          "dúvidas, e que CONSINTO, de forma livre, informada e inequívoca, com o tratamento da "
          "minha imagem facial para a finalidade específica descrita neste termo.")


def texto_integral():
    """O termo completo, em texto puro — a forma que vai para o hash e o arquivo."""
    linhas = [TITULO, f"Versão {VERSAO}", ""]
    for titulo, paragrafos in SECOES:
        linhas.append(titulo)
        linhas.extend(f"   - {p}" for p in paragrafos)
        linhas.append("")
    linhas.append(ACEITE)
    return "\n".join(linhas)


def hash_termo():
    """Identifica a versão exata que a pessoa leu.

    Guardar só "aceitou v1.0" não provaria nada se o texto da v1.0 mudasse depois.
    O hash fixa o conteúdo.
    """
    return hashlib.sha256(texto_integral().encode("utf-8")).hexdigest()


def documento(nome, matricula=None, momento=None):
    """Via do titular, para imprimir ou guardar — com espaço para assinatura.

    A ETP (4.5 e 12.3) exige termo ASSINADO. O aceite em tela registra a
    manifestação; este documento é o que vai para o papel.
    """
    momento = momento or datetime.now()
    cabecalho = [
        "=" * 78,
        TITULO.upper().center(78),
        "=" * 78,
        "",
        f"Titular: {nome}",
    ]
    if matricula:
        cabecalho.append(f"Matrícula atribuída: {matricula}")
    cabecalho += [
        f"Data e hora do aceite: {momento:%d/%m/%Y às %H:%M:%S}",
        f"Versão do termo: {VERSAO}",
        f"Identificador do texto (SHA-256): {hash_termo()}",
        "",
        "-" * 78,
        "",
    ]
    rodape = [
        "",
        "-" * 78,
        "",
        "Assinatura do titular: ______________________________________________",
        "",
        "Nome legível: _______________________________________________________",
        "",
        f"Data: ____/____/________",
        "",
        "Este documento é a via do titular. O aceite eletrônico correspondente foi",
        "registrado no sistema com o identificador de texto acima, que permite",
        "verificar exatamente qual versão do termo foi apresentada.",
        "",
        "Para revogar o consentimento, comunique qualquer integrante do grupo.",
    ]
    return "\n".join(cabecalho + [texto_integral()] + rodape)
