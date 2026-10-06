"""Tela de autenticação — conduz os fatores exigidos pelo nível solicitado.

N1: só câmera. N2: matrícula + senha -> câmera. N3: matrícula + senha forte ->
câmera -> desafio de vivacidade -> repete tudo para a segunda pessoa, dentro da janela.

A última etapa do N3 depende de `exigir_segunda_pessoa` no config.ini. A tela não
decide isso: pergunta ao motor (`aguarda_segunda_pessoa`), que é o mesmo dono da
resposta que a política consulta.

A faixa de etapas no topo mostra quais fatores o nível exige e em qual deles a
tentativa está. A lista sai de FATORES_POR_NIVEL, a MESMA que a política usa
para decidir — assim a tela nunca anuncia um fator que a decisão não exige, nem
esconde um que ela exige.

CUIDADO AO MEXER NAS SAÍDAS: quando a primeira pessoa do N3 já se autenticou e a
segunda ainda não chegou, há uma tentativa ABERTA no motor. Qualquer caminho que
feche esta janela precisa encerrá-la — ver `_encerrar_regra_dois_pendente`, ligado
ao botão, ao X, ao Esc e ao <Destroy>. Na auditoria, um acesso iniciado e nunca
concluído é indistinguível de um acesso concedido.
"""
import logging
import time
import tkinter as tk
from tkinter import ttk

import configuracao
from autenticacao.politica import Fator, fatores_do_nivel
from interface import tema
from interface.comum import CORES_NIVEL, NOMES_NIVEL, Visor, desenhar_faces
from visao.aquisicao import WebcamIndisponivel

VERDE, VERMELHO, AMARELO, NEUTRO = (0, 190, 0), (0, 0, 220), (0, 200, 230), (200, 200, 200)

# SENHA_FORTE não vira etapa própria: é a mesma digitação da senha, com régua
# mais exigente. Mostrá-la em separado sugeriria um passo a mais que não existe.
ROTULOS_FATOR = {
    Fator.SENHA: "Matrícula e senha",
    Fator.FACE: "Reconhecimento facial",
    Fator.VIVACIDADE: "Desafio na câmera",
    Fator.REGRA_DOIS: "Segunda pessoa",
}

PENDENTE, ATUAL, CUMPRIDA = "pendente", "atual", "cumprida"


class FaixaEtapas(ttk.Frame):
    """Os fatores do nível, em ordem, com o estado de cada um."""

    def __init__(self, mestre, nivel, exigir_segunda_pessoa=True):
        super().__init__(mestre, style="Superficie.TFrame", padding=(16, 10))
        # a faixa sai da MESMA função que a política consulta, agora incluindo a
        # regra dos dois ligada ou não: a tela nunca anuncia uma etapa que a
        # decisão não vai cobrar
        self.fatores = [f for f in fatores_do_nivel(nivel, exigir_segunda_pessoa) or ()
                        if f in ROTULOS_FATOR]
        self._rotulos = {}
        for coluna, fator in enumerate(self.fatores):
            if coluna:
                ttk.Label(self, text="›", style="Detalhe.TLabel").grid(row=0, column=coluna * 2 - 1,
                                                                      padx=8)
            rotulo = ttk.Label(self, style="Superficie.TLabel")
            rotulo.grid(row=0, column=coluna * 2, sticky="w")
            self._rotulos[fator] = rotulo
        self.marcar(self.fatores[0] if self.fatores else None)

    def marcar(self, atual):
        """Tudo antes de `atual` fica cumprido; o resto, pendente."""
        indice_atual = self.fatores.index(atual) if atual in self.fatores else len(self.fatores)
        for i, fator in enumerate(self.fatores):
            estado = CUMPRIDA if i < indice_atual else (ATUAL if i == indice_atual else PENDENTE)
            simbolo = {CUMPRIDA: "✓", ATUAL: "●", PENDENTE: "○"}[estado]
            cor = {CUMPRIDA: tema.OK, ATUAL: tema.ACENTO, PENDENTE: tema.TEXTO_SUAVE}[estado]
            fonte = tema.F_FORTE if estado == ATUAL else tema.F_SUBTITULO
            self._rotulos[fator].configure(text=f"{simbolo}  {ROTULOS_FATOR[fator]}",
                                           foreground=cor, font=fonte)

    def concluir(self):
        self.marcar(None)


class Medidor(ttk.Frame):
    """Progresso da etapa facial: frames confirmados, distância e tempo restante.

    A distância aparece ao lado do limiar do nível de propósito. É a grandeza que
    decide o acesso — vê-la cair enquanto o rosto se estabiliza explica o
    reconhecimento melhor do que qualquer texto, e deixa evidente que o LBPH
    devolve DISTÂNCIA: quanto menor, mais parecido.
    """

    def __init__(self, mestre, nivel):
        super().__init__(mestre, style="Superficie.TFrame", padding=(16, 10))
        self.limiar = configuracao.limiar(nivel)
        self.total = configuracao.carregar().getint("autenticacao", "frames_confirmacao")

        linha = ttk.Frame(self, style="SuperficieLisa.TFrame")
        linha.pack(fill="x")
        self.rotulo_progresso = ttk.Label(linha, style="Superficie.TLabel", font=tema.F_SUBTITULO)
        self.rotulo_progresso.pack(side="left")
        self.rotulo_tempo = ttk.Label(linha, style="Detalhe.TLabel")
        self.rotulo_tempo.pack(side="right")

        self.barra = ttk.Progressbar(self, maximum=self.total, length=100,
                                     style="Medidor.Horizontal.TProgressbar")
        self.barra.pack(fill="x", pady=(6, 7))

        # distância e limiar numa frase só: separá-los em cantos opostos fazia os
        # dois textos colidirem quando a janela encolhe
        self.rotulo_distancia = ttk.Label(self, style="Superficie.TLabel", font=tema.F_FORTE)
        self.rotulo_distancia.pack(anchor="w")
        self.limpar()

    def atualizar(self, confirmados, distancia, segundos):
        self.barra.configure(value=confirmados)
        self.rotulo_progresso.configure(text=f"{confirmados} de {self.total} quadros coerentes")
        self.rotulo_tempo.configure(text=f"{segundos:.0f} s restantes")
        if distancia is None:
            return self.rotulo_distancia.configure(
                text=f"distância —   ·   aceita até {self.limiar:.0f}", foreground=tema.TEXTO_SUAVE)
        dentro = distancia <= self.limiar
        self.rotulo_distancia.configure(
            text=f"distância {distancia:.1f}".replace(".", ",")
                 + f"   ·   aceita até {self.limiar:.0f}   "
                 f"{'✓' if dentro else '✗'}", foreground=tema.OK if dentro else tema.ERRO)

    def limpar(self):
        self.barra.configure(value=0)
        self.rotulo_progresso.configure(text="aguardando o rosto")
        self.rotulo_tempo.configure(text="")
        self.rotulo_distancia.configure(text=f"distância —   ·   aceita até {self.limiar:.0f}",
                                        foreground=tema.TEXTO_SUAVE)


class JanelaAutenticacao(tk.Toplevel):
    def __init__(self, mestre, ctx, nivel, ao_conceder):
        super().__init__(mestre)
        # estado antes dos widgets: fechar uma janela meio construída não pode
        # levantar um segundo erro por cima do primeiro
        self._agendado = None
        self.tentativa = None
        self.primeira_pessoa = None
        self.ctx, self.nivel, self.ao_conceder = ctx, nivel, ao_conceder
        self.motor = ctx.motor
        self.janela_dois = ctx.cfg.getfloat("autenticacao", "janela_regra_dois")
        # quem responde é o motor, não um "nivel == 3" repetido aqui
        self.aguarda_segunda = self.motor.aguarda_segunda_pessoa(nivel)
        self.title(f"Autenticação — Nível {nivel}")
        self.configure(bg=tema.FUNDO)
        self.withdraw()               # só aparece depois de dimensionada, sem piscar
        self.protocol("WM_DELETE_WINDOW", self.fechar)
        self.bind("<Escape>", lambda _: self.fechar())
        # cobre o caminho que não passa por fechar(): a janela ser destruída
        # junto com a de trás
        self.bind("<Destroy>", lambda e: e.widget is self
                  and self._encerrar_regra_dois_pendente())

        tk.Label(self, text=f"Nível {nivel} — {NOMES_NIVEL[nivel]}", bg=CORES_NIVEL[nivel],
                 fg="white", font=tema.F_TITULO, padx=16, pady=10).pack(fill="x")
        self.etapas = FaixaEtapas(self, nivel, self.aguarda_segunda)
        self.etapas.pack(fill="x")

        # A faixa é o bloco mais largo da tela e o único que não encolhe: em
        # monitor com escala de DPI os rótulos crescem junto com a fonte, e um
        # número fixo de pixels cortaria «Segunda pessoa» no nível 3. Então é a
        # faixa quem dita a largura da janela — medida, não chutada.
        self.update_idletasks()
        largura = max(780, self.etapas.winfo_reqwidth() + 40)
        self._largura_minima = min(largura, 700)
        self.minsize(self._largura_minima, 470)
        self.largura, self.altura_com_video = tema.ajustar_a_tela(self, largura, 820)
        altura = self.altura_com_video

        self.formulario = ttk.Frame(self, padding=16)
        # a coluna dos campos é quem estica: com `width` em caracteres, a
        # matrícula (fonte de código) e a senha (fonte normal) terminavam com
        # larguras diferentes e a tela ficava visivelmente torta
        self.formulario.columnconfigure(1, weight=1, minsize=260)
        self.titulo_form = ttk.Label(self.formulario, style="Forte.TLabel")
        self.titulo_form.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        ttk.Label(self.formulario, text="Matrícula").grid(row=1, column=0, sticky="w", padx=(0, 10))
        self.matricula = ttk.Entry(self.formulario, font=tema.F_CODIGO)
        self.matricula.grid(row=1, column=1, pady=3, sticky="ew")
        ttk.Label(self.formulario, text="Senha").grid(row=2, column=0, sticky="w", padx=(0, 10))
        self.senha = ttk.Entry(self.formulario, show="•")
        self.senha.grid(row=2, column=1, pady=3, sticky="ew")
        self.senha.bind("<Return>", lambda _: self._continuar())
        self.matricula.bind("<Return>", lambda _: self.senha.focus_set())
        ttk.Button(self.formulario, text="Continuar", style="Acento.TButton",
                   command=self._continuar).grid(row=3, column=1, sticky="e", pady=(10, 0))
        ttk.Label(self.formulario, style="Suave.TLabel",
                  text="A matrícula é o código do crachá, como R0902G8.").grid(
            row=4, column=1, sticky="w", pady=(8, 0))

        # Botões e mensagem são ancorados na BASE antes do vídeo existir. O vídeo
        # é o único elemento elástico da tela; empacotado primeiro, ele empurraria
        # «Tentar novamente» e «Cancelar» para fora do monitor — e a pessoa
        # ficaria sem como repetir a tentativa nem como sair.
        self.botoes = ttk.Frame(self, padding=(12, 10))
        self.botoes.pack(side="bottom", fill="x")
        ttk.Button(self.botoes, text="Cancelar", command=self.fechar).pack(side="right")
        self.tentar = ttk.Button(self.botoes, text="Tentar novamente", style="Acento.TButton",
                                 command=self._reiniciar)
        self.status = tk.Label(self, font=tema.F_SUBTITULO, bg=tema.FUNDO, anchor="w",
                               justify="left")
        self.status.pack(side="bottom", fill="x", padx=12, pady=(0, 4))
        tema.quebrar_com_a_janela(self.status, self, margem=36)

        # O medidor entra na conta da altura e só então sai de cena: ele volta na
        # etapa facial, e o vídeo precisa ter reservado o espaço dele desde já.
        # A folga extra cobre a mensagem de status, que cresce para duas ou três
        # linhas quando o acesso é negado.
        self.medidor = Medidor(self, nivel)
        self.medidor.pack(side="bottom", fill="x", padx=8, pady=8)
        self.visor = Visor(self, largura - 40, tema.altura_para_video(self, altura - 48))
        self.medidor.pack_forget()

        self._reiniciar()
        self.deiconify()

    # ------------------------------------------------------------ etapas
    def _reiniciar(self):
        self.tentar.pack_forget()
        self.primeira_pessoa = None
        self.etapas.marcar(self.etapas.fatores[0] if self.etapas.fatores else None)
        if self.nivel == 1:
            self._iniciar_face(None, None)
        else:
            self._mostrar_formulario("Informe matrícula e senha")

    def _mostrar_formulario(self, titulo):
        self.visor.pack_forget()
        self.medidor.pack_forget()
        self.titulo_form.configure(text=titulo)
        self.matricula.delete(0, "end")
        self.senha.delete(0, "end")
        self.formulario.pack(fill="x")
        self.matricula.focus_set()
        self._mensagem("", None)
        self._altura_conforme_o_conteudo(com_video=False)

    def _altura_conforme_o_conteudo(self, com_video):
        """A janela encolhe quando mostra só o formulário.

        A altura é dimensionada para caber o vídeo, que é o elemento alto. Nas
        etapas de digitação isso deixava dois terços da janela vazios, com o
        «Cancelar» sozinho lá embaixo, longe do «Continuar» — parecendo que
        faltava algo na tela. Encolher mantém os dois botões no campo de visão.
        """
        if com_video:
            self.minsize(self._largura_minima, 470)
            return self.geometry(f"{self.largura}x{self.altura_com_video}")
        self.update_idletasks()
        # o piso também acompanha: um mínimo pensado para caber vídeo deixaria a
        # janela do formulário parada numa altura que ela não usa
        necessaria = sum(filho.winfo_reqheight() for filho in self.pack_slaves()) + 24
        alta = min(necessaria, self.altura_com_video)
        self.minsize(self._largura_minima, min(alta, 470))
        self.geometry(f"{self.largura}x{alta}")

    def _continuar(self):
        usuario, ev, negada = self.motor.validar_credenciais(self.nivel, self.matricula.get().strip(),
                                                             self.senha.get())
        self.senha.delete(0, "end")
        if negada:
            self._negar(negada.mensagem, ev)
            return
        self._iniciar_face(usuario, ev)

    def _iniciar_face(self, usuario, ev):
        self.formulario.pack_forget()
        self.medidor.limpar()
        self.medidor.pack(side="bottom", fill="x", padx=8, pady=8)
        self.visor.pack(padx=8, pady=(8, 0), expand=True)
        self._altura_conforme_o_conteudo(com_video=True)
        self.etapas.marcar(Fator.FACE)
        try:
            self.ctx.camera()
        except WebcamIndisponivel as erro:
            # o botão de repetir aparece também aqui: antes, a única saída era
            # fechar e reabrir a janela depois de liberar a câmera
            self._mensagem("Não foi possível abrir a webcam. Feche outros programas que estejam "
                           "usando a câmera e confira em Configurações › Privacidade › Câmera "
                           f"se o Windows permite o acesso. ({erro})", VERMELHO)
            self.tentar.pack(side="right", padx=(0, 8))
            self.tentar.focus_set()
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
        if st.fase == "VIVACIDADE":
            self.etapas.marcar(Fator.VIVACIDADE)
        cor = AMARELO if not a.qualidade.aprovado else (VERDE if st.fase == "VIVACIDADE" else NEUTRO)
        self.visor.mostrar(desenhar_faces(frame, a.retangulos, cor))
        if st.fase == "FACE":
            self.medidor.atualizar(self.tentativa.confirmador.confirmados, a.distancia,
                                   self.tentativa.segundos_restantes)
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
        if not self.aguarda_segunda:
            return self._conceder(self.motor.abrir_sessao(ev))
        self.primeira_pessoa = (ev, time.monotonic())
        self.etapas.marcar(Fator.REGRA_DOIS)
        self._mostrar_formulario(f"Regra dos dois: segunda pessoa autorizada, em até "
                                 f"{self.janela_dois:.0f} s")
        self.after(1000, self._vigiar_janela)

    def _vigiar_janela(self):
        if not self.primeira_pessoa or not self.winfo_exists():
            return
        restante = self.janela_dois - (time.monotonic() - self.primeira_pessoa[1])
        if restante <= 0:
            return self._expirar_regra_dois()
        self.titulo_form.configure(text=f"Regra dos dois: segunda pessoa autorizada "
                                        f"— {int(restante)} s restantes")
        self.after(1000, self._vigiar_janela)

    def _expirar_regra_dois(self):
        ev_a, instante_a = self.primeira_pessoa
        final, _ = self.motor.concluir_regra_dois(ev_a, instante_a)   # sem segunda pessoa
        self.primeira_pessoa = None
        self._negar(final.mensagem, ev_a)

    # ------------------------------------------------------------ desfechos
    def _negar(self, mensagem, _ev):
        self._cancelar_laco()
        self._encerrar_regra_dois_pendente()           # 2ª pessoa barrada antes da face
        self._mensagem(f"ACESSO NEGADO — {mensagem}", VERMELHO)
        self.tentar.pack(side="right", padx=(0, 8))
        self.tentar.focus_set()        # Enter repete a tentativa, sem caçar o botão

    def _conceder(self, sessao):
        self._cancelar_laco()
        self.etapas.concluir()
        self.destroy()
        self.ao_conceder(sessao)

    def _mensagem(self, texto, cor_bgr):
        cor = "#%02x%02x%02x" % cor_bgr[::-1] if cor_bgr else tema.TEXTO
        self.status.configure(text=texto, fg=cor)

    def _cancelar_laco(self):
        agendado = getattr(self, "_agendado", None)
        if agendado:
            self.after_cancel(agendado)
            self._agendado = None

    def _encerrar_regra_dois_pendente(self):
        """Fecha a tentativa da primeira pessoa que ficou sem par.

        Sem isto, desistir no meio da regra dos dois — fechando a janela, pelo X
        ou pelo Esc — deixava na trilha um acesso de nível 3 iniciado e nunca
        concluído. Uma trilha que não registra o desfecho não serve de trilha: na
        auditoria, o acesso em aberto é indistinguível de um acesso concedido.
        """
        if not getattr(self, "primeira_pessoa", None):
            return
        ev_a, instante_a = self.primeira_pessoa
        self.primeira_pessoa = None
        try:
            self.motor.concluir_regra_dois(ev_a, instante_a)      # sem segunda pessoa
        except Exception:
            # a janela está fechando; o erro não tem para onde subir, mas não
            # pode sumir — quem audita precisa saber que este desfecho faltou
            logging.exception("Falha ao encerrar a regra dos dois da tentativa %r", ev_a)

    def fechar(self):
        self._cancelar_laco()
        self._encerrar_regra_dois_pendente()
        self.destroy()
