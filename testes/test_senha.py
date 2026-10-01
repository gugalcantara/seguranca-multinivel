"""RF-06: bcrypt com sal; verificação segura."""
from autenticacao import senha


def test_hash_e_verificacao():
    h = senha.gerar_hash("Correta#123", custo=4)
    assert h.startswith("$2b$04$") and "Correta" not in h
    assert senha.verificar("Correta#123", h)
    assert not senha.verificar("errada", h)


def test_sal_torna_hashes_distintos():
    assert senha.gerar_hash("igual", custo=4) != senha.gerar_hash("igual", custo=4)


def test_hash_corrompido_ou_vazio_nega():
    assert not senha.verificar("x", "nao-e-bcrypt")
    assert not senha.verificar("x", None)
    assert not senha.verificar("", senha.gerar_hash("x", custo=4))


def test_custo_padrao_e_12():
    assert senha.CUSTO == 12


def test_politica_senha_forte():
    assert senha.avaliar_senha_forte("Abcdefgh1!xy", 12) == []
    pendencias = senha.avaliar_senha_forte("abc", 12)
    assert len(pendencias) == 4
