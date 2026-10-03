"""Identidade visual da aplicação: paleta, fontes, estilos ttk, widgets de painel
e o dimensionamento das janelas.

Centralizado aqui pelo mesmo motivo que os parâmetros ficam no config.ini
(princípio 10): nenhuma cor ou fonte solta no meio da lógica das telas.

O tema base é o "clam", não o "vista" padrão do Windows. O vista delega o
desenho ao tema nativo e IGNORA background/foreground na maioria dos widgets,
o que tornaria qualquer paleta própria inócua. O clam aceita as opções de cor.

As três funções do fim do arquivo — `ajustar_a_tela`, `altura_para_video` e
`quebrar_com_a_janela` — existem porque medida fixa em pixels não sobrevive à
escala de DPI: o que a janela ganha de altura sai pela base, levando junto os
botões. Todas MEDEM em vez de estimar, e por isso `altura_para_video` só pode
ser chamada depois que o restante da janela já foi empacotado.
"""
from datetime import date, datetime
from decimal import Decimal
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk
from typing import NamedTuple

# ------------------------------------------------------------------ paleta
FUNDO = "#f4f6f8"            # ground da janela
SUPERFICIE = "#ffffff"       # cartões e tabelas
SUPERFICIE_ALT = "#f8fafb"   # linha alternada da tabela
CABECALHO = "#e8ecef"
BORDA = "#d4dae0"
TEXTO = "#1d2429"
TEXTO_SUAVE = "#6b767f"
ACENTO = "#2e6f8e"
ACENTO_ESCURO = "#255a73"

OK = "#1f7a4d"
AVISO = "#b07d14"
ERRO = "#a8322d"

# Cor e nome de cada nível de acesso — fonte única; comum.py reexporta para
# não haver o mesmo valor escrito em dois lugares.
CORES_NIVEL = {1: "#8a949c", 2: ACENTO, 3: ERRO}
NOMES_NIVEL = {1: "Consulta pública assistida", 2: "Consulta restrita", 3: "Custódia"}

# ------------------------------------------------------------------ fontes
FAMILIA = "Segoe UI"
MONO = "Consolas"
F_TITULO = (FAMILIA, 16, "bold")
F_SUBTITULO = (FAMILIA, 10)
F_BASE = (FAMILIA, 10)
F_FORTE = (FAMILIA, 10, "bold")
F_ROTULO = (FAMILIA, 8, "bold")
F_VALOR = (FAMILIA, 22, "bold")
F_VALOR_TEXTO = (FAMILIA, 15, "bold")   # valor que é palavra, não número
F_MONO = (MONO, 9)
F_CODIGO = (MONO, 12, "bold")   # matrícula e outros códigos lidos/digitados


def aplicar(raiz):
    """Configura o ttk.Style da aplicação. Chamar uma vez, sobre a janela raiz."""
    estilo = ttk.Style(raiz)
    estilo.theme_use("clam")
    raiz.configure(bg=FUNDO)

    estilo.configure(".", background=FUNDO, foreground=TEXTO, font=F_BASE,
                     borderwidth=0, focuscolor=ACENTO)
    estilo.configure("TFrame", background=FUNDO)
    estilo.configure("TLabel", background=FUNDO, foreground=TEXTO)
    estilo.configure("TNotebook", background=FUNDO, borderwidth=0)
    estilo.configure("TNotebook.Tab", background=FUNDO, foreground=TEXTO_SUAVE,
                     padding=(16, 8), font=F_BASE)
    estilo.map("TNotebook.Tab",
               background=[("selected", SUPERFICIE)],
               foreground=[("selected", ACENTO)],
               font=[("selected", F_FORTE)])

    # --- rótulos de texto
    estilo.configure("Titulo.TLabel", font=F_TITULO)
    estilo.configure("Subtitulo.TLabel", font=F_SUBTITULO, foreground=TEXTO_SUAVE)
    estilo.configure("Forte.TLabel", font=F_FORTE)
    estilo.configure("Suave.TLabel", foreground=TEXTO_SUAVE)
    estilo.configure("Erro.TLabel", foreground=ERRO, font=F_FORTE)
    # título de seção sobre o fundo da janela (o Rotulo.TLabel tem fundo branco,
    # próprio para o interior dos cartões)
    estilo.configure("Secao.TLabel", font=F_ROTULO, foreground=TEXTO_SUAVE)

    # --- superfícies. A variante "Lisa" é para frames ANINHADOS dentro de uma
    # superfície: sem ela, cada frame interno redesenha a borda e aparecem
    # retângulos soltos no meio do conteúdo.
    for nome in ("Superficie.TFrame", "Cartao.TFrame"):
        estilo.configure(nome, background=SUPERFICIE, relief="solid",
                         borderwidth=1, bordercolor=BORDA)
    estilo.configure("SuperficieLisa.TFrame", background=SUPERFICIE, relief="flat", borderwidth=0)
    for nome in ("Superficie.TLabel", "Rotulo.TLabel", "Valor.TLabel", "Detalhe.TLabel"):
        estilo.configure(nome, background=SUPERFICIE)
    estilo.configure("Rotulo.TLabel", font=F_ROTULO, foreground=TEXTO_SUAVE)
    estilo.configure("Valor.TLabel", font=F_VALOR)
    estilo.configure("Detalhe.TLabel", foreground=TEXTO_SUAVE, font=F_SUBTITULO)

    # --- botões
    estilo.configure("TButton", background=CABECALHO, foreground=TEXTO,
                     padding=(12, 7), relief="flat", font=F_BASE)
    estilo.map("TButton", background=[("active", BORDA), ("disabled", FUNDO)],
               foreground=[("disabled", TEXTO_SUAVE)])
    estilo.configure("Acento.TButton", background=ACENTO, foreground="white", font=F_FORTE)
    estilo.map("Acento.TButton", background=[("active", ACENTO_ESCURO), ("disabled", BORDA)])
    estilo.configure("Perigo.TButton", background=ERRO, foreground="white", font=F_FORTE)
    estilo.map("Perigo.TButton", background=[("active", "#8c2824"), ("disabled", BORDA)])

    # --- barra de progresso
    estilo.configure("Medidor.Horizontal.TProgressbar", background=ACENTO,
                     troughcolor=CABECALHO, borderwidth=0, thickness=8)

    # --- tabelas: o layout nu remove a moldura que o clam desenha por padrão.
    # A altura da linha vem da métrica da fonte, não de um número de pixels:
    # em tela com escala de DPI a fonte cresce e uma altura fixa cortaria o texto.
    altura_linha = tkfont.Font(font=F_BASE).metrics("linespace") + 8
    estilo.layout("Tabela.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    estilo.configure("Tabela.Treeview", background=SUPERFICIE, fieldbackground=SUPERFICIE,
                     foreground=TEXTO, rowheight=altura_linha, font=F_BASE, borderwidth=0)
    estilo.configure("Tabela.Treeview.Heading", background=CABECALHO, foreground=TEXTO_SUAVE,
                     font=F_ROTULO, relief="flat", padding=(8, 7))
    estilo.map("Tabela.Treeview.Heading", background=[("active", BORDA)])
    estilo.map("Tabela.Treeview", background=[("selected", ACENTO)],
               foreground=[("selected", "white")])
    return estilo


# ------------------------------------------------------------------ formatação
def formatar(valor):
    """Valor vindo do banco -> texto de célula. None vira travessão, não "None"."""
    if valor is None:
        return "—"
    if isinstance(valor, bool):
        return "sim" if valor else "não"
    if isinstance(valor, datetime):
        return valor.strftime("%d/%m/%Y %H:%M:%S")
    if isinstance(valor, date):
        return valor.strftime("%d/%m/%Y")
    if isinstance(valor, Decimal):
        return f"{float(valor):g}"
    return str(valor)


def _chave_ordem(valor):
    """Ordena coluna de tipo misto sem explodir: nulos, números, datas, texto.

    A tupla devolvida é sempre (int, float, str), então quaisquer dois valores
    da mesma coluna ficam comparáveis — inclusive None ao lado de número, que
    com sorted() puro levantaria TypeError.
    """
    if valor is None:
        return (0, 0.0, "")
    if isinstance(valor, bool):
        return (1, float(valor), "")
    if isinstance(valor, (int, float, Decimal)):
        return (1, float(valor), "")
    if isinstance(valor, (datetime, date)):
        return (2, 0.0, valor.isoformat())   # ISO ordena na mesma ordem da data
    return (3, 0.0, str(valor).casefold())


# ------------------------------------------------------------------ widgets
def _fonte_do_valor(valor):
    """Número fica grande; palavra ("ÍNTEGRA", "RUPTURA") usa corpo menor para
    não quebrar em duas linhas dentro do cartão."""
    return F_VALOR if len(str(valor)) <= 6 else F_VALOR_TEXTO


class Coluna(NamedTuple):
    chave: str           # chave do dicionário devolvido pelo repositório
    titulo: str
    largura: int = 12    # TETO em caracteres (a largura real sai do conteúdo)
    ancora: str = "w"
    elastica: bool = False   # recebe o espaço que sobra na tabela
    formato: object = None   # callable(valor) -> str; sem ele, usa formatar()


def texto_da_celula(coluna, linha):
    valor = linha.get(coluna.chave)
    return coluna.formato(valor) if coluna.formato else formatar(valor)


PADDING_CELULA = 24
MINIMO_COLUNA = 46


class Cartao(ttk.Frame):
    """Indicador do painel: rótulo pequeno, número grande, detalhe embaixo."""

    def __init__(self, mestre, rotulo, valor="—", detalhe="", cor=None, largura=185):
        super().__init__(mestre, style="Cartao.TFrame", padding=(14, 12))
        ttk.Label(self, text=rotulo.upper(), style="Rotulo.TLabel").pack(anchor="w")
        self._valor = ttk.Label(self, text=valor, style="Valor.TLabel",
                                foreground=cor or TEXTO, font=_fonte_do_valor(valor))
        self._valor.pack(anchor="w", pady=(2, 0))
        self._detalhe = ttk.Label(self, text=detalhe, style="Detalhe.TLabel", wraplength=largura)
        self._detalhe.pack(anchor="w")

    def atualizar(self, valor, detalhe="", cor=None):
        self._valor.configure(text=str(valor), foreground=cor or TEXTO,
                              font=_fonte_do_valor(valor))
        self._detalhe.configure(text=detalhe)

    @property
    def valor(self):
        return self._valor.cget("text")

    @property
    def detalhe(self):
        return self._detalhe.cget("text")

    @property
    def cor(self):
        return str(self._valor.cget("foreground"))


class Tabela(ttk.Frame):
    """Treeview sobre uma lista de dicionários — substitui o texto de largura fixa.

    Guarda o dicionário original de cada linha, para que selecionada() devolva o
    registro inteiro (com id e tipos nativos) e não as strings exibidas.
    Clicar no cabeçalho ordena; clicar de novo inverte.
    """

    def __init__(self, mestre, colunas, altura=12, ao_selecionar=None, tag_por_linha=None):
        super().__init__(mestre, style="Superficie.TFrame")
        self.colunas = [c if isinstance(c, Coluna) else Coluna(*c) for c in colunas]
        self._linhas = {}
        self._ordenado_por = None
        self._decrescente = False
        self._tag_por_linha = tag_por_linha

        chaves = [c.chave for c in self.colunas]
        self.arvore = ttk.Treeview(self, columns=chaves, show="headings", height=altura,
                                   style="Tabela.Treeview", selectmode="browse")
        self._fonte = tkfont.Font(font=F_BASE)
        # Só a coluna elástica estica. Com stretch em todas, a sobra é repartida
        # igualmente e abrem-se vãos enormes entre colunas curtas.
        elasticas = {c.chave for c in self.colunas if c.elastica} or {self.colunas[-1].chave}
        for c in self.colunas:
            self.arvore.heading(c.chave, text=c.titulo, anchor=c.ancora,
                                command=lambda k=c.chave: self._ordenar(k))
            self.arvore.column(c.chave, anchor=c.ancora, minwidth=MINIMO_COLUNA,
                               stretch=c.chave in elasticas)
        self.arvore.tag_configure("impar", background=SUPERFICIE)
        self.arvore.tag_configure("par", background=SUPERFICIE_ALT)

        vertical = ttk.Scrollbar(self, orient="vertical", command=self.arvore.yview)
        self._horizontal = ttk.Scrollbar(self, orient="horizontal", command=self.arvore.xview)
        self.arvore.configure(yscrollcommand=vertical.set, xscrollcommand=self._xscroll)
        self.arvore.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        self._horizontal.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self._vazio = ttk.Label(self, text="(nenhum registro)", style="Detalhe.TLabel")
        if ao_selecionar:
            self.arvore.bind("<<TreeviewSelect>>", lambda _: ao_selecionar(self.selecionada()))

    def _xscroll(self, inicio, fim):
        """Mostra a barra horizontal só quando há o que rolar.

        Deixá-la fixa custa uma faixa de altura em cada tabela — espaço que, numa
        tela com escala de DPI, vale uma linha de dados.
        """
        self._horizontal.set(inicio, fim)
        if float(inicio) <= 0.0 and float(fim) >= 1.0:
            self._horizontal.grid_remove()
        else:
            self._horizontal.grid()

    def configurar_tag(self, nome, **opcoes):
        """Cor própria para um grupo de linhas (ex.: negadas em vermelho)."""
        self.arvore.tag_configure(nome, **opcoes)

    def preencher(self, linhas):
        self.arvore.delete(*self.arvore.get_children())
        self._linhas = {}
        for i, linha in enumerate(linhas):
            iid = str(i)
            self._linhas[iid] = linha
            tags = ["par" if i % 2 else "impar"]
            if self._tag_por_linha:
                extra = self._tag_por_linha(linha)
                if extra:
                    tags.append(extra)
            self.arvore.insert("", "end", iid=iid, tags=tuple(tags),
                               values=[texto_da_celula(c, linha) for c in self.colunas])
        self._ajustar_colunas(linhas)
        if linhas:
            self._vazio.place_forget()
        else:
            self._vazio.place(relx=0.5, rely=0.5, anchor="center")

    def _ajustar_colunas(self, linhas):
        """Largura = maior conteúdo realmente exibido, com teto por coluna.

        Medir o texto em vez de fixar pixels resolve dois problemas de uma vez:
        a coluna não trunca em tela com escala de DPI (a fonte cresce, a medida
        acompanha) e não sobra coluna larga e vazia. Coluna.largura passa a ser
        só o TETO, em caracteres, para que um motivo longo não empurre o resto
        da tabela para fora da tela — aí entra a barra horizontal.
        """
        amostra = linhas[:200]          # o bastante para dimensionar; não varre tudo
        largura_zero = self._fonte.measure("0")
        for c in self.colunas:
            largura = self._fonte.measure(c.titulo) + PADDING_CELULA + 12   # cabe a seta de ordem
            for linha in amostra:
                largura = max(largura,
                              self._fonte.measure(texto_da_celula(c, linha)) + PADDING_CELULA)
            teto = largura_zero * c.largura + PADDING_CELULA
            self.arvore.column(c.chave, width=max(MINIMO_COLUNA, min(largura, teto)))

    def _ordenar(self, chave):
        self._decrescente = not self._decrescente if self._ordenado_por == chave else False
        self._ordenado_por = chave
        ordenadas = sorted(self._linhas.values(), key=lambda l: _chave_ordem(l.get(chave)),
                           reverse=self._decrescente)
        seta = " ▾" if self._decrescente else " ▴"
        for c in self.colunas:
            self.arvore.heading(c.chave, text=c.titulo + (seta if c.chave == chave else ""))
        self.preencher(ordenadas)

    def selecionada(self):
        """Dicionário completo da linha selecionada, ou None."""
        selecao = self.arvore.selection()
        return self._linhas.get(selecao[0]) if selecao else None


class CartaoNivel(ttk.Frame):
    """Cartão de um nível de acesso: faixa colorida, o que exige e o que entrega.

    Substituiu três botões iguais que só diziam o nome do nível. Mostrar os
    fatores e o alcance de cada um na própria porta de entrada poupa a explicação
    e deixa visível, de relance, que a exigência cresce junto com o que se vê.
    """

    def __init__(self, mestre, nivel, nome, fatores, alcance, exportacao, ao_entrar):
        super().__init__(mestre, style="Cartao.TFrame")
        cor = CORES_NIVEL[nivel]
        faixa = tk.Frame(self, bg=cor, height=6)
        faixa.pack(fill="x")

        corpo = ttk.Frame(self, style="SuperficieLisa.TFrame", padding=(16, 14))
        corpo.pack(fill="both", expand=True)

        # o botão é ancorado na BASE antes do texto entrar: assim os três cartões
        # alinham os botões entre si, por mais que as descrições tenham alturas
        # diferentes
        tk.Button(corpo, text=f"Entrar no nível {nivel}", bg=cor, fg="white",
                  font=F_FORTE, relief="flat", pady=8, cursor="hand2",
                  activebackground=cor, activeforeground="white",
                  command=ao_entrar).pack(side="bottom", fill="x", pady=(14, 0))

        ttk.Label(corpo, text=f"NÍVEL {nivel}", style="Rotulo.TLabel",
                  foreground=cor).pack(anchor="w")
        ttk.Label(corpo, text=nome, style="Superficie.TLabel",
                  font=(FAMILIA, 13, "bold")).pack(anchor="w", pady=(2, 10))

        for icone, texto in (("🔑", fatores), ("👁", alcance), ("⬇", exportacao)):
            linha = ttk.Frame(corpo, style="SuperficieLisa.TFrame")
            linha.pack(fill="x", pady=2, anchor="n")
            ttk.Label(linha, text=icone, style="Superficie.TLabel",
                      width=3).pack(side="left", anchor="n")
            ttk.Label(linha, text=texto, style="Detalhe.TLabel", wraplength=210,
                      justify="left").pack(side="left", anchor="w")


def ajustar_a_tela(janela, largura, altura, margem_vertical=90):
    """Centra a janela e a limita à área útil da tela.

    Sem isto, uma janela que se dimensiona pelo conteúdo cresce além do monitor
    quando há escala de DPI — e o que fica de fora é sempre a parte de baixo,
    justamente onde ficam os botões de continuar. Devolve o tamanho concedido.
    """
    disponivel_l = janela.winfo_screenwidth() - 60
    disponivel_a = janela.winfo_screenheight() - margem_vertical
    larga = min(largura, disponivel_l)
    alta = min(altura, disponivel_a)
    x = max(0, (janela.winfo_screenwidth() - larga) // 2)
    y = max(0, (janela.winfo_screenheight() - alta) // 2 - 20)
    janela.geometry(f"{larga}x{alta}+{x}+{y}")
    return larga, alta


def altura_para_video(janela, altura_janela, minimo=240):
    """Altura livre para o vídeo: o que sobra depois de TUDO que já foi empacotado.

    O vídeo é o único elemento que pode encolher sem prejuízo — texto e botões
    não. Então ele recebe a sobra, nunca o contrário. E a sobra é MEDIDA, não
    estimada: reservar um número fixo de pixels erra em tela com escala de DPI,
    onde os mesmos textos e botões ocupam bem mais altura. Por isso esta função
    só funciona se for chamada depois de empacotar o restante da janela.
    """
    janela.update_idletasks()
    ocupado = sum(filho.winfo_reqheight() for filho in janela.pack_slaves())
    return max(minimo, altura_janela - ocupado)


def quebrar_com_a_janela(rotulo, janela, margem=40):
    """Faz o rótulo quebrar linha na largura ATUAL da janela, não numa medida fixa.

    wraplength em pixels fixos erra para os dois lados: numa janela estreita o
    texto vaza pelas bordas, e numa mensagem longa ele força a janela a crescer
    além da tela — levando os botões junto. Religar a cada <Configure> custa
    nada e mantém a mensagem inteira legível em qualquer largura.
    """
    def ajustar(evento):
        if evento.widget is janela:
            rotulo.configure(wraplength=max(240, evento.width - margem))

    janela.bind("<Configure>", ajustar, add="+")
    janela.after_idle(
        lambda: rotulo.winfo_exists()
        and rotulo.configure(wraplength=max(240, janela.winfo_width() - margem)))


def cabecalho(mestre, titulo, subtitulo="", cor=ACENTO):
    """Faixa de título no topo de uma janela. Devolve o rótulo da direita, livre
    para quem chama escrever ali um relógio ou um status."""
    barra = ttk.Frame(mestre, style="Superficie.TFrame", padding=(16, 12))
    barra.pack(fill="x")
    esquerda = ttk.Frame(barra, style="SuperficieLisa.TFrame")
    esquerda.pack(side="left")
    ttk.Label(esquerda, text=titulo, style="Titulo.TLabel",
              background=SUPERFICIE, foreground=cor).pack(anchor="w")
    if subtitulo:
        ttk.Label(esquerda, text=subtitulo, style="Detalhe.TLabel").pack(anchor="w")
    direita = ttk.Label(barra, style="Detalhe.TLabel")
    direita.pack(side="right")
    return direita
