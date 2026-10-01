"""Encadeamento das cinco fases e a alternância Haar/KCF (D-02).

Os colaboradores são dublês: o que se testa aqui é a ORQUESTRAÇÃO — quando o
detector é chamado, quando o rastreador assume, o que o portão de qualidade
recebe e qual modo de reconhecimento é usado. Haar, KCF e LBPH têm os seus
próprios testes; repetir a detecção real aqui tornaria o teste lento e
dependente de imagem de rosto, que não entra no repositório (R-07).
"""
import numpy as np
import pytest

import configuracao
from visao.pipeline import PipelineFacial
from visao.segmentacao import SegmentadorRastreado

FRAME = np.random.RandomState(3).randint(0, 255, (480, 640, 3), dtype=np.uint8)
UMA_FACE = [(200, 150, 120, 120)]


class DetectorDuble:
    def __init__(self, faces=None):
        self.faces = faces if faces is not None else UMA_FACE
        self.chamadas = 0

    def detectar(self, _cinza):
        self.chamadas += 1
        return list(self.faces)


class RastreadorDuble:
    criados = 0

    def __init__(self, ok=True, caixa=(210, 160, 120, 120)):
        self.ok, self.caixa = ok, caixa
        self.atualizacoes = 0
        RastreadorDuble.criados += 1

    def init(self, _frame, _caixa):
        return True

    def update(self, _frame):
        self.atualizacoes += 1
        return self.ok, self.caixa


@pytest.fixture
def kcf(monkeypatch):
    """Substitui o KCF real: o teste é sobre QUANDO rastrear, não sobre rastrear."""
    RastreadorDuble.criados = 0
    criado = {}

    def fabricar():
        criado["ultimo"] = RastreadorDuble()
        return criado["ultimo"]

    monkeypatch.setattr("visao.segmentacao._criar_kcf", fabricar)
    return criado


# ------------------------------------------------------------------ segmentação
def test_detecta_no_primeiro_frame_e_rastreia_nos_seguintes(kcf):
    """D-02: o Haar custa caro, então roda a cada N frames; o KCF cobre o meio."""
    cfg = configuracao.carregar()
    n = cfg.getint("rastreamento", "detectar_a_cada")
    detector = DetectorDuble()
    seg = SegmentadorRastreado(detector=detector, cfg=cfg)

    seg.segmentar(FRAME, FRAME[:, :, 0])
    assert detector.chamadas == 1
    for _ in range(n - 1):
        seg.segmentar(FRAME, FRAME[:, :, 0])
    assert detector.chamadas == 1                      # ainda no mesmo ciclo
    assert kcf["ultimo"].atualizacoes == n - 1

    seg.segmentar(FRAME, FRAME[:, :, 0])
    assert detector.chamadas == 2                      # fecha o ciclo: detecta de novo


def test_rastreador_que_perde_a_face_cai_para_a_deteccao(kcf, monkeypatch):
    cfg = configuracao.carregar()
    detector = DetectorDuble()
    seg = SegmentadorRastreado(detector=detector, cfg=cfg)
    seg.segmentar(FRAME, FRAME[:, :, 0])               # detecta e cria o rastreador
    monkeypatch.setattr(kcf["ultimo"], "ok", False)    # perdeu o alvo

    seg.segmentar(FRAME, FRAME[:, :, 0])
    assert detector.chamadas == 2                      # detectou no MESMO frame


def test_mais_de_uma_face_descarta_o_rastreamento(kcf):
    """EXC-02: uma pessoa por vez. Com duas, não há ROI única a rastrear."""
    seg = SegmentadorRastreado(detector=DetectorDuble([(0, 0, 50, 50), (100, 0, 50, 50)]),
                               cfg=configuracao.carregar())
    assert len(seg.segmentar(FRAME, FRAME[:, :, 0])) == 2
    assert seg._rastreador is None


def test_nenhuma_face_tambem_descarta_o_rastreamento(kcf):
    seg = SegmentadorRastreado(detector=DetectorDuble([]), cfg=configuracao.carregar())
    assert seg.segmentar(FRAME, FRAME[:, :, 0]) == []
    assert seg._rastreador is None


def test_reiniciar_forca_nova_deteccao(kcf):
    """Trocar de pessoa exige zerar: senão o KCF entrega a ROI da anterior."""
    detector = DetectorDuble()
    seg = SegmentadorRastreado(detector=detector, cfg=configuracao.carregar())
    seg.segmentar(FRAME, FRAME[:, :, 0])
    seg.reiniciar()
    seg.segmentar(FRAME, FRAME[:, :, 0])
    assert detector.chamadas == 2
    assert seg._contador == 1


# ------------------------------------------------------------------ pipeline
class PortaoDuble:
    def __init__(self, aprovado=True):
        self.aprovado = aprovado
        self.recebidos = []

    def avaliar(self, face_cinza, n_faces=1):
        from visao.qualidade import ResultadoQualidade
        self.recebidos.append(face_cinza)
        if n_faces == 0:
            return ResultadoQualidade(False, "SEM_FACE", "")
        if n_faces > 1:
            return ResultadoQualidade(False, "MULTIPLAS_FACES", "")
        return ResultadoQualidade(self.aprovado, "OK" if self.aprovado else "DESFOCADO", "",
                                  escore=0.9 if self.aprovado else 0.1)


class ReconhecedorDuble:
    def __init__(self):
        self.identificou = self.verificou = 0

    def identificar(self, _face):
        self.identificou += 1
        return 7, 42.0

    def verificar(self, _face, usuario_id):
        self.verificou += 1
        return 33.0


def montar(faces=None, aprovado=True):
    cfg = configuracao.carregar()
    rec = ReconhecedorDuble()
    pipe = PipelineFacial(rec, cfg)
    pipe.segmentador = SegmentadorRastreado(detector=DetectorDuble(faces), cfg=cfg)
    pipe.portao = PortaoDuble(aprovado)
    return pipe, rec


def test_sem_usuario_alegado_usa_identificacao_1n(kcf):
    """Nível 1: não há matrícula, então a identidade vem do 1:N."""
    pipe, rec = montar()
    analise = pipe.analisar(FRAME)
    assert (rec.identificou, rec.verificou) == (1, 0)
    assert (analise.rotulo, analise.distancia) == (7, 42.0)


def test_com_usuario_alegado_usa_verificacao_11(kcf):
    """Níveis 2 e 3: a senha já disse quem é; a face só confirma."""
    pipe, rec = montar()
    analise = pipe.analisar(FRAME, usuario_alegado=99)
    assert (rec.identificou, rec.verificou) == (0, 1)
    assert analise.rotulo == 99 and analise.distancia == 33.0


def test_qualidade_reprovada_nao_chega_ao_reconhecedor(kcf):
    """Amostra ruim não gera decisão — gera orientação (D-03/RF-17)."""
    pipe, rec = montar(aprovado=False)
    analise = pipe.analisar(FRAME)
    assert (rec.identificou, rec.verificou) == (0, 0)
    assert analise.rotulo is None and analise.distancia is None
    assert not analise.qualidade.aprovado


def test_sem_face_nao_reconhece_e_informa(kcf):
    pipe, rec = montar(faces=[])
    analise = pipe.analisar(FRAME)
    assert analise.qualidade.motivo == "SEM_FACE"
    assert (rec.identificou, rec.verificou) == (0, 0)
    assert analise.retangulo is None


def test_varias_faces_nao_reconhece(kcf):
    pipe, rec = montar(faces=[(0, 0, 90, 90), (200, 0, 90, 90)])
    analise = pipe.analisar(FRAME)
    assert analise.qualidade.motivo == "MULTIPLAS_FACES"
    assert (rec.identificou, rec.verificou) == (0, 0)
    assert analise.retangulo is None            # só há retângulo com UMA face


def test_reconhecer_false_pula_a_classificacao(kcf):
    """O cadastro só coleta; não faz sentido reconhecer quem ainda não existe."""
    pipe, rec = montar()
    analise = pipe.analisar(FRAME, reconhecer=False)
    assert (rec.identificou, rec.verificou) == (0, 0)
    assert analise.face is not None and analise.qualidade.aprovado


def test_qualidade_e_medida_no_recorte_cru_e_o_lbph_recebe_o_realcado(kcf):
    """Decisão 10 do README: o CLAHE mascara imagem escura e sem contraste.

    Medir a qualidade depois dele deixaria o portão cego justamente ao que deve
    barrar — então o portão recebe o recorte CRU e o LBPH, o realçado.
    """
    pipe, _ = montar()
    analise = pipe.analisar(FRAME)
    recebido_pelo_portao = pipe.portao.recebidos[-1]
    assert recebido_pelo_portao is not None
    assert recebido_pelo_portao.shape == analise.face.shape
    assert not np.array_equal(recebido_pelo_portao, analise.face)   # cru != realçado


def test_face_sem_pipeline_de_reconhecimento_nao_quebra(kcf):
    """PipelineFacial(None) é o caminho do cadastro e do esqueleto."""
    cfg = configuracao.carregar()
    pipe = PipelineFacial(None, cfg)
    pipe.segmentador = SegmentadorRastreado(detector=DetectorDuble(), cfg=cfg)
    analise = pipe.analisar(FRAME)
    assert analise.face is not None and analise.rotulo is None
