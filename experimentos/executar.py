"""Roda o protocolo da ETP 7.2 sobre a base experimental e gera os artefatos do
capítulo de resultados: planilha, curva DET, matriz de confusão e limiares sugeridos.

Uso:  python -m experimentos.executar [--base dados_faciais]

Os limiares sugeridos devem ser copiados para [limiares] no config.ini —
é assim que eles deixam de ser arbitrários (princípio 9).
"""
import argparse
import json
from datetime import datetime

import cv2
import numpy as np
import pandas as pd

import configuracao
from experimentos import metricas, protocolo
from visao.extracao import ReconhecedorLBPH


class ReconhecedorEigen(ReconhecedorLBPH):
    """Linha de base Eigenfaces (PCA) com a mesma interface do LBPH."""

    def __init__(self, cfg=None):
        super().__init__(cfg)
        self.modelo = cv2.face.EigenFaceRecognizer_create()


def _resumo(nome, r, far_alvo):
    eer_1n, limiar_eer = metricas.eer(r["genuinas_1n"], r["impostoras_1n"])
    eer_11, _ = metricas.eer(r["genuinas_11"], r["impostoras_11"])
    limiar_n2 = metricas.limiar_para_far(r["impostoras_11"], far_alvo)
    far_n2, frr_n2 = metricas.far_frr(r["genuinas_11"], r["impostoras_11"], limiar_n2)
    return {
        "metodo": nome, "n_treino": r["n_treino"], "n_teste": r["n_teste"],
        "acuracia_1n": r["acuracia_1n"], "eer_1n": eer_1n, "eer_11": eer_11,
        "limiar_n1_eer": limiar_eer, "limiar_n2_far_alvo": limiar_n2,
        "far_n2": far_n2, "frr_n2": frr_n2,
        "limiar_n3_far_zero": metricas.limiar_para_far(r["impostoras_11"], 0.0),
    }


def main():
    cfg = configuracao.carregar()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=str(configuracao.RAIZ / "dados_faciais"))
    args = parser.parse_args()

    semente = cfg.getint("experimentos", "semente")
    proporcao = cfg.getfloat("experimentos", "proporcao_teste")
    far_alvo = cfg.getfloat("experimentos", "far_alvo_nivel_2")
    faces, ids, sessoes = protocolo.carregar_base(f"{args.base}/cadastrados")
    impostoras, _, _ = protocolo.carregar_base(f"{args.base}/impostores")

    saida = configuracao.caminho("resultados") / datetime.now().strftime("%Y%m%d_%H%M%S")
    saida.mkdir(parents=True, exist_ok=True)

    resumos, curvas = [], {}
    for nome, fabrica in (("LBPH", ReconhecedorLBPH), ("Eigenfaces", ReconhecedorEigen)):
        r = protocolo.avaliar(fabrica, faces, ids, sessoes, impostoras, proporcao, semente)
        resumos.append(_resumo(nome, r, far_alvo))
        for modo in ("1n", "11"):
            _, far, frr = metricas.curva_det(r[f"genuinas_{modo}"], r[f"impostoras_{modo}"])
            curvas[f"{nome} {'1:N' if modo == '1n' else '1:1'}"] = (far, frr)
        if nome == "LBPH":
            matriz, rotulos = metricas.matriz_confusao(r["reais"], r["preditos"])
            pd.DataFrame(matriz, index=rotulos, columns=rotulos).to_csv(saida / "matriz_confusao_lbph.csv")

    pd.DataFrame(resumos).to_csv(saida / "resumo.csv", index=False)
    metricas.plotar_det(curvas, saida / "curva_det.png")
    (saida / "manifesto.json").write_text(json.dumps({
        "semente": semente, "proporcao_teste": proporcao, "identidades": len(set(ids)),
        "amostras": len(faces), "impostoras": len(impostoras),
        "parametros_lbph": dict(cfg.items("lbph")),
    }, indent=2), encoding="utf-8")
    print(pd.DataFrame(resumos).T.to_string())
    print(f"\nArtefatos em {saida}")


if __name__ == "__main__":
    np.set_printoptions(precision=4)
    main()
