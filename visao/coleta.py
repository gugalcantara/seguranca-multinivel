"""Coleta de amostras de uma sessão de cadastro (ETP 4.2 e 4.6).

Recebe as análises do pipeline frame a frame e só aceita a amostra que passa
no portão de qualidade e não é quase idêntica à anterior (descarte de duplicata).
As faces ficam SÓ EM MEMÓRIA: vão direto para o treino e são descartadas.

A coleta por ARQUIVOS de imagem (RF-01, alternativa à webcam) passa pelo MESMO
portão de qualidade: foto ruim é recusada do mesmo jeito, com o mesmo motivo.
"""
import cv2
import numpy as np

import configuracao
from visao.qualidade import diferenca_media

EXTENSOES = (".png", ".jpg", ".jpeg", ".bmp", ".webp")


class ColetorAmostras:
    def __init__(self, sessao, cfg=None, alvo=None, minimo=None):
        """alvo/minimo explícitos atendem o cadastro por ARQUIVOS, onde exigir as
        mesmas 40 capturas da webcam seria irreal."""
        cfg = cfg or configuracao.carregar()
        self.sessao = sessao
        self.alvo = cfg.getint("cadastro", "frames_por_sessao") if alvo is None else alvo
        self.minimo = cfg.getint("cadastro", "frames_minimos_validos") if minimo is None else minimo
        self.diferenca_minima = cfg.getfloat("qualidade", "diferenca_minima_duplicata")
        self.faces = []
        self.qualidades = []
        self.descartes = {}

    def alimentar(self, analise):
        """True se a amostra foi aceita."""
        if not analise.qualidade.aprovado:
            self._descartar(analise.qualidade.motivo)
            return False
        if self.faces and diferenca_media(self.faces[-1], analise.face) < self.diferenca_minima:
            self._descartar("DUPLICATA")
            return False
        self.faces.append(analise.face)
        self.qualidades.append(analise.qualidade.escore)
        return True

    def _descartar(self, motivo):
        self.descartes[motivo] = self.descartes.get(motivo, 0) + 1

    @property
    def completa(self):
        return len(self.faces) >= self.alvo

    @property
    def valida(self):
        return len(self.faces) >= self.minimo

    def descartar_imagens(self):
        """Chamado após o treino: nenhuma imagem bruta persiste (ETP 4.3)."""
        self.faces.clear()


# ---------------------------------------------------------------- por arquivo
def carregar_imagem(caminho, largura_maxima=None):
    """Lê um arquivo de imagem como BGR, ou None se não for imagem legível.

    Usa np.fromfile + imdecode em vez de cv2.imread porque o imread falha EM
    SILÊNCIO (devolve None) com caminhos acentuados no Windows — e nomes de
    arquivo em português são a regra, não a exceção.
    """
    try:
        dados = np.fromfile(str(caminho), dtype=np.uint8)
    except OSError:
        return None
    if dados.size == 0:
        return None
    imagem = cv2.imdecode(dados, cv2.IMREAD_COLOR)
    if imagem is None:
        return None
    if largura_maxima and imagem.shape[1] > largura_maxima:
        escala = largura_maxima / imagem.shape[1]
        imagem = cv2.resize(imagem, None, fx=escala, fy=escala, interpolation=cv2.INTER_AREA)
    return imagem


def coletar_de_arquivos(caminhos, pipeline, coletor, largura_maxima=None):
    """Passa cada arquivo pelo pipeline e alimenta o coletor.

    Devolve [(caminho, aceito, motivo, escore)] — um laudo por arquivo, para que
    a tela diga POR QUE uma foto foi recusada em vez de só ignorá-la.
    """
    laudos = []
    for caminho in caminhos:
        imagem = carregar_imagem(caminho, largura_maxima)
        if imagem is None:
            laudos.append((caminho, False, "ILEGIVEL", 0.0))
            continue
        # cada arquivo é independente: sem isso o KCF da imagem anterior seria
        # reaproveitado aqui e devolveria a ROI da foto errada
        pipeline.segmentador.reiniciar()
        analise = pipeline.analisar(imagem, reconhecer=False)
        aceito = coletor.alimentar(analise)
        motivo = "OK" if aceito else (analise.qualidade.motivo
                                      if not analise.qualidade.aprovado else "DUPLICATA")
        laudos.append((caminho, aceito, motivo, analise.qualidade.escore))
    return laudos
