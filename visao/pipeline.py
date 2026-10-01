"""As cinco fases encadeadas sobre um frame — usado pelo cadastro, pela
autenticação e pelo esqueleto de demonstração.

    Aquisição (frame) -> Pré-processamento (cinza, CLAHE, ruído)
    -> Segmentação (Haar + KCF) -> portão de qualidade
    -> Extração + Classificação (LBPH: 1:N ou 1:1)
"""
from dataclasses import dataclass

import configuracao
from visao.preprocessamento import PreProcessador, para_cinza
from visao.qualidade import PortaoQualidade, ResultadoQualidade
from visao.segmentacao import SegmentadorRastreado


@dataclass
class AnaliseFrame:
    retangulos: list
    qualidade: ResultadoQualidade
    face: object = None            # ROI 200x200 realçada (entrada do LBPH)
    cinza: object = None           # frame em cinza (para vivacidade)
    rotulo: int | None = None      # identidade (1:N) ou a alegada (1:1)
    distancia: float | None = None

    @property
    def retangulo(self):
        return self.retangulos[0] if len(self.retangulos) == 1 else None


class PipelineFacial:
    def __init__(self, reconhecedor=None, cfg=None):
        cfg = cfg or configuracao.carregar()
        self.pre = PreProcessador(cfg)
        self.segmentador = SegmentadorRastreado(cfg=cfg)
        self.portao = PortaoQualidade(cfg)
        self.reconhecedor = reconhecedor

    def analisar(self, frame, usuario_alegado=None, reconhecer=True):
        cinza = para_cinza(frame)
        realcado = self.pre.realcar(frame)
        retangulos = self.segmentador.segmentar(frame, realcado)
        if len(retangulos) != 1:
            return AnaliseFrame(retangulos, self.portao.avaliar(None, len(retangulos)), cinza=cinza)

        # qualidade medida no recorte CRU (antes do CLAHE, que mascara escuridão e baixo contraste)
        bruto = self.pre.recortar_face(cinza, retangulos[0])
        face = self.pre.recortar_face(realcado, retangulos[0])
        if face is None:
            return AnaliseFrame(retangulos, self.portao.avaliar(None, 0), cinza=cinza)
        qualidade = self.portao.avaliar(bruto)
        analise = AnaliseFrame(retangulos, qualidade, face=face, cinza=cinza)
        if not qualidade.aprovado or not reconhecer or self.reconhecedor is None:
            return analise

        if usuario_alegado is None:
            analise.rotulo, analise.distancia = self.reconhecedor.identificar(face)
        else:
            analise.rotulo = usuario_alegado
            analise.distancia = self.reconhecedor.verificar(face, usuario_alegado)
        return analise
