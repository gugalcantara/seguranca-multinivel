"""Utilitários de linha de comando.

    python -m ferramentas gerar-chave        # chave Fernet para CHAVE_CIFRAGEM no .env
    python -m ferramentas hash-admin         # hash bcrypt para ADMIN_SENHA_HASH no .env
    python -m ferramentas gerar-acervo       # 9 itens sintéticos + metadados.json
    python -m ferramentas importar-acervo    # metadados.json -> MySQL (--recriar troca o acervo)
    python -m ferramentas verificar-trilha   # S-04: integridade da cadeia de hash
    python -m ferramentas extrair-marca ARQ  # S-07: quem exportou este arquivo?
    python -m ferramentas inspecionar REF ATUAL [--saida mapa.png]   # M-03
    python -m ferramentas expurgar-fotos     # apaga fotos de tentativas negadas expiradas
    python -m ferramentas limpar-operacao --confirmar   # zera usuários/trilha, preserva o acervo
    python -m ferramentas preparar           # .env + banco + acervo, num passo (usado pelo instalar.bat)
"""
import argparse
import getpass
import sys

import configuracao


def preparar(args):
    import preparacao
    sys.exit(preparacao.preparar(silencioso=args.silencioso))


def gerar_chave(_):
    from cryptography.fernet import Fernet
    print(Fernet.generate_key().decode())


def hash_admin(_):
    from autenticacao import senha
    primeira = getpass.getpass("Senha do administrador: ")
    pendencias = senha.avaliar_senha_forte(primeira, 12)
    if pendencias:
        sys.exit("Senha fraca — falta: " + ", ".join(pendencias))
    if getpass.getpass("Confirme: ") != primeira:
        sys.exit("As senhas não conferem.")
    print(senha.gerar_hash(primeira))


def gerar_acervo(_):
    from acervo.gerar_exemplos import gerar
    destino, n_pend, n_itens = gerar()
    print(f"{n_itens} itens e {n_pend} pendências sintéticas gerados em {destino}")


def _banco():
    from dados.conexao import Banco
    return Banco()


def importar_acervo(args):
    """Importa metadados.json. Com --recriar, apaga o acervo atual antes.

    A recriação é necessária quando o acervo muda (regiões sensíveis novas, ou a
    troca dos itens sintéticos pelos reais): item_acervo.codigo é UNIQUE, então
    importar por cima falharia.
    """
    from acervo.repositorio_acervo import RepositorioAcervo

    if getattr(args, "recriar", False):
        _recriar_acervo(args)
    n_pend, n_itens = RepositorioAcervo(_banco()).importar_metadados(
        configuracao.caminho("acervo_metadados"))
    print(f"Importados: {n_pend} pendências, {n_itens} itens")


def _recriar_acervo(args):
    import mysql.connector

    from dados.manutencao import acervo_em_uso, limpar_acervo

    credenciais = configuracao.credenciais_banco()
    credenciais["user"] = args.usuario
    credenciais["password"] = args.senha if args.senha is not None else \
        getpass.getpass(f"Senha de {args.usuario}@MySQL: ")
    conexao = mysql.connector.connect(**credenciais)
    try:
        cursor = conexao.cursor()
        em_uso = acervo_em_uso(cursor)
        if em_uso:
            sys.exit(
                f"[FALHA] A trilha tem {em_uso} registro(s) de consulta ou exportação apontando\n"
                f"        para itens do acervo. Apagar os itens exigiria apagar esses registros —\n"
                f"        ou seja, reescrever o passado para trocar o conteúdo.\n\n"
                f"        Para seguir, zere a operação primeiro (o acervo é reimportável):\n"
                f"            python -m ferramentas limpar-operacao --confirmar")
        removidos = limpar_acervo(cursor)
        conexao.commit()
        print("Acervo anterior removido: "
              + ", ".join(f"{n} {tabela}" for tabela, n in removidos.items() if n))
    finally:
        conexao.close()


def verificar_trilha(_):
    from dados.auditoria import TrilhaAuditoria
    r = TrilhaAuditoria(_banco()).verificar()
    if r.integra:
        print(f"[ OK ] Cadeia íntegra — {r.total} registros verificados")
    else:
        sys.exit(f"[FALHA] Ruptura no registro id={r.id_ruptura} ({r.tipo}): {r.detalhe}")


def extrair_marca(args):
    import cv2
    from acervo import marca_dagua
    imagem = cv2.imread(args.arquivo)
    if imagem is None:
        sys.exit("Não foi possível abrir a imagem")
    resultado = marca_dagua.extrair(imagem)
    if resultado is None:
        sys.exit("Nenhuma marca d'água recuperável")
    metodo, usuario_id, momento = resultado
    print(f"Marca {metodo.upper()}: usuario_id={usuario_id}, momento={momento:%d/%m/%Y %H:%M:%S}")


def inspecionar(args):
    import cv2
    from acervo.inspecao import inspecionar as inspecionar_imagens
    r = inspecionar_imagens(cv2.imread(args.referencia), cv2.imread(args.atual))
    print(f"Alterado: {r.alterado} | SSIM: {r.similaridade:.4f} | alinhado: {r.alinhado} "
          f"({r.correspondencias} correspondências) | regiões: {r.regioes}")
    if args.saida:
        cv2.imwrite(args.saida, r.mapa_diferenca)


def expurgar_fotos(_):
    from dados.auditoria import TrilhaAuditoria
    print(f"{TrilhaAuditoria(_banco()).expurgar_fotos_expiradas()} fotos expiradas removidas")


def limpar_operacao(args):
    """Zera usuários, amostras, bloqueios e trilha; preserva o acervo.

    Exige conta administrativa: a conta da aplicação não tem DELETE em
    log_acesso nem em usuario — é essa restrição que o RF-13 demonstra.
    """
    import mysql.connector

    from dados.manutencao import (TABELAS_DE_OPERACAO, TABELAS_PRESERVADAS,
                                  contar, limpar_operacao as executar)

    credenciais = configuracao.credenciais_banco(args.banco)
    credenciais["user"] = args.usuario
    credenciais["password"] = args.senha if args.senha is not None else \
        getpass.getpass(f"Senha de {args.usuario}@MySQL: ")

    conexao = mysql.connector.connect(**credenciais)
    try:
        cursor = conexao.cursor()
        antes = contar(cursor, TABELAS_DE_OPERACAO)
        print(f"Banco: {credenciais['database']}")
        for tabela, n in antes.items():
            print(f"  {tabela:20s} {n:>6} registro(s)")
        if not sum(antes.values()):
            return print("\nNada a remover.")
        if not args.confirmar:
            return print("\nNada foi alterado. Repita com --confirmar para apagar de fato.")

        removidos = executar(cursor)
        conexao.commit()
        print("\nRemovidos:")
        for tabela, n in removidos.items():
            print(f"  {tabela:20s} {n:>6}")
        print("\nPreservado (acervo):")
        for tabela, n in contar(cursor, TABELAS_PRESERVADAS).items():
            print(f"  {tabela:20s} {n:>6}")
        print("\nA trilha recomeça do GENESIS: a cadeia volta a verificar íntegra.")
    finally:
        conexao.close()


def main():
    parser = argparse.ArgumentParser(prog="python -m ferramentas", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="comando", required=True)
    for nome, funcao in (("gerar-chave", gerar_chave), ("hash-admin", hash_admin),
                         ("gerar-acervo", gerar_acervo),
                         ("verificar-trilha", verificar_trilha), ("expurgar-fotos", expurgar_fotos)):
        sub.add_parser(nome).set_defaults(funcao=funcao)

    p = sub.add_parser("preparar", help="cria/completa o .env, espera o banco e importa o acervo")
    p.add_argument("--silencioso", action="store_true", help="só fala se algo precisar de atenção")
    p.set_defaults(funcao=preparar)

    p = sub.add_parser("importar-acervo", help="carrega metadados.json no MySQL")
    p.add_argument("--recriar", action="store_true",
                   help="apaga o acervo atual antes de importar (exige conta administrativa)")
    p.add_argument("--usuario", default="root", help="conta administrativa, para --recriar")
    p.add_argument("--senha", default=None, help="senha; se omitida, é pedida sem eco")
    p.set_defaults(funcao=importar_acervo)
    p = sub.add_parser("extrair-marca")
    p.add_argument("arquivo")
    p.set_defaults(funcao=extrair_marca)
    p = sub.add_parser("inspecionar")
    p.add_argument("referencia")
    p.add_argument("atual")
    p.add_argument("--saida")
    p.set_defaults(funcao=inspecionar)

    p = sub.add_parser("limpar-operacao",
                       help="zera usuários, amostras, bloqueios e trilha; preserva o acervo")
    p.add_argument("--confirmar", action="store_true",
                   help="sem esta opção, apenas mostra o que seria removido")
    p.add_argument("--usuario", default="root", help="conta administrativa do MySQL (padrão: root)")
    p.add_argument("--senha", default=None, help="senha; se omitida, é pedida sem eco")
    p.add_argument("--banco", default=None, help="banco alvo (padrão: DB_NOME do .env)")
    p.set_defaults(funcao=limpar_operacao)
    args = parser.parse_args()
    from dados.conexao import BancoIndisponivel
    try:
        args.funcao(args)
    except BancoIndisponivel as erro:
        sys.exit(f"[FALHA] {erro}\n        O MySQL está rodando (docker compose up -d)? "
                 f"DB_PORTA no .env é 3307 para o Docker.")
    except RuntimeError as erro:
        sys.exit(f"[FALHA] {erro}")


if __name__ == "__main__":
    main()
