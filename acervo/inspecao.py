"""M-03 — Inspeção de acondicionamento por comparação de imagens (RF-16).

Compara a foto atual de um lacre/tambor com a foto de referência:
1. alinhamento ORB + homografia (RANSAC), para que deslocamento da câmera não
   vire falso positivo;
2. diferença absoluta e SSIM (implementado aqui, sem scikit-image);
3. limiarização + morfologia isolam as regiões alteradas.
"""
from dataclasses import dataclass, field

import cv2
import numpy as np

import configuracao


def ssim(a, b):
    """SSIM com janela gaussiana 11x11, sigma 1.5 (Wang et al., 2004). Devolve (média, mapa)."""
    a, b = a.astype(np.float64), b.astype(np.float64)
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    def g(x):
        return cv2.GaussianBlur(x, (11, 11), 1.5)
    mu_a, mu_b = g(a), g(b)
    var_a = g(a * a) - mu_a ** 2
    var_b = g(b * b) - mu_b ** 2
    cov = g(a * b) - mu_a * mu_b
    mapa = ((2 * mu_a * mu_b + c1) * (2 * cov + c2)) / ((mu_a ** 2 + mu_b ** 2 + c1) * (var_a + var_b + c2))
    return float(mapa.mean()), mapa


def alinhar(referencia, atual, cfg=None):
    """Devolve (atual_alinhada, mascara_valida, n_correspondencias) ou (None, None, n)."""
    cfg = cfg or configuracao.carregar()
    orb = cv2.ORB_create(cfg.getint("inspecao", "orb_features"))
    kp_r, des_r = orb.detectAndCompute(referencia, None)
    kp_a, des_a = orb.detectAndCompute(atual, None)
    if des_r is None or des_a is None:
        return None, None, 0
    pares = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(des_a, des_r, k=2)
    razao = cfg.getfloat("inspecao", "razao_lowe")
    bons = [p[0] for p in pares if len(p) == 2 and p[0].distance < razao * p[1].distance]
    if len(bons) < cfg.getint("inspecao", "correspondencias_minimas"):
        return None, None, len(bons)
    origem = np.float32([kp_a[m.queryIdx].pt for m in bons]).reshape(-1, 1, 2)
    destino = np.float32([kp_r[m.trainIdx].pt for m in bons]).reshape(-1, 1, 2)
    homografia, _ = cv2.findHomography(origem, destino, cv2.RANSAC, 5.0)
    if homografia is None:
        return None, None, len(bons)
    h, w = referencia.shape[:2]
    alinhada = cv2.warpPerspective(atual, homografia, (w, h))
    mascara = cv2.warpPerspective(np.full(atual.shape[:2], 255, np.uint8), homografia, (w, h))
    mascara = cv2.erode(mascara, np.ones((7, 7), np.uint8))   # descarta a borda interpolada
    return alinhada, mascara, len(bons)


@dataclass
class ResultadoInspecao:
    alterado: bool
    similaridade: float
    alinhado: bool
    correspondencias: int
    regioes: list = field(default_factory=list)   # [(x, y, w, h)]
    mapa_diferenca: np.ndarray | None = None      # BGR para exibição no relatório A2-06


def inspecionar(referencia_bgr, atual_bgr, cfg=None):
    cfg = cfg or configuracao.carregar()
    ref = cv2.GaussianBlur(cv2.cvtColor(referencia_bgr, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    atu = cv2.GaussianBlur(cv2.cvtColor(atual_bgr, cv2.COLOR_BGR2GRAY), (5, 5), 0)

    alinhada, mascara, n = alinhar(ref, atu, cfg)
    alinhou = alinhada is not None
    if not alinhou:   # sem alinhamento: compara direto, e o relatório avisa
        alinhada = cv2.resize(atu, (ref.shape[1], ref.shape[0]))
        mascara = np.full(ref.shape, 255, np.uint8)

    indice, mapa_ssim = ssim(ref, alinhada)
    validos = mascara > 0
    similaridade = float(mapa_ssim[validos].mean()) if validos.any() else indice

    diferenca = cv2.absdiff(ref, alinhada)
    diferenca[~validos] = 0
    _, binaria = cv2.threshold(diferenca, cfg.getint("inspecao", "limiar_diferenca"), 255, cv2.THRESH_BINARY)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (cfg.getint("inspecao", "kernel_morfologia"),) * 2)
    binaria = cv2.morphologyEx(cv2.morphologyEx(binaria, cv2.MORPH_OPEN, k), cv2.MORPH_CLOSE, k)
    contornos, _ = cv2.findContours(binaria, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    area_minima = cfg.getint("inspecao", "area_minima")
    regioes = [cv2.boundingRect(c) for c in contornos if cv2.contourArea(c) >= area_minima]

    mapa = cv2.applyColorMap(diferenca, cv2.COLORMAP_JET)
    for x, y, w, h in regioes:
        cv2.rectangle(mapa, (x, y), (x + w, y + h), (255, 255, 255), 2)

    alterado = bool(regioes) or similaridade < cfg.getfloat("inspecao", "limiar_ssim")
    return ResultadoInspecao(alterado, similaridade, alinhou, n, regioes, mapa)
