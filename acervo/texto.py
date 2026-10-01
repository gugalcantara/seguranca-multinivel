"""Escrita de texto com acentos sobre imagens OpenCV (cv2.putText não suporta UTF-8)."""
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

_FONTES = ("arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf")


@lru_cache(maxsize=16)
def fonte(tamanho, negrito=False):
    nomes = ("arialbd.ttf", "DejaVuSans-Bold.ttf") + _FONTES if negrito else _FONTES
    for nome in nomes:
        try:
            return ImageFont.truetype(nome, tamanho)
        except OSError:
            continue
    return ImageFont.load_default()


def escrever(imagem_bgr, linhas, cor=(20, 20, 20), tamanho=20, negrito=False):
    """linhas: [(x, y, texto)]. Devolve nova imagem BGR."""
    pil = Image.fromarray(cv2.cvtColor(imagem_bgr, cv2.COLOR_BGR2RGB))
    desenho = ImageDraw.Draw(pil)
    for x, y, texto in linhas:
        desenho.text((x, y), texto, fill=cor[::-1], font=fonte(tamanho, negrito))
    return cv2.cvtColor(np.asarray(pil), cv2.COLOR_RGB2BGR)


def carimbar_ficticio(imagem_bgr):
    """RF-18: faixa permanente identificando conteúdo sintético."""
    saida = imagem_bgr.copy()
    cv2.rectangle(saida, (0, 0), (saida.shape[1], 30), (40, 40, 180), -1)
    return escrever(saida, [(10, 4, "DADO FICTÍCIO — conteúdo sintético para fins acadêmicos (APS PIVC 2026/2)")],
                    cor=(255, 255, 255), tamanho=17, negrito=True)
