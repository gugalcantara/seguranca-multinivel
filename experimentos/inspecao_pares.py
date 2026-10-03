"""Experimento do módulo de inspeção de acondicionamento (ETP 7.1, 7.2 e RF-16).

A ETP pede 20 pares de imagens, metade com alteração simulada controlada, e
estabelece meta de detecção ≥ 90%. Mede-se aqui o que importa num detector:

- **sensibilidade** — das alterações reais, quantas foram vistas;
- **falso positivo** — dos pares ÍNTEGROS, quantos foram acusados à toa.

Os dois juntos, nunca só o primeiro: um detector que acusa tudo tem 100% de
sensibilidade e é inútil. Por isso metade dos pares não tem alteração alguma —
só o deslocamento e a rotação de câmera que o alinhamento ORB deve absorver.

Uso:  python -m experimentos.inspecao_pares [--pares 20] [--saida resultados]
"""
import argparse
import random
from datetime import datetime

import cv2
import numpy as np

import configuracao
from acervo.gerar_exemplos import ALTURA, LARGURA, _tambores
from acervo.inspecao import inspecionar

FUNDO = lambda: np.full((ALTURA, LARGURA, 3), 250, np.uint8)      # noqa: E731


# ---------------------------------------------------------------- alterações
def _lacre_rompido(img, rng):
    """O caso-alvo do RF-16: o selo de um tambor desapareceu."""
    return _tambores(FUNDO(), deslocamento=_tremor(rng), angulo=_angulo(rng),
                     lacre_rompido=True)


def _vazamento(img, rng):
    """Mancha escura no piso — indício de derramamento."""
    saida = img.copy()
    centro = (rng.randint(200, 700), rng.randint(450, 600))
    eixos = (rng.randint(45, 80), rng.randint(25, 45))
    cv2.ellipse(saida, centro, eixos, rng.randint(0, 180), 0, 360, (35, 40, 55), -1)
    return saida


def _tambor_removido(img, rng):
    """Um tambor some da cena — perda de carga."""
    saida = img.copy()
    x = rng.choice((180, 400, 620))
    cv2.rectangle(saida, (x - 6, 180), (x + 156, 445), (150, 150, 140), -1)
    return saida


def _rotulo_trocado(img, rng):
    """Identificação do lote adulterada."""
    saida = img.copy()
    x = rng.choice((180, 400, 620))
    cv2.rectangle(saida, (x + 15, 265), (x + 140, 300), (30, 110, 160), -1)
    cv2.putText(saida, "LOTE-X9", (x + 20, 292), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                (255, 255, 255), 2)
    return saida


ALTERACOES = [("lacre rompido", _lacre_rompido), ("vazamento", _vazamento),
              ("tambor removido", _tambor_removido), ("rótulo trocado", _rotulo_trocado)]


def _tremor(rng):
    """Deslocamento de câmera entre a foto de referência e a de verificação."""
    return (rng.randint(-18, 18), rng.randint(-12, 12))


def _angulo(rng):
    return rng.uniform(-2.5, 2.5)


def gerar_pares(quantidade=20, semente=2026):
    """Metade íntegros (só tremor de câmera), metade alterados."""
    rng = random.Random(semente)
    referencia = _tambores(FUNDO())
    pares = []
    for i in range(quantidade):
        alterado = i % 2 == 1
        if alterado:
            rotulo, aplicar = ALTERACOES[(i // 2) % len(ALTERACOES)]
            atual = aplicar(_tambores(FUNDO(), deslocamento=_tremor(rng), angulo=_angulo(rng)), rng)
        else:
            rotulo = "íntegro (só tremor de câmera)"
            atual = _tambores(FUNDO(), deslocamento=_tremor(rng), angulo=_angulo(rng))
        pares.append({"indice": i + 1, "alterado": alterado, "tipo": rotulo,
                      "referencia": referencia, "atual": atual})
    return pares


def avaliar(pares):
    linhas = []
    for par in pares:
        resultado = inspecionar(par["referencia"], par["atual"])
        linhas.append({
            "par": par["indice"], "tipo": par["tipo"], "alterado": par["alterado"],
            "detectado": resultado.alterado, "ssim": round(resultado.similaridade, 4),
            "regioes": len(resultado.regioes), "alinhou": resultado.alinhado,
            "correspondencias": resultado.correspondencias,
            "acerto": resultado.alterado == par["alterado"],
        })
    return linhas


def resumir(linhas, limiar_ssim=None):
    """Além das taxas, apura QUAL critério disparou cada detecção.

    O inspetor acusa alteração por dois caminhos: regiões de diferença isoladas
    pela morfologia, ou SSIM abaixo do limiar. Saber qual deles age importa: se
    o SSIM nunca dispara, o limiar configurado não está defendendo nada, e isso
    precisa aparecer no relatório em vez de ficar escondido atrás da acurácia.
    """
    limiar_ssim = (limiar_ssim if limiar_ssim is not None
                   else configuracao.carregar().getfloat("inspecao", "limiar_ssim"))
    alterados = [l for l in linhas if l["alterado"]]
    integros = [l for l in linhas if not l["alterado"]]
    detectados = sum(l["detectado"] for l in alterados)
    falsos = sum(l["detectado"] for l in integros)
    acusados = [l for l in linhas if l["detectado"]]
    por_regiao = sum(1 for l in acusados if l["regioes"] > 0)
    por_ssim = sum(1 for l in acusados if l["ssim"] < limiar_ssim)
    return {
        "limiar_ssim": limiar_ssim,
        "detecoes_por_regiao": por_regiao,
        "detecoes_por_ssim": por_ssim,
        "pares": len(linhas),
        "alterados": len(alterados),
        "integros": len(integros),
        "sensibilidade": detectados / len(alterados) if alterados else 0.0,
        "falso_positivo": falsos / len(integros) if integros else 0.0,
        "acuracia": sum(l["acerto"] for l in linhas) / len(linhas),
        "alinhamento": sum(l["alinhou"] for l in linhas) / len(linhas),
        "ssim_alterados": float(np.mean([l["ssim"] for l in alterados])) if alterados else 0.0,
        "ssim_integros": float(np.mean([l["ssim"] for l in integros])) if integros else 0.0,
    }


def plotar(linhas, caminho):
    """SSIM de cada par, com o limiar de decisão — mostra a separação entre os grupos."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    limiar = configuracao.carregar().getfloat("inspecao", "limiar_ssim")
    figura, eixo = plt.subplots(figsize=(9.5, 5))
    for alterado, cor, rotulo in ((False, "#1f7a4d", "íntegro"), (True, "#a8322d", "alterado")):
        grupo = [l for l in linhas if l["alterado"] == alterado]
        eixo.scatter([l["par"] for l in grupo], [l["ssim"] for l in grupo],
                     color=cor, s=70, label=rotulo, zorder=3)
    eixo.axhline(limiar, color="#2e6f8e", linestyle="--",
                 label=f"limiar SSIM ({limiar})")
    eixo.set_xlabel("Par")
    eixo.set_ylabel("Índice de similaridade (SSIM)")
    eixo.set_title("Inspeção de acondicionamento — separação entre pares íntegros e alterados")
    eixo.legend()
    eixo.grid(alpha=0.3, zorder=0)
    figura.tight_layout()
    figura.savefig(caminho, dpi=150)
    plt.close(figura)


def main():
    import pandas as pd

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pares", type=int, default=20)
    parser.add_argument("--saida", default=None)
    args = parser.parse_args()

    linhas = avaliar(gerar_pares(args.pares))
    resumo = resumir(linhas)
    saida = (configuracao.RAIZ / args.saida if args.saida
             else configuracao.caminho("resultados") / datetime.now().strftime("%Y%m%d_%H%M%S"))
    saida.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(linhas).to_csv(saida / "inspecao_pares.csv", index=False)
    pd.DataFrame([resumo]).to_csv(saida / "inspecao_resumo.csv", index=False)
    plotar(linhas, saida / "inspecao_pares.png")

    print(f"{'PAR':>4}  {'TIPO':30}  {'SSIM':>7}  {'REG':>4}  RESULTADO")
    print("-" * 68)
    for l in linhas:
        esperado = "alterado" if l["alterado"] else "íntegro"
        obtido = "alterado" if l["detectado"] else "íntegro"
        marca = "ok" if l["acerto"] else "ERRO"
        print(f"{l['par']:>4}  {l['tipo']:30}  {l['ssim']:>7.4f}  {l['regioes']:>4}  "
              f"{esperado} -> {obtido}  [{marca}]")
    print()
    print(f"  sensibilidade (detectou alteração) : {resumo['sensibilidade']:.1%}   "
          f"meta ETP 7.1: 90%")
    print(f"  falso positivo (acusou sem motivo) : {resumo['falso_positivo']:.1%}")
    print(f"  acurácia geral                     : {resumo['acuracia']:.1%}")
    print(f"  alinhamento ORB bem-sucedido       : {resumo['alinhamento']:.1%}")
    print(f"  SSIM médio — íntegros {resumo['ssim_integros']:.4f} · "
          f"alterados {resumo['ssim_alterados']:.4f}")
    print()
    print(f"  Critério que disparou: {resumo['detecoes_por_regiao']} por REGIÃO, "
          f"{resumo['detecoes_por_ssim']} por SSIM (limiar {resumo['limiar_ssim']})")
    if resumo["detecoes_por_ssim"] == 0 and resumo["detecoes_por_regiao"]:
        print("  >> O SSIM global NÃO disparou nenhuma vez. Ele é uma média sobre a imagem")
        print("     inteira, e alterações localizadas (um lacre, um rótulo) quase não o")
        print("     movem. Quem detecta é a análise de regiões — o limiar de SSIM, como")
        print("     está, só pegaria uma degradação ampla, do quadro todo.")
    print(f"\nArtefatos em {saida}")


if __name__ == "__main__":
    main()
