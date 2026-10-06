"""Cadastro de usuário: formulário, captura facial e importação de imagens (RF-01).

As telas administrativas (relatórios do sistema e ferramentas) vivem no painel,
em interface/painel.py — aqui fica só o caminho de cadastro, usado por ele.

REGRA QUE ATRAVESSA O MÓDULO: as faces coletadas vivem só em memória, e toda
saída destas telas tem de terminar sem nenhuma delas. Concluir, cancelar, Esc, o
X da janela, fechar a janela de trás, falhar no meio do cadastro — todas. Por
isso o descarte está pendurado no evento <Destroy>, que é o único ponto por onde
todas passam, e não nos botões: era assim antes, e três caminhos de saída
escapavam. A única exceção é a entrega bem-sucedida, que precisa das faces vivas
para treinar e as apaga logo em seguida, num `finally` (ver `_descartar_tudo` e
`DialogoNovoUsuario._concluir`).

Quem alterar o fluxo aqui deve manter os testes de `testes/test_fluxos_de_uso.py`
passando: cada caminho de saída tem um teste que verifica a memória depois.
"""
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import cv2

import configuracao
from autenticacao import senha
from dados.auditoria import novo_registro
from interface import tema
from interface.comum import Visor, avaliar_enquadramento, desenhar_guia
from interface.tema import Coluna
from interface.termo import DialogoTermo
from lgpd import termo as lgpd_termo
from visao.aquisicao import WebcamIndisponivel
from visao.coleta import EXTENSOES, ColetorAmostras, coletar_de_arquivos
from visao.pipeline import PipelineFacial

UFS = ["", "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA", "PB", "PE",
       "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO"]


OPCOES_NIVEL = [f"{n} — {tema.NOMES_NIVEL[n]}" for n in (1, 2, 3)]

# Critérios exibidos no checklist da senha. O "cumprido" de cada um NÃO é
# recalculado aqui: sai das pendências que senha.avaliar_senha_forte devolve,
# a mesma função que valida o formulário. Duas regras paralelas acabariam
# divergindo, e a tela marcaria ✓ num critério que a validação recusa.
CRITERIOS_SENHA = (
    ("tamanho", None),                         # texto depende do nível (8 ou 12+)
    ("minuscula", "minúscula"),
    ("maiuscula", "maiúscula"),
    ("digito", "número"),
    ("simbolo", "símbolo"),
    ("confere", "senhas iguais"),
)
_PENDENCIA_DO_CRITERIO = {
    "tamanho": lambda p: p.startswith("ao menos"),
    "minuscula": lambda p: p == "uma letra minúscula",
    "maiuscula": lambda p: p == "uma letra maiúscula",
    "digito": lambda p: p == "um dígito",
    "simbolo": lambda p: p == "um símbolo",
}


class DialogoNovoUsuario(tk.Toplevel):
    """Cadastro de usuário: formulário, captura facial e treino incremental (RF-01).

    Caminho único de cadastro, aberto pelo painel de gerenciamento. A regra de
    senha, UF e matrícula mora só aqui — antes estava embutida na aba de
    administração, e havia duas versões capazes de divergir.
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
        # a coluna dos campos estica: com `width` em caracteres, a matrícula
        # (fonte de código) saía bem mais larga que os outros campos
        form.columnconfigure(1, weight=1, minsize=280)
        self.campos = {}
        for linha, (rotulo, chave) in enumerate((("Matrícula", "matricula"), ("Nome", "nome"),
                                                 ("Senha", "senha"), ("Confirmar senha", "confirmacao"))):
            ttk.Label(form, text=rotulo).grid(row=linha, column=0, sticky="w", pady=3, padx=(0, 10))
            entrada = ttk.Entry(form, show="•" if chave in ("senha", "confirmacao") else "")
            entrada.grid(row=linha, column=1, pady=3, sticky="ew")
            self.campos[chave] = entrada

        # A matrícula é gerada pelo sistema, não escolhida: evita colisão, evita
        # que a pessoa invente um padrão e deixa o código legível para digitar.
        self.campos["matricula"].configure(state="readonly", font=tema.F_CODIGO)
        ttk.Button(form, text="Gerar outra", width=11,
                   command=self._gerar_matricula).grid(row=0, column=2, padx=(8, 0))
        self._gerar_matricula()

        self.mostrar_senha = tk.BooleanVar(value=False)
        ttk.Checkbutton(form, text="Mostrar", variable=self.mostrar_senha,
                        command=self._alternar_senha).grid(row=2, column=2, sticky="w", padx=(8, 0))

        # Checklist da senha, atualizado a cada tecla. Antes, a pessoa só
        # descobria o que faltava DEPOIS de clicar, num aviso que sumia — e a
        # exigência muda com o nível (12 caracteres no N3, 8 nos outros).
        self.checklist = ttk.Frame(form)
        self.checklist.grid(row=4, column=1, columnspan=2, sticky="w", pady=(2, 6))
        self._itens_senha = {}
        for coluna, (chave, texto) in enumerate(CRITERIOS_SENHA):
            rotulo = ttk.Label(self.checklist, style="Suave.TLabel")
            rotulo.grid(row=coluna // 3, column=coluna % 3, sticky="w", padx=(0, 14))
            self._itens_senha[chave] = (rotulo, texto)
        for chave in ("senha", "confirmacao"):
            self.campos[chave].bind("<KeyRelease>", lambda _: self._avaliar_senha(), add="+")

        ttk.Label(form, text="Nível").grid(row=5, column=0, sticky="w", pady=3, padx=(0, 10))
        # o nível aparece com o nome: "1" sozinho obrigava a lembrar o que cada
        # número libera na hora de decidir o acesso de alguém
        self.nivel = ttk.Combobox(form, values=OPCOES_NIVEL, state="readonly")
        self.nivel.current(0)
        self.nivel.grid(row=5, column=1, sticky="ew", pady=3)
        self.nivel.bind("<<ComboboxSelected>>", self._ajustar_uf)
        ttk.Label(form, text="UF").grid(row=6, column=0, sticky="w", pady=3, padx=(0, 10))
        self.uf = ttk.Combobox(form, values=UFS, width=6, state="readonly")
        self.uf.grid(row=6, column=1, sticky="w", pady=3)
        self.nota_uf = ttk.Label(form, style="Suave.TLabel")
        self.nota_uf.grid(row=6, column=1, sticky="w", padx=(70, 0))
        self._ajustar_uf()
        ttk.Label(form, text="Só cadastre quem assinou o termo de autorização\n"
                             "de uso de imagem (LGPD art. 11).",
                  style="Erro.TLabel").grid(row=7, column=0, columnspan=3, sticky="w", pady=(12, 0))

        acoes = ttk.Frame(form)
        acoes.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(14, 0))
        ttk.Button(acoes, text="Capturar pela webcam", style="Acento.TButton",
                   command=self._cadastrar_webcam).pack(side="left")
        ttk.Button(acoes, text="Usar imagens…",
                   command=self._cadastrar_imagens).pack(side="left", padx=6)
        ttk.Button(acoes, text="Cancelar", command=self.destroy).pack(side="right")
        self.bind("<Escape>", lambda _: self.destroy())
        self._avaliar_senha()
        self.campos["nome"].focus_set()

    # O formulário é validado ANTES de abrir a captura, qualquer que seja a
    # origem das faces: não adianta capturar 40 frames para só então descobrir
    # que a matrícula já existe.
    def _cadastrar_webcam(self):
        self._com_consentimento(lambda dados, nivel: JanelaCaptura(
            self, self.ctx, lambda c: self._concluir(dados, nivel, c, "webcam")))

    def _cadastrar_imagens(self):
        self._com_consentimento(lambda dados, nivel: JanelaImportarImagens(
            self, self.ctx, lambda c: self._concluir(dados, nivel, c, "imagem")))

    def _com_consentimento(self, prosseguir):
        """Valida o formulário, colhe o consentimento e só então captura.

        A ordem é exigência legal, não preferência: o consentimento tem de ser
        PRÉVIO e informado (LGPD art. 9º). Pedir depois de capturar o rosto
        significaria ter tratado dado sensível sem base legal.
        """
        validado = self._validar()
        if validado is None:
            return
        dados, nivel = validado

        def decidiu(aceitou, momento):
            if not aceitou:
                self.ctx.trilha.registrar(novo_registro(
                    "CADASTRO", nivel, "NEGADO", "CONSENTIMENTO_RECUSADO"))
                messagebox.showinfo(
                    "Cadastro cancelado",
                    "Sem o consentimento não é possível tratar a imagem facial.\n\n"
                    "Nenhum dado foi coletado, e a recusa não traz prejuízo algum.",
                    parent=self)
                return
            self._consentimento = {"momento": momento, "nome": dados["nome"]}
            prosseguir(dados, nivel)

        DialogoTermo(self, dados["nome"], decidiu)

    def _nivel_escolhido(self):
        """1, 2 ou 3 — a opção exibida é "2 — Consulta restrita"."""
        return int(self.nivel.get().split()[0])

    def _minimo_senha(self):
        if self._nivel_escolhido() == 3:
            return self.ctx.cfg.getint("autenticacao", "senha_forte_min_caracteres")
        return 8

    def _alternar_senha(self):
        caractere = "" if self.mostrar_senha.get() else "•"
        for chave in ("senha", "confirmacao"):
            self.campos[chave].configure(show=caractere)

    def _avaliar_senha(self):
        """Marca no checklist o que a senha digitada já cumpre."""
        digitada = self.campos["senha"].get()
        minimo = self._minimo_senha()
        pendencias = senha.avaliar_senha_forte(digitada, minimo)
        for chave, (rotulo, texto) in self._itens_senha.items():
            if chave == "confere":
                cumprido = bool(digitada) and digitada == self.campos["confirmacao"].get()
            else:
                cumprido = bool(digitada) and not any(
                    _PENDENCIA_DO_CRITERIO[chave](p) for p in pendencias)
            texto = texto or f"{minimo}+ caracteres"
            rotulo.configure(text=f"{'✓' if cumprido else '○'} {texto}",
                             foreground=tema.OK if cumprido else tema.TEXTO_SUAVE)

    def _ajustar_uf(self, _=None):
        """A UF só filtra no nível 2.

        No N1 o conteúdo é agregado nacional e no N3 a visão é nacional inteira —
        nos dois a UF é ignorada na consulta. Deixar o campo editável ali sugere
        um efeito que não existe, então ele é desabilitado e explicado.
        """
        nivel_2 = self._nivel_escolhido() == 2
        self.uf.configure(state="readonly" if nivel_2 else "disabled")
        if not nivel_2:
            self.uf.set("")
        self.nota_uf.configure(text="região que o diretor enxerga" if nivel_2
                               else "só se aplica ao nível 2")
        if hasattr(self, "_itens_senha"):
            self._avaliar_senha()                  # o mínimo de caracteres muda com o nível

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
        nivel = self._nivel_escolhido()
        if not dados["matricula"] or not dados["nome"]:
            messagebox.showwarning("Cadastro", "Preencha matrícula e nome.", parent=self)
            return None
        if dados["senha"] != dados["confirmacao"]:
            messagebox.showwarning("Cadastro", "As senhas não conferem.", parent=self)
            return None
        pendencias = senha.avaliar_senha_forte(dados["senha"], self._minimo_senha())
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
        """Grava o usuário, treina o modelo e apaga as imagens.

        O `finally` não é zelo excessivo: as faces chegam aqui vivas em memória e
        qualquer falha no meio — disco cheio, chave inválida, banco caindo —
        deixaria dado biométrico retido numa tela que a pessoa já fechou.

        Se a falha vier DEPOIS de criar o usuário, ele é desativado. Um usuário
        ativo cujo rosto não entrou no modelo salvo é o pior desfecho possível:
        o banco diz que ele existe, o modelo em disco diz que não, e isso só
        apareceria na próxima vez que alguém tentasse entrar. Desativar deixa o
        estado coerente e visível no painel (ETP 6.6: na dúvida, não conceder).
        """
        chave = configuracao.env("CHAVE_CIFRAGEM", obrigatorio=False)
        if not chave:
            for c in coletores:
                c.descartar_imagens()
            return messagebox.showerror("Cadastro", "CHAVE_CIFRAGEM ausente no .env — o modelo não "
                                                    "pode ser salvo sem cifragem.", parent=self)
        usuario_id = None
        try:
            usuario_id = self.ctx.usuarios.criar(
                dados["matricula"], dados["nome"], nivel,
                senha.gerar_hash(dados["senha"]), self.uf.get() or None)
            # evidência do consentimento, com o hash do texto efetivamente apresentado:
            # provar o consentimento é ônus do controlador (LGPD art. 8º, §2º)
            self.ctx.consentimentos.registrar(
                dados["nome"], lgpd_termo.VERSAO, lgpd_termo.hash_termo(),
                momento=self._consentimento["momento"], usuario_id=usuario_id)
            faces = [f for c in coletores for f in c.faces]
            total_amostras = len(faces)
            self.ctx.reconhecedor.atualizar(faces, [usuario_id] * total_amostras)  # D-04
            self.ctx.reconhecedor.salvar(configuracao.caminho("modelo"), chave)
            faces = None          # solta as referências; o finally limpa os coletores
            for c in coletores:
                self.ctx.usuarios.registrar_amostras(usuario_id, c.sessao, c.qualidades, origem)
        except Exception as erro:
            self._desfazer_cadastro(usuario_id, nivel, erro)
            return
        finally:
            for c in coletores:
                c.descartar_imagens()                      # nenhuma imagem persiste
        self.ctx.trilha.registrar(novo_registro("CADASTRO", nivel, "CONCEDIDO", "CADASTRO_USUARIO",
                                                usuario_id=usuario_id))
        messagebox.showinfo(
            "Cadastro concluído",
            f"{dados['nome']} cadastrado com {total_amostras} amostras ({origem}).\n\n"
            f"MATRÍCULA:  {dados['matricula']}\n\n"
            f"Anote: é com ela que a pessoa entra nos níveis 2 e 3.", parent=self)
        if self.ao_concluir:
            self.ao_concluir(usuario_id)
        self.destroy()

    def _desfazer_cadastro(self, usuario_id, nivel, erro):
        """Deixa o sistema coerente quando o cadastro falha no meio."""
        desativado = False
        if usuario_id is not None:
            try:
                self.ctx.usuarios.definir_ativo(usuario_id, False)
                desativado = True
            except Exception:
                pass                     # o aviso abaixo já instrui o administrador
        try:
            self.ctx.trilha.registrar(novo_registro("CADASTRO", nivel, "NEGADO", "CADASTRO_FALHOU",
                                                    usuario_id=usuario_id))
        except Exception:
            pass                         # se o próprio banco caiu, o aviso é o que resta
        messagebox.showerror(
            "Cadastro não concluído",
            f"O cadastro falhou e nenhuma imagem foi mantida.\n\n{erro}\n\n"
            + ("O usuário criado foi DESATIVADO para não ficar sem rosto no modelo. "
               "Refaça o cadastro." if desativado else
               "Verifique o painel de gerenciamento antes de tentar de novo."),
            parent=self)


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
        self.minsize(720, 460)
        tema.ajustar_a_tela(self, 980, 620)
        self.transient(mestre)
        # Mesmas saídas da captura pela webcam: pelo X, pelo Esc ou pelo
        # fechamento da janela de trás, as faces carregadas têm de sumir.
        # Antes, só o botão «Cancelar» descartava — fechar pelo X deixava as
        # imagens na memória (LGPD art. 6º, III e V; ETP 4.3).
        self.protocol("WM_DELETE_WINDOW", self._cancelar)
        self.bind("<Escape>", lambda _: self._cancelar())
        self.bind("<Destroy>", self._descartar_tudo)
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

        nota = ttk.Label(quadro, text="Rostos frontais, bem iluminados, um por foto. As imagens "
                                      "não são gravadas: treinam o modelo e são descartadas.",
                         style="Suave.TLabel", justify="left")
        nota.pack(side="bottom", anchor="w", pady=(4, 0))
        tema.quebrar_com_a_janela(nota, self, margem=60)
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
        # a entrega desarma o gancho de <Destroy>: daqui para a frente quem
        # recebe os coletores é que responde por apagar as faces (ver
        # DialogoNovoUsuario._concluir, que o faz num finally)
        self._entregues = True
        self.destroy()
        self.ao_concluir(coletores)

    def _cancelar(self):
        self._descartar_tudo()
        self.destroy()

    def _descartar_tudo(self, evento=None):
        """Apaga as faces carregadas; ligado ao <Destroy> além do botão Cancelar.

        Não age após a entrega dos coletores ao cadastro — ver a explicação no
        método de mesmo nome em JanelaCaptura.
        """
        if evento is not None and evento.widget is not self:
            return                              # <Destroy> de um filho, não da janela
        if getattr(self, "_entregues", False):
            return
        for coletor in getattr(self, "coletores", []):
            coletor.descartar_imagens()


# (singular, plural) — algumas formas não variam, por isso o par explícito
DESCARTES_LEGIVEIS = {
    "ESCURO": ("escura", "escuras"),
    "CLARO": ("estourada", "estouradas"),
    "SEM_CONTRASTE": ("sem contraste", "sem contraste"),
    "DESFOCADO": ("desfocada", "desfocadas"),
    "RUIDOSO": ("ruidosa", "ruidosas"),
    "DUPLICATA": ("repetida", "repetidas"),
    "SEM_FACE": ("sem rosto", "sem rosto"),
    "MULTIPLAS_FACES": ("com mais de um rosto", "com mais de um rosto"),
}


# O que fazer para destravar, por motivo de descarte. Entra em cena quando a
# sessão para de avançar: a pessoa vê o contador parado em "12 de 40" e não tem
# como adivinhar que o problema é a luz atrás dela. A captura não tem prazo —
# sem esta dica, a única saída visível é cancelar tudo e recomeçar às cegas.
DICAS_DE_DESCARTE = {
    "ESCURO": "acenda mais luz ou vire-se para a janela",
    "CLARO": "afaste-se da luz forte, ou feche um pouco a cortina",
    "SEM_CONTRASTE": "evite ficar com uma parede muito clara atrás de você",
    "DESFOCADO": "fique parado um instante e limpe a lente da câmera",
    "RUIDOSO": "melhore a iluminação — no escuro a câmera gera ruído",
    "DUPLICATA": "mova um pouco a cabeça: as imagens estão saindo iguais",
    "SEM_FACE": "centralize o rosto na moldura e tire o que o estiver cobrindo",
    "MULTIPLAS_FACES": "peça para as outras pessoas saírem do enquadramento",
}

SEGUNDOS_SEM_AVANCO = 12        # a partir daqui, a tela deixa de só descrever e sugere


def dica_para_destravar(descartes):
    """Sugestão baseada no motivo que MAIS barrou amostras, ou "" se não houver."""
    if not descartes:
        return ""
    motivo = max(descartes.items(), key=lambda kv: kv[1])[0]
    return DICAS_DE_DESCARTE.get(motivo, "")


def _resumir(descartes, limite=3):
    """"7 repetidas, 3 desfocadas, 1 escura" — diz o que corrigir (luz, foco,
    distância) em vez de apenas somar falhas."""
    partes = sorted(descartes.items(), key=lambda kv: -kv[1])[:limite]
    return ", ".join(f"{n} {DESCARTES_LEGIVEIS.get(motivo, (motivo.lower(),) * 2)[n != 1]}"
                     for motivo, n in partes)


class JanelaCaptura(tk.Toplevel):
    """Captura as sessões faciais do cadastro (ETP 4.2: duas sessões, iluminações distintas)."""

    def __init__(self, mestre, ctx, ao_concluir):
        super().__init__(mestre)
        # O estado vem ANTES de qualquer widget. Se a construção falhar no meio,
        # a janela ainda existe na tela e o usuário vai fechá-la — e fechar não
        # pode levantar um segundo erro em cima do primeiro, escondendo a causa.
        self._agendado = None
        self.coletores = []
        self._amostras_vistas = -1
        self._ultimo_avanco = time.monotonic()
        self.ctx, self.ao_concluir = ctx, ao_concluir
        self.pipeline = PipelineFacial(cfg=ctx.cfg)
        self.total_sessoes = ctx.cfg.getint("cadastro", "sessoes")
        self.title("Captura facial")
        self.configure(bg=tema.FUNDO)
        self.protocol("WM_DELETE_WINDOW", self._cancelar)
        self.bind("<Escape>", lambda _: self._cancelar())
        self.bind("<Destroy>", self._descartar_tudo)   # cobre o fechamento pelo pai
        self.minsize(720, 520)
        _, altura = tema.ajustar_a_tela(self, 900, 860)
        tema.cabecalho(self, "Captura facial",
                       f"{self.total_sessoes} sessões — mude a iluminação entre elas (ETP 4.2)")

        # ORDEM DE EMPACOTAMENTO: tudo que a pessoa precisa CLICAR é ancorado na
        # base primeiro. Assim o botão de continuar nunca é empurrado para fora
        # da tela — antes ele sumia quando a janela crescia além do monitor, e
        # não havia como seguir para a sessão seguinte.
        rodape = ttk.Frame(self, padding=(10, 10))
        rodape.pack(side="bottom", fill="x")
        self.botao = ttk.Button(rodape, text="Iniciar sessão 1", style="Acento.TButton",
                                command=self._iniciar_sessao)
        self.botao.pack(side="right")
        ttk.Button(rodape, text="Cancelar", command=self._cancelar).pack(side="right", padx=8)
        self.resumo_sessoes = ttk.Label(rodape, style="Suave.TLabel")
        self.resumo_sessoes.pack(side="left")

        progresso = ttk.Frame(self, style="Superficie.TFrame", padding=(14, 10))
        progresso.pack(side="bottom", fill="x", padx=10)
        self.barra = ttk.Progressbar(progresso, style="Medidor.Horizontal.TProgressbar",
                                     maximum=ctx.cfg.getint("cadastro", "frames_por_sessao"))
        self.barra.pack(fill="x", pady=(0, 6))
        # os descartes já são contados pelo coletor; mostrá-los diz à pessoa o que
        # corrigir (luz, foco, distância) em vez de deixá-la adivinhar por que não avança
        self.detalhe = ttk.Label(progresso, style="Detalhe.TLabel")
        self.detalhe.pack(anchor="w")

        self.instrucao = ttk.Label(self, style="Forte.TLabel", padding=(10, 8))
        self.instrucao.pack(side="bottom", fill="x")
        tema.quebrar_com_a_janela(self.instrucao, self, margem=56)

        # Checklist antes de começar. Ler quatro linhas agora evita a sessão
        # inteira recusando quadro por quadro depois.
        preparo = ttk.Frame(self, style="Superficie.TFrame", padding=(14, 10))
        preparo.pack(fill="x", padx=10, pady=(10, 0))
        ttk.Label(preparo, text="ANTES DE COMEÇAR", style="Rotulo.TLabel").pack(anchor="w")
        for dica in ("Fique de frente para a luz — nunca de costas para a janela.",
                     "Enquadre o rosto dentro da moldura que aparece no vídeo.",
                     "Tire boné e óculos escuros; óculos de grau pode manter.",
                     "Mova a cabeça devagar: um pouco para os lados e para cima e para baixo."):
            ttk.Label(preparo, text=f"•  {dica}", style="Detalhe.TLabel").pack(anchor="w")
        self.preparo = preparo

        # o vídeo fica por último e recebe o que sobrou: é o único elemento que
        # encolhe sem prejuízo
        self.visor = Visor(self, 860, tema.altura_para_video(self, altura))
        self.visor.pack(padx=10, pady=(8, 0), expand=True)
        self._atualizar_resumo()
        self.instrucao.configure(
            text="Sessão 1 — leia o preparo acima e clique em «Iniciar sessão 1» quando "
                 "estiver pronto.")

    def _atualizar_resumo(self):
        """Quantas sessões já fecharam — a pessoa precisa saber quanto falta."""
        feitas = sum(1 for c in self.coletores if len(c.faces) >= c.alvo)
        self.resumo_sessoes.configure(
            text=f"Sessão {min(feitas + 1, self.total_sessoes)} de {self.total_sessoes}"
                 + (f"   ·   {feitas} concluída(s)" if feitas else ""))

    def _iniciar_sessao(self):
        # Desabilitar o botão já barra o clique repetido, mas não protege o
        # método em si: um Enter enfileirado ou uma chamada vinda de outro ponto
        # abriria uma segunda sessão por cima da que está rodando, e as duas
        # disputariam o mesmo laço de vídeo. O estado real dos coletores é a
        # guarda mais confiável — não depende de widget nenhum.
        if self.coletores and not self.coletores[-1].completa:
            return
        try:
            self.ctx.camera()
        except WebcamIndisponivel as erro:
            messagebox.showerror(
                "Câmera indisponível",
                f"Não foi possível abrir a webcam.\n\n{erro}\n\n"
                "Confira se: outra aplicação está usando a câmera (feche-a), se o "
                "cabo está conectado, ou se o Windows bloqueou o acesso em\n"
                "Configurações › Privacidade › Câmera.", parent=self)
            return
        self.botao.configure(state="disabled")
        self.preparo.pack_forget()
        self._atualizar_resumo()
        self._amostras_vistas = -1          # zera o detector de sessão travada
        self._ultimo_avanco = time.monotonic()
        self.coletores.append(ColetorAmostras(len(self.coletores) + 1, self.ctx.cfg))
        self.pipeline.segmentador.reiniciar()
        self._laco()

    def _dica_se_travou(self, coletor):
        """Acrescenta o que fazer quando a contagem para de subir.

        A sessão não tem prazo: enquanto as amostras não chegam ao alvo, o laço
        segue. Isso é proposital — ninguém deve ser barrado por demorar. Mas
        significa que uma pessoa com a luz atrás de si ficaria indefinidamente
        vendo o contador parado, com o botão «Cancelar» como única saída óbvia.
        Passados alguns segundos sem avanço, a tela para de apenas descrever o
        problema e passa a dizer o que ajustar.
        """
        if len(coletor.faces) != self._amostras_vistas:
            self._amostras_vistas = len(coletor.faces)
            self._ultimo_avanco = time.monotonic()
            return ""
        if time.monotonic() - self._ultimo_avanco < SEGUNDOS_SEM_AVANCO:
            return ""
        dica = dica_para_destravar(coletor.descartes)
        return f"   ·   parado há alguns segundos: {dica}" if dica else ""

    def _laco(self):
        coletor = self.coletores[-1]
        frame = self.ctx.camera().ler(timeout=0.5)
        if frame is None:
            messagebox.showerror(
                "Câmera parou de responder",
                "A webcam deixou de enviar imagem no meio da captura.\n\n"
                "Nenhuma amostra foi gravada. Reconecte a câmera e repita o cadastro.",
                parent=self)
            return self._cancelar()
        analise = self.pipeline.analisar(frame, reconhecer=False)
        aceito = coletor.alimentar(analise)
        self.visor.mostrar(desenhar_guia(frame, analise.retangulos,
                                         (0, 190, 0) if aceito else (0, 0, 220)))
        # enquadramento vem antes da qualidade: de nada adianta avisar "desfocado"
        # se a pessoa está longe demais para o recorte sair nítido
        enquadramento = avaliar_enquadramento(frame, analise.retangulo)
        orientacao = enquadramento or analise.qualidade.mensagem
        self.instrucao.configure(text=f"Sessão {coletor.sessao} de {self.total_sessoes} — "
                                      f"{orientacao}{self._dica_se_travou(coletor)}")
        self.barra.configure(value=len(coletor.faces))
        self.detalhe.configure(text=f"{len(coletor.faces)} de {coletor.alvo} amostras"
                                    + (f"   ·   descartadas: {_resumir(coletor.descartes)}"
                                       if coletor.descartes else ""))
        if not coletor.completa:
            self._agendado = self.after(15, self._laco)
            return
        if len(self.coletores) < self.total_sessoes:
            self.preparo.pack(fill="x", padx=10, pady=(10, 0))
            self.instrucao.configure(
                text=f"✓ Sessão {coletor.sessao} concluída com {len(coletor.faces)} amostras. "
                     f"Agora MUDE a condição — acenda outra luz, vire-se um pouco ou "
                     f"aproxime-se — e clique em «Iniciar sessão {len(self.coletores) + 1}», "
                     f"no canto inferior direito.")
            self._atualizar_resumo()
            self.botao.configure(text=f"Iniciar sessão {len(self.coletores) + 1}", state="normal")
            self.botao.focus_set()        # Enter/Espaço seguem sem precisar do mouse
            return
        self._entregues = True            # ver _descartar_tudo: a posse passa adiante
        self.destroy()
        self.ao_concluir(self.coletores)

    def _cancelar(self):
        """Fecha a janela e descarta o que foi coletado — tolerante a janela
        parcialmente construída (ver o comentário no __init__)."""
        agendado = getattr(self, "_agendado", None)
        if agendado:
            self.after_cancel(agendado)
        self._descartar_tudo()
        self.destroy()

    def _descartar_tudo(self, evento=None):
        """Apaga as faces coletadas. Ligado também ao <Destroy> da janela.

        Sem o gancho em <Destroy>, fechar a janela PAI (o formulário de cadastro)
        destruía esta aqui sem passar por _cancelar, e as imagens faciais ficavam
        na memória até o coletor ser recolhido pelo GC. Imagem de rosto é dado
        pessoal sensível: só pode existir enquanto for necessária (LGPD art. 6º,
        III e V; ETP 4.3). Um `for` sobre uma lista vazia é barato, então não há
        motivo para não cobrir todos os caminhos de saída.

        A exceção é a conclusão bem-sucedida: ali os coletores são ENTREGUES ao
        cadastro, que precisa das faces para treinar e as apaga em seguida. Sem
        essa ressalva, o gancho apagaria as amostras antes do treino.
        """
        if evento is not None and evento.widget is not self:
            return                              # <Destroy> de um filho, não da janela
        if getattr(self, "_entregues", False):
            return
        for coletor in getattr(self, "coletores", []):
            coletor.descartar_imagens()
