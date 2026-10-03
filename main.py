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


# O que cada nível exige e entrega — na porta de entrada, não só na documentação.
NIVEIS = {
    1: ("face apenas, sem senha",
        "números e mapas agregados, sem localização",
        "exportação livre"),
    2: ("matrícula e senha, depois a face",
        "registros completos da sua região, com endereço e responsável",
        "exportação com marca d'água invisível"),
    3: ("senha forte, face, desafio na câmera e uma segunda pessoa",
        "visão nacional consolidada, incluindo pontos de custódia",
        "exportação bloqueada — somente visualização"),
}


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
        ttk.Label(rodape, text="Protótipo com taxa de erro conhecida — toda negação admite "
                               "revisão humana.", style="Suave.TLabel").pack(side="right")
        if not ctx.reconhecedor.treinado:
            ttk.Label(self, text="Nenhuma face cadastrada ainda — comece pelo Painel de "
                                 "gerenciamento para cadastrar a primeira pessoa.",
                      style="Erro.TLabel").pack(pady=(14, 0))

    def _autenticar(self, nivel):
        JanelaAutenticacao(self, self.ctx, nivel, lambda sessao: JanelaConsulta(self, self.ctx, sessao))


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

    TelaInicial(raiz, ctx)
    # A raiz se dimensiona pelo conteúdo e, sem limite, uma tela menor que ele
    # cortaria justamente a base — onde ficam os botões de entrar em cada nível.
    # O mínimo é o próprio conteúdo: encolher abaixo disso só esconderia botão.
    raiz.update_idletasks()
    raiz.minsize(*tema.ajustar_a_tela(raiz, raiz.winfo_reqwidth(), raiz.winfo_reqheight()))

    def sair():
        ctx.encerrar()
        raiz.destroy()

    raiz.protocol("WM_DELETE_WINDOW", sair)
    raiz.mainloop()


if __name__ == "__main__":
    main()
