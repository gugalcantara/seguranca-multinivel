"""Fase 2 — Pré-processamento.

Escala de cinza -> CLAHE -> redução de ruído -> normalização 200x200.
O portão de qualidade (D-03) fica em qualidade.py e é aplicado sobre a saída daqui.
"""
import cv2

import configuracao


def para_cinza(frame):
    if frame.ndim == 2:
        return frame
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


def reduzir_ruido(cinza, kernel):
    if kernel and kernel > 1:
        return cv2.GaussianBlur(cinza, (kernel, kernel), 0)
    return cinza


class PreProcessador:
    def __init__(self, cfg=None):
        cfg = cfg or configuracao.carregar()
        self.clahe = cv2.createCLAHE(
            clipLimit=cfg.getfloat("preprocessamento", "clahe_clip_limit"),
            tileGridSize=cfg.gettupla("preprocessamento", "clahe_grade"),
        )
        self.kernel_ruido = cfg.getint("preprocessamento", "ruido_kernel")
        self.dimensao = cfg.gettupla("preprocessamento", "dimensao_face")

    def realcar(self, frame):
        """Frame inteiro em cinza realçado — entrada da detecção."""
        return reduzir_ruido(self.clahe.apply(para_cinza(frame)), self.kernel_ruido)

    def recortar_face(self, cinza_realcado, retangulo):
        """ROI da face normalizada para a dimensão fixa — entrada do LBPH."""
        x, y, w, h = retangulo
        altura, largura = cinza_realcado.shape[:2]
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(largura, x + w), min(altura, y + h)
        if x1 <= x0 or y1 <= y0:
            return None
        return cv2.resize(cinza_realcado[y0:y1, x0:x1], self.dimensao, interpolation=cv2.INTER_AREA)
