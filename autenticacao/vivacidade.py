"""Prova de vivacidade por desafio-resposta aleatório (nível 3, RF-07).

O desafio é sorteado na hora, então uma fotografia ou vídeo pré-gravado não
sabe o que responder. Desafios implementados:

- PISCAR: olhos (Haar de olhos na metade superior da face) somem por alguns
  frames e reaparecem.
- MOVER_ESQUERDA / MOVER_DIREITA: o centro da face se desloca horizontalmente
  uma fração mínima da largura do rosto, no sentido pedido.

Limitação declarada (EXC-06): não é anti-spoofing robusto. Um vídeo da pessoa
fazendo o gesto certo passaria. O objetivo é barrar apresentação estática.

Nota: o frame da webcam NÃO é espelhado aqui. "Esquerda" é a esquerda do
usuário, que aparece à DIREITA na imagem crua — por isso o sinal é invertido.
"""
import random
import time
from enum import Enum

import cv2

import configuracao


class Estado(str, Enum):
    EM_ANDAMENTO = "EM_ANDAMENTO"
    CONFIRMADO = "CONFIRMADO"
    EXPIRADO = "EXPIRADO"


INSTRUCOES = {
    "PISCAR": "Pisque os olhos devagar.",
    "MOVER_ESQUERDA": "Mova o rosto para a SUA esquerda.",
    "MOVER_DIREITA": "Mova o rosto para a SUA direita.",
}


class DesafioVivacidade:
    def __init__(self, cfg=None, rng=None, relogio=time.monotonic):
        cfg = cfg or configuracao.carregar()
        self.desafios = cfg.getlista("vivacidade", "desafios")
        self.timeout = cfg.getfloat("vivacidade", "timeout")
        self.deslocamento_minimo = cfg.getfloat("vivacidade", "deslocamento_minimo")
        self.frames_olho_fechado = cfg.getint("vivacidade", "frames_olho_fechado")
        self.fracao_minima_visivel = cfg.getfloat("vivacidade", "fracao_minima_rosto_visivel")
        self._olhos = cv2.CascadeClassifier(cv2.data.haarcascades + cfg.get("haar", "arquivo_olhos"))
        self._rng = rng or random.SystemRandom()
        self._relogio = relogio
        self.desafio = None

    def sortear(self):
        self.desafio = self._rng.choice(self.desafios)
        self._inicio = self._relogio()
        self._centro_inicial = None
        self._viu_olhos_abertos = False
        self._frames_sem_olhos = 0
        self._piscou = False
        return self.desafio

    @property
    def instrucao(self):
        return INSTRUCOES.get(self.desafio, "")

    def alimentar(self, cinza, retangulo_face):
        """Recebe o frame atual (cinza) e a face; devolve o Estado do desafio."""
        if self.desafio is None:
            raise RuntimeError("Chame sortear() antes de alimentar()")
        if self._relogio() - self._inicio > self.timeout:
            return Estado.EXPIRADO
        if retangulo_face is None:
            return Estado.EM_ANDAMENTO
        if self.desafio == "PISCAR":
            return self._avaliar_piscada(cinza, retangulo_face)
        return self._avaliar_movimento(retangulo_face)

    def _metade_superior(self, cinza, rf):
        """Recorte dos olhos limitado à imagem, ou None se o rosto saiu do quadro.

        Sem este limite, um retângulo com coordenada negativa — o KCF devolve
        isso quando a pessoa encosta na borda — produz uma fatia VAZIA, e o Haar
        responde "nenhum olho" sem erro algum. A piscada seria dada como vista, e
        bastaria sair de cena para cumprir o desafio do nível 3.
        """
        x, y, w, h = rf
        altura, largura = cinza.shape[:2]
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(largura, x + w), min(altura, y + h // 2)
        if x1 <= x0 or y1 <= y0:
            return None
        esperado = max(1, w) * max(1, h // 2)
        if (x1 - x0) * (y1 - y0) < self.fracao_minima_visivel * esperado:
            return None            # rosto cortado demais para concluir qualquer coisa
        return cinza[y0:y1, x0:x1]

    def _avaliar_piscada(self, cinza, rf):
        x, _, w, _ = rf
        metade_superior = self._metade_superior(cinza, rf)
        if metade_superior is None:
            return Estado.EM_ANDAMENTO     # inconclusivo não é piscada
        olhos = self._olhos.detectMultiScale(metade_superior, 1.1, 5, minSize=(w // 10, w // 10))
        if len(olhos) >= 1:
            if self._frames_sem_olhos >= self.frames_olho_fechado and self._viu_olhos_abertos:
                return Estado.CONFIRMADO          # abriu -> fechou -> abriu
            self._viu_olhos_abertos = True
            self._frames_sem_olhos = 0
        elif self._viu_olhos_abertos:
            self._frames_sem_olhos += 1
        return Estado.EM_ANDAMENTO

    def _avaliar_movimento(self, rf):
        x, _, w, _ = rf
        centro = x + w / 2
        if self._centro_inicial is None:
            self._centro_inicial = centro
            return Estado.EM_ANDAMENTO
        deslocamento = (centro - self._centro_inicial) / w   # >0 = direita da imagem
        # imagem não espelhada: esquerda do usuário = direita da imagem
        esperado = 1 if self.desafio == "MOVER_ESQUERDA" else -1
        if deslocamento * esperado >= self.deslocamento_minimo:
            return Estado.CONFIRMADO
        return Estado.EM_ANDAMENTO
