"""Métricas biométricas (ETP 7.1).

Convenção: as entradas são DISTÂNCIAS LBPH. Aceita-se quando distancia <= limiar.
- FAR(l) = impostores aceitos / tentativas de impostores
- FRR(l) = genuínos rejeitados / tentativas genuínas
- EER   = ponto em que FAR = FRR (interpolado)
A curva DET plota FRR × FAR em escala de desvio normal (probit) — a escala
padrão em biometria, que torna as curvas aproximadamente retas.
"""
from statistics import NormalDist

import numpy as np


def far_frr(genuinas, impostoras, limiar):
    genuinas, impostoras = np.asarray(genuinas, float), np.asarray(impostoras, float)
    far = float((impostoras <= limiar).mean()) if impostoras.size else 0.0
    frr = float((genuinas > limiar).mean()) if genuinas.size else 0.0
    return far, frr


def curva_det(genuinas, impostoras, limiares=None):
    """Devolve (limiares, far[], frr[]) varrendo toda a faixa de distâncias observadas."""
    if limiares is None:
        todas = np.concatenate([np.asarray(genuinas, float), np.asarray(impostoras, float)])
        todas = todas[np.isfinite(todas)]
        limiares = np.unique(np.concatenate([[0.0], todas, [todas.max() + 1 if todas.size else 1.0]]))
    pares = [far_frr(genuinas, impostoras, l) for l in limiares]
    return np.asarray(limiares), np.array([p[0] for p in pares]), np.array([p[1] for p in pares])


def eer(genuinas, impostoras):
    """(eer, limiar_eer) com interpolação linear entre os dois limiares vizinhos."""
    limiares, far, frr = curva_det(genuinas, impostoras)
    diferenca = far - frr                       # cresce com o limiar
    i = int(np.argmax(diferenca >= 0))
    if i == 0:
        return float((far[0] + frr[0]) / 2), float(limiares[0])
    d0, d1 = diferenca[i - 1], diferenca[i]
    t = 0.0 if d1 == d0 else -d0 / (d1 - d0)
    taxa = far[i - 1] + t * (far[i] - far[i - 1])
    return float(taxa), float(limiares[i - 1] + t * (limiares[i] - limiares[i - 1]))


def limiar_para_far(impostoras, far_alvo):
    """Maior limiar cujo FAR não ultrapassa o alvo (ponto de operação do N2)."""
    impostoras = np.sort(np.asarray(impostoras, float))
    if impostoras.size == 0:
        return float("inf")
    permitidos = int(np.floor(far_alvo * impostoras.size))
    if permitidos == 0:
        return float(np.nextafter(impostoras[0], -np.inf))
    return float(np.nextafter(impostoras[permitidos], -np.inf))


def acuracia(reais, preditos):
    reais, preditos = np.asarray(reais), np.asarray(preditos)
    return float((reais == preditos).mean()) if reais.size else 0.0


def matriz_confusao(reais, preditos, rotulos=None):
    rotulos = list(rotulos if rotulos is not None else sorted(set(reais) | set(preditos)))
    indice = {r: i for i, r in enumerate(rotulos)}
    matriz = np.zeros((len(rotulos), len(rotulos)), dtype=int)
    for r, p in zip(reais, preditos):
        if r in indice and p in indice:
            matriz[indice[r], indice[p]] += 1
    return matriz, rotulos


def _probit(p, eps=1e-4):
    return NormalDist().inv_cdf(min(max(p, eps), 1 - eps))


def plotar_det(curvas, caminho, pontos_operacao=None):
    """curvas: {"LBPH 1:N": (far[], frr[]), ...}; pontos: {"N2": (far, frr)}."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    marcas = [0.001, 0.01, 0.05, 0.1, 0.2, 0.4]
    fig, ax = plt.subplots(figsize=(6.5, 6))
    for nome, (far, frr) in curvas.items():
        ax.plot([_probit(f) for f in far], [_probit(f) for f in frr], label=nome, linewidth=2)
    for nome, (far, frr) in (pontos_operacao or {}).items():
        ax.plot(_probit(far), _probit(frr), "o", markersize=8)
        ax.annotate(nome, (_probit(far), _probit(frr)), textcoords="offset points", xytext=(6, 6))
    ax.plot([_probit(0.001), _probit(0.4)], [_probit(0.001), _probit(0.4)], ":", color="gray", label="FAR = FRR")
    ticks = [_probit(m) for m in marcas]
    ax.set_xticks(ticks, [f"{m:.1%}" for m in marcas])
    ax.set_yticks(ticks, [f"{m:.1%}" for m in marcas])
    ax.set_xlim(ticks[0], ticks[-1])
    ax.set_ylim(ticks[0], ticks[-1])
    ax.set_xlabel("FAR — taxa de falsa aceitação")
    ax.set_ylabel("FRR — taxa de falsa rejeição")
    ax.set_title("Curva DET")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(caminho, dpi=150)
    plt.close(fig)
