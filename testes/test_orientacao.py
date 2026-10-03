"""Orientação ao usuário durante a captura (RNF-02) e o que ela pode revelar.

Mensagem que apenas constata deixa a pessoa travada; mensagem que orienta
resolve. Mas nem toda orientação é segura: na autenticação, dizer demais entrega
informação a quem está tentando entrar. Os dois lados estão cobertos aqui.
"""
import numpy as np

from interface.comum import avaliar_enquadramento, desenhar_guia, moldura_alvo
from visao.qualidade import PortaoQualidade

FRAME = np.zeros((480, 640, 3), np.uint8)


def _no_alvo():
    x, y, lado, _ = moldura_alvo(FRAME)
    return (x, y, lado, lado)


# ------------------------------------------------------------------ enquadramento
def test_rosto_no_alvo_nao_gera_aviso():
    """Orientar quem já está certo é ruído: a pessoa deixa de ler os avisos."""
    assert avaliar_enquadramento(FRAME, _no_alvo()) is None


def test_rosto_pequeno_pede_aproximacao():
    x, y, lado, _ = moldura_alvo(FRAME)
    aviso = avaliar_enquadramento(FRAME, (x + 60, y + 60, int(lado * 0.5), int(lado * 0.5)))
    assert "aproxime-se" in aviso.lower()


def test_rosto_grande_pede_afastamento():
    x, y, lado, _ = moldura_alvo(FRAME)
    aviso = avaliar_enquadramento(FRAME, (x - 40, y - 40, int(lado * 1.6), int(lado * 1.6)))
    assert "afaste-se" in aviso.lower()


def test_desvio_lateral_indica_o_lado_do_usuario():
    """A imagem não é espelhada: quem está à esquerda do quadro move-se para a
    SUA direita. Errar o lado faz a pessoa se afastar ainda mais do centro."""
    _, y, lado, _ = moldura_alvo(FRAME)
    esquerda_do_quadro = avaliar_enquadramento(FRAME, (10, y, lado, lado))
    assert "direita" in esquerda_do_quadro.lower()
    direita_do_quadro = avaliar_enquadramento(FRAME, (640 - lado - 10, y, lado, lado))
    assert "esquerda" in direita_do_quadro.lower()


def test_sem_rosto_nao_orienta_enquadramento():
    """Sem face detectada, quem fala é o portão de qualidade, não o enquadramento."""
    assert avaliar_enquadramento(FRAME, None) is None


def test_guia_desenha_sem_alterar_o_frame_original():
    copia = FRAME.copy()
    saida = desenhar_guia(FRAME, [_no_alvo()], (0, 190, 0))
    assert np.array_equal(FRAME, copia)            # o original não é tocado
    assert not np.array_equal(saida, FRAME)        # e a guia aparece


# ------------------------------------------------------------------ portão de qualidade
def test_cada_recusa_diz_o_que_fazer():
    """RNF-02: mensagens explícitas de resultado. "Imagem escura" informa;
    "acenda uma luz à sua frente" resolve."""
    portao = PortaoQualidade()
    acoes = ("acenda", "afaste", "fique", "centralize", "peça", "ilumine", "confira", "vire")
    for n_faces in (0, 2):
        mensagem = portao.avaliar(None, n_faces=n_faces).mensagem.lower()
        assert any(a in mensagem for a in acoes), mensagem

    escura = (np.random.RandomState(1).randint(40, 215, (200, 200)) * 0.12).astype(np.uint8)
    resultado = portao.avaliar(escura)
    assert resultado.motivo == "ESCURO"
    assert any(a in resultado.mensagem.lower() for a in acoes), resultado.mensagem


def test_mensagem_de_aprovacao_mantem_a_pessoa_no_movimento():
    """Parar de mover a cabeça reduz a variedade das amostras; a mensagem lembra."""
    import cv2
    boa = cv2.resize(np.random.RandomState(1).randint(40, 215, (60, 60)).astype(np.uint8),
                     (200, 200), interpolation=cv2.INTER_CUBIC)
    resultado = PortaoQualidade().avaliar(boa)
    assert resultado.aprovado
    assert "devagar" in resultado.mensagem.lower()
