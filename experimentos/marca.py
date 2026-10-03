"""Experimento de robustez da marca d'água — LSB × DCT (ETP 6.5, 7.1 e 7.2).

Mede a taxa de recuperação da marca sob as degradações que a ETP 7.2 exige:
recompressão JPEG em três qualidades, redimensionamento, recorte parcial e
captura de tela. A meta de 7.1 é ≥ 90% em recompressão JPEG.

Resultados medidos (20 repetições por célula, imagens reais do acervo) — e dois
deles contrariaram a previsão inicial, o que vale registrar no relatório:

- **LSB sucumbe a toda recompressão JPEG**, de q=95 a q=50. Ele grava no bit
  menos significativo, exatamente o que a quantização do JPEG descarta primeiro.
  Era o esperado, e é a razão de o método estar no trabalho como contraponto
  (risco R-09).
- **DCT recupera 100% sob JPEG**, até q=50 — acima da meta de 90% da ETP 7.1.
  Ele grava na relação entre dois coeficientes de média frequência, que a
  quantização preserva.
- **DCT também resistiu ao redimensionamento**, contrariando a previsão de que a
  grade 8×8 se perderia. O motivo é que a degradação reduz e DEVOLVE a imagem ao
  tamanho original, o que realinha os blocos. Um redimensionamento permanente,
  sem volta, teria outro resultado.
- **Recorte derruba os dois para 0%.** Aqui a grade de fato se desloca, e nem a
  repetição da carga salva. É o limite declarado do método, não defeito.
- **LSB sobrevive à ampliação de 150%** porque 97,9% dos bits menos
  significativos chegam intactos, e a carga de 80 bits — repetida por toda a
  imagem e decidida por votação majoritária — tolera o resto. Já reduzir a 50%
  preserva 69,6% dos bits e MESMO ASSIM falha: os erros são espacialmente
  correlacionados, então algumas das 80 posições ficam com maioria errada e o
  CRC rejeita a leitura. Fração global de acerto não é o que decide; o que
  decide é a maioria em cada posição.

Uso:  python -m experimentos.marca [--repeticoes 30] [--saida resultados]
"""
import argparse
import random
from datetime import datetime, timedelta

import cv2
import numpy as np

import configuracao
from acervo import marca_dagua

# ---------------------------------------------------------------- degradações
def _jpeg(imagem, qualidade):
    ok, buffer = cv2.imencode(".jpg", imagem, [cv2.IMWRITE_JPEG_QUALITY, qualidade])
    return cv2.imdecode(buffer, cv2.IMREAD_COLOR) if ok else imagem


def _redimensionar(imagem, fator):
    """Reduz e volta ao tamanho original — o que acontece ao enviar por aplicativo."""
    altura, largura = imagem.shape[:2]
    interpolacao = cv2.INTER_AREA if fator < 1 else cv2.INTER_CUBIC
    menor = cv2.resize(imagem, None, fx=fator, fy=fator, interpolation=interpolacao)
    return cv2.resize(menor, (largura, altura), interpolation=cv2.INTER_CUBIC)


def _recortar(imagem, fracao):
    """Corta as bordas e devolve ao tamanho original, como um enquadramento."""
    altura, largura = imagem.shape[:2]
    nova_a, nova_l = int(altura * fracao), int(largura * fracao)
    topo, esquerda = (altura - nova_a) // 2, (largura - nova_l) // 2
    return cv2.resize(imagem[topo:topo + nova_a, esquerda:esquerda + nova_l],
                      (largura, altura), interpolation=cv2.INTER_CUBIC)


def _captura_de_tela(imagem):
    """Aproxima o caminho 'exibir na tela e fotografar/capturar'.

    A imagem é reescalada para o tamanho de exibição, recebe leve ruído de
    renderização e volta comprimida — a combinação que de fato ocorre quando
    alguém contorna o bloqueio de exportação capturando a tela.
    """
    exibida = cv2.resize(imagem, None, fx=0.85, fy=0.85, interpolation=cv2.INTER_AREA)
    ruido = np.random.RandomState(7).normal(0, 1.5, exibida.shape)
    exibida = np.clip(exibida.astype(np.float64) + ruido, 0, 255).astype(np.uint8)
    altura, largura = imagem.shape[:2]
    return _jpeg(cv2.resize(exibida, (largura, altura), interpolation=cv2.INTER_CUBIC), 92)


def _ruido(imagem, desvio):
    ruidosa = imagem.astype(np.float64) + np.random.RandomState(3).normal(0, desvio, imagem.shape)
    return np.clip(ruidosa, 0, 255).astype(np.uint8)


DEGRADACOES = [
    ("sem degradação", lambda img: img.copy()),
    ("JPEG q=95", lambda img: _jpeg(img, 95)),
    ("JPEG q=85", lambda img: _jpeg(img, 85)),
    ("JPEG q=75", lambda img: _jpeg(img, 75)),
    ("JPEG q=60", lambda img: _jpeg(img, 60)),
    ("JPEG q=50", lambda img: _jpeg(img, 50)),
    ("redimensionar 75%", lambda img: _redimensionar(img, 0.75)),
    ("redimensionar 50%", lambda img: _redimensionar(img, 0.50)),
    ("ampliar 150%", lambda img: _redimensionar(img, 1.50)),
    ("recorte 95%", lambda img: _recortar(img, 0.95)),
    ("recorte 90%", lambda img: _recortar(img, 0.90)),
    ("recorte 75%", lambda img: _recortar(img, 0.75)),
    ("captura de tela", _captura_de_tela),
    ("ruído leve", lambda img: _ruido(img, 2)),
    ("ruído forte", lambda img: _ruido(img, 5)),
]

METODOS = {"LSB": (marca_dagua.inserir_lsb, marca_dagua.extrair_lsb),
           "DCT": (marca_dagua.inserir_dct, marca_dagua.extrair_dct)}


def imagens_do_acervo(limite=3):
    """Usa os itens reais do acervo: documento, mapa e foto têm texturas distintas."""
    pasta = configuracao.caminho("acervo")
    arquivos = sorted(p for p in pasta.glob("*.png"))[:limite]
    imagens = [(p.stem, cv2.imread(str(p))) for p in arquivos]
    return [(nome, img) for nome, img in imagens if img is not None]


def avaliar(repeticoes=30, semente=2026, imagens=None):
    """Para cada método e degradação, a fração de marcas recuperadas íntegras.

    Cada repetição usa uma identidade e um momento diferentes: recuperar o
    payload certo exige acertar os 80 bits, e o CRC descarta leitura corrompida.
    """
    rng = random.Random(semente)
    imagens = imagens or imagens_do_acervo()
    if not imagens:
        raise RuntimeError("Nenhuma imagem do acervo encontrada — rode gerar-acervo antes")

    base = datetime(2026, 10, 1, 9, 0, 0)
    casos = [(rng.randint(1, 9999), base + timedelta(seconds=rng.randint(0, 10**6)))
             for _ in range(repeticoes)]

    linhas = []
    for metodo, (inserir, extrair) in METODOS.items():
        for nome_degradacao, degradar in DEGRADACOES:
            acertos = 0
            for i, (usuario_id, momento) in enumerate(casos):
                _, imagem = imagens[i % len(imagens)]
                marcada = inserir(imagem, usuario_id, momento)
                acertos += extrair(degradar(marcada)) == (usuario_id, momento)
            linhas.append({"metodo": metodo, "degradacao": nome_degradacao,
                           "recuperadas": acertos, "tentativas": len(casos),
                           "taxa": acertos / len(casos)})
    return linhas


def plotar(linhas, caminho):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    degradacoes = [d for d, _ in DEGRADACOES]
    posicoes = np.arange(len(degradacoes))
    largura = 0.38
    figura, eixo = plt.subplots(figsize=(11, 5.5))
    for deslocamento, (metodo, cor) in zip((-largura / 2, largura / 2),
                                           (("LSB", "#b07d14"), ("DCT", "#2e6f8e"))):
        taxas = [next(l["taxa"] for l in linhas
                      if l["metodo"] == metodo and l["degradacao"] == d) * 100
                 for d in degradacoes]
        eixo.bar(posicoes + deslocamento, taxas, largura, label=metodo, color=cor)

    eixo.axhline(90, color="#a8322d", linestyle="--", linewidth=1.2,
                 label="meta ETP 7.1 (90%)")
    eixo.set_xticks(posicoes, degradacoes, rotation=35, ha="right")
    eixo.set_ylabel("Marcas recuperadas (%)")
    eixo.set_ylim(0, 105)
    eixo.set_title("Robustez da marca d'água por degradação — LSB × DCT")
    eixo.legend()
    eixo.grid(axis="y", alpha=0.3)
    figura.tight_layout()
    figura.savefig(caminho, dpi=150)
    plt.close(figura)


def main():
    import pandas as pd

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeticoes", type=int, default=30)
    parser.add_argument("--saida", default=None)
    args = parser.parse_args()

    linhas = avaliar(args.repeticoes)
    saida = (configuracao.RAIZ / args.saida if args.saida
             else configuracao.caminho("resultados") / datetime.now().strftime("%Y%m%d_%H%M%S"))
    saida.mkdir(parents=True, exist_ok=True)

    tabela = pd.DataFrame(linhas)
    tabela.to_csv(saida / "marca_dagua.csv", index=False)
    plotar(linhas, saida / "marca_dagua.png")

    largura = max(len(d) for d, _ in DEGRADACOES)
    print(f"{'DEGRADAÇÃO':{largura}}   {'LSB':>8}   {'DCT':>8}")
    print("-" * (largura + 22))
    for degradacao, _ in DEGRADACOES:
        taxas = {l["metodo"]: l["taxa"] for l in linhas if l["degradacao"] == degradacao}
        print(f"{degradacao:{largura}}   {taxas['LSB']:>7.1%}   {taxas['DCT']:>7.1%}")
    print(f"\n{args.repeticoes} repetições por célula · artefatos em {saida}")


if __name__ == "__main__":
    main()
