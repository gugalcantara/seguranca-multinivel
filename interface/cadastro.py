"""Módulo administrativo (protegido por senha de administrador — ETP 4.5).

Aba Usuários: cadastro com captura facial em duas sessões (RF-01).
Aba Sistema: relatórios S-01 a S-07.
Aba Ferramentas: extração de marca d'água e inspeção de acondicionamento.
"""
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import cv2

import configuracao
from acervo import marca_dagua
from acervo.inspecao import inspecionar
from autenticacao import senha
from dados.auditoria import novo_registro
from dados.relatorios_sistema import RelatoriosSistema
from interface import tema
from interface.comum import Visor, desenhar_faces, exigir_administrador, tabela_texto
from interface.tema import Coluna
from visao.aquisicao import WebcamIndisponivel
from visao.coleta import EXTENSOES, ColetorAmostras, coletar_de_arquivos
from visao.pipeline import PipelineFacial

UFS = ["", "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA", "PB", "PE",
       "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO"]


def abrir_administracao(mestre, ctx):
    if exigir_administrador(mestre):
        JanelaAdministracao(mestre, ctx)


class JanelaAdministracao(tk.Toplevel):
    def __init__(self, mestre, ctx):
        super().__init__(mestre)
        self.ctx = ctx
        self.relatorios = RelatoriosSistema(ctx.banco)
        self.title("Administração do sistema")
        self.geometry("1100x700")
        abas = ttk.Notebook(self)
        abas.pack(fill="both", expand=True, padx=8, pady=8)
        abas.add(self._aba_usuarios(abas), text="Usuários")
        abas.add(self._aba_sistema(abas), text="Relatórios do sistema")
        abas.add(self._aba_ferramentas(abas), text="Ferramentas")

    # ------------------------------------------------------------ usuários
    def _aba_usuarios(self, abas):
        quadro = ttk.Frame(abas, padding=8)
        barra = ttk.Frame(quadro)
        barra.pack(fill="x", pady=(0, 8))
        ttk.Button(barra, text="Novo usuário", style="Acento.TButton",
                   command=self._novo_usuario).pack(side="left")
        ttk.Button(barra, text="Atualizar", command=self._atualizar_galeria).pack(side="left", padx=6)
        self.galeria = tk.Text(quadro, font=tema.F_MONO)
        self.galeria.pack(fill="both", expand=True)
        self._atualizar_galeria()
        return quadro

    def _atualizar_galeria(self):
        self.galeria.delete("1.0", "end")
        self.galeria.insert("end", "S-06 GALERIA BIOMÉTRICA\n\n"
                            + tabela_texto(self.relatorios.s06_galeria_biometrica()))

    def _novo_usuario(self):
        DialogoNovoUsuario(self, self.ctx, ao_concluir=lambda _: self._atualizar_galeria())

    # ------------------------------------------------------------ sistema
    def _aba_sistema(self, abas):
        quadro = ttk.Frame(abas, padding=8)
        botoes = ttk.Frame(quadro)
        botoes.pack(fill="x")
        saida = tk.Text(quadro, font=("Consolas", 9), wrap="none")
        saida.pack(fill="both", expand=True, pady=(8, 0))

        def mostrar(titulo, conteudo):
            saida.delete("1.0", "end")
            saida.insert("end", f"{titulo}\n\n{conteudo}")

        def integridade():
            r = self.relatorios.s04_integridade()
            mostrar("S-04 INTEGRIDADE DA CADEIA DE HASH",
                    f"ÍNTEGRA — {r.total} registros verificados" if r.integra else
                    f"RUPTURA no registro id={r.id_ruptura}\nTipo: {r.tipo}\n{r.detalhe}")

        for texto, acao in (
            ("S-01 Log", lambda: mostrar("S-01 LOG DE ACESSOS", tabela_texto(self.relatorios.s01_log_acessos()))),
            ("S-02 Negadas", lambda: mostrar("S-02 TENTATIVAS NEGADAS", tabela_texto(self.relatorios.s02_tentativas_negadas()))),
            ("S-03 Bloqueios", lambda: mostrar("S-03 BLOQUEIOS ATIVOS", tabela_texto(self.relatorios.s03_bloqueios_ativos()))),
            ("S-04 Integridade", integridade),
            ("S-05 Estatísticas", lambda: mostrar("S-05 ESTATÍSTICAS DE RECONHECIMENTO",
                                                  tabela_texto(self.relatorios.s05_estatisticas_reconhecimento()))),
            ("S-07 Exportações", lambda: mostrar("S-07 AUDITORIA DE EXPORTAÇÃO",
                                                 tabela_texto(self.relatorios.s07_auditoria_exportacao()))),
        ):
            ttk.Button(botoes, text=texto, command=acao).pack(side="left", padx=2)
        return quadro

    # ------------------------------------------------------------ ferramentas
    def _aba_ferramentas(self, abas):
        quadro = ttk.Frame(abas, padding=8)
        botoes = ttk.Frame(quadro)
        botoes.pack(fill="x")
        self.resultado = ttk.Label(quadro, font=("Segoe UI", 10))
        self.resultado.pack(anchor="w", pady=6)
        self.visor_ferr = Visor(quadro, 1000, 560)
        self.visor_ferr.pack()
        ttk.Button(botoes, text="Extrair marca d'água de arquivo", command=self._extrair_marca).pack(side="left", padx=2)
        ttk.Button(botoes, text="Inspecionar acondicionamento (M-03)", command=self._inspecionar).pack(side="left", padx=2)
        return quadro

    def _extrair_marca(self):
        caminho = filedialog.askopenfilename(parent=self, filetypes=[("Imagens", "*.png *.jpg *.jpeg")])
        if not caminho:
            return
        imagem = cv2.imread(caminho)
        r = marca_dagua.extrair(imagem) if imagem is not None else None
        self.resultado.configure(text="Nenhuma marca recuperável." if r is None else
                                 f"Marca {r[0].upper()}: usuário {r[1]}, em {r[2]:%d/%m/%Y %H:%M:%S}")
        if imagem is not None:
            self.visor_ferr.mostrar(imagem)

    def _inspecionar(self):
        ref = filedialog.askopenfilename(parent=self, title="Imagem de REFERÊNCIA")
        atual = ref and filedialog.askopenfilename(parent=self, title="Imagem ATUAL")
        if not atual:
            return
        r = inspecionar(cv2.imread(ref), cv2.imread(atual))
        self.resultado.configure(text=f"{'ALTERAÇÃO DETECTADA' if r.alterado else 'Sem alteração'} — "
                                      f"SSIM {r.similaridade:.4f}, {len(r.regioes)} região(ões), "
                                      f"alinhamento {'ok' if r.alinhado else 'FALHOU'}")
        self.visor_ferr.mostrar(r.mapa_diferenca)


class DialogoNovoUsuario(tk.Toplevel):
    """Cadastro de usuário: formulário, captura facial e treino incremental (RF-01).

    É o caminho ÚNICO de cadastro — usado pelo painel de gerenciamento e pela
    administração. Estava embutido na aba de administração; foi extraído para
    que a regra de senha, UF e matrícula não exista em duas versões que podem
    divergir.
    """

    def __init__(self, mestre, ctx, ao_concluir=None):
        super().__init__(mestre)
        self.ctx = ctx
        self.ao_concluir = ao_concluir
        self.title("Novo usuário")
        self.resizable(False, False)
        self.transient(mestre)
        self.configure(bg=tema.FUNDO)
        tema.cabecalho(self, "Novo usuário", "Cadastro com captura facial — RF-01")

        form = ttk.Frame(self, padding=16)
        form.pack(fill="both", expand=True)
        self.campos = {}
        for linha, (rotulo, chave) in enumerate((("Matrícula", "matricula"), ("Nome", "nome"),
                                                 ("Senha", "senha"), ("Confirmar senha", "confirmacao"))):
            ttk.Label(form, text=rotulo).grid(row=linha, column=0, sticky="w", pady=3, padx=(0, 10))
            entrada = ttk.Entry(form, width=28,
                                show="•" if "senha" in chave or chave == "confirmacao" else "")
            entrada.grid(row=linha, column=1, pady=3, sticky="w")
            self.campos[chave] = entrada

        # A matrícula é gerada pelo sistema, não escolhida: evita colisão, evita
        # que a pessoa invente um padrão e deixa o código legível para digitar.
        self.campos["matricula"].configure(state="readonly", font=tema.F_CODIGO)
        ttk.Button(form, text="Gerar outra", width=11,
                   command=self._gerar_matricula).grid(row=0, column=2, padx=(8, 0))
        self._gerar_matricula()
        ttk.Label(form, text="Nível").grid(row=4, column=0, sticky="w", pady=3, padx=(0, 10))
        self.nivel = ttk.Combobox(form, values=[1, 2, 3], width=6, state="readonly")
        self.nivel.current(0)
        self.nivel.grid(row=4, column=1, sticky="w", pady=3)
        self.nivel.bind("<<ComboboxSelected>>", self._ajustar_uf)
        ttk.Label(form, text="UF").grid(row=5, column=0, sticky="w", pady=3, padx=(0, 10))
        self.uf = ttk.Combobox(form, values=UFS, width=6, state="readonly")
        self.uf.grid(row=5, column=1, sticky="w", pady=3)
        self.nota_uf = ttk.Label(form, style="Suave.TLabel")
        self.nota_uf.grid(row=5, column=2, sticky="w", padx=(8, 0))
        self._ajustar_uf()
        ttk.Label(form, text="Só cadastre quem assinou o termo de autorização\n"
                             "de uso de imagem (LGPD art. 11).",
                  style="Erro.TLabel").grid(row=6, column=0, columnspan=3, sticky="w", pady=(12, 0))

        acoes = ttk.Frame(form)
        acoes.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(14, 0))
        ttk.Button(acoes, text="Capturar pela webcam", style="Acento.TButton",
                   command=self._cadastrar_webcam).pack(side="left")
        ttk.Button(acoes, text="Usar imagens…",
                   command=self._cadastrar_imagens).pack(side="left", padx=6)
        ttk.Button(acoes, text="Cancelar", command=self.destroy).pack(side="right")
        self.campos["nome"].focus_set()

    # O formulário é validado ANTES de abrir a captura, qualquer que seja a
    # origem das faces: não adianta capturar 40 frames para só então descobrir
    # que a matrícula já existe.
    def _cadastrar_webcam(self):
        validado = self._validar()
        if validado is None:
            return
        dados, nivel = validado
        JanelaCaptura(self, self.ctx,
                      lambda coletores: self._concluir(dados, nivel, coletores, "webcam"))

    def _cadastrar_imagens(self):
        validado = self._validar()
        if validado is None:
            return
        dados, nivel = validado
        JanelaImportarImagens(self, self.ctx,
                              lambda coletores: self._concluir(dados, nivel, coletores, "imagem"))

    def _ajustar_uf(self, _=None):
        """A UF só filtra no nível 2.

        No N1 o conteúdo é agregado nacional e no N3 a visão é nacional inteira —
        nos dois a UF é ignorada na consulta. Deixar o campo editável ali sugere
        um efeito que não existe, então ele é desabilitado e explicado.
        """
        nivel_2 = self.nivel.get() == "2"
        self.uf.configure(state="readonly" if nivel_2 else "disabled")
        if not nivel_2:
            self.uf.set("")
        self.nota_uf.configure(text="região que o diretor enxerga" if nivel_2
                               else "só se aplica ao nível 2")

    def _gerar_matricula(self):
        campo = self.campos["matricula"]
        try:
            codigo = self.ctx.usuarios.nova_matricula()
        except Exception as erro:
            messagebox.showerror("Cadastro", f"Não foi possível gerar a matrícula.\n{erro}",
                                 parent=self)
            return
        campo.configure(state="normal")
        campo.delete(0, "end")
        campo.insert(0, codigo)
        campo.configure(state="readonly")

    def _validar(self):
        """Devolve (dados, nivel) se o formulário está consistente, ou None."""
        dados = {k: v.get().strip() for k, v in self.campos.items()}
        nivel = int(self.nivel.get())
        if not dados["matricula"] or not dados["nome"]:
            messagebox.showwarning("Cadastro", "Preencha matrícula e nome.", parent=self)
            return None
        if dados["senha"] != dados["confirmacao"]:
            messagebox.showwarning("Cadastro", "As senhas não conferem.", parent=self)
            return None
        minimo = self.ctx.cfg.getint("autenticacao", "senha_forte_min_caracteres")
        pendencias = senha.avaliar_senha_forte(dados["senha"], minimo if nivel == 3 else 8)
        if pendencias:
            messagebox.showwarning("Cadastro", "Senha fraca — falta: " + ", ".join(pendencias),
                                   parent=self)
            return None
        if nivel == 2 and not self.uf.get():
            messagebox.showwarning("Cadastro", "Diretor de nível 2 precisa de UF.", parent=self)
            return None
        if self.ctx.usuarios.por_matricula(dados["matricula"]):
            messagebox.showwarning("Cadastro", "Matrícula já cadastrada.", parent=self)
            return None
        return dados, nivel

    def _concluir(self, dados, nivel, coletores, origem="webcam"):
        chave = configuracao.env("CHAVE_CIFRAGEM", obrigatorio=False)
        if not chave:
            return messagebox.showerror("Cadastro", "CHAVE_CIFRAGEM ausente no .env — o modelo não "
                                                    "pode ser salvo sem cifragem.", parent=self)
        usuario_id = self.ctx.usuarios.criar(dados["matricula"], dados["nome"], nivel,
                                             senha.gerar_hash(dados["senha"]), self.uf.get() or None)
        faces = [f for c in coletores for f in c.faces]
        self.ctx.reconhecedor.atualizar(faces, [usuario_id] * len(faces))     # D-04
        self.ctx.reconhecedor.salvar(configuracao.caminho("modelo"), chave)
        for c in coletores:
            self.ctx.usuarios.registrar_amostras(usuario_id, c.sessao, c.qualidades, origem)
            c.descartar_imagens()                                             # nenhuma imagem persiste
        self.ctx.trilha.registrar(novo_registro("CADASTRO", nivel, "CONCEDIDO", "CADASTRO_USUARIO",
                                                usuario_id=usuario_id))
        messagebox.showinfo(
            "Cadastro concluído",
            f"{dados['nome']} cadastrado com {len(faces)} amostras ({origem}).\n\n"
            f"MATRÍCULA:  {dados['matricula']}\n\n"
            f"Anote: é com ela que a pessoa entra nos níveis 2 e 3.", parent=self)
        if self.ao_concluir:
            self.ao_concluir(usuario_id)
        self.destroy()


MOTIVOS_IMAGEM = {
    "OK": "",
    "ILEGIVEL": "arquivo não é uma imagem legível",
    "SEM_FACE": "nenhum rosto encontrado",
    "MULTIPLAS_FACES": "mais de um rosto na foto",
    "DUPLICATA": "quase idêntica à anterior",
    "ESCURO": "muito escura",
    "CLARO": "estourada de luz",
    "SEM_CONTRASTE": "pouco contraste",
    "DESFOCADO": "fora de foco",
    "RUIDOSO": "ruído excessivo",
}

COLUNAS_IMAGENS = [
    Coluna("sessao", "Lote", 5, "center"),
    Coluna("arquivo", "Arquivo", 34, "w", elastica=True),
    Coluna("situacao", "Situação", 10, "center"),
    Coluna("explicacao", "Motivo", 28),
    Coluna("escore", "Qualidade", 10, "e"),
]


class JanelaImportarImagens(tk.Toplevel):
    """Cadastro facial a partir de ARQUIVOS de imagem, alternativa à webcam (RF-01).

    As fotos passam exatamente pelo mesmo caminho da captura ao vivo — Haar,
    portão de qualidade, recorte 200x200 — então uma foto ruim é recusada pelo
    mesmo motivo que um frame ruim. Nada aqui afrouxa o portão; o que muda é só
    a origem do pixel, registrada como 'imagem' na tabela amostra.

    Cada seleção de arquivos vira um LOTE, gravado como uma sessão distinta.
    Isso preserva a divisão treino/teste por sessão da ETP 4.7: use fotos de
    ocasiões diferentes em lotes diferentes.
    """

    def __init__(self, mestre, ctx, ao_concluir):
        super().__init__(mestre)
        self.ctx = ctx
        self.ao_concluir = ao_concluir
        self.pipeline = PipelineFacial(cfg=ctx.cfg)
        self.coletores = []
        self.laudos = []
        self.minimo = ctx.cfg.getint("cadastro", "imagens_minimas")
        self.largura_maxima = ctx.cfg.getint("cadastro", "largura_maxima_imagem")

        self.title("Cadastrar a partir de imagens")
        self.configure(bg=tema.FUNDO)
        self.geometry("980x620")
        self.transient(mestre)
        tema.cabecalho(self, "Cadastrar a partir de imagens",
                       f"Mínimo de {self.minimo} fotos aceitas · cada seleção vira um lote (sessão)")

        quadro = ttk.Frame(self, padding=12)
        quadro.pack(fill="both", expand=True)
        barra = ttk.Frame(quadro)
        barra.pack(fill="x", pady=(0, 10))
        ttk.Button(barra, text="Selecionar imagens…", style="Acento.TButton",
                   command=self._selecionar).pack(side="left")
        ttk.Button(barra, text="Cancelar", command=self._cancelar).pack(side="right")
        self.botao_concluir = ttk.Button(barra, text="Concluir cadastro", state="disabled",
                                         command=self._concluir)
        self.botao_concluir.pack(side="right", padx=6)

        ttk.Label(quadro, text="Rostos frontais, bem iluminados, um por foto. As imagens não são "
                               "gravadas: treinam o modelo e são descartadas.",
                  style="Suave.TLabel", wraplength=940,
                  justify="left").pack(side="bottom", anchor="w", pady=(4, 0))
        self.resumo = ttk.Label(quadro, text="Nenhuma imagem carregada ainda.", style="Forte.TLabel")
        self.resumo.pack(side="bottom", anchor="w", pady=(10, 0))
        self.tabela = tema.Tabela(quadro, COLUNAS_IMAGENS, altura=11,
                                  tag_por_linha=lambda l: None if l["aceito"] else "recusada")
        self.tabela.configurar_tag("recusada", foreground=tema.ERRO)
        self.tabela.pack(fill="both", expand=True)

    def _selecionar(self):
        caminhos = filedialog.askopenfilenames(
            parent=self, title=f"Imagens do lote {len(self.coletores) + 1}",
            filetypes=[("Imagens", " ".join("*" + e for e in EXTENSOES)), ("Todos", "*.*")])
        if not caminhos:
            return
        coletor = ColetorAmostras(len(self.coletores) + 1, self.ctx.cfg,
                                  alvo=len(caminhos), minimo=1)
        self.coletores.append(coletor)
        self.configure(cursor="watch")
        self.update_idletasks()
        try:
            laudos = coletar_de_arquivos(caminhos, self.pipeline, coletor, self.largura_maxima)
        finally:
            self.configure(cursor="")
        for caminho, aceito, motivo, escore in laudos:
            self.laudos.append({
                "sessao": coletor.sessao, "arquivo": Path(caminho).name, "aceito": aceito,
                "situacao": "aceita" if aceito else "recusada",
                "explicacao": MOTIVOS_IMAGEM.get(motivo, motivo),
                "escore": round(escore, 3) if escore else None,
            })
        self.tabela.preencher(self.laudos)
        self._atualizar_resumo()

    def _atualizar_resumo(self):
        aceitas = self.total_aceitas()
        lotes = len([c for c in self.coletores if c.faces])
        falta = max(0, self.minimo - aceitas)
        texto = (f"{aceitas} foto(s) aceita(s) em {lotes} lote(s), "
                 f"de {len(self.laudos)} analisada(s).")
        self.resumo.configure(text=texto + (f"  Faltam {falta} para concluir." if falta else
                                            "  Pronto para cadastrar."))
        self.botao_concluir.configure(state="disabled" if falta else "normal")

    def total_aceitas(self):
        return sum(len(c.faces) for c in self.coletores)

    def _concluir(self):
        if self.total_aceitas() < self.minimo:
            return
        coletores = [c for c in self.coletores if c.faces]
        self.destroy()
        self.ao_concluir(coletores)

    def _cancelar(self):
        for c in self.coletores:
            c.descartar_imagens()
        self.destroy()


class JanelaCaptura(tk.Toplevel):
    """Captura as sessões faciais do cadastro (ETP 4.2: duas sessões, iluminações distintas)."""

    def __init__(self, mestre, ctx, ao_concluir):
        super().__init__(mestre)
        self.ctx, self.ao_concluir = ctx, ao_concluir
        self.pipeline = PipelineFacial(cfg=ctx.cfg)
        self.total_sessoes = ctx.cfg.getint("cadastro", "sessoes")
        self.coletores = []
        self.title("Captura facial")
        self.protocol("WM_DELETE_WINDOW", self._cancelar)
        self.instrucao = ttk.Label(self, font=("Segoe UI", 11), padding=8)
        self.instrucao.pack()
        self.visor = Visor(self, 640, 480)
        self.visor.pack(padx=8)
        self.botao = ttk.Button(self, text="Iniciar sessão 1", command=self._iniciar_sessao)
        self.botao.pack(pady=8)
        self._agendado = None
        self.instrucao.configure(text="Sessão 1: olhe para a câmera e mova a cabeça devagar.")

    def _iniciar_sessao(self):
        try:
            self.ctx.camera()
        except WebcamIndisponivel as erro:
            messagebox.showerror("Captura", str(erro), parent=self)
            return
        self.botao.configure(state="disabled")
        self.coletores.append(ColetorAmostras(len(self.coletores) + 1, self.ctx.cfg))
        self.pipeline.segmentador.reiniciar()
        self._laco()

    def _laco(self):
        coletor = self.coletores[-1]
        frame = self.ctx.camera().ler(timeout=0.5)
        if frame is None:
            messagebox.showerror("Captura", "A câmera parou de responder.", parent=self)
            return self._cancelar()
        analise = self.pipeline.analisar(frame, reconhecer=False)
        aceito = coletor.alimentar(analise)
        self.visor.mostrar(desenhar_faces(frame, analise.retangulos, (0, 190, 0) if aceito else (0, 0, 220)))
        self.instrucao.configure(text=f"Sessão {coletor.sessao}: {len(coletor.faces)}/{coletor.alvo} — "
                                      f"{analise.qualidade.mensagem}")
        if not coletor.completa:
            self._agendado = self.after(15, self._laco)
            return
        if len(self.coletores) < self.total_sessoes:
            self.instrucao.configure(text=f"Sessão {coletor.sessao} concluída. Mude a iluminação ou a "
                                          f"distância e inicie a próxima sessão.")
            self.botao.configure(text=f"Iniciar sessão {len(self.coletores) + 1}", state="normal")
            return
        self.destroy()
        self.ao_concluir(self.coletores)

    def _cancelar(self):
        if self._agendado:
            self.after_cancel(self._agendado)
        for c in self.coletores:
            c.descartar_imagens()
        self.destroy()
