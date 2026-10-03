"""Toda janela precisa CONSTRUIR sem erro e CABER na tela, com os botões ao alcance.

Duas falhas reais deram origem a esta suíte, e cada uma cobre metade dela:

1. Um import enxugado levou junto o `Visor`, e `JanelaCaptura` quebrou com
   NameError na hora de cadastrar um rosto. Importar o módulo não bastava para
   detectar — o nome só é resolvido quando a janela é instanciada. Por isso cada
   tela é realmente montada aqui.

2. O botão de avançar entre as sessões de captura saía da tela em monitor com
   escala de DPI: a janela se dimensionava pelo conteúdo e o que ficava de fora
   era sempre a parte de baixo. Montar sem erro não bastava — daí os testes de
   layout, que recusam janela maior que a tela, controle fora do quadro no
   tamanho mínimo, e vídeo que não cede altura quando os textos crescem.

O fluxo de USO das telas (cadastrar, desistir, fechar no meio) fica em
testes/test_fluxos_de_uso.py.
"""
from datetime import datetime

import pytest

# o módulo inteiro depende de Tk; a raiz em si vem do conftest
pytest.importorskip("tkinter")

import configuracao                                          # noqa: E402
from interface.comum import Contexto                         # noqa: E402
from testes.test_painel import BancoDuble, ReconhecedorDuble, TrilhaDuble   # noqa: E402


# a raiz Tk e a limpeza das janelas vivem em testes/conftest.py: um interpretador
# para a sessão inteira, porque criar e destruir vários Tk() quebra o ttk::Style


@pytest.fixture
def ctx():
    from dados.repositorio import RepositorioUsuarios
    banco = BancoDuble()
    return Contexto(cfg=configuracao.carregar(), banco=banco, trilha=TrilhaDuble(),
                    reconhecedor=ReconhecedorDuble(), motor=None, acervo=None,
                    usuarios=RepositorioUsuarios(banco), consentimentos=None)


def test_dialogo_de_novo_usuario_monta(raiz, ctx):
    from interface.cadastro import DialogoNovoUsuario
    dialogo = DialogoNovoUsuario(raiz, ctx)
    dialogo.withdraw()
    assert dialogo.campos["matricula"].get()          # matrícula já gerada


def test_janela_de_captura_monta(raiz, ctx):
    """Regressão do NameError: 'Visor' is not defined."""
    from interface.cadastro import JanelaCaptura
    janela = JanelaCaptura(raiz, ctx, lambda coletores: None)
    janela.withdraw()
    assert janela.visor is not None
    assert janela.barra is not None
    assert janela.preparo.winfo_exists()              # checklist presente


def test_janela_de_importar_imagens_monta(raiz, ctx):
    from interface.cadastro import JanelaImportarImagens
    janela = JanelaImportarImagens(raiz, ctx, lambda coletores: None)
    janela.withdraw()
    assert janela.tabela is not None
    assert str(janela.botao_concluir.cget("state")) == "disabled"


def test_dialogo_do_termo_monta(raiz):
    from interface.termo import DialogoTermo
    dialogo = DialogoTermo(raiz, "Ana Ribeiro Salles", lambda ok, momento: None)
    dialogo.withdraw()
    dialogo.grab_release()
    assert dialogo.texto.get("1.0", "end").strip()


def test_painel_monta(raiz, ctx):
    from interface.painel import JanelaPainel
    painel = JanelaPainel(raiz, ctx)
    painel.withdraw()
    assert painel.cartoes and painel.tabela_usuarios is not None


def test_tela_inicial_monta(raiz, ctx):
    import main
    tela = main.TelaInicial(raiz, ctx)
    assert tela.winfo_exists()


def test_consulta_ao_acervo_monta(raiz, ctx):
    """A tela que a captura de tela já pegou quebrando uma vez (pady em tupla)."""
    from acervo.entrega import ServicoAcervo
    from acervo.repositorio_acervo import RepositorioAcervo
    from autenticacao.motor import SessaoAutenticada
    from interface.relatorios import JanelaConsulta

    class AcervoVazio(ServicoAcervo):
        def listar(self, sessao):
            return []

    class RepoVazio(RepositorioAcervo):
        def agregado_por_atividade(self):
            return []

        def agregado_por_motivo(self):
            return []

        def pendencias_vencidas(self, nivel, uf=None):
            return []

    ctx.acervo = AcervoVazio(RepoVazio(ctx.banco), ctx.trilha)
    janela = JanelaConsulta(raiz, ctx, SessaoAutenticada(1, "Ana", 2, "SP", datetime.now()))
    janela.withdraw()
    assert janela.tabela_itens is not None


# ------------------------------------------------------------------ construção parcial
def test_captura_fecha_mesmo_com_construcao_interrompida(raiz, ctx, monkeypatch):
    """Regressão: 'JanelaCaptura' object has no attribute '_agendado'.

    Quando o __init__ morre no meio (foi o que aconteceu com o NameError do
    Visor), a janela já está na tela e o usuário vai fechá-la. Fechar não pode
    levantar um SEGUNDO erro em cima do primeiro — isso esconde a causa real e
    deixa a janela presa.
    """
    from interface.cadastro import JanelaCaptura

    class Explode(Exception):
        pass

    monkeypatch.setattr("interface.cadastro.Visor",
                        lambda *a, **k: (_ for _ in ()).throw(Explode("falha simulada")))
    with pytest.raises(Explode):
        JanelaCaptura(raiz, ctx, lambda c: None)

    # a janela meio construída é a última filha da raiz; fechá-la não pode estourar
    parcial = raiz.winfo_children()[-1]
    parcial._cancelar()                      # antes: AttributeError '_agendado'


def test_autenticacao_fecha_mesmo_com_construcao_interrompida(raiz, ctx, monkeypatch):
    from interface.autenticacao import JanelaAutenticacao

    class Explode(Exception):
        pass

    monkeypatch.setattr("interface.autenticacao.Visor",
                        lambda *a, **k: (_ for _ in ()).throw(Explode("falha simulada")))
    ctx.motor = object()
    with pytest.raises(Explode):
        JanelaAutenticacao(raiz, ctx, 1, lambda sessao: None)

    parcial = raiz.winfo_children()[-1]
    parcial.fechar()


def test_cancelar_captura_descarta_as_imagens(raiz, ctx):
    """Cancelar não pode deixar imagem facial viva na memória (ETP 4.3)."""
    import numpy as np
    from interface.cadastro import JanelaCaptura
    from visao.coleta import ColetorAmostras

    janela = JanelaCaptura(raiz, ctx, lambda c: None)
    janela.withdraw()
    coletor = ColetorAmostras(1, ctx.cfg)
    coletor.faces.append(np.zeros((200, 200), np.uint8))
    janela.coletores.append(coletor)

    janela._cancelar()
    assert coletor.faces == []


# ------------------------------------------------------------------ layout alcançável
# Montar sem erro não basta: a janela também precisa CABER na tela e manter os
# botões ao alcance. Um usuário relatou não conseguir avançar entre as sessões
# de captura porque o vídeo, elástico, empurrava o botão para fora do monitor.
def _controles(widget, achados=None):
    achados = achados if achados is not None else []
    if widget.winfo_class() in ("TButton", "Button", "TCheckbutton"):
        achados.append(widget)
    for filho in widget.winfo_children():
        _controles(filho, achados)
    return achados


def _dimensao(janela):
    largura, altura = janela.geometry().split("+")[0].split("x")
    return int(largura), int(altura)


@pytest.fixture
def sem_webcam(ctx):
    """A autenticação de nível 1 vai direto para a câmera; nos testes, não há."""
    from visao.aquisicao import WebcamIndisponivel

    def recusar():
        raise WebcamIndisponivel("sem câmera no ambiente de teste")

    ctx.camera = recusar
    return ctx


def test_captura_ancora_os_controles_na_base(raiz, ctx):
    """Regressão: o botão da próxima sessão saía da tela.

    O vídeo é o único elemento elástico da janela. Empacotado antes dos
    controles, ele cresce e os empurra para baixo do monitor — e a pessoa fica
    sem como seguir para a sessão seguinte nem como cancelar.
    """
    from interface.cadastro import JanelaCaptura
    janela = JanelaCaptura(raiz, ctx, lambda coletores: None)
    janela.withdraw()
    ordem = janela.pack_slaves()
    rodape = janela.botao.master
    assert rodape.pack_info()["side"] == "bottom"
    assert ordem.index(janela.visor) > ordem.index(rodape),         "o vídeo precisa ser empacotado DEPOIS dos controles"


def test_autenticacao_ancora_os_controles_na_base(raiz, sem_webcam):
    from interface.autenticacao import JanelaAutenticacao
    # nível 1 vai direto à etapa facial, que é quando o vídeo entra na tela
    janela = JanelaAutenticacao(raiz, sem_webcam, 1, lambda sessao: None)
    janela.withdraw()
    ordem = janela.pack_slaves()
    assert janela.botoes.pack_info()["side"] == "bottom"
    assert janela.status.pack_info()["side"] == "bottom"
    assert ordem.index(janela.visor) > ordem.index(janela.botoes)

    # e, depois de negar, o botão de repetir precisa estar junto dos demais
    janela._negar("webcam indisponível", None)
    assert janela.tentar.winfo_manager() == "pack"
    assert janela.tentar.master is janela.botoes


def test_nenhuma_janela_passa_do_tamanho_da_tela(raiz, sem_webcam):
    """Uma janela maior que o monitor perde justamente a parte de baixo."""
    from interface.autenticacao import JanelaAutenticacao
    from interface.cadastro import JanelaCaptura, JanelaImportarImagens
    from interface.painel import JanelaPainel
    from interface.termo import DialogoTermo

    tela_l, tela_a = raiz.winfo_screenwidth(), raiz.winfo_screenheight()
    janelas = {
        "captura": JanelaCaptura(raiz, sem_webcam, lambda c: None),
        "importar": JanelaImportarImagens(raiz, sem_webcam, lambda c: None),
        "autenticacao": JanelaAutenticacao(raiz, sem_webcam, 3, lambda s: None),
        "painel": JanelaPainel(raiz, sem_webcam),
        "termo": DialogoTermo(raiz, "Ana Ribeiro Salles", lambda ok, momento: None),
    }
    janelas["termo"].grab_release()
    for nome, janela in janelas.items():
        janela.withdraw()
        largura, altura = _dimensao(janela)
        assert largura <= tela_l, f"{nome} mais larga que a tela"
        assert altura <= tela_a, f"{nome} mais alta que a tela"


def test_largura_da_autenticacao_acompanha_a_faixa_de_etapas(raiz, sem_webcam):
    """Em tela com escala de DPI os rótulos crescem; a janela tem de crescer junto.

    O nível 3 é o caso extremo: quatro fatores lado a lado. Com largura fixa em
    pixels, «Segunda pessoa» ficaria cortado justamente no nível que mais
    depende de a pessoa entender o que ainda falta.
    """
    from interface.autenticacao import JanelaAutenticacao
    janela = JanelaAutenticacao(raiz, sem_webcam, 3, lambda sessao: None)
    janela.withdraw()
    raiz.update_idletasks()
    assert _dimensao(janela)[0] >= janela.etapas.winfo_reqwidth()


def test_controles_continuam_no_quadro_quando_a_janela_encolhe(raiz, sem_webcam):
    """No tamanho mínimo declarado, nenhum botão pode ficar fora da janela."""
    from interface.cadastro import JanelaCaptura
    janela = JanelaCaptura(raiz, sem_webcam, lambda c: None)
    minima = janela.wm_minsize()
    janela.geometry("{}x{}".format(*minima))
    janela.update_idletasks()
    altura = minima[1]
    for controle in _controles(janela):
        topo = controle.winfo_rooty() - janela.winfo_rooty()
        assert topo + controle.winfo_reqheight() <= altura,             f"{controle.cget('text')!r} escapa da janela no tamanho mínimo"


def test_video_cede_espaco_quando_a_escala_de_dpi_cresce(raiz, ctx):
    """Em tela com DPI escalado, textos e botões ocupam mais — quem encolhe é o vídeo.

    Esta é a raiz do problema relatado: a altura dos blocos fixos era um número
    em pixels, e numa tela escalada eles passavam desse número. O excedente saía
    pela base da janela, levando junto o botão de iniciar a próxima sessão.
    """
    from interface.cadastro import JanelaCaptura
    escala_original = raiz.tk.call("tk", "scaling")
    alturas = {}
    try:
        for escala in (1.0, 2.0):
            raiz.tk.call("tk", "scaling", escala)
            janela = JanelaCaptura(raiz, ctx, lambda coletores: None)
            janela.withdraw()
            alturas[escala] = janela.visor.altura
            janela.destroy()
    finally:
        raiz.tk.call("tk", "scaling", escala_original)
    assert alturas[2.0] < alturas[1.0],         "o vídeo precisa ceder altura quando os blocos fixos crescem"
