"""Ponto de entrada da aplicação desktop.

    python main.py

Pré-requisitos: MySQL com o schema criado, .env preenchido (ver README).
Falha segura desde a partida: sem banco, sem chave ou sem modelo legível, a
aplicação não abre o acervo.
"""
import logging
import tkinter as tk
import traceback
from tkinter import messagebox, ttk

import configuracao
from acervo.entrega import ServicoAcervo
from acervo.repositorio_acervo import RepositorioAcervo
from autenticacao.motor import MotorAutenticacao
from dados.auditoria import TrilhaAuditoria
from dados.conexao import Banco, BancoIndisponivel
from dados.repositorio import RepositorioConsentimento, RepositorioUsuarios
from interface import tema
from interface.autenticacao import JanelaAutenticacao
from interface.comum import CORES_NIVEL, NOMES_NIVEL, Contexto
from interface.painel import abrir_painel
from interface.relatorios import JanelaConsulta
from visao.extracao import ReconhecedorLBPH

PASTA_LOGS = configuracao.RAIZ / "logs"


def _configurar_log():
    PASTA_LOGS.mkdir(exist_ok=True)
    logging.basicConfig(filename=PASTA_LOGS / "erros.log", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")


def _montar_contexto():
    cfg = configuracao.carregar()
    banco = Banco()
    trilha = TrilhaAuditoria(banco)
    reconhecedor = ReconhecedorLBPH(cfg)
    caminho_modelo = configuracao.caminho("modelo")
    if caminho_modelo.exists():
        reconhecedor.carregar(caminho_modelo, configuracao.env("CHAVE_CIFRAGEM"))
    return Contexto(
        cfg=cfg, banco=banco, trilha=trilha, reconhecedor=reconhecedor,
        motor=MotorAutenticacao(banco, reconhecedor, trilha, cfg),
        acervo=ServicoAcervo(RepositorioAcervo(banco), trilha, cfg),
        usuarios=RepositorioUsuarios(banco),
        consentimentos=RepositorioConsentimento(banco),
    )


INTERVALO_EXPURGO_MS = 60 * 60 * 1000      # repete de hora em hora com o programa aberto


def expurgar_fotos_vencidas(ctx, raiz=None):
    """Apaga as fotos de tentativas negadas que passaram do prazo de retenção.

    O prazo existia (`retencao_foto_negada_dias`), mas só como rótulo: nada o
    aplicava, e o expurgo dependia de alguém lembrar de rodar
    `ferramentas expurgar-fotos`. Essas fotos são de quem foi NEGADO — em geral
    alguém que nunca consentiu —, então guardá-las além do necessário é
    justamente o que a LGPD veda (art. 15 e 16: eliminação ao fim do tratamento).

    Falhar aqui não impede o programa de abrir: o erro vai para o log e a
    próxima rodada tenta de novo.
    """
    try:
        removidas = ctx.trilha.expurgar_fotos_expiradas()
        if removidas:
            logging.info("%d foto(s) de tentativas negadas expiradas foram eliminadas", removidas)
    except Exception:
        logging.exception("Falha ao eliminar fotos de tentativas negadas expiradas")
        removidas = None
    if raiz is not None:
        raiz.after(INTERVALO_EXPURGO_MS, lambda: expurgar_fotos_vencidas(ctx, raiz))
    return removidas


# O que cada nível exige e entrega — na porta de entrada, não só na documentação.
NIVEIS = {
    1: ("face apenas, sem senha",
        "números e mapas agregados, sem localização",
        "exportação livre"),
    2: ("matrícula e senha, depois a face",
        "registros completos da sua região, com endereço e responsável",
        "exportação com marca d'água invisível"),
    3: ("senha forte, face e desafio na câmera",
        "visão nacional consolidada, incluindo pontos de custódia",
        "exportação bloqueada — somente visualização"),
}


def fatores_do_nivel_3(cfg):
    """O texto do cartão do N3 acompanha a regra dos dois ligada ou não.

    A porta de entrada anuncia o que cada nível exige. Deixar "e uma segunda
    pessoa" fixo no texto faria a tela prometer uma exigência que a configuração
    pode ter dispensado — e a primeira coisa que um sistema de controle de acesso
    não pode fazer é descrever errado o próprio controle.
    """
    if cfg.getboolean("autenticacao", "exigir_segunda_pessoa", fallback=True):
        return NIVEIS[3][0] + " e uma segunda pessoa"
    return NIVEIS[3][0]


class TelaInicial(ttk.Frame):
    def __init__(self, raiz, ctx):
        super().__init__(raiz, padding=26)
        self.ctx = ctx
        self.pack(fill="both", expand=True)
        ttk.Label(self, text="Cadastro Consolidado de Passivos Perigosos Pendentes",
                  style="Titulo.TLabel").pack()
        ttk.Label(self, text="Controle de acesso multinível por reconhecimento facial "
                             "— protótipo acadêmico, APS PIVC 2026/2",
                  style="Subtitulo.TLabel").pack(pady=(2, 20))

        cartoes = ttk.Frame(self)
        cartoes.pack(fill="both", expand=True)
        for coluna, nivel in enumerate((1, 2, 3)):
            fatores, alcance, exportacao = NIVEIS[nivel]
            if nivel == 3:
                fatores = fatores_do_nivel_3(ctx.cfg)
            cartao = tema.CartaoNivel(cartoes, nivel, NOMES_NIVEL[nivel], fatores, alcance,
                                      exportacao, lambda n=nivel: self._autenticar(n))
            cartao.grid(row=0, column=coluna, sticky="nsew", padx=(0 if not coluna else 10, 0))
            cartoes.columnconfigure(coluna, weight=1, uniform="nivel")
        cartoes.rowconfigure(0, weight=1)

        ttk.Separator(self).pack(fill="x", pady=18)
        rodape = ttk.Frame(self)
        rodape.pack(fill="x")
        ttk.Button(rodape, text="Painel de gerenciamento", style="Acento.TButton",
                   command=lambda: abrir_painel(self, ctx)).pack(side="left")
        ttk.Label(rodape, text="Atalhos: 1, 2 e 3 abrem os níveis  ·  Ctrl+P, o painel  ·  Esc fecha a janela",
                  style="Suave.TLabel").pack(side="right")
        ttk.Label(self, text="Protótipo com taxa de erro conhecida — toda negação admite revisão humana.",
                  style="Suave.TLabel").pack(anchor="e", pady=(6, 0))

        # Atalhos na janela principal. Ficam presos à raiz, então digitar um
        # número dentro de outra janela (matrícula, senha) não abre nível nenhum:
        # o evento de teclado de uma janela filha não chega aos bindings da raiz.
        raiz = self.winfo_toplevel()
        for nivel in (1, 2, 3):
            raiz.bind(f"<Key-{nivel}>", lambda _, n=nivel: self._autenticar(n))
        raiz.bind("<Control-p>", lambda _: abrir_painel(self, ctx))
        if not ctx.reconhecedor.treinado:
            ttk.Label(self, text="Nenhuma face cadastrada ainda — comece pelo Painel de "
                                 "gerenciamento para cadastrar a primeira pessoa.",
                      style="Erro.TLabel").pack(pady=(14, 0))

    def _autenticar(self, nivel):
        """Abre a autenticação do nível — uma de cada vez.

        Dois cliques (ou a tecla repetida) abriam duas janelas disputando a mesma
        câmera. Se já houver uma aberta, ela é trazida para a frente.
        """
        aberta = getattr(self, "_janela_auth", None)
        if aberta is not None and aberta.winfo_exists():
            aberta.deiconify()
            aberta.lift()
            aberta.focus_force()
            return
        self._janela_auth = JanelaAutenticacao(
            self, self.ctx, nivel, lambda sessao: JanelaConsulta(self, self.ctx, sessao))


def iniciar_interface(raiz, ctx):
    """Tudo o que acontece entre o contexto pronto e a janela principal na tela.

    Fica fora de main() para ser testável: main() cria o Tk e entra no laço de
    eventos, e um teste não consegue observá-la por dentro. Foi assim que a
    chamada do expurgo de fotos podia sumir sem nenhum teste acusar.
    """
    expurgar_fotos_vencidas(ctx, raiz)
    tela = TelaInicial(raiz, ctx)
    # A raiz se dimensiona pelo conteúdo e, sem limite, uma tela menor que ele
    # cortaria justamente a base — onde ficam os botões de entrar em cada nível.
    # O mínimo é o próprio conteúdo: encolher abaixo disso só esconderia botão.
    raiz.update_idletasks()
    raiz.minsize(*tema.ajustar_a_tela(raiz, raiz.winfo_reqwidth(), raiz.winfo_reqheight()))
    return tela


def main():
    _configurar_log()
    raiz = tk.Tk()
    raiz.title("APS PIVC 2026/2 — Controle de acesso multinível")
    tema.aplicar(raiz)

    def erro_global(tipo, valor, tb):
        # ETP 6.6: erro não previsto é registrado e a aplicação segue, sem conceder nada
        logging.error("".join(traceback.format_exception(tipo, valor, tb)))
        messagebox.showerror("Erro", f"Falha inesperada — operação negada.\n{valor}\n(detalhes em logs/erros.log)")

    raiz.report_callback_exception = erro_global
    try:
        ctx = _montar_contexto()
    except (BancoIndisponivel, RuntimeError, FileNotFoundError) as erro:
        logging.error("Falha na inicialização: %s", erro)
        messagebox.showerror("Inicialização", f"Acesso bloqueado — o sistema não pôde iniciar com segurança.\n\n{erro}")
        raiz.destroy()
        return
    except Exception as erro:     # ex.: modelo cifrado com outra chave (InvalidToken)
        logging.exception("Falha na inicialização")
        messagebox.showerror("Inicialização", f"Acesso bloqueado — falha ao carregar o modelo.\n\n{erro!r}")
        raiz.destroy()
        return

    iniciar_interface(raiz, ctx)

    def sair():
        ctx.encerrar()
        raiz.destroy()

    raiz.protocol("WM_DELETE_WINDOW", sair)
    raiz.mainloop()


if __name__ == "__main__":
    main()
