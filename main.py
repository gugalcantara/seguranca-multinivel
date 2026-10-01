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
from dados.repositorio import RepositorioUsuarios
from interface import tema
from interface.autenticacao import JanelaAutenticacao
from interface.cadastro import abrir_administracao
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
    )


class TelaInicial(ttk.Frame):
    def __init__(self, raiz, ctx):
        super().__init__(raiz, padding=28)
        self.ctx = ctx
        self.pack(fill="both", expand=True)
        ttk.Label(self, text="Cadastro Consolidado de Passivos Perigosos Pendentes",
                  style="Titulo.TLabel").pack()
        ttk.Label(self, text="Controle de acesso multinível por reconhecimento facial "
                             "— protótipo APS PIVC 2026/2", style="Subtitulo.TLabel").pack(pady=(0, 20))
        for nivel in (1, 2, 3):
            tk.Button(self, text=f"Entrar no nível {nivel} — {NOMES_NIVEL[nivel]}", width=46,
                      bg=CORES_NIVEL[nivel], fg="white", font=tema.F_FORTE, relief="flat",
                      pady=10, cursor="hand2", activebackground=CORES_NIVEL[nivel],
                      activeforeground="white", command=lambda n=nivel: self._autenticar(n)).pack(pady=4)
        ttk.Separator(self).pack(fill="x", pady=18)
        ttk.Button(self, text="Painel de gerenciamento", style="Acento.TButton",
                   command=lambda: abrir_painel(self, ctx)).pack(pady=(0, 6))
        ttk.Button(self, text="Administração (relatórios do sistema e ferramentas)",
                   command=lambda: abrir_administracao(self, ctx)).pack()
        if not ctx.reconhecedor.treinado:
            ttk.Label(self, text="Nenhuma face cadastrada ainda — comece pelo Painel de gerenciamento.",
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

    def sair():
        ctx.encerrar()
        raiz.destroy()

    raiz.protocol("WM_DELETE_WINDOW", sair)
    raiz.mainloop()


if __name__ == "__main__":
    main()
