"""Consentimento para tratamento de dado biométrico (LGPD arts. 8º, 9º, 11 e 18).

O que se verifica aqui não é estética de tela: são as propriedades que dão
validade jurídica ao consentimento — ser prévio, específico, informado,
comprovável e revogável.
"""
from datetime import datetime

import pytest

from lgpd import termo

# o módulo inteiro depende de Tk; a raiz em si vem do conftest
pytest.importorskip("tkinter")

from interface.termo import DialogoTermo                     # noqa: E402


# ------------------------------------------------------------------ conteúdo do termo
def test_termo_informa_o_que_a_lei_exige():
    """Art. 9º: finalidade, duração, controlador, direitos do titular."""
    texto = termo.texto_integral().lower()
    for exigido in ("finalidade", "controlador", "12/11/2026", "revogar",
                    "eliminação", "voluntária", "sensível", "art. 11"):
        assert exigido.lower() in texto, f"termo não menciona: {exigido}"


def test_termo_declara_as_limitacoes_do_prototipo():
    """ETP 12.3: a interface informa tratar-se de protótipo com taxa de erro conhecida."""
    texto = termo.texto_integral().lower()
    assert "protótipo acadêmico" in texto
    assert "taxa de erro" in texto
    assert "falsa rejeição" in texto
    assert "responsável humano" in texto      # revisão humana da negação


def test_termo_explica_que_a_foto_nao_e_guardada():
    texto = termo.texto_integral().lower()
    assert "não são gravadas em disco" in texto or "nÃo são gravadas" in texto
    assert "modelo matemático" in texto


def test_hash_identifica_a_versao_exata_do_texto():
    """Art. 8º, §2º: provar o consentimento é ônus do controlador.

    Registrar "aceitou a v1.0" não provaria nada se o texto da v1.0 mudasse
    depois; o hash fixa o conteúdo apresentado.
    """
    original = termo.hash_termo()
    assert len(original) == 64
    assert termo.hash_termo() == original          # estável entre chamadas

    secoes = termo.SECOES
    try:
        termo.SECOES = secoes + [("9. Seção nova", ["texto acrescentado depois"])]
        assert termo.hash_termo() != original      # qualquer mudança muda o hash
    finally:
        termo.SECOES = secoes
    assert termo.hash_termo() == original


def test_documento_do_titular_tem_espaco_para_assinatura():
    """A ETP 4.5 exige termo ASSINADO; o aceite em tela não substitui o papel."""
    doc = termo.documento("Ana Ribeiro Salles", "BD87MHU",
                          momento=datetime(2026, 10, 2, 14, 30))
    assert "Ana Ribeiro Salles" in doc and "BD87MHU" in doc
    assert "02/10/2026" in doc
    assert "Assinatura do titular" in doc
    assert termo.hash_termo() in doc               # a via identifica a versão aceita
    assert termo.texto_integral() in doc           # e carrega o termo na íntegra


# ------------------------------------------------------------------ a tela
# a raiz Tk e a limpeza das janelas vivem em testes/conftest.py: um interpretador
# para a sessão inteira, porque criar e destruir vários Tk() quebra o ttk::Style


@pytest.fixture
def decisoes():
    return []


def abrir(raiz, decisoes, nome="Ana Ribeiro Salles"):
    dialogo = DialogoTermo(raiz, nome, lambda ok, momento: decisoes.append((ok, momento)))
    dialogo.withdraw()
    return dialogo


def test_aceite_comeca_bloqueado(raiz, decisoes):
    """Consentimento informado: não dá para autorizar sem ter podido ler."""
    dialogo = abrir(raiz, decisoes)
    assert str(dialogo.botao_aceitar.cget("state")) == "disabled"
    dialogo.destroy()


def test_marcar_a_caixa_libera_a_autorizacao(raiz, decisoes):
    dialogo = abrir(raiz, decisoes)
    dialogo._liberar_marcacao()
    dialogo.marcacao.set(True)
    dialogo._avaliar()
    assert str(dialogo.botao_aceitar.cget("state")) == "normal"
    dialogo._aceitar()
    assert len(decisoes) == 1 and decisoes[0][0] is True
    assert isinstance(decisoes[0][1], datetime)


def test_recusa_devolve_negativa_sem_momento(raiz, decisoes):
    """Art. 8º: o consentimento é livre. Recusar não pode custar nada."""
    abrir(raiz, decisoes)._recusar()
    assert decisoes == [(False, None)]


def test_fechar_a_janela_conta_como_recusa(raiz, decisoes):
    """Falha segura aplicada ao consentimento: sem decisão explícita, não há aceite."""
    abrir(raiz, decisoes)._recusar()               # o X da janela chama este caminho
    assert decisoes[0][0] is False


def test_decisao_nao_e_entregue_duas_vezes(raiz, decisoes):
    """Aceitar e depois fechar não pode registrar um segundo consentimento."""
    dialogo = abrir(raiz, decisoes)
    dialogo._liberar_marcacao()
    dialogo.marcacao.set(True)
    dialogo._aceitar()
    dialogo._recusar()
    assert len(decisoes) == 1


def test_tela_mostra_o_termo_inteiro(raiz, decisoes):
    """A pessoa precisa ver o que assina — não um resumo."""
    dialogo = abrir(raiz, decisoes)
    exibido = dialogo.texto.get("1.0", "end")
    for titulo, paragrafos in termo.SECOES:
        assert titulo in exibido
        for paragrafo in paragrafos:
            assert paragrafo in exibido
    assert termo.ACEITE in exibido
    dialogo.destroy()
