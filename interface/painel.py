"""Painel de gerenciamento e monitoramento do protótipo.

Para que serve: acompanhar o estado da aplicação sem abrir o MySQL na mão —
quem está cadastrado, quantas amostras cada identidade tem, o que foi negado
nas últimas horas, se a trilha encadeada continua íntegra e se o modelo LBPH
cifrado foi carregado.

O acesso hoje é a senha de administrador (ETP 4.5). A intenção é que o painel
passe a ser exclusivo do desenvolvedor; quando isso mudar, o portão a alterar é
exigir_administrador(), em interface/comum.py — não este arquivo.

Nenhum SQL mora aqui: tudo vem de dados/relatorios_sistema.py e dos
repositórios, como no resto da interface.
"""
import logging
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from dados.auditoria import novo_registro
from dados.relatorios_sistema import RelatoriosSistema
from interface import tema
from interface.cadastro import DialogoNovoUsuario
from interface.comum import exigir_administrador
from interface.tema import Coluna

def _situacao(valor):
    """ativo chega do MySQL como 0/1 (BOOLEAN), não como bool do Python."""
    return "ativo" if valor else "inativo"


# Coluna.largura é o TETO em caracteres; a largura real sai do conteúdo exibido
COLUNAS_USUARIOS = [
    Coluna("matricula", "Matrícula", 12),
    Coluna("nome", "Nome", 26, "w", elastica=True),
    Coluna("nivel_id", "Nível", 6, "center"),
    Coluna("uf", "UF", 5, "center"),
    Coluna("amostras", "Amostras", 9, "center"),
    Coluna("ativo", "Situação", 9, "center", formato=_situacao),
    Coluna("criado_em", "Cadastrado em", 20),
]

COLUNAS_EVENTOS = [
    Coluna("id", "Id", 5, "e"),
    Coluna("momento", "Momento", 20),
    Coluna("evento", "Evento", 14),
    Coluna("nivel", "Nível", 6, "center"),
    Coluna("resultado", "Resultado", 11),
    Coluna("motivo", "Motivo", 26, "w", elastica=True),
]

COLUNAS_MOTIVOS = [
    Coluna("motivo", "Motivo da negação", 26, "w", elastica=True),
    Coluna("nivel", "Nível", 6, "center"),
    Coluna("eventos", "Nº", 5, "e"),
    Coluna("distancia_media", "Dist.", 9, "e"),
]

CAMPOS_FICHA = [
    ("matricula", "Matrícula", None), ("nome", "Nome", None), ("nivel_id", "Nível", None),
    ("uf", "UF", None), ("amostras", "Amostras", None), ("ativo", "Situação", _situacao),
    ("criado_em", "Cadastrado em", None), ("id", "Rótulo no LBPH", None),
]


def abrir_painel(mestre, ctx):
    if exigir_administrador(mestre):
        JanelaPainel(mestre, ctx)


class Ficha(ttk.Frame):
    """Pares rótulo/valor do registro selecionado na tabela."""

    def __init__(self, mestre, campos, titulo="REGISTRO SELECIONADO"):
        super().__init__(mestre, style="Superficie.TFrame", padding=14)
        self.campos = campos
        self._valores = {}
        ttk.Label(self, text=titulo, style="Rotulo.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        for i, (chave, rotulo, _) in enumerate(campos, start=1):
            ttk.Label(self, text=rotulo, style="Detalhe.TLabel").grid(
                row=i, column=0, sticky="w", padx=(0, 14), pady=2)
            valor = ttk.Label(self, text="—", style="Superficie.TLabel", font=tema.F_FORTE)
            valor.grid(row=i, column=1, sticky="w", pady=2)
            self._valores[chave] = valor

    def mostrar(self, linha):
        for chave, _, formato in self.campos:
            if not linha:
                self._valores[chave].configure(text="—")
                continue
            valor = linha.get(chave)
            self._valores[chave].configure(
                text=formato(valor) if formato else tema.formatar(valor))


class JanelaPainel(tk.Toplevel):
    HORAS_JANELA = 24      # janela de observação dos indicadores de negação

    def __init__(self, mestre, ctx):
        super().__init__(mestre)
        self.ctx = ctx
        self.relatorios = RelatoriosSistema(ctx.banco)
        self.title("Painel de gerenciamento")
        # dimensão relativa à tela: um tamanho fixo em pixels fica apertado em
        # monitor com escala de DPI, onde as fontes ocupam mais espaço
        largura = min(1380, int(self.winfo_screenwidth() * 0.92))
        altura = min(900, int(self.winfo_screenheight() * 0.86))
        self.geometry(f"{largura}x{altura}")
        self.minsize(900, 600)
        self.configure(bg=tema.FUNDO)
        self.status = tema.cabecalho(self, "Painel de gerenciamento",
                                     "Monitoramento do protótipo — APS PIVC 2026/2")

        abas = ttk.Notebook(self)
        abas.pack(fill="both", expand=True, padx=10, pady=10)
        abas.add(self._aba_visao_geral(abas), text="Visão geral")
        abas.add(self._aba_usuarios(abas), text="Usuários")
        self.atualizar()

    # ------------------------------------------------------------ visão geral
    def _aba_visao_geral(self, abas):
        quadro = ttk.Frame(abas, padding=12)
        faixa = ttk.Frame(quadro)
        faixa.pack(fill="x")
        self.cartoes = {}
        for chave, rotulo in (("usuarios", "Usuários"), ("modelo", "Identidades no modelo"),
                              ("amostras", "Amostras"), ("negadas", f"Negadas ({self.HORAS_JANELA} h)"),
                              ("bloqueios", "Bloqueios ativos"), ("trilha", "Trilha de auditoria")):
            cartao = tema.Cartao(faixa, rotulo)
            cartao.pack(side="left", fill="both", expand=True, padx=(0, 8))
            self.cartoes[chave] = cartao

        # As duas tabelas ficam EMPILHADAS, não lado a lado: com escala de DPI a
        # fonte cresce e duas tabelas na mesma linha empurrariam a coluna Motivo
        # — a mais informativa — para fora da vista.
        baixo = ttk.Frame(quadro)
        baixo.pack(fill="both", expand=True, pady=(16, 0))
        baixo.columnconfigure(0, weight=1)
        baixo.rowconfigure(1, weight=3)
        baixo.rowconfigure(3, weight=2)

        ttk.Label(baixo, text="ÚLTIMOS EVENTOS (S-01)", style="Secao.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 5))
        self.tabela_eventos = tema.Tabela(
            baixo, COLUNAS_EVENTOS, altura=12,
            tag_por_linha=lambda l: "negado" if l.get("resultado") == "NEGADO" else None)
        self.tabela_eventos.configurar_tag("negado", foreground=tema.ERRO)
        self.tabela_eventos.grid(row=1, column=0, sticky="nsew")

        ttk.Label(baixo, text=f"POR QUE FOI NEGADO (ÚLTIMAS {self.HORAS_JANELA} H)",
                  style="Secao.TLabel").grid(row=2, column=0, sticky="w", pady=(14, 5))
        self.tabela_motivos = tema.Tabela(baixo, COLUNAS_MOTIVOS, altura=7)
        self.tabela_motivos.grid(row=3, column=0, sticky="nsew")

        ttk.Button(quadro, text="Atualizar", style="Acento.TButton",
                   command=self.atualizar).pack(anchor="e", pady=(12, 0))
        return quadro

    # ------------------------------------------------------------ usuários
    def _aba_usuarios(self, abas):
        quadro = ttk.Frame(abas, padding=12)
        barra = ttk.Frame(quadro)
        barra.pack(fill="x", pady=(0, 10))
        ttk.Button(barra, text="Cadastrar usuário", style="Acento.TButton",
                   command=self._novo_usuario).pack(side="left")
        self.botao_situacao = ttk.Button(barra, text="Desativar", state="disabled",
                                        command=self._alternar_situacao)
        self.botao_situacao.pack(side="left", padx=6)
        ttk.Button(barra, text="Atualizar", command=self.atualizar).pack(side="right")

        corpo = ttk.Frame(quadro)
        corpo.pack(fill="both", expand=True)
        corpo.columnconfigure(0, weight=1)
        corpo.rowconfigure(0, weight=1)
        self.tabela_usuarios = tema.Tabela(
            corpo, COLUNAS_USUARIOS, altura=18, ao_selecionar=self._selecionar_usuario,
            tag_por_linha=lambda l: None if l.get("ativo") else "inativo")
        self.tabela_usuarios.configurar_tag("inativo", foreground=tema.TEXTO_SUAVE)
        self.tabela_usuarios.grid(row=0, column=0, sticky="nsew")

        lateral = ttk.Frame(corpo)
        lateral.grid(row=0, column=1, sticky="ns", padx=(12, 0))
        self.ficha = Ficha(lateral, CAMPOS_FICHA)
        self.ficha.pack(fill="x")
        ttk.Label(lateral, text="Desativar não apaga as amostras nem retira a\n"
                               "face do modelo LBPH: a política passa a negar\n"
                               "pelo motivo USUARIO_INATIVO (falha segura).",
                  style="Suave.TLabel", justify="left").pack(anchor="w", pady=(12, 0))
        return quadro

    def _novo_usuario(self):
        DialogoNovoUsuario(self, self.ctx, ao_concluir=lambda _: self.atualizar())

    def _selecionar_usuario(self, usuario):
        self.ficha.mostrar(usuario)
        if not usuario:
            self.botao_situacao.configure(state="disabled", text="Desativar", style="TButton")
            return
        ativo = bool(usuario["ativo"])
        self.botao_situacao.configure(state="normal", text="Desativar" if ativo else "Reativar",
                                      style="Perigo.TButton" if ativo else "TButton")

    def _alternar_situacao(self):
        usuario = self.tabela_usuarios.selecionada()
        if not usuario:
            return
        ativo = bool(usuario["ativo"])
        acao = "desativar" if ativo else "reativar"
        if not messagebox.askyesno("Situação do usuário",
                                   f"Confirma {acao} {usuario['nome']} "
                                   f"({usuario['matricula']})?", parent=self):
            return
        self.ctx.usuarios.definir_ativo(usuario["id"], not ativo)
        # o ato administrativo entra na MESMA cadeia de hash dos acessos (RF-12):
        # desativar alguém é decisão auditável, não configuração silenciosa
        self.ctx.trilha.registrar(novo_registro(
            "CADASTRO", usuario["nivel_id"], "CONCEDIDO",
            "USUARIO_DESATIVADO" if ativo else "USUARIO_REATIVADO", usuario_id=usuario["id"]))
        self.atualizar()

    # ------------------------------------------------------------ carga dos dados
    def atualizar(self):
        usuarios = self._seguro(self.ctx.usuarios.listar, []) or []
        self._atualizar_cartoes(usuarios)
        self.tabela_usuarios.preencher(usuarios)
        self._selecionar_usuario(None)
        self.tabela_eventos.preencher(self._seguro(lambda: self.relatorios.s01_log_acessos(60), []) or [])
        self.tabela_motivos.preencher(
            self._seguro(lambda: self.relatorios.motivos_de_negacao(self.HORAS_JANELA), []) or [])
        self.status.configure(text=f"Atualizado às {datetime.now():%H:%M:%S}")

    def _atualizar_cartoes(self, usuarios):
        # --- usuários por nível
        por_nivel = self._seguro(self.relatorios.contagem_usuarios, []) or []
        total = sum(l["usuarios"] for l in por_nivel)
        ativos = sum(int(l["ativos"] or 0) for l in por_nivel)
        detalhe = "  ".join(f"N{l['nivel']}·{l['usuarios']}" for l in por_nivel) or "nenhum cadastrado"
        if total != ativos:
            detalhe += f"   {total - ativos} inativo(s)"
        self.cartoes["usuarios"].atualizar(total, detalhe, None if total else tema.AVISO)

        # --- modelo LBPH em memória × amostras registradas no banco.
        # A divergência é o sinal operacional mais útil do painel: significa
        # modelo perdido, recriado com outra chave, ou cadastro interrompido.
        rotulos = self.ctx.reconhecedor.rotulos_cadastrados()
        com_amostras = {u["id"] for u in usuarios if u.get("amostras")}
        fora = com_amostras - rotulos
        if not rotulos:
            self.cartoes["modelo"].atualizar(0, "nenhuma face no modelo", tema.AVISO)
        elif fora:
            self.cartoes["modelo"].atualizar(len(rotulos), f"{len(fora)} com amostra fora do modelo",
                                             tema.AVISO)
        else:
            self.cartoes["modelo"].atualizar(len(rotulos), "modelo cifrado carregado", tema.OK)

        # --- amostras
        amostras = self._seguro(self.relatorios.contagem_amostras)
        if amostras is None:
            self.cartoes["amostras"].atualizar("—", "indisponível", tema.TEXTO_SUAVE)
        else:
            self.cartoes["amostras"].atualizar(
                amostras["amostras"],
                f"{amostras['identidades']} identidades · qual. "
                f"{tema.formatar(amostras['qualidade_media'])}")

        # --- negadas na janela
        negadas = self._seguro(lambda: self.relatorios.contagem_negadas(self.HORAS_JANELA))
        if negadas is None:
            self.cartoes["negadas"].atualizar("—", "indisponível", tema.TEXTO_SUAVE)
        else:
            self.cartoes["negadas"].atualizar(negadas, "autenticações negadas",
                                              tema.ERRO if negadas else tema.OK)

        # --- bloqueios ativos
        bloqueios = self._seguro(self.relatorios.s03_bloqueios_ativos, []) or []
        self.cartoes["bloqueios"].atualizar(
            len(bloqueios), "matrícula(s) em bloqueio" if bloqueios else "nenhum bloqueio",
            tema.AVISO if bloqueios else tema.OK)

        # --- integridade da cadeia (S-04): recomputa todos os hashes
        resultado = self._seguro(self.relatorios.s04_integridade)
        if resultado is None:
            self.cartoes["trilha"].atualizar("—", "indisponível", tema.TEXTO_SUAVE)
        elif resultado.integra:
            self.cartoes["trilha"].atualizar("ÍNTEGRA", f"{resultado.total} registros verificados",
                                             tema.OK)
        else:
            self.cartoes["trilha"].atualizar("RUPTURA", f"id={resultado.id_ruptura} · {resultado.tipo}",
                                             tema.ERRO)

    def _seguro(self, funcao, padrao=None):
        """Indicador indisponível não derruba o painel: registra e devolve o padrão.

        Monitoramento é leitura. Um travessão num cartão é melhor do que a
        janela inteira não abrir porque uma consulta falhou.
        """
        try:
            return funcao()
        except Exception as erro:
            logging.warning("Painel: indicador indisponível (%s)", erro)
            return padrao
