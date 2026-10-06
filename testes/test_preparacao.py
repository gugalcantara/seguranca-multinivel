"""O instalador de um clique: cada decisão que ele toma, sem MySQL nem teclado.

Os casos vêm de tropeços reais de quem configurou o projeto: porta 3306 no
.env antigo, senha recusada pela política, banco ainda subindo, banco de uma
versão anterior. E da regra que não pode ser quebrada: uma CHAVE_CIFRAGEM que já
existe nunca é trocada — trocá-la tornaria ilegível o modelo com os rostos.
"""
import itertools

import pytest

import preparacao
from autenticacao import senha
from preparacao import (BancoDesatualizado, aguardar_banco, definir_no_env, pedir_senha_admin,
                        preparar, preparar_env, valor_no_env)

EXEMPLO = """# Copie para .env e preencha.
DB_HOST=127.0.0.1
# porta: 3307 com o Docker do projeto
DB_PORTA=3307
DB_SENHA=troque-esta-senha
CHAVE_CIFRAGEM=
# Gere com: python -m ferramentas hash-admin
ADMIN_SENHA_HASH=
"""


@pytest.fixture
def projeto(tmp_path):
    (tmp_path / ".env.exemplo").write_text(EXEMPLO, encoding="utf-8")
    return tmp_path


def chave_fixa():
    return b"chave-gerada-no-teste"


def silencio(*_):
    pass


# ------------------------------------------------------------------ .env
def test_cria_o_env_completo_a_partir_do_exemplo(projeto):
    preparar_env(projeto, pedir_senha=lambda: "$2b$hash", gerar_chave=chave_fixa, avisar=silencio)
    texto = (projeto / ".env").read_text(encoding="utf-8")
    assert valor_no_env(texto, "CHAVE_CIFRAGEM") == "chave-gerada-no-teste"
    assert valor_no_env(texto, "ADMIN_SENHA_HASH") == "$2b$hash"
    assert "# Gere com: python -m ferramentas hash-admin" in texto     # comentários preservados
    assert texto.index("DB_HOST") < texto.index("CHAVE_CIFRAGEM")      # e a ordem também


def test_rodar_de_novo_nao_muda_nada_nem_pede_senha(projeto):
    preparar_env(projeto, pedir_senha=lambda: "$2b$hash", gerar_chave=chave_fixa, avisar=silencio)
    antes = (projeto / ".env").read_text(encoding="utf-8")

    def nao_deveria_pedir():
        raise AssertionError("pediu senha de novo")

    assert preparar_env(projeto, pedir_senha=nao_deveria_pedir, avisar=silencio) is False
    assert (projeto / ".env").read_text(encoding="utf-8") == antes


def test_chave_de_cifragem_existente_nunca_e_trocada(projeto):
    """Trocar a chave tornaria o modelo facial ilegível — e as faces já foram descartadas."""
    (projeto / ".env").write_text(EXEMPLO.replace("CHAVE_CIFRAGEM=", "CHAVE_CIFRAGEM=a-chave-de-sempre"),
                                  encoding="utf-8")
    preparar_env(projeto, pedir_senha=lambda: "$2b$hash", gerar_chave=chave_fixa, avisar=silencio)
    assert valor_no_env((projeto / ".env").read_text(encoding="utf-8"), "CHAVE_CIFRAGEM") \
        == "a-chave-de-sempre"


def test_env_escrito_sem_bom_e_lido_mesmo_com_bom(projeto):
    """Um BOM no início vira parte do nome da primeira variável para o dotenv."""
    (projeto / ".env").write_text(EXEMPLO, encoding="utf-8-sig")          # editado num bloco de notas
    preparar_env(projeto, pedir_senha=lambda: "$2b$hash", gerar_chave=chave_fixa, avisar=silencio)
    assert not (projeto / ".env").read_bytes().startswith(b"\xef\xbb\xbf")


def test_definir_no_env_acrescenta_chave_ausente():
    assert valor_no_env(definir_no_env("A=1\n", "B", "2"), "B") == "2"


# ------------------------------------------------------------------ senha do administrador
def test_senha_e_pedida_ate_cumprir_a_politica_e_sai_como_hash():
    """Antes o comando recusava e ENCERRAVA; a pessoa recomeçava sem saber o que faltava."""
    respostas = iter(["123APS",                                  # fraca
                      "Unip#Aps2026", "Unip#Aps2027",            # não conferem
                      "Unip#Aps2026", "Unip#Aps2026"])           # ok
    avisos = []
    hash_ = pedir_senha_admin(entrada=lambda _: next(respostas), avisar=avisos.append)
    assert senha.verificar("Unip#Aps2026", hash_)
    assert any("Falta:" in a for a in avisos)
    assert any("não conferem" in a for a in avisos)


# ------------------------------------------------------------------ espera pelo banco
class Relogio:
    def __init__(self):
        self.agora = 0.0

    def __call__(self):
        return self.agora

    def dormir(self, segundos):
        self.agora += segundos


def test_espera_o_banco_subir_em_vez_de_falhar_na_primeira_tentativa():
    relogio = Relogio()
    tentativas = itertools.count()

    def conectar(porta):
        if next(tentativas) < 3:
            raise ConnectionError("ainda subindo")
        return True

    assert aguardar_banco(conectar, [3307], relogio=relogio, dormir=relogio.dormir,
                          avisar=silencio) == 3307


def test_desiste_com_mensagem_depois_do_prazo():
    relogio = Relogio()

    def nunca(porta):
        raise ConnectionError("recusada")

    with pytest.raises(TimeoutError, match="não respondeu"):
        aguardar_banco(nunca, [3307], timeout=10, relogio=relogio, dormir=relogio.dormir,
                       avisar=silencio)


def test_banco_desatualizado_nao_e_esperado_a_toa():
    """Esperar 2 minutos por algo que não vai se resolver sozinho seria pior que falhar já."""
    def antigo(porta):
        raise BancoDesatualizado("falta consentimento")

    with pytest.raises(BancoDesatualizado):
        aguardar_banco(antigo, [3307], avisar=silencio)


# ------------------------------------------------------------------ orquestração
def preparado(projeto, porta_no_env):
    (projeto / ".env").write_text(
        EXEMPLO.replace("DB_PORTA=3307", f"DB_PORTA={porta_no_env}")
               .replace("CHAVE_CIFRAGEM=", "CHAVE_CIFRAGEM=k")
               .replace("ADMIN_SENHA_HASH=", "ADMIN_SENHA_HASH=h"), encoding="utf-8")


def test_corrige_a_porta_3306_quando_o_banco_do_projeto_esta_na_3307(projeto, monkeypatch, capsys):
    """O tropeço do seu colega: na 3306 respondia OUTRO MySQL, com 'Access denied'."""
    monkeypatch.delenv("DB_PORTA", raising=False)
    preparado(projeto, 3306)

    def conectar(porta):
        if porta == 3306:
            raise PermissionError("1045 Access denied for user 'aps_app'@'localhost'")
        return True

    assert preparar(projeto, conectar=conectar, importar=lambda: 0) == 0
    assert valor_no_env((projeto / ".env").read_text(encoding="utf-8"), "DB_PORTA") == "3307"
    assert "corrigida de 3306 para 3307" in capsys.readouterr().out


def test_banco_de_versao_antiga_e_explicado_e_nada_e_apagado(projeto, capsys):
    preparado(projeto, 3307)

    def antigo(porta):
        raise BancoDesatualizado("falta consentimento")

    importados = []
    assert preparar(projeto, conectar=antigo, importar=lambda: importados.append(1)) == 1
    saida = capsys.readouterr().out
    assert "docker compose down -v" in saida and "APAGA" in saida      # diz o custo antes
    assert importados == []                                           # e não segue adiante


def test_tudo_pronto_devolve_zero_e_importa_o_acervo(projeto, capsys):
    preparado(projeto, 3307)
    assert preparar(projeto, conectar=lambda p: True, importar=lambda: 9) == 0
    assert "9 itens importados" in capsys.readouterr().out


def test_modo_silencioso_so_fala_quando_ha_problema(projeto, capsys):
    """O executar.bat roda isto toda vez; repetir "já estava pronto" seria ruído."""
    preparado(projeto, 3307)
    assert preparar(projeto, silencioso=True, conectar=lambda p: True, importar=lambda: 0) == 0
    assert capsys.readouterr().out.strip() == ""
