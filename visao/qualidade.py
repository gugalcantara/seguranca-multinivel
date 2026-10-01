"""Portão de qualidade (D-03, RF-17, ETP 4.6).

Usado em dois momentos com o mesmo cálculo:
- no cadastro, para decidir se o frame entra na base;
- na autenticação, para rejeitar o frame antes de ele chegar ao LBPH.
Amostra reprovada não gera decisão — gera uma mensagem de orientação.
"""
from dataclasses import dataclass

import cv2
import numpy as np

import configuracao

_KERNEL_IMMERKAER = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], dtype=np.float64)


def nitidez(cinza):
    """Variância do Laplaciano — baixa = imagem desfocada."""
    return float(cv2.Laplacian(cinza, cv2.CV_64F).var())


def brilho_contraste(cinza):
    return float(cinza.mean()), float(cinza.std())


def ruido(cinza):
    """Desvio-padrão do ruído pelo método de Immerkær (1996)."""
    altura, largura = cinza.shape[:2]
    if altura < 3 or largura < 3:
        return 0.0
    resposta = cv2.filter2D(cinza.astype(np.float64), -1, _KERNEL_IMMERKAER)[1:-1, 1:-1]
    return float(np.sqrt(np.pi / 2) * np.abs(resposta).sum() / (6 * (largura - 2) * (altura - 2)))


def diferenca_media(a, b):
    """Diferença absoluta média entre dois recortes — detecta frame duplicado."""
    return float(cv2.absdiff(a, b).mean())


@dataclass
class ResultadoQualidade:
    aprovado: bool
    motivo: str          # código curto, vai para o log
    mensagem: str        # orientação ao usuário
    nitidez: float = 0.0
    brilho: float = 0.0
    contraste: float = 0.0
    ruido: float = 0.0
    escore: float = 0.0  # 0..1, gravado em amostra.qualidade e log_acesso.qualidade


class PortaoQualidade:
    def __init__(self, cfg=None):
        cfg = cfg or configuracao.carregar()
        q = "qualidade"
        self.nitidez_minima = cfg.getfloat(q, "nitidez_minima")
        self.brilho_minimo = cfg.getfloat(q, "brilho_minimo")
        self.brilho_maximo = cfg.getfloat(q, "brilho_maximo")
        self.contraste_minimo = cfg.getfloat(q, "contraste_minimo")
        self.ruido_maximo = cfg.getfloat(q, "ruido_maximo")

    def avaliar(self, face_cinza, n_faces=1):
        if n_faces == 0:
            return ResultadoQualidade(False, "SEM_FACE", "Posicione o rosto no centro da câmera.")
        if n_faces > 1:
            return ResultadoQualidade(False, "MULTIPLAS_FACES", "Apenas uma pessoa por vez diante da câmera.")

        n = nitidez(face_cinza)
        b, c = brilho_contraste(face_cinza)
        r = ruido(face_cinza)
        escore = float(np.clip(min(n / (2 * self.nitidez_minima), c / (2 * self.contraste_minimo), 1.0), 0, 1))
        medidas = dict(nitidez=n, brilho=b, contraste=c, ruido=r, escore=escore)

        if b < self.brilho_minimo:
            return ResultadoQualidade(False, "ESCURO", "Imagem escura — aproxime-se da luz.", **medidas)
        if b > self.brilho_maximo:
            return ResultadoQualidade(False, "CLARO", "Imagem estourada — evite luz direta na câmera.", **medidas)
        if c < self.contraste_minimo:
            return ResultadoQualidade(False, "SEM_CONTRASTE", "Pouco contraste — evite contra-luz.", **medidas)
        if n < self.nitidez_minima:
            return ResultadoQualidade(False, "DESFOCADO", "Imagem desfocada — fique parado por um instante.", **medidas)
        if r > self.ruido_maximo:
            return ResultadoQualidade(False, "RUIDOSO", "Imagem com muito ruído — melhore a iluminação.", **medidas)
        return ResultadoQualidade(True, "OK", "Qualidade adequada.", **medidas)
