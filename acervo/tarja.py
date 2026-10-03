"""M-01 / D-06 — Tarja adaptativa por nível (RF-09, RF-10).

A supressão é aplicada sobre uma CÓPIA da imagem, antes de qualquer coisa ser
entregue à interface. A UI nunca recebe o pixel original de uma região que o
nível não autoriza. Filtro gaussiano de núcleo grande (várias passadas) ou
pixelização — irreversível na imagem entregue, ao contrário de um retângulo
desenhado por cima na tela.

Falha segura no conteúdo (ETP 6.6): item cujas regiões sensíveis ainda não
foram revisadas é tratado como totalmente sensível e servido apenas ao nível 3.
"""
from dataclasses import dataclass

import cv2

import configuracao


class AcessoNegado(PermissionError):
    pass


@dataclass
class Regiao:
    x: int
    y: int
    largura: int
    altura: int
    nivel_minimo: int
    rotulo: str | None = None

    @classmethod
    def de_linha(cls, linha):
        return cls(linha["x"], linha["y"], linha["largura"], linha["altura"],
                   linha["nivel_minimo"], linha.get("rotulo"))


def _recorte(imagem, r):
    altura, largura = imagem.shape[:2]
    x0, y0 = max(0, r.x), max(0, r.y)
    x1, y1 = min(largura, r.x + r.largura), min(altura, r.y + r.altura)
    return (slice(y0, y1), slice(x0, x1)) if x1 > x0 and y1 > y0 else None


def suprimir(imagem, regiao, cfg=None):
    """Suprime a região in-place.

    O método depende do que a região carrega. Para TEXTO, o borrão gaussiano
    basta: o conteúdo fica ilegível. Para POSIÇÃO — os pontos de um mapa — não
    basta: o gaussiano preserva o centroide, e o pico do resíduo de cor ainda
    aponta o lugar exato. Rótulos listados em [tarja] rotulos_supressao_total
    recebem supressão sólida, que apaga a estrutura espacial.
    """
    cfg = cfg or configuracao.carregar()
    janela = _recorte(imagem, regiao)
    if janela is None:
        return
    roi = imagem[janela]
    metodo = cfg.get("tarja", "metodo")
    if regiao.rotulo in cfg.getlista("tarja", "rotulos_supressao_total"):
        metodo = "solido"
    if metodo == "pixelizacao":
        bloco = cfg.getint("tarja", "bloco_pixelizacao")
        h, w = roi.shape[:2]
        pequeno = cv2.resize(roi, (max(1, w // bloco), max(1, h // bloco)), interpolation=cv2.INTER_AREA)
        roi[:] = cv2.resize(pequeno, (w, h), interpolation=cv2.INTER_NEAREST)
    elif metodo == "solido":
        roi[:] = 40
    else:
        k = cfg.getint("tarja", "kernel_gaussiano") | 1
        for _ in range(cfg.getint("tarja", "passadas_gaussiano")):
            roi[:] = cv2.GaussianBlur(roi, (k, k), 0)


def aplicar_tarja(imagem, regioes, nivel, cfg=None):
    """Nova imagem com toda região de nivel_minimo > nivel suprimida."""
    saida = imagem.copy()
    for r in regioes:
        if r.nivel_minimo > nivel:
            suprimir(saida, r, cfg)
    return saida


def autorizar_item(nivel_item, regioes_revisadas, nivel):
    """Levanta AcessoNegado se o nível não pode ver o item."""
    if nivel < nivel_item:
        raise AcessoNegado(f"Item exige nível {nivel_item}")
    if not regioes_revisadas and nivel < 3:
        raise AcessoNegado("Item sem marcação de regiões sensíveis: restrito ao nível 3")
