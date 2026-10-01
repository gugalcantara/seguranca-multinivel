"""Consulta ao acervo após a autenticação — o conteúdo já chega tratado para o nível.

Aba Acervo: itens que o nível pode ver, abertos com tarja + carimbo + marca d'água.
Aba Indicadores: agregados da camada causal (N1) e pendências vencidas (RF-15).
"""
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from acervo.entrega import POLITICA_EXPORTACAO
from acervo.repositorio_acervo import RepositorioAcervo
from acervo.tarja import AcessoNegado
from interface.comum import CORES_NIVEL, NOMES_NIVEL, Visor, tabela_texto

ROTULOS_EXPORTACAO = {"LIVRE": "livre", "COM_MARCA_DAGUA": "com marca d'água invisível",
                      "BLOQUEADA": "bloqueada — só visualização"}


class JanelaConsulta(tk.Toplevel):
    def __init__(self, mestre, ctx, sessao):
        super().__init__(mestre)
        self.ctx, self.sessao = ctx, sessao
        self.repo = RepositorioAcervo(ctx.banco)
        self.atual = None
        self.title(f"Acervo — {sessao.nome} (nível {sessao.nivel})")
        self.geometry("1280x780")

        cab = tk.Frame(self, bg=CORES_NIVEL[sessao.nivel])
        cab.pack(fill="x")
        dois = f" + {sessao.usuario2_id} (regra dos dois)" if sessao.usuario2_id else ""
        tk.Label(cab, text=f"{sessao.nome}{dois} — Nível {sessao.nivel}: {NOMES_NIVEL[sessao.nivel]}",
                 bg=CORES_NIVEL[sessao.nivel], fg="white", font=("Segoe UI", 12, "bold"),
                 padx=12, pady=6).pack(side="left")
        self.relogio = tk.Label(cab, bg=CORES_NIVEL[sessao.nivel], fg="white", padx=12)
        self.relogio.pack(side="right")
        tk.Label(self, text="Protótipo acadêmico — todo item marcado como DADO FICTÍCIO é sintético.",
                 fg="#a8322d").pack(anchor="w", padx=12)

        abas = ttk.Notebook(self)
        abas.pack(fill="both", expand=True, padx=8, pady=8)
        abas.add(self._aba_acervo(abas), text="Acervo")
        abas.add(self._aba_indicadores(abas), text="Indicadores")
        self._tique()

    # ------------------------------------------------------------ acervo
    def _aba_acervo(self, abas):
        quadro = ttk.Frame(abas)
        esquerda = ttk.Frame(quadro, padding=6)
        esquerda.pack(side="left", fill="y")
        ttk.Label(esquerda, text="Itens disponíveis para o seu nível").pack(anchor="w")
        self.lista = tk.Listbox(esquerda, width=40, height=20)
        self.lista.pack(fill="y", expand=True)
        self.lista.bind("<<ListboxSelect>>", self._abrir)
        self.itens = self.ctx.acervo.listar(self.sessao)
        for item in self.itens:
            self.lista.insert("end", f"{item['codigo']}  {item['titulo']}")

        politica = POLITICA_EXPORTACAO[self.sessao.nivel]
        self.exportar = ttk.Button(esquerda, text="Exportar item aberto", command=self._exportar,
                                   state="disabled" if politica == "BLOQUEADA" else "normal")
        self.exportar.pack(fill="x", pady=(8, 0))
        ttk.Label(esquerda, text=f"Exportação: {ROTULOS_EXPORTACAO[politica]}",
                  foreground="#555").pack(anchor="w")
        self.ficha = tk.Text(esquerda, width=46, height=14, font=("Consolas", 9), wrap="word")
        self.ficha.pack(fill="x", pady=(8, 0))

        self.visor = Visor(quadro, 880, 640)
        self.visor.pack(side="left", padx=8)
        return quadro

    def _abrir(self, _evento):
        selecao = self.lista.curselection()
        if not selecao:
            return
        item_id = self.itens[selecao[0]]["id"]
        try:
            item, imagem = self.ctx.acervo.abrir(self.sessao, item_id)
        except AcessoNegado as erro:
            messagebox.showwarning("Acesso negado", str(erro), parent=self)
            if "expirada" in str(erro):
                self.destroy()
            return
        self.atual = (item_id, imagem)
        self.visor.mostrar(imagem)
        self._mostrar_ficha(item)

    def _mostrar_ficha(self, item):
        """A2-01: ficha causal e cadeia de responsabilidade — só a partir do N2 (RF-21)."""
        self.ficha.delete("1.0", "end")
        if not item.get("pendencia_id"):
            return
        ficha = self.repo.ficha_pendencia(item["pendencia_id"], self.sessao.nivel)
        if ficha is None:
            self.ficha.insert("end", "Ficha causal disponível a partir do nível 2.")
            return
        linhas = [f"{ficha['codigo']} — {ficha['substancia']}",
                  f"Atividade: {ficha['atividade']} {ficha['atividade_descricao']}",
                  f"Motivo: {ficha['motivo']} {ficha['motivo_descricao']}",
                  f"Base legal: {ficha['base_legal']}",
                  f"Ação: {ficha['acao_institucional']}", "", "Cadeia de responsabilidade:"]
        linhas += [f"  {r['vinculo']}: {r['nome']} ({r['situacao_cadastral']})"
                   for r in self.repo.responsaveis(item["pendencia_id"], self.sessao.nivel)]
        self.ficha.insert("end", "\n".join(linhas))

    def _exportar(self):
        if not self.atual:
            messagebox.showinfo("Exportar", "Abra um item primeiro.", parent=self)
            return
        try:
            destino = self.ctx.acervo.exportar(self.sessao, *self.atual)
        except AcessoNegado as erro:
            messagebox.showwarning("Exportação bloqueada", str(erro), parent=self)
            return
        messagebox.showinfo("Exportado", f"Arquivo gravado em:\n{destino}", parent=self)

    # ------------------------------------------------------------ indicadores
    def _aba_indicadores(self, abas):
        quadro = ttk.Frame(abas, padding=6)
        texto = tk.Text(quadro, font=("Consolas", 10))
        texto.pack(fill="both", expand=True)
        partes = ["DISTRIBUIÇÃO POR ATIVIDADE GERADORA (A1-02)", tabela_texto(self.repo.agregado_por_atividade()),
                  "", "DISTRIBUIÇÃO POR MOTIVO DA PERMANÊNCIA", tabela_texto(self.repo.agregado_por_motivo()),
                  "", "PENDÊNCIAS VENCIDAS (RF-15)",
                  tabela_texto(self.repo.pendencias_vencidas(self.sessao.nivel, self.sessao.uf))]
        texto.insert("end", "\n".join(partes))
        texto.configure(state="disabled")
        return quadro

    # ------------------------------------------------------------ sessão N3
    def _tique(self):
        if not self.winfo_exists():
            return
        if self.sessao.expira_em:
            restante = (self.sessao.expira_em - datetime.now()).total_seconds()
            if restante <= 0:
                messagebox.showinfo("Sessão encerrada", "Tempo máximo da sessão de nível 3 atingido.", parent=self)
                self.destroy()
                return
            self.relogio.configure(text=f"Sessão expira em {int(restante // 60):02d}:{int(restante % 60):02d}")
        self.after(1000, self._tique)
