"""Peças compartilhadas pelas telas.

Tem três papéis distintos, e vale saber qual é qual antes de mexer:

- `Contexto`: as dependências montadas uma vez no main.py (banco, trilha,
  reconhecedor, motor, repositórios) e a câmera, aberta sob demanda.
- `Visor` e as funções de desenho: o vídeo na tela, com a moldura de
  enquadramento e a orientação de posição.
- `exigir_administrador`: o portão do módulo administrativo (ETP 4.5).

A camada visual — paleta, estilos, `Cartao`, `Tabela` — fica em interface/tema.py,
não aqui.
"""
import logging
from dataclasses import dataclass, field
from tkinter import messagebox, simpledialog, ttk

import cv2
from PIL import Image, ImageTk

import configuracao
from autenticacao import senha
from interface.tema import CORES_NIVEL, NOMES_NIVEL  # noqa: F401 (reexportado às telas)
from visao.aquisicao import CapturaThread


MATRICULA_ADMIN = "@ADMIN"      # chave do contador de tentativas do portão administrativo


def exigir_administrador(mestre, ctx=None):
    """Portão do módulo administrativo (ETP 4.5). True só se a senha conferir.

    Compartilhado pelo painel de gerenciamento e pela administração para que
    exista UM só ponto de verificação — quando o painel virar exclusivo do
    desenvolvedor, é aqui que a regra muda.

    Com `ctx`, a tentativa é tratada como qualquer outra: entra na trilha e conta
    para o bloqueio. Sem isso, o portão que dá acesso a TODOS os cadastros, à
    trilha de auditoria e ao acervo era a única porta do sistema que podia ser
    tentada infinitas vezes sem travar e sem deixar rastro — enquanto o login de
    um usuário comum bloqueia após poucas falhas. A assimetria estava no lado
    errado: aqui o estrago de um acerto é maior, não menor.

    Se o próprio banco estiver fora do ar, o portão continua exigindo a senha e
    apenas deixa de contar: negar o painel justamente quando há algo a
    diagnosticar seria trocar um risco por outro maior.
    """
    hash_admin = configuracao.env("ADMIN_SENHA_HASH", obrigatorio=False)
    if not hash_admin:
        messagebox.showerror("Acesso administrativo",
                             "ADMIN_SENHA_HASH não configurado no .env\n"
                             "(python -m ferramentas hash-admin)", parent=mestre)
        return False

    bloqueios = _bloqueios(ctx)
    if bloqueios and _seguro(lambda: bloqueios.esta_bloqueado(MATRICULA_ADMIN), False):
        messagebox.showerror("Acesso administrativo",
                             "Acesso administrativo bloqueado por excesso de tentativas.\n"
                             "Aguarde alguns minutos e tente de novo.", parent=mestre)
        _auditar(ctx, "NEGADO", "ADMIN_BLOQUEADO")
        return False

    digitada = simpledialog.askstring("Acesso administrativo", "Senha do administrador:",
                                      show="•", parent=mestre)
    if digitada is None:              # o usuário cancelou: não é tentativa
        return False
    if not senha.verificar(digitada, hash_admin):
        bloqueou = False
        if bloqueios:
            cfg = ctx.cfg
            bloqueou = _seguro(lambda: bloqueios.registrar_falha(
                MATRICULA_ADMIN, cfg.getint("autenticacao", "tentativas_senha"),
                cfg.getint("autenticacao", "bloqueio_minutos")), False)
        _auditar(ctx, "NEGADO", "ADMIN_SENHA_INCORRETA")
        messagebox.showerror("Acesso administrativo",
                             "Senha incorreta." + ("\n\nAcesso administrativo bloqueado "
                                                   "temporariamente." if bloqueou else ""),
                             parent=mestre)
        return False

    if bloqueios:
        _seguro(lambda: bloqueios.zerar(MATRICULA_ADMIN))
    _auditar(ctx, "CONCEDIDO", "ADMIN_AUTENTICADO")
    return True


def _bloqueios(ctx):
    """Repositório de bloqueio do contexto, ou None quando não há banco."""
    if ctx is None or getattr(ctx, "banco", None) is None:
        return None
    from dados.repositorio import RepositorioBloqueio
    return RepositorioBloqueio(ctx.banco)


def _auditar(ctx, resultado, motivo):
    """O acesso ao painel é um evento como outro qualquer — nível 3 porque é o
    que ele enxerga: todos os cadastros e a trilha inteira.

    O evento vai como CADASTRO porque é assim que o painel já classifica seus
    atos administrativos, e o ENUM de log_acesso no schema não tem um valor
    próprio para isso. O motivo é que diferencia o registro.
    """
    if ctx is None or getattr(ctx, "trilha", None) is None:
        return
    from dados.auditoria import novo_registro
    _seguro(lambda: ctx.trilha.registrar(novo_registro("CADASTRO", 3, resultado, motivo)))


def _seguro(funcao, padrao=None):
    """Executa sem deixar falha de banco derrubar o portão (ver a docstring acima)."""
    try:
        return funcao()
    except Exception:
        logging.exception("Falha ao registrar tentativa de acesso administrativo")
        return padrao


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
    consentimentos: object = None
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


# A moldura ocupa esta fração da altura do quadro. Dentro dela o rosto tem
# resolução suficiente para o recorte 200×200 sem ampliar pixel.
FRACAO_ALVO = 0.55
TOLERANCIA_ALVO = 0.35          # quanto o rosto pode fugir do alvo antes do aviso


def moldura_alvo(frame):
    """Retângulo onde o rosto deve caber: centrado e proporcional à altura."""
    altura, largura = frame.shape[:2]
    lado = int(altura * FRACAO_ALVO)
    return ((largura - lado) // 2, (altura - lado) // 2, lado, lado)


def desenhar_guia(frame, retangulos, cor):
    """Vídeo com a moldura de enquadramento e a face marcada.

    A moldura resolve sozinha o problema mais comum da captura — a pessoa não
    sabe onde se posicionar nem a que distância ficar — sem precisar de texto.
    """
    saida = frame.copy()
    ax, ay, al, ah = moldura_alvo(frame)
    canto = int(al * 0.18)
    for (cx, cy, dx, dy) in ((ax, ay, 1, 1), (ax + al, ay, -1, 1),
                             (ax, ay + ah, 1, -1), (ax + al, ay + ah, -1, -1)):
        cv2.line(saida, (cx, cy), (cx + dx * canto, cy), (210, 210, 210), 2)
        cv2.line(saida, (cx, cy), (cx, cy + dy * canto), (210, 210, 210), 2)
    for (x, y, w, h) in retangulos:
        cv2.rectangle(saida, (x, y), (x + w, y + h), cor, 2)
    return saida


def avaliar_enquadramento(frame, retangulo):
    """Orienta sobre distância e centralização, ou None se está bom.

    O portão de qualidade mede nitidez, luz e ruído — não mede se a pessoa está
    perto demais ou fora do centro, que é justamente o que ela consegue corrigir
    na hora.
    """
    if retangulo is None:
        return None
    altura, largura = frame.shape[:2]
    _, _, lado, _ = moldura_alvo(frame)
    x, y, w, h = retangulo
    proporcao = w / lado
    if proporcao < 1 - TOLERANCIA_ALVO:
        return "Aproxime-se da câmera até o rosto preencher a moldura."
    if proporcao > 1 + TOLERANCIA_ALVO:
        return "Afaste-se um pouco: o rosto está maior que a moldura."
    centro_x, centro_y = x + w / 2, y + h / 2
    if abs(centro_x - largura / 2) > largura * 0.18:
        lado_texto = "direita" if centro_x < largura / 2 else "esquerda"
        return f"Centralize-se: mova-se para a sua {lado_texto}."
    if abs(centro_y - altura / 2) > altura * 0.18:
        return "Ajuste a altura: o rosto deve ficar no centro da moldura."
    return None
