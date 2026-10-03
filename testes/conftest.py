"""Fixtures compartilhadas pelos testes de interface.

Por que uma raiz Tk para a SESSÃO inteira, e não uma por módulo:

o ttk::Style guarda estado global dentro do interpretador Tcl. Criar e destruir
vários Tk() no mesmo processo deixa esse estado inconsistente — o segundo
destroy já provoca "application has been destroyed" no ttk::ThemeChanged, e a
criação seguinte falha com `invalid command name "tcl_findLibrary"`. Quando isso
acontecia, a fixture caía no pytest.skip e a suíte de telas INTEIRA sumia do
relatório sem falhar. Era o pior desfecho possível: justamente os testes que
existem para barrar regressão de interface deixavam de rodar, em silêncio.

Com um único interpretador para toda a sessão o problema não aparece. Cada teste
limpa as janelas que abriu (ver `limpar_janelas`), de modo que um não enxerga os
widgets do outro.

Os imports de tkinter ficam DENTRO da fixture de propósito: num ambiente sem Tk,
importá-los aqui no topo derrubaria a coleta do conftest e, com ela, a suíte
inteira — inclusive os testes que não tocam em interface.
"""
import pytest


@pytest.fixture(scope="session")
def raiz():
    tkinter = pytest.importorskip("tkinter")
    from interface import tema

    try:
        janela = tkinter.Tk()
    except tkinter.TclError as erro:        # ambiente sem display
        pytest.skip(f"Tk indisponível: {erro}")
    janela.withdraw()
    tema.aplicar(janela)
    yield janela
    janela.destroy()


@pytest.fixture(autouse=True)
def limpar_janelas(request):
    """Fecha as janelas abertas pelo teste, sem derrubar a raiz da sessão.

    Só age em testes que realmente pedem a raiz: pedi-la aqui para todo mundo
    criaria um Tk mesmo nos testes que não encostam em interface.
    """
    yield
    if "raiz" not in request.fixturenames:
        return
    for filho in request.getfixturevalue("raiz").winfo_children():
        filho.destroy()
