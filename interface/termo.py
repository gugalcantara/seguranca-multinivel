"""Tela do termo de consentimento, exibida ANTES de qualquer captura facial.

A ordem importa juridicamente: o consentimento tem de ser prévio e informado
(LGPD art. 9º). Pedir depois de já ter capturado o rosto inverteria a lógica — o
tratamento já teria começado sem base legal.

A tela obriga a rolar o texto até o fim antes de habilitar o aceite. Não é
burocracia: um "li e concordo" clicado sem rolagem possível é consentimento
duvidoso, e a ETP 12.3 exige termo informado.
"""
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from interface import tema
from lgpd import termo


class DialogoTermo(tk.Toplevel):
    """Devolve (aceitou, momento) por callback. Modal: nada acontece até decidir."""

    def __init__(self, mestre, nome_titular, ao_decidir):
        super().__init__(mestre)
        self.nome_titular = nome_titular
        self.ao_decidir = ao_decidir
        self.decidido = False

        self.title("Termo de consentimento — uso de imagem facial")
        self.configure(bg=tema.FUNDO)
        self.minsize(640, 460)
        tema.ajustar_a_tela(self, 900, 760)
        self.transient(mestre)
        self.protocol("WM_DELETE_WINDOW", self._recusar)
        self.bind("<Escape>", lambda _: self._recusar())   # como o X: fechar é recusar

        tema.cabecalho(self, termo.TITULO,
                       f"Versão {termo.VERSAO} · leia antes de prosseguir · "
                       f"titular: {nome_titular}")

        quadro = ttk.Frame(self, padding=12)
        quadro.pack(fill="both", expand=True)

        # Os controles de decisão entram ANTES do corpo: com expand=True no texto,
        # eles seriam empurrados para fora da janela e ficariam inalcançáveis.
        self.nota = ttk.Label(quadro, style="Suave.TLabel",
                              text="Role o texto até o fim para habilitar a marcação.")
        self.nota.pack(side="bottom", anchor="w", pady=(4, 0))
        self.marcacao = tk.BooleanVar(value=False)
        self.caixa = ttk.Checkbutton(
            quadro, variable=self.marcacao, state="disabled", command=self._avaliar,
            text="Li o termo integralmente, compreendi e consinto com o tratamento da minha "
                 "imagem facial para a finalidade descrita.", width=90)
        self.caixa.pack(side="bottom", anchor="w", pady=(10, 0))
        acoes = ttk.Frame(quadro)
        acoes.pack(side="bottom", fill="x", pady=(12, 0))

        aviso = ttk.Label(quadro, style="Erro.TLabel", justify="left",
                          text="Imagem de rosto é dado pessoal SENSÍVEL (LGPD, art. 5º, II). "
                               "O tratamento depende do seu consentimento específico e destacado "
                               "(art. 11, I) — e a participação é voluntária.")
        aviso.pack(anchor="w", pady=(0, 10))
        tema.quebrar_com_a_janela(aviso, self, margem=60)

        corpo = ttk.Frame(quadro, style="Superficie.TFrame")
        corpo.pack(fill="both", expand=True)
        self.texto = tk.Text(corpo, wrap="word", font=tema.F_BASE, relief="flat",
                             background=tema.SUPERFICIE, foreground=tema.TEXTO,
                             padx=18, pady=14, spacing1=2, spacing3=6, cursor="arrow")
        barra = ttk.Scrollbar(corpo, orient="vertical", command=self.texto.yview)
        self.texto.configure(yscrollcommand=self._rolou)
        self.texto.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        self._barra = barra
        self._preencher()

        ttk.Button(acoes, text="Salvar uma via…", command=self._salvar).pack(side="left")
        ttk.Button(acoes, text="Imprimir", command=self._imprimir).pack(side="left", padx=6)
        self.botao_recusar = ttk.Button(acoes, text="Não concordo", command=self._recusar)
        self.botao_recusar.pack(side="right")
        self.botao_aceitar = ttk.Button(acoes, text="Concordo e autorizo", style="Acento.TButton",
                                        state="disabled", command=self._aceitar)
        self.botao_aceitar.pack(side="right", padx=6)

        self.grab_set()
        self.after(120, self._verificar_rolagem)   # texto curto em tela grande já nasce no fim

    # ------------------------------------------------------------ conteúdo
    def _preencher(self):
        self.texto.configure(state="normal")
        self.texto.tag_configure("titulo", font=tema.F_TITULO, foreground=tema.ACENTO,
                                 spacing3=10)
        self.texto.tag_configure("secao", font=tema.F_FORTE, foreground=tema.TEXTO,
                                 spacing1=12, spacing3=4)
        self.texto.tag_configure("item", lmargin1=16, lmargin2=30, spacing3=5)
        self.texto.tag_configure("aceite", font=tema.F_FORTE, spacing1=16, lmargin1=8,
                                 lmargin2=8)

        # o título já está no cabeçalho da janela; repeti-lo aqui só gastaria altura
        for titulo, paragrafos in termo.SECOES:
            self.texto.insert("end", f"{titulo}\n", "secao")
            for paragrafo in paragrafos:
                self.texto.insert("end", f"•  {paragrafo}\n", "item")
        self.texto.insert("end", f"\n{termo.ACEITE}\n", "aceite")
        self.texto.configure(state="disabled")

    # ------------------------------------------------------------ rolagem
    def _rolou(self, inicio, fim):
        self._barra.set(inicio, fim)
        if float(fim) >= 0.999:
            self._liberar_marcacao()

    def _verificar_rolagem(self):
        if self.texto.yview()[1] >= 0.999:
            self._liberar_marcacao()

    def _liberar_marcacao(self):
        if str(self.caixa.cget("state")) != "disabled":
            return
        self.caixa.configure(state="normal")
        self.nota.configure(text="Marque a caixa acima para habilitar a autorização.")

    def _avaliar(self):
        self.botao_aceitar.configure(state="normal" if self.marcacao.get() else "disabled")

    # ------------------------------------------------------------ via do titular
    def _documento(self):
        return termo.documento(self.nome_titular, momento=datetime.now())

    def _salvar(self):
        destino = filedialog.asksaveasfilename(
            parent=self, title="Salvar a via do titular", defaultextension=".txt",
            initialfile=f"termo-consentimento-{self.nome_titular.split()[0].lower()}.txt",
            filetypes=[("Texto", "*.txt")])
        if not destino:
            return
        Path(destino).write_text(self._documento(), encoding="utf-8")
        messagebox.showinfo("Termo salvo",
                            f"Via gravada em:\n{destino}\n\nImprima e assine para arquivar "
                            "junto aos termos do projeto.", parent=self)

    def _imprimir(self):
        """Grava e entrega ao programa padrão do sistema — o Tk não imprime sozinho."""
        import os
        import tempfile
        arquivo = Path(tempfile.gettempdir()) / f"termo_{self.nome_titular.split()[0].lower()}.txt"
        arquivo.write_text(self._documento(), encoding="utf-8")
        try:
            os.startfile(str(arquivo), "print")          # Windows
            messagebox.showinfo("Impressão", "Enviado para a impressora padrão.", parent=self)
        except Exception:
            # sem impressora configurada, abrir o arquivo já permite imprimir pelo editor
            try:
                os.startfile(str(arquivo))
                messagebox.showinfo("Impressão", "Não foi possível imprimir direto.\n"
                                                 "O termo foi aberto para você imprimir pelo "
                                                 "editor.", parent=self)
            except Exception as erro:
                messagebox.showwarning("Impressão", f"Não foi possível imprimir ou abrir.\n"
                                                    f"Use 'Salvar uma via…'.\n\n{erro}", parent=self)

    # ------------------------------------------------------------ desfecho
    def _aceitar(self):
        # a guarda espelha a de _recusar: sem ela, um duplo clique em «Concordo»
        # dispara o callback duas vezes e abre DUAS janelas de captura, cada uma
        # tentando cadastrar a mesma pessoa
        if self.decidido:
            return
        self.decidido = True
        self.grab_release()
        self.destroy()
        self.ao_decidir(True, datetime.now())

    def _recusar(self):
        if not self.decidido:
            self.decidido = True
            self.grab_release()
            self.destroy()
            self.ao_decidir(False, None)
