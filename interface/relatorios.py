"""Consulta ao acervo após a autenticação — o conteúdo já chega tratado para o nível.

Aba Acervo: itens que o nível pode ver, abertos com tarja + carimbo + marca d'água.
Aba Indicadores: agregados da camada causal (RF-20) e pendências vencidas (RF-15).

A tela não decide nada sobre visibilidade: ela exibe o que o ServicoAcervo
entrega. A supressão já aconteceu antes, sobre os pixels (RF-10).
"""
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from acervo.entrega import POLITICA_EXPORTACAO
from acervo.repositorio_acervo import RepositorioAcervo
from acervo.tarja import AcessoNegado
from interface import tema
from interface.comum import CORES_NIVEL, NOMES_NIVEL, Visor
from interface.tema import Coluna, legivel

ROTULOS_EXPORTACAO = {"LIVRE": "livre", "COM_MARCA_DAGUA": "com marca d'água invisível",
                      "BLOQUEADA": "bloqueada — somente visualização"}

COLUNAS_ITENS = [
    Coluna("codigo", "Código", 8),
    Coluna("titulo", "Título", 26, "w", elastica=True),
    Coluna("tipo", "Tipo", 11, formato=legivel),
    Coluna("nivel_minimo", "Nível", 6, "center"),
]

COLUNAS_ATIVIDADE = [
    Coluna("uf", "UF", 5, "center"),
    Coluna("atividade", "Atividade", 8),
    Coluna("descricao", "Descrição", 40, "w", elastica=True),
    Coluna("pendencias", "Pendências", 11, "e"),
]

COLUNAS_MOTIVO = [
    Coluna("motivo", "Motivo", 8, formato=legivel),
    Coluna("descricao", "Descrição", 40, "w", elastica=True),
    Coluna("pendencias", "Pendências", 11, "e"),
    Coluna("vencidas", "Vencidas", 9, "e"),
]

# O nível 1 recebe só a contagem por UF; a partir do 2, a lista detalhada (RF-15)
COLUNAS_VENCIDAS_N1 = [
    Coluna("uf", "UF", 6, "center"),
    Coluna("vencidas", "Pendências vencidas", 20, "e"),
]
COLUNAS_VENCIDAS = [
    Coluna("codigo", "Código", 10),
    Coluna("substancia", "Substância", 30, "w", elastica=True),
    Coluna("uf", "UF", 5, "center"),
    Coluna("municipio", "Município", 22),
    Coluna("prazo_coleta", "Prazo", 12),
    Coluna("dias_atraso", "Atraso (dias)", 13, "e"),
    Coluna("motivo", "Motivo", 8, formato=legivel),
]


class JanelaConsulta(tk.Toplevel):
    def __init__(self, mestre, ctx, sessao):
        super().__init__(mestre)
        self.ctx, self.sessao = ctx, sessao
        self.repo = RepositorioAcervo(ctx.banco)
        self.atual = None
        self.title(f"Acervo — {sessao.nome} (nível {sessao.nivel})")
        self.bind("<Escape>", lambda _: self.destroy())
        self.minsize(900, 600)
        tema.ajustar_a_tela(self, 1340, 880)
        self.configure(bg=tema.FUNDO)

        cor = CORES_NIVEL[sessao.nivel]
        cabecalho = tk.Frame(self, bg=cor)
        cabecalho.pack(fill="x")
        dois = f"  +  usuário {sessao.usuario2_id} (regra dos dois)" if sessao.usuario2_id else ""
        # tk.Label (clássico) só aceita pady inteiro; a tupla pertence ao pack
        tk.Label(cabecalho, text=f"{sessao.nome}{dois}", bg=cor, fg="white", font=tema.F_TITULO,
                 padx=16).pack(anchor="w", pady=(10, 0))
        tk.Label(cabecalho, text=f"Nível {sessao.nivel} — {NOMES_NIVEL[sessao.nivel]}"
                                 + (f"  ·  região {sessao.uf}" if sessao.uf else ""),
                 bg=cor, fg="white", font=tema.F_SUBTITULO, padx=16).pack(anchor="w", pady=(0, 10))
        self.relogio = tk.Label(cabecalho, bg=cor, fg="white", font=tema.F_FORTE, padx=16)
        self.relogio.place(relx=1.0, rely=0.5, anchor="e")

        ttk.Label(self, text="Protótipo acadêmico — todo item marcado como DADO FICTÍCIO é sintético.",
                  style="Erro.TLabel").pack(anchor="w", padx=12, pady=(8, 0))

        abas = ttk.Notebook(self)
        abas.pack(fill="both", expand=True, padx=10, pady=10)
        abas.add(self._aba_acervo(abas), text="Acervo")
        abas.add(self._aba_indicadores(abas), text="Indicadores")
        self._tique()

    # ------------------------------------------------------------ acervo
    def _aba_acervo(self, abas):
        quadro = ttk.Frame(abas, padding=12)
        esquerda = ttk.Frame(quadro)
        esquerda.pack(side="left", fill="y")
        ttk.Label(esquerda, text="ITENS DISPONÍVEIS PARA O SEU NÍVEL",
                  style="Secao.TLabel").pack(anchor="w", pady=(0, 5))

        self.itens = self.ctx.acervo.listar(self.sessao)
        self.tabela_itens = tema.Tabela(esquerda, COLUNAS_ITENS, altura=8,
                                        ao_selecionar=self._abrir)
        self.tabela_itens.pack(fill="x")
        self.tabela_itens.preencher(self.itens)

        politica = POLITICA_EXPORTACAO[self.sessao.nivel]
        acoes = ttk.Frame(esquerda)
        acoes.pack(fill="x", pady=(10, 0))
        # habilita só com um item aberto: antes ele ficava ativo desde o início e
        # o único efeito do clique era um aviso dizendo para abrir um item
        self.exporta = politica != "BLOQUEADA"
        self.exportar = ttk.Button(acoes, text="Exportar item aberto", style="Acento.TButton",
                                   state="disabled", command=self._exportar)
        self.exportar.pack(side="left")
        ttk.Label(esquerda, text=f"Exportação: {ROTULOS_EXPORTACAO[politica]}",
                  style="Suave.TLabel").pack(anchor="w", pady=(4, 0))

        ttk.Label(esquerda, text="FICHA CAUSAL", style="Secao.TLabel").pack(anchor="w", pady=(14, 5))
        self.ficha = tk.Text(esquerda, width=56, height=16, font=tema.F_MONO, wrap="word",
                             relief="solid", borderwidth=1, background=tema.SUPERFICIE,
                             foreground=tema.TEXTO, padx=10, pady=8)
        self.ficha.pack(fill="both", expand=True)
        self.ficha.tag_configure("orientacao", foreground=tema.TEXTO_SUAVE)
        self._escrever_ficha("Selecione um item na lista acima para ver aqui a ficha causal.",
                             orientacao=True)
        esquerda.pack_propagate(False)
        esquerda.configure(width=540)

        direita = ttk.Frame(quadro)
        direita.pack(side="left", fill="both", expand=True, padx=(12, 0))
        self.titulo_item = ttk.Label(direita, style="Forte.TLabel")
        self.titulo_item.pack(anchor="w", pady=(0, 5))
        self.visor = Visor(direita, 900, 660, style="Suave.TLabel",
                           text="Selecione um item na lista à esquerda para abri-lo aqui.")
        self.visor.pack(pady=(40, 0))
        return quadro

    def _abrir(self, item_selecionado):
        if not item_selecionado:
            return
        item_id = item_selecionado["id"]
        try:
            item, imagem = self.ctx.acervo.abrir(self.sessao, item_id)
        except AcessoNegado as erro:
            messagebox.showwarning("Acesso negado", str(erro), parent=self)
            if "expirada" in str(erro):
                self.destroy()
            return
        self.atual = (item_id, imagem)
        self.visor.configure(text="")
        self.visor.pack_configure(pady=0)
        self.visor.mostrar(imagem)
        if self.exporta:
            self.exportar.configure(state="normal")
        self.titulo_item.configure(text=f"{item['codigo']} — {item['titulo']}")
        self._mostrar_ficha(item)

    def _mostrar_ficha(self, item):
        """A2-01: ficha causal e cadeia de responsabilidade — só a partir do N2 (RF-21)."""
        if not item.get("pendencia_id"):
            return self._escrever_ficha("Item sem pendência vinculada.", orientacao=True)
        ficha = self.repo.ficha_pendencia(item["pendencia_id"], self.sessao.nivel)
        if ficha is None:
            return self._escrever_ficha("Ficha causal disponível a partir do nível 2.\n\n"
                                        "O nível 1 vê apenas dados agregados, sem localização "
                                        "nem cadeia de responsabilidade (RF-20, RF-21).",
                                        orientacao=True)
        linhas = [f"{ficha['codigo']} — {ficha['substancia']}", "",
                  f"Atividade geradora: {ficha['atividade']}",
                  f"  {ficha['atividade_descricao']}", "",
                  f"Motivo da permanência: {ficha['motivo']}",
                  f"  {ficha['motivo_descricao']}", "",
                  f"Base legal: {ficha['base_legal']}", "",
                  f"Ação institucional: {ficha['acao_institucional']}", "",
                  "Cadeia de responsabilidade:"]
        responsaveis = self.repo.responsaveis(item["pendencia_id"], self.sessao.nivel)
        linhas += [f"  · {r['vinculo']}: {r['nome']} ({r['situacao_cadastral']})"
                   for r in responsaveis] or ["  (nenhum visível neste nível)"]
        self._escrever_ficha("\n".join(linhas))

    def _escrever_ficha(self, texto, orientacao=False):
        """Único ponto que escreve na ficha — e a deixa travada para edição.

        A ficha é um registro do acervo, não um campo de anotação; antes o
        tk.Text aceitava digitação e a pessoa podia escrever por cima dela.
        """
        self.ficha.configure(state="normal")
        self.ficha.delete("1.0", "end")
        self.ficha.insert("end", texto, ("orientacao",) if orientacao else ())
        self.ficha.configure(state="disabled")

    def _exportar(self):
        if not self.atual:
            messagebox.showinfo("Exportar", "Abra um item primeiro.", parent=self)
            return
        try:
            destino = self.ctx.acervo.exportar(self.sessao, *self.atual)
        except AcessoNegado as erro:
            messagebox.showwarning("Exportação bloqueada", str(erro), parent=self)
            return
        messagebox.showinfo("Exportado", f"Arquivo gravado em:\n{destino}\n\n"
                                         "A marca d'água invisível registra quem exportou e quando.",
                            parent=self)

    # ------------------------------------------------------------ indicadores
    def _aba_indicadores(self, abas):
        quadro = ttk.Frame(abas, padding=12)
        quadro.columnconfigure(0, weight=1)
        quadro.rowconfigure(1, weight=1)
        quadro.rowconfigure(3, weight=1)

        ttk.Label(quadro, text="DISTRIBUIÇÃO POR ATIVIDADE GERADORA E POR MOTIVO (A1-02)",
                  style="Secao.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 5))
        par = ttk.Frame(quadro)
        par.grid(row=1, column=0, sticky="nsew")
        par.columnconfigure(0, weight=1)
        par.columnconfigure(1, weight=1)
        par.rowconfigure(0, weight=1)
        atividade = tema.Tabela(par, COLUNAS_ATIVIDADE, altura=9)
        atividade.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        atividade.preencher(self._seguro(self.repo.agregado_por_atividade))
        motivo = tema.Tabela(par, COLUNAS_MOTIVO, altura=9)
        motivo.grid(row=0, column=1, sticky="nsew")
        motivo.preencher(self._seguro(self.repo.agregado_por_motivo))

        rotulo = ("PENDÊNCIAS VENCIDAS POR UF — CONTAGEM AGREGADA (RF-15)" if self.sessao.nivel == 1
                  else f"PENDÊNCIAS VENCIDAS (RF-15)"
                       + (f" — REGIÃO {self.sessao.uf}" if self.sessao.nivel == 2 else " — NACIONAL"))
        ttk.Label(quadro, text=rotulo, style="Secao.TLabel").grid(row=2, column=0, sticky="w",
                                                                  pady=(14, 5))
        colunas = COLUNAS_VENCIDAS_N1 if self.sessao.nivel == 1 else COLUNAS_VENCIDAS
        vencidas = tema.Tabela(quadro, colunas, altura=10)
        vencidas.grid(row=3, column=0, sticky="nsew")
        vencidas.preencher(self._seguro(
            lambda: self.repo.pendencias_vencidas(self.sessao.nivel, self.sessao.uf)))
        return quadro

    def _seguro(self, consulta):
        """Indicador indisponível não derruba a consulta ao acervo."""
        try:
            return consulta()
        except Exception:
            return []

    # ------------------------------------------------------------ sessão N3
    def _tique(self):
        if not self.winfo_exists():
            return
        if self.sessao.expira_em:
            restante = (self.sessao.expira_em - datetime.now()).total_seconds()
            if restante <= 0:
                messagebox.showinfo("Sessão encerrada",
                                    "Tempo máximo da sessão de nível 3 atingido.", parent=self)
                self.destroy()
                return
            self.relogio.configure(text=f"Sessão expira em {int(restante // 60):02d}:"
                                        f"{int(restante % 60):02d}")
        self.after(1000, self._tique)
