"""Métricas biométricas e divisão treino/teste por sessão."""
import numpy as np

from experimentos import metricas
from experimentos.protocolo import dividir_por_sessao


def test_far_frr_distancia_menor_aceita():
    genuinas = [10, 20, 30, 80]
    impostoras = [50, 60, 90, 100]
    far, frr = metricas.far_frr(genuinas, impostoras, 55)
    assert far == 0.25 and frr == 0.25


def test_eer_em_conjuntos_separaveis_e_zero():
    taxa, limiar = metricas.eer([10, 12, 15], [50, 60, 70])
    assert taxa == 0.0 and 15 <= limiar <= 50


def test_eer_com_sobreposicao():
    rng = np.random.RandomState(0)
    taxa, _ = metricas.eer(rng.normal(40, 8, 500), rng.normal(70, 8, 500))
    assert 0.02 < taxa < 0.06       # duas gaussianas separadas por 3,75 sigma -> EER ~ 3%


def test_limiar_para_far():
    impostoras = np.arange(1, 101, dtype=float)          # 100 impostores
    limiar = metricas.limiar_para_far(impostoras, 0.05)
    far, _ = metricas.far_frr([], impostoras, limiar)
    assert far <= 0.05 and far >= 0.04
    assert metricas.far_frr([], impostoras, metricas.limiar_para_far(impostoras, 0.0))[0] == 0.0


def test_matriz_confusao():
    m, rotulos = metricas.matriz_confusao([1, 1, 2, 2], [1, 2, 2, 2])
    assert rotulos == [1, 2] and m.tolist() == [[1, 1], [0, 2]]


def test_divisao_por_sessao_nao_vaza_frames():
    identidades, sessoes = [], []
    for ident in range(1, 7):
        for sessao in ("s1", "s2", "s3"):
            identidades += [ident] * 10
            sessoes += [sessao] * 10
    treino, teste = dividir_por_sessao(identidades, sessoes, 0.3, semente=2026)
    grupos_treino = {(identidades[i], sessoes[i]) for i in treino}
    grupos_teste = {(identidades[i], sessoes[i]) for i in teste}
    assert not grupos_treino & grupos_teste                          # nenhuma sessão nos dois lados
    assert {g[0] for g in grupos_treino} == set(range(1, 7))         # toda identidade no treino
    assert {g[0] for g in grupos_teste} == set(range(1, 7))          # estratificado
    assert dividir_por_sessao(identidades, sessoes, 0.3, 2026) == (treino, teste)   # semente fixa


def test_identidade_com_uma_sessao_fica_no_treino():
    treino, teste = dividir_por_sessao([1, 1, 2, 2], ["a", "a", "a", "b"], 0.5, 1)
    assert set(treino) >= {0, 1} and not {0, 1} & set(teste)
