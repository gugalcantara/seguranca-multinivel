"""Matrícula gerada pelo sistema (não escolhida pela pessoa).

A matrícula é DIGITADA no login dos níveis 2 e 3. Por isso o código evita os
caracteres que se confundem ao ler de um papel, e por isso estes testes travam
o alfabeto: trocá-lo por conveniência quebraria a legibilidade na prática.
"""
import random

import pytest

from dados.repositorio import (DIGITOS_MATRICULA, LETRAS_MATRICULA, RepositorioUsuarios,
                               gerar_codigo_matricula)

AMBIGUOS = set("IO01")


def test_tamanho_respeitado():
    for tamanho in (5, 6, 7, 10):
        assert len(gerar_codigo_matricula(tamanho)) == tamanho


def test_nao_usa_caracteres_ambiguos():
    """I/1 e O/0 são o par que mais gera erro de digitação."""
    gerados = "".join(gerar_codigo_matricula() for _ in range(2000))
    assert not (set(gerados) & AMBIGUOS)
    assert set(gerados) <= set(LETRAS_MATRICULA + DIGITOS_MATRICULA)


def test_sempre_mistura_letra_e_digito():
    """Só dígitos pareceria um número de documento; só letras, uma sigla."""
    for _ in range(500):
        codigo = gerar_codigo_matricula()
        assert any(c in LETRAS_MATRICULA for c in codigo)
        assert any(c in DIGITOS_MATRICULA for c in codigo)


def test_codigo_e_sorteado_e_nao_sequencial():
    codigos = {gerar_codigo_matricula() for _ in range(5000)}
    assert len(codigos) > 4990          # colisão é rara, não sistemática


def test_rng_proprio_torna_o_codigo_reproduzivel():
    """Um rng injetado permite teste determinístico sem fixar o algoritmo."""
    assert gerar_codigo_matricula(7, random.Random(42)) == \
           gerar_codigo_matricula(7, random.Random(42))


# ------------------------------------------------------------------ unicidade
class RepositorioFalso(RepositorioUsuarios):
    """Finge que as matrículas em `existentes` já estão no banco."""

    def __init__(self, existentes):
        self.existentes = set(existentes)
        self.consultas = 0

    def por_matricula(self, matricula):
        self.consultas += 1
        return {"id": 1} if matricula in self.existentes else None


def test_nova_matricula_pula_as_ja_usadas(monkeypatch):
    sequencia = iter(["AAA2222", "BBB3333", "CCC4444"])
    monkeypatch.setattr("dados.repositorio.gerar_codigo_matricula",
                        lambda *a, **k: next(sequencia))
    repo = RepositorioFalso({"AAA2222", "BBB3333"})
    assert repo.nova_matricula(tamanho=7) == "CCC4444"
    assert repo.consultas == 3


def test_desiste_depois_de_muitas_tentativas(monkeypatch):
    """Falha explícita é melhor que laço infinito quando o espaço se esgota."""
    monkeypatch.setattr("dados.repositorio.gerar_codigo_matricula", lambda *a, **k: "REPETIDO")
    repo = RepositorioFalso({"REPETIDO"})
    with pytest.raises(RuntimeError, match="tamanho_matricula"):
        repo.nova_matricula(tamanho=7, tentativas=5)
    assert repo.consultas == 5
