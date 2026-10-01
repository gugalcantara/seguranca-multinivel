"""Tela de autenticação — conduz os fatores exigidos pelo nível solicitado.

N1: só câmera. N2: matrícula + senha -> câmera. N3: matrícula + senha forte ->
câmera -> desafio de vivacidade -> repete tudo para a segunda pessoa, dentro da janela.
"""
import time
import tkinter as tk
from tkinter import ttk

from interface.comum import CORES_NIVEL, NOMES_NIVEL, Visor, desenhar_faces
from visao.aquisicao import WebcamIndisponivel

VERDE, VERMELHO, AMARELO = (0, 190, 0), (0, 0, 220), (0, 200, 230)


class JanelaAutenticacao(tk.Toplevel):
    def __init__(self, mestre, ctx, nivel, ao_conceder):
        super().__init__(mestre)
        self.ctx, self.nivel, self.ao_conceder = ctx, nivel, ao_conceder
        self.motor = ctx.motor
        self.janela_dois = ctx.cfg.getfloat("autenticacao", "janela_regra_dois")
        self.primeira_pessoa = None      # (evidencias, instante) no N3
        self.tentativa = None
        self._agendado = None
        self.title(f"Autenticação — Nível {nivel}")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.fechar)

        tk.Label(self, text=f"Nível {nivel} — {NOMES_NIVEL[nivel]}", bg=CORES_NIVEL[nivel], fg="white",
                 font=("Segoe UI", 13, "bold"), padx=12, pady=8).pack(fill="x")

        self.formulario = ttk.Frame(self, padding=16)
        self.titulo_form = ttk.Label(self.formulario, font=("Segoe UI", 10, "bold"))
        self.titulo_form.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Label(self.formulario, text="Matrícula").grid(row=1, column=0, sticky="w")
        self.matricula = ttk.Entry(self.formulario, width=28)
        self.matricula.grid(row=1, column=1, pady=3)
        ttk.Label(self.formulario, text="Senha").grid(row=2, column=0, sticky="w")
        self.senha = ttk.Entry(self.formulario, width=28, show="•")
        self.senha.grid(row=2, column=1, pady=3)
        self.senha.bind("<Return>", lambda _: self._continuar())
        ttk.Button(self.formulario, text="Continuar", command=self._continuar).grid(row=3, column=1, sticky="e", pady=6)

        self.visor = Visor(self, 640, 480)
        self.status = tk.Label(self, font=("Segoe UI", 11), pady=8, wraplength=620)
        self.status.pack(side="bottom", fill="x")
        self.botoes = ttk.Frame(self, padding=8)
        self.botoes.pack(side="bottom")
        self.tentar = ttk.Button(self.botoes, text="Tentar novamente", command=self._reiniciar)
        ttk.Button(self.botoes, text="Cancelar", command=self.fechar).pack(side="right", padx=4)

        self._reiniciar()

    # ------------------------------------------------------------ etapas
    def _reiniciar(self):
        self.tentar.pack_forget()
        self.primeira_pessoa = None
        if self.nivel == 1:
            self._iniciar_face(None, None)
        else:
            self._mostrar_formulario("Informe matrícula e senha")

    def _mostrar_formulario(self, titulo):
        self.visor.pack_forget()
        self.titulo_form.configure(text=titulo)
        self.matricula.delete(0, "end")
        self.senha.delete(0, "end")
        self.formulario.pack(fill="x")
        self.matricula.focus_set()
        self._mensagem("", None)

    def _continuar(self):
        usuario, ev, negada = self.motor.validar_credenciais(self.nivel, self.matricula.get().strip(), self.senha.get())
        self.senha.delete(0, "end")
        if negada:
            self._negar(negada.mensagem, ev)
            return
        self._iniciar_face(usuario, ev)

    def _iniciar_face(self, usuario, ev):
        self.formulario.pack_forget()
        self.visor.pack(padx=8, pady=8)
        try:
            self.ctx.camera()
        except WebcamIndisponivel as erro:
            self._mensagem(f"Webcam indisponível — acesso negado. ({erro})", VERMELHO)
            return
        self.tentativa = self.motor.iniciar_face(self.nivel, ev, usuario)
        self._laco()

    def _laco(self):
        frame = self.ctx.camera().ler(timeout=0.5)
        if frame is None:
            self._mensagem("A câmera parou de responder — acesso negado.", VERMELHO)
            return
        st = self.tentativa.alimentar(frame)
        a = st.analise
        cor = AMARELO if not a.qualidade.aprovado else (VERDE if st.fase == "VIVACIDADE" else (200, 200, 200))
        self.visor.mostrar(desenhar_faces(frame, a.retangulos, cor))
        self._mensagem(st.mensagem, None)
        if self.primeira_pessoa and time.monotonic() - self.primeira_pessoa[1] > self.janela_dois:
            return self._expirar_regra_dois()
        if st.fase != "CONCLUIDA":
            self._agendado = self.after(10, self._laco)
            return
        self._concluida(st.decisao)

    def _concluida(self, decisao):
        ev = self.tentativa.ev
        if self.primeira_pessoa:                       # fim da segunda pessoa (N3)
            ev_a, instante_a = self.primeira_pessoa
            self.primeira_pessoa = None
            final, sessao = self.motor.concluir_regra_dois(ev_a, instante_a, ev, time.monotonic())
            return self._conceder(sessao) if sessao else self._negar(final.mensagem, ev)
        if not decisao.concedido:
            return self._negar(decisao.mensagem, ev)
        if self.nivel < 3:
            return self._conceder(self.motor.abrir_sessao(ev))
        self.primeira_pessoa = (ev, time.monotonic())
        self._mostrar_formulario(f"Regra dos dois: segunda pessoa autorizada, em até "
                                 f"{self.janela_dois:.0f} s")
        self.after(1000, self._vigiar_janela)

    def _vigiar_janela(self):
        if not self.primeira_pessoa or not self.winfo_exists():
            return
        if time.monotonic() - self.primeira_pessoa[1] > self.janela_dois:
            return self._expirar_regra_dois()
        self.after(1000, self._vigiar_janela)

    def _expirar_regra_dois(self):
        ev_a, instante_a = self.primeira_pessoa
        final, _ = self.motor.concluir_regra_dois(ev_a, instante_a)   # sem segunda pessoa
        self.primeira_pessoa = None
        self._negar(final.mensagem, ev_a)

    # ------------------------------------------------------------ desfechos
    def _negar(self, mensagem, _ev):
        self._cancelar_laco()
        if self.primeira_pessoa:                       # 2ª pessoa barrada antes da face
            ev_a, instante_a = self.primeira_pessoa
            self.primeira_pessoa = None
            self.motor.concluir_regra_dois(ev_a, instante_a)
        self._mensagem(f"ACESSO NEGADO — {mensagem}", VERMELHO)
        self.tentar.pack(side="left", padx=4)

    def _conceder(self, sessao):
        self._cancelar_laco()
        self.destroy()
        self.ao_conceder(sessao)

    def _mensagem(self, texto, cor_bgr):
        cor = "#%02x%02x%02x" % cor_bgr[::-1] if cor_bgr else "#222"
        self.status.configure(text=texto, fg=cor)

    def _cancelar_laco(self):
        if self._agendado:
            self.after_cancel(self._agendado)
            self._agendado = None

    def fechar(self):
        self._cancelar_laco()
        self.destroy()
