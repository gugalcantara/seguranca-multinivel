"""Desafio de vivacidade do nível 3 (RF-07).

O módulo já nasceu testável — aceita `rng` e `relogio` injetáveis —, então aqui
o desafio é determinístico e o tempo é controlado, sem webcam e sem sleep.

O Haar de olhos é substituído por um dublê: detectar olho em imagem real é
problema do OpenCV, não desta lógica. O que se verifica é a MÁQUINA DE ESTADOS
— abriu, fechou, abriu — e o sentido do movimento, que é onde mora o erro fácil
(a imagem não é espelhada, então a esquerda do usuário é a direita da imagem).
"""
import numpy as np
import pytest

import configuracao
from autenticacao.vivacidade import DesafioVivacidade, Estado

CINZA = np.full((480, 640), 128, np.uint8)


class Relogio:
    """Tempo controlado pelo teste."""

    def __init__(self):
        self.agora = 1000.0

    def __call__(self):
        return self.agora

    def avancar(self, segundos):
        self.agora += segundos


class RngFixo:
    def __init__(self, escolha):
        self.escolha = escolha

    def choice(self, _opcoes):
        return self.escolha


class OlhosDuble:
    """Devolve olhos ou nada, conforme a sequência programada."""

    def __init__(self, sequencia):
        self.sequencia = list(sequencia)

    def detectMultiScale(self, *_a, **_k):
        tem_olhos = self.sequencia.pop(0) if self.sequencia else True
        return [(10, 10, 20, 20), (50, 10, 20, 20)] if tem_olhos else []


def montar(desafio, relogio=None, olhos=None):
    d = DesafioVivacidade(configuracao.carregar(), rng=RngFixo(desafio),
                          relogio=relogio or Relogio())
    if olhos is not None:
        d._olhos = OlhosDuble(olhos)
    d.sortear()
    return d


# ------------------------------------------------------------------ sorteio
def test_sorteia_entre_os_desafios_configurados():
    cfg = configuracao.carregar()
    d = DesafioVivacidade(cfg)
    assert d.sortear() in cfg.getlista("vivacidade", "desafios")
    assert d.instrucao                       # toda opção tem instrução ao usuário


def test_alimentar_antes_de_sortear_e_erro():
    """Sem desafio sorteado não há o que avaliar — falhar alto é melhor que
    avaliar contra um desafio indefinido."""
    with pytest.raises(RuntimeError):
        DesafioVivacidade(configuracao.carregar()).alimentar(CINZA, (10, 10, 100, 100))


# ------------------------------------------------------------------ movimento
def test_mover_para_a_esquerda_do_usuario_e_para_a_direita_da_imagem():
    """A webcam NÃO é espelhada: a esquerda de quem olha aparece à direita."""
    d = montar("MOVER_ESQUERDA")
    assert d.alimentar(CINZA, (100, 50, 100, 100)) == Estado.EM_ANDAMENTO   # fixa o centro
    assert d.alimentar(CINZA, (120, 50, 100, 100)) == Estado.EM_ANDAMENTO   # 20% — insuficiente
    assert d.alimentar(CINZA, (140, 50, 100, 100)) == Estado.CONFIRMADO     # 40% >= 35%


def test_mover_para_a_direita_do_usuario_diminui_o_x():
    d = montar("MOVER_DIREITA")
    assert d.alimentar(CINZA, (300, 50, 100, 100)) == Estado.EM_ANDAMENTO
    assert d.alimentar(CINZA, (260, 50, 100, 100)) == Estado.CONFIRMADO


def test_movimento_no_sentido_errado_nao_confirma():
    """Quem move para o lado errado não cumpriu o desafio — é o ponto do RF-07."""
    d = montar("MOVER_ESQUERDA")
    d.alimentar(CINZA, (300, 50, 100, 100))
    for x in (260, 200, 120):
        assert d.alimentar(CINZA, (x, 50, 100, 100)) == Estado.EM_ANDAMENTO


def test_deslocamento_e_relativo_ao_tamanho_do_rosto():
    """35% da largura do rosto: perto da câmera exige mais pixels que longe."""
    perto = montar("MOVER_ESQUERDA")
    perto.alimentar(CINZA, (100, 50, 200, 200))
    assert perto.alimentar(CINZA, (160, 50, 200, 200)) == Estado.EM_ANDAMENTO   # 30%

    longe = montar("MOVER_ESQUERDA")
    longe.alimentar(CINZA, (100, 50, 50, 50))
    assert longe.alimentar(CINZA, (160, 50, 50, 50)) == Estado.CONFIRMADO       # 120%


# ------------------------------------------------------------------ piscada
def test_piscada_exige_abrir_fechar_e_abrir():
    # olhos: aberto, fechado, fechado, aberto
    d = montar("PISCAR", olhos=[True, False, False, True])
    assert d.alimentar(CINZA, (10, 10, 100, 100)) == Estado.EM_ANDAMENTO
    assert d.alimentar(CINZA, (10, 10, 100, 100)) == Estado.EM_ANDAMENTO
    assert d.alimentar(CINZA, (10, 10, 100, 100)) == Estado.EM_ANDAMENTO
    assert d.alimentar(CINZA, (10, 10, 100, 100)) == Estado.CONFIRMADO


def test_olhos_sempre_abertos_nunca_confirmam():
    """Uma fotografia de olhos abertos não pisca."""
    d = montar("PISCAR", olhos=[True] * 10)
    for _ in range(10):
        assert d.alimentar(CINZA, (10, 10, 100, 100)) == Estado.EM_ANDAMENTO


def test_fechar_de_saida_sem_ter_aberto_nao_conta():
    """Só conta a piscada observada do começo: evita que um quadro escuro inicial
    seja interpretado como olho fechado."""
    d = montar("PISCAR", olhos=[False, False, False, True])
    for _ in range(3):
        assert d.alimentar(CINZA, (10, 10, 100, 100)) == Estado.EM_ANDAMENTO
    assert d.alimentar(CINZA, (10, 10, 100, 100)) == Estado.EM_ANDAMENTO


def test_piscada_rapida_demais_nao_conta():
    """Um único frame sem olhos pode ser falha de detecção, não piscada."""
    d = montar("PISCAR", olhos=[True, False, True])
    d.alimentar(CINZA, (10, 10, 100, 100))
    d.alimentar(CINZA, (10, 10, 100, 100))
    assert d.alimentar(CINZA, (10, 10, 100, 100)) == Estado.EM_ANDAMENTO


# ------------------------------------------------------------------ tempo e ausência
def test_expira_depois_do_timeout():
    relogio = Relogio()
    d = montar("MOVER_ESQUERDA", relogio=relogio)
    d.alimentar(CINZA, (100, 50, 100, 100))
    relogio.avancar(configuracao.carregar().getfloat("vivacidade", "timeout") + 0.1)
    assert d.alimentar(CINZA, (300, 50, 100, 100)) == Estado.EXPIRADO


def test_sem_face_no_frame_apenas_aguarda():
    """Rosto fora de quadro não expira nem confirma — só não conta."""
    d = montar("MOVER_ESQUERDA")
    assert d.alimentar(CINZA, None) == Estado.EM_ANDAMENTO
    assert d.alimentar(CINZA, (100, 50, 100, 100)) == Estado.EM_ANDAMENTO
    assert d.alimentar(CINZA, None) == Estado.EM_ANDAMENTO
    assert d.alimentar(CINZA, (140, 50, 100, 100)) == Estado.CONFIRMADO


def test_sair_do_quadro_nao_vale_como_piscada():
    """Regressão: o Haar devolve "nenhum olho" para recorte vazio, SEM erro.

    Com o rosto saindo pela borda (o KCF devolve x ou y negativo), a fatia fica
    vazia e os frames seriam contados como olhos fechados — bastaria sair de cena
    depois de aparecer para cumprir o desafio do nível 3.
    """
    d = montar("PISCAR", olhos=[True, False, False, True])
    assert d.alimentar(CINZA, (100, 100, 120, 120)) == Estado.EM_ANDAMENTO   # viu aberto
    # agora o rosto sai do quadro: recortes vazios, que NÃO podem contar
    assert d.alimentar(CINZA, (-130, 100, 120, 120)) == Estado.EM_ANDAMENTO
    assert d.alimentar(CINZA, (100, -130, 120, 120)) == Estado.EM_ANDAMENTO
    assert d.alimentar(CINZA, (100, 100, 120, 120)) == Estado.EM_ANDAMENTO   # não confirmou


def test_rosto_parcialmente_cortado_e_inconclusivo():
    """Metade do rosto fora do quadro não dá base para afirmar que piscou."""
    d = montar("PISCAR", olhos=[True, False, False, True])
    d.alimentar(CINZA, (100, 100, 120, 120))
    for _ in range(2):
        assert d.alimentar(CINZA, (-80, 100, 120, 120)) == Estado.EM_ANDAMENTO  # só 1/3 visível
    assert d.alimentar(CINZA, (100, 100, 120, 120)) == Estado.EM_ANDAMENTO


def test_rosto_quase_todo_visivel_continua_valendo():
    """A proteção não pode ser tão rígida que rejeite rosto levemente na borda."""
    d = montar("PISCAR", olhos=[True, False, False, True])
    assert d.alimentar(CINZA, (-10, 100, 120, 120)) == Estado.EM_ANDAMENTO   # 92% visível
    assert d.alimentar(CINZA, (-10, 100, 120, 120)) == Estado.EM_ANDAMENTO
    assert d.alimentar(CINZA, (-10, 100, 120, 120)) == Estado.EM_ANDAMENTO
    assert d.alimentar(CINZA, (-10, 100, 120, 120)) == Estado.CONFIRMADO


def test_sortear_de_novo_zera_o_progresso():
    """Novo desafio não pode herdar o deslocamento já feito no anterior."""
    d = montar("MOVER_ESQUERDA")
    d.alimentar(CINZA, (100, 50, 100, 100))
    d.sortear()
    assert d.alimentar(CINZA, (140, 50, 100, 100)) == Estado.EM_ANDAMENTO
