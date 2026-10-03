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
        """Cada recusa vem com a AÇÃO que resolve, não só com o diagnóstico.

        "Imagem escura" informa; "acenda uma luz à sua frente" resolve. Quem
        está diante da câmera não sabe o que é variância de Laplaciano — sabe
        acender a luz, limpar a lente e parar de se mexer.
        """
        if n_faces == 0:
            return ResultadoQualidade(False, "SEM_FACE",
                                      "Nenhum rosto encontrado. Centralize-se na moldura e "
                                      "olhe para a câmera.")
        if n_faces > 1:
            return ResultadoQualidade(False, "MULTIPLAS_FACES",
                                      "Há mais de um rosto na imagem. Peça para as outras pessoas "
                                      "saírem do enquadramento — é uma por vez.")

        n = nitidez(face_cinza)
        b, c = brilho_contraste(face_cinza)
        r = ruido(face_cinza)
        escore = float(np.clip(min(n / (2 * self.nitidez_minima), c / (2 * self.contraste_minimo), 1.0), 0, 1))
        medidas = dict(nitidez=n, brilho=b, contraste=c, ruido=r, escore=escore)

        if b < self.brilho_minimo:
            return ResultadoQualidade(False, "ESCURO",
                                      "Ambiente escuro demais. Acenda uma luz à sua frente ou "
                                      "vire-se para a janela.", **medidas)
        if b > self.brilho_maximo:
            return ResultadoQualidade(False, "CLARO",
                                      "Luz forte demais no rosto. Afaste-se da luz direta ou "
                                      "feche um pouco a cortina.", **medidas)
        if c < self.contraste_minimo:
            return ResultadoQualidade(False, "SEM_CONTRASTE",
                                      "Você está contra a luz. Fique de frente para a fonte de "
                                      "luz, não de costas.", **medidas)
        if n < self.nitidez_minima:
            return ResultadoQualidade(False, "DESFOCADO",
                                      "Imagem fora de foco. Fique parado um instante e confira "
                                      "se a lente está limpa.", **medidas)
        if r > self.ruido_maximo:
            return ResultadoQualidade(False, "RUIDOSO",
                                      "Muito ruído na imagem — sinal de pouca luz. Ilumine melhor "
                                      "o ambiente.", **medidas)
        return ResultadoQualidade(True, "OK", "Boa — continue assim, movendo a cabeça devagar.",
                                  **medidas)
