"""Peças compartilhadas pelas telas: contexto da aplicação, vídeo e tabelas."""
from dataclasses import dataclass, field
from tkinter import messagebox, simpledialog, ttk

import cv2
from PIL import Image, ImageTk

import configuracao
from autenticacao import senha
from interface.tema import CORES_NIVEL, NOMES_NIVEL  # noqa: F401 (reexportado às telas)
from visao.aquisicao import CapturaThread


def exigir_administrador(mestre):
    """Portão do módulo administrativo (ETP 4.5). True só se a senha conferir.

    Compartilhado pelo painel de gerenciamento e pela administração para que
    exista UM só ponto de verificação — quando o painel virar exclusivo do
    desenvolvedor, é aqui que a regra muda.
    """
    hash_admin = configuracao.env("ADMIN_SENHA_HASH", obrigatorio=False)
    if not hash_admin:
        messagebox.showerror("Acesso administrativo",
                             "ADMIN_SENHA_HASH não configurado no .env\n"
                             "(python -m ferramentas hash-admin)", parent=mestre)
        return False
    digitada = simpledialog.askstring("Acesso administrativo", "Senha do administrador:",
                                      show="•", parent=mestre)
    if not senha.verificar(digitada, hash_admin):
        if digitada is not None:      # None = o usuário cancelou o diálogo
            messagebox.showerror("Acesso administrativo", "Senha incorreta.", parent=mestre)
        return False
    return True


@dataclass
class Contexto:
    """Dependências montadas uma vez no main.py e passadas às telas."""
    cfg: object
    banco: object
    trilha: object
    reconhecedor: object
    motor: object
    acervo: object
    usuarios: object
    _camera: CapturaThread | None = field(default=None, repr=False)

    def camera(self):
        if self._camera is None:
            self._camera = CapturaThread().iniciar()
        return self._camera

    def encerrar(self):
        if self._camera:
            self._camera.parar()
            self._camera = None


def para_tk(imagem_bgr, largura_max, altura_max):
    altura, largura = imagem_bgr.shape[:2]
    escala = min(largura_max / largura, altura_max / altura, 1.0)
    if escala < 1.0:
        imagem_bgr = cv2.resize(imagem_bgr, (int(largura * escala), int(altura * escala)), interpolation=cv2.INTER_AREA)
    return ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(imagem_bgr, cv2.COLOR_BGR2RGB)))


class Visor(ttk.Label):
    """Label que exibe uma imagem OpenCV mantendo a referência (senão o Tk a descarta)."""

    def __init__(self, mestre, largura=640, altura=480, **kw):
        super().__init__(mestre, **kw)
        self.largura, self.altura = largura, altura
        self._foto = None

    def mostrar(self, imagem_bgr):
        self._foto = para_tk(imagem_bgr, self.largura, self.altura)
        self.configure(image=self._foto)


def desenhar_faces(frame, retangulos, cor):
    saida = frame.copy()
    for (x, y, w, h) in retangulos:
        cv2.rectangle(saida, (x, y), (x + w, y + h), cor, 2)
    return saida


def tabela_texto(linhas, colunas=None):
    """Formata uma lista de dicionários como tabela de largura fixa."""
    if not linhas:
        return "(nenhum registro)"
    colunas = colunas or list(linhas[0].keys())
    texto = [[str(l.get(c, "")) if l.get(c) is not None else "—" for c in colunas] for l in linhas]
    larguras = [max(len(c), *(len(t[i]) for t in texto)) for i, c in enumerate(colunas)]
    cab = "  ".join(c.ljust(w) for c, w in zip(colunas, larguras))
    return "\n".join([cab, "-" * len(cab)] + ["  ".join(v.ljust(w) for v, w in zip(t, larguras)) for t in texto])
