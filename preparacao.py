"""Deixa o projeto pronto para abrir: .env, banco e acervo — num comando só.

Antes eram oito comandos e duas edições à mão no .env (copiar a chave e o hash
da senha), e cada colega tropeçou em algo diferente: porta errada, banco ainda
subindo, senha recusada pela política. Este módulo faz essas etapas e explica o
que fez. É chamado pelo instalar.bat e pelo executar.bat (`ferramentas preparar`).

Pode rodar quantas vezes quiser: cada etapa verifica o que já existe e só
completa o que falta. E NUNCA troca um valor que já está no .env — em especial a
CHAVE_CIFRAGEM: trocada, ela tornaria ilegível o modelo com os rostos já
cadastrados, e as faces originais foram descartadas (LGPD), então não haveria
como treinar de novo.

A parte de rede e banco recebe as funções de conexão por parâmetro, para que os
testes verifiquem cada decisão sem MySQL nem teclado.
"""
import getpass
import re
import sys
import time
from pathlib import Path

PORTA_DO_DOCKER = 3307          # a que o docker-compose.yml publica no host


# ------------------------------------------------------------------ .env
def valor_no_env(texto, chave):
    """Valor de CHAVE=valor no texto do .env, ou None se a linha não existir."""
    achado = re.search(rf"^{re.escape(chave)}=(.*)$", texto, re.M)
    return achado.group(1).strip() if achado else None


def definir_no_env(texto, chave, valor):
    """Troca o valor na linha existente, preservando comentários e a ordem."""
    linha = f"{chave}={valor}"
    if re.search(rf"^{re.escape(chave)}=.*$", texto, re.M):
        return re.sub(rf"^{re.escape(chave)}=.*$", lambda _: linha, texto, count=1, flags=re.M)
    return texto.rstrip("\n") + "\n" + linha + "\n"


def _escrever(caminho, texto):
    # UTF-8 SEM BOM: um BOM no início vira parte do nome da primeira variável
    caminho.write_text(texto, encoding="utf-8", newline="\n")


def preparar_env(raiz, pedir_senha, gerar_chave=None, avisar=print):
    """Cria e completa o .env. Devolve True se algo precisou ser feito."""
    raiz = Path(raiz)
    env, exemplo = raiz / ".env", raiz / ".env.exemplo"
    mudou = False
    if not env.exists():
        _escrever(env, exemplo.read_text(encoding="utf-8"))
        avisar("   .env criado a partir do .env.exemplo")
        mudou = True
    texto = env.read_text(encoding="utf-8-sig")       # tolera um BOM de edição manual

    if not valor_no_env(texto, "CHAVE_CIFRAGEM"):
        if gerar_chave is None:
            from cryptography.fernet import Fernet
            gerar_chave = Fernet.generate_key
        texto = definir_no_env(texto, "CHAVE_CIFRAGEM", gerar_chave().decode())
        avisar("   chave de cifragem gerada (protege o modelo facial em disco)")
        mudou = True

    if not valor_no_env(texto, "ADMIN_SENHA_HASH"):
        avisar("   defina a senha do administrador — ela abre o Painel de gerenciamento")
        texto = definir_no_env(texto, "ADMIN_SENHA_HASH", pedir_senha())
        avisar("   senha do administrador registrada (só o hash fica no .env)")
        mudou = True

    if mudou:
        _escrever(env, texto)
    return mudou


def pedir_senha_admin(entrada=None, avisar=print, minimo=12):
    """Pede a senha até ela cumprir a política, e devolve o HASH bcrypt.

    A política é a mesma do nível 3 e do `ferramentas hash-admin`. Antes, a
    pessoa digitava, o comando recusava e encerrava — e era preciso recomeçar
    sem saber direito o que faltava.
    """
    from autenticacao import senha
    if entrada is None:
        # getpass esconde a digitação, mas no Windows lê direto do console e
        # ignora dados vindos por pipe; fora de um terminal, usa input()
        entrada = getpass.getpass if sys.stdin.isatty() else input
    avisar(f"   (mínimo {minimo} caracteres, com maiúscula, minúscula, número e símbolo —"
           " ex.: Unip#Aps2026)")
    while True:
        primeira = entrada("   Senha do administrador: ")
        pendencias = senha.avaliar_senha_forte(primeira, minimo)
        if pendencias:
            avisar("   Falta: " + ", ".join(pendencias) + ". Tente de novo.")
            continue
        if entrada("   Repita a senha: ") != primeira:
            avisar("   As duas não conferem. Tente de novo.")
            continue
        return senha.gerar_hash(primeira)


# ------------------------------------------------------------------ banco
class BancoDesatualizado(RuntimeError):
    """O MySQL responde, mas o schema é de uma versão anterior do projeto."""


def aguardar_banco(conectar, portas, timeout=120.0, intervalo=3.0,
                   relogio=time.monotonic, dormir=time.sleep, avisar=print):
    """Tenta conectar até o banco responder. Devolve a porta que funcionou.

    `conectar(porta)` devolve True ou levanta exceção. O MySQL do Docker leva
    alguns segundos para rodar os scripts de criação na primeira subida: falhar
    na primeira tentativa é normal, não erro de configuração — antes, quem
    rodava o passo seguinte cedo demais achava que tinha configurado algo errado.
    """
    limite = relogio() + timeout
    ultimo_erro = None
    avisado = False
    while True:
        for porta in portas:
            try:
                if conectar(porta):
                    return porta
            except BancoDesatualizado:
                raise
            except Exception as erro:          # ainda subindo, porta errada etc.
                ultimo_erro = erro
        if relogio() >= limite:
            raise TimeoutError(f"o MySQL não respondeu em {timeout:.0f} s ({ultimo_erro})")
        if not avisado:
            avisar("   aguardando o MySQL ficar pronto (na primeira vez leva uns segundos)...")
            avisado = True
        dormir(intervalo)


def conectar_e_conferir(porta):
    """Conecta com a conta da aplicação e confere que o schema é o atual."""
    import configuracao
    from dados.conexao import Banco
    credenciais = {**configuracao.credenciais_banco(), "port": int(porta)}
    banco = Banco(credenciais, tamanho_pool=1)
    banco.consultar("SELECT 1 FROM nivel LIMIT 1")
    tabelas = {linha["t"] for linha in banco.consultar(
        "SELECT table_name AS t FROM information_schema.tables WHERE table_schema = DATABASE()")}
    if "consentimento" not in tabelas:
        raise BancoDesatualizado("falta a tabela consentimento")
    return True


# ------------------------------------------------------------------ orquestração
def preparar(raiz=None, silencioso=False, pedir_senha=None, conectar=None, importar=None):
    """As três etapas, com relato. Devolve 0 (pronto) ou 1 (precisa de ação)."""
    import configuracao
    raiz = Path(raiz or configuracao.RAIZ)
    falar = (lambda *_: None) if silencioso else print

    def etapa(titulo):
        falar(f"\n== {titulo}")

    etapa("Configuração (.env)")
    if not preparar_env(raiz, pedir_senha or (lambda: pedir_senha_admin()), avisar=print):
        falar("   já estava completo")

    etapa("Banco de dados")
    texto = (raiz / ".env").read_text(encoding="utf-8-sig")
    configurada = int(valor_no_env(texto, "DB_PORTA") or PORTA_DO_DOCKER)
    portas = [configurada] + ([PORTA_DO_DOCKER] if configurada != PORTA_DO_DOCKER else [])
    try:
        porta = aguardar_banco(conectar or conectar_e_conferir, portas, avisar=falar)
    except BancoDesatualizado:
        print("\n[!] O banco é de uma versão anterior do projeto (falta a tabela de consentimento).\n"
              "    Para recriá-lo — isso APAGA usuários e trilha do banco de demonstração:\n"
              "        docker compose down -v\n"
              "        docker compose up -d\n"
              "    e rode o instalar.bat de novo.")
        return 1
    except TimeoutError as erro:
        print(f"\n[!] Não consegui falar com o banco: {erro}\n"
              "    Confira se o Docker Desktop está aberto e rode o instalar.bat de novo.")
        return 1
    if porta != configurada:
        # o tropeço mais comum: .env antigo com 3306, que é a porta de um MySQL
        # instalado na máquina — e esse responde "Access denied", porque não
        # tem a conta do projeto
        texto = definir_no_env(texto, "DB_PORTA", str(porta))
        _escrever(raiz / ".env", texto)
        import os
        os.environ["DB_PORTA"] = str(porta)
        print(f"   DB_PORTA corrigida de {configurada} para {porta} no .env "
              "(é a porta do MySQL do projeto, no Docker)")
    falar(f"   MySQL pronto na porta {porta}")

    etapa("Acervo de exemplo")
    importados = (importar or importar_acervo_se_vazio)()
    falar(f"   {importados} itens importados" if importados else "   já estava importado")
    falar("\nTudo pronto.")
    return 0


def importar_acervo_se_vazio():
    """Importa o acervo só na primeira vez; devolve quantos itens importou."""
    import configuracao
    from acervo.repositorio_acervo import RepositorioAcervo
    from dados.conexao import Banco
    banco = Banco()
    if banco.consultar("SELECT id FROM item_acervo LIMIT 1"):
        return 0
    _, itens = RepositorioAcervo(banco).importar_metadados(configuracao.caminho("acervo_metadados"))
    return itens
