"""M-02 / D-07 — Marca d'água invisível com identidade e momento (RF-11).

Carga útil de 80 bits: usuario_id (32) + instante Unix em segundos (32) + CRC-16 (16).
A carga é repetida por toda a imagem; na extração cada bit é decidido por
votação majoritária entre as repetições, e o CRC rejeita leituras corrompidas.

Dois métodos, para a comparação exigida na ETP (6.5):
- LSB: bit menos significativo do canal azul. Simples e exato, mas frágil —
  qualquer recompressão JPEG apaga.
- DCT: em cada bloco 8x8 da luminância, a relação entre dois coeficientes de
  média frequência codifica um bit. Sobrevive a JPEG de qualidade moderada.
  Antes da inserção a luminância é comprimida levemente para longe de 0 e 255
  (folga), senão o fundo branco dos documentos satura e apaga a marca.
"""
import binascii
import struct
from datetime import datetime

import cv2
import numpy as np

import configuracao

BITS = 80
_FOLGA = 12.0


# ------------------------------------------------------------------ carga útil
def montar_carga(usuario_id, momento):
    dados = struct.pack(">II", usuario_id, int(momento.timestamp()))
    crc = binascii.crc_hqx(dados, 0xFFFF)
    return np.unpackbits(np.frombuffer(dados + struct.pack(">H", crc), dtype=np.uint8))


def interpretar_carga(bits):
    """(usuario_id, datetime) ou None se o CRC não fechar."""
    dados = np.packbits(np.asarray(bits, dtype=np.uint8)).tobytes()
    corpo, crc = dados[:8], struct.unpack(">H", dados[8:10])[0]
    if binascii.crc_hqx(corpo, 0xFFFF) != crc:
        return None
    usuario_id, instante = struct.unpack(">II", corpo)
    return usuario_id, datetime.fromtimestamp(instante)


def _votar(bits_lidos):
    """bits_lidos[i] pertence à posição i % 80 da carga; decide por maioria."""
    n = len(bits_lidos) - len(bits_lidos) % BITS
    if n == 0:
        return None
    return (np.asarray(bits_lidos[:n]).reshape(-1, BITS).mean(axis=0) >= 0.5).astype(np.uint8)


# ------------------------------------------------------------------ LSB
def inserir_lsb(imagem, usuario_id, momento):
    saida = imagem.copy()
    azul = saida[:, :, 0].reshape(-1)
    bits = np.resize(montar_carga(usuario_id, momento), azul.size)
    saida[:, :, 0] = ((azul & 0xFE) | bits).reshape(saida.shape[:2])
    return saida


def extrair_lsb(imagem):
    votados = _votar(imagem[:, :, 0].reshape(-1) & 1)
    return interpretar_carga(votados) if votados is not None else None


# ------------------------------------------------------------------ DCT
def _matriz_dct(n=8):
    """Matriz da DCT-II ortonormal (mesma convenção de cv2.dct)."""
    k = np.arange(n)[:, None]
    i = np.arange(n)[None, :]
    c = np.sqrt(2 / n) * np.cos(np.pi * (2 * i + 1) * k / (2 * n))
    c[0] /= np.sqrt(2)
    return c


_C = _matriz_dct()


def _blocos(y):
    h, w = (y.shape[0] // 8) * 8, (y.shape[1] // 8) * 8
    return y[:h, :w].reshape(h // 8, 8, w // 8, 8).swapaxes(1, 2).reshape(-1, 8, 8), (h, w)


def _remontar(blocos, h, w):
    return blocos.reshape(h // 8, w // 8, 8, 8).swapaxes(1, 2).reshape(h, w)


def _parametros(cfg):
    cfg = cfg or configuracao.carregar()
    return (cfg.getfloat("marca_dagua", "forca_dct"),
            cfg.gettupla("marca_dagua", "coef_a"), cfg.gettupla("marca_dagua", "coef_b"))


def inserir_dct(imagem, usuario_id, momento, cfg=None):
    forca, (ai, aj), (bi, bj) = _parametros(cfg)
    ycrcb = cv2.cvtColor(imagem, cv2.COLOR_BGR2YCrCb).astype(np.float64)
    y = ycrcb[:, :, 0] * (255 - 2 * _FOLGA) / 255 + _FOLGA
    blocos, (h, w) = _blocos(y)
    coef = _C @ blocos @ _C.T
    bits = np.resize(montar_carga(usuario_id, momento), len(coef)).astype(bool)

    a, b = coef[:, ai, aj], coef[:, bi, bj]
    media = (a + b) / 2
    # bit 1: a - b >= forca ; bit 0: b - a >= forca. Só mexe onde a relação não basta.
    corrigir = np.where(bits, a - b < forca, b - a < forca)
    sinal = np.where(bits, 1.0, -1.0)
    coef[corrigir, ai, aj] = media[corrigir] + sinal[corrigir] * forca / 2
    coef[corrigir, bi, bj] = media[corrigir] - sinal[corrigir] * forca / 2

    y[:h, :w] = _remontar(_C.T @ coef @ _C, h, w)
    ycrcb[:, :, 0] = y
    return cv2.cvtColor(np.clip(np.rint(ycrcb), 0, 255).astype(np.uint8), cv2.COLOR_YCrCb2BGR)


def extrair_dct(imagem, cfg=None):
    _, (ai, aj), (bi, bj) = _parametros(cfg)
    y = cv2.cvtColor(imagem, cv2.COLOR_BGR2YCrCb)[:, :, 0].astype(np.float64)
    blocos, _ = _blocos(y)
    coef = _C @ blocos @ _C.T
    votados = _votar((coef[:, ai, aj] > coef[:, bi, bj]).astype(np.uint8))
    return interpretar_carga(votados) if votados is not None else None


# ------------------------------------------------------------------ fachada
def inserir(imagem, usuario_id, momento, metodo=None, cfg=None):
    metodo = metodo or (cfg or configuracao.carregar()).get("marca_dagua", "metodo_padrao")
    return inserir_lsb(imagem, usuario_id, momento) if metodo == "lsb" else inserir_dct(imagem, usuario_id, momento, cfg)


def extrair(imagem, cfg=None):
    """Tenta LSB e depois DCT. Devolve (metodo, usuario_id, momento) ou None."""
    for metodo, funcao in (("lsb", extrair_lsb), ("dct", lambda img: extrair_dct(img, cfg))):
        resultado = funcao(imagem)
        if resultado:
            return (metodo, *resultado)
    return None
