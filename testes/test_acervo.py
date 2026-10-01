"""Tarja (RF-09, RF-10), entrega (RF-18), marca d'água (RF-11) e inspeção (RF-16)."""
from datetime import datetime

import cv2
import numpy as np
import pytest

from acervo import marca_dagua
from acervo.entrega import preparar_imagem
from acervo.gerar_exemplos import _tambores
from acervo.inspecao import inspecionar
from acervo.tarja import AcessoNegado, Regiao, aplicar_tarja, autorizar_item
from acervo.texto import escrever

MOMENTO = datetime(2026, 10, 1, 14, 30, 5)


def _documento():
    img = np.full((480, 640, 3), 250, np.uint8)
    linhas = [(30, 40 + 28 * i, f"Linha {i:02d} — Gerador: Empresa Fictícia {i} Ltda., 12,5 t") for i in range(14)]
    return escrever(img, linhas, tamanho=18)


REGIOES = [Regiao(30, 40, 400, 26, nivel_minimo=2, rotulo="RESPONSAVEL"),
           Regiao(30, 96, 400, 26, nivel_minimo=3, rotulo="CUSTODIA")]


def _variancia(img, r):
    return float(img[r.y:r.y + r.altura, r.x:r.x + r.largura].var())


# ------------------------------------------------------------------ tarja
def test_tarja_por_nivel():
    doc = _documento()
    n1, n2, n3 = (aplicar_tarja(doc, REGIOES, n) for n in (1, 2, 3))
    assert _variancia(n1, REGIOES[0]) < _variancia(doc, REGIOES[0]) / 5      # N1 não vê responsável
    assert np.array_equal(n2[40:66, 30:430], doc[40:66, 30:430])             # N2 vê responsável
    assert _variancia(n2, REGIOES[1]) < _variancia(doc, REGIOES[1]) / 5      # N2 não vê custódia
    assert np.array_equal(n3, doc)                                           # N3 vê tudo


def test_tarja_nao_altera_o_original_nem_fora_da_regiao():
    doc = _documento()
    copia = doc.copy()
    saida = aplicar_tarja(doc, REGIOES, 1)
    assert np.array_equal(doc, copia)
    assert np.array_equal(saida[200:], doc[200:])


def test_item_sem_regioes_revisadas_so_no_n3():
    with pytest.raises(AcessoNegado):
        autorizar_item(1, False, 2)
    autorizar_item(1, False, 3)
    with pytest.raises(AcessoNegado):
        autorizar_item(3, True, 2)


# ------------------------------------------------------------------ entrega
ITEM = {"nivel_minimo": 1, "regioes_revisadas": True, "sintetico": True}


def test_entrega_aplica_supressao_antes_da_interface():
    """RF-10: o objeto entregue já tem os pixels suprimidos."""
    entregue = preparar_imagem(_documento(), ITEM, REGIOES, 1)
    assert _variancia(entregue, REGIOES[0]) < _variancia(_documento(), REGIOES[0]) / 5


def test_entrega_carimba_conteudo_sintetico():
    entregue = preparar_imagem(_documento(), ITEM, [], 1)
    faixa = entregue[26:29, :, :]                       # abaixo do texto, dentro da faixa
    assert faixa[:, :, 2].mean() > 150 and faixa[:, :, 0].mean() < 80   # vermelha


def test_entrega_n2_leva_marca_dagua_recuperavel():
    entregue = preparar_imagem(_documento(), ITEM, REGIOES, 2, usuario_id=42, momento=MOMENTO)
    metodo, usuario, momento = marca_dagua.extrair(entregue)
    assert (usuario, momento) == (42, MOMENTO)


def test_entrega_n2_sem_identidade_e_negada():
    with pytest.raises(AcessoNegado):
        preparar_imagem(_documento(), ITEM, REGIOES, 2)


# ------------------------------------------------------------------ marca d'água
def _jpeg(img, qualidade):
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, qualidade])
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def test_carga_util_e_crc():
    bits = marca_dagua.montar_carga(123456, MOMENTO)
    assert len(bits) == marca_dagua.BITS
    assert marca_dagua.interpretar_carga(bits) == (123456, MOMENTO)
    bits[3] ^= 1
    assert marca_dagua.interpretar_carga(bits) is None


def test_lsb_exato_mas_fragil_a_jpeg():
    doc = _documento()
    marcada = marca_dagua.inserir_lsb(doc, 7, MOMENTO)
    assert np.abs(marcada.astype(int) - doc.astype(int)).max() <= 1          # invisível
    assert marca_dagua.extrair_lsb(marcada) == (7, MOMENTO)
    assert marca_dagua.extrair_lsb(_jpeg(marcada, 90)) is None               # frágil (R-09)


@pytest.mark.parametrize("qualidade", [95, 85, 75])
def test_dct_resiste_a_recompressao_jpeg(qualidade):
    marcada = marca_dagua.inserir_dct(_documento(), 7, MOMENTO)
    assert marca_dagua.extrair_dct(_jpeg(marcada, qualidade)) == (7, MOMENTO)


def test_dct_sem_marca_nao_inventa_identidade():
    assert marca_dagua.extrair_dct(_documento()) is None


# ------------------------------------------------------------------ inspeção
def test_inspecao_ignora_deslocamento_de_camera():
    fundo = np.full((640, 900, 3), 250, np.uint8)
    r = inspecionar(_tambores(fundo.copy()), _tambores(fundo.copy(), deslocamento=(12, -8), angulo=1.5))
    assert r.alinhado and not r.alterado


def test_inspecao_detecta_lacre_rompido():
    fundo = np.full((640, 900, 3), 250, np.uint8)
    r = inspecionar(_tambores(fundo.copy()),
                    _tambores(fundo.copy(), deslocamento=(12, -8), angulo=1.5, lacre_rompido=True))
    assert r.alterado and len(r.regioes) >= 1
    x, y, w, h = r.regioes[0]
    assert 440 < x + w / 2 < 520 and 170 < y + h / 2 < 230      # lacre do tambor do meio
