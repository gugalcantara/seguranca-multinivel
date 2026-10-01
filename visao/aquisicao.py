"""Fase 1 — Aquisição.

D-01: a captura roda numa thread dedicada e publica em uma fila de tamanho 1.
Quando chega frame novo e o anterior ainda não foi consumido, o antigo é
descartado. Assim o consumidor sempre recebe o frame mais recente e a latência
nunca se acumula, mesmo que o reconhecimento seja mais lento que a câmera.
"""
import queue
import threading

import cv2

import configuracao


class WebcamIndisponivel(RuntimeError):
    pass


class CapturaThread:
    def __init__(self, indice=None, largura=None, altura=None):
        cfg = configuracao.carregar()
        self.indice = cfg.getint("captura", "indice_camera") if indice is None else indice
        self.largura = largura or cfg.getint("captura", "largura")
        self.altura = altura or cfg.getint("captura", "altura")
        self.timeout = cfg.getfloat("captura", "timeout_leitura")
        self._fila = queue.Queue(maxsize=1)
        self._rodando = threading.Event()
        self._thread = None
        self._camera = None

    def iniciar(self):
        # CAP_DSHOW abre bem mais rápido que o backend padrão no Windows
        self._camera = cv2.VideoCapture(self.indice, cv2.CAP_DSHOW)
        if not self._camera.isOpened():
            self._camera = cv2.VideoCapture(self.indice)
        if not self._camera.isOpened():
            raise WebcamIndisponivel(f"Webcam no índice {self.indice} não abriu")
        self._camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.largura)
        self._camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.altura)
        self._rodando.set()
        self._thread = threading.Thread(target=self._laco, name="captura", daemon=True)
        self._thread.start()
        return self

    def _laco(self):
        while self._rodando.is_set():
            ok, frame = self._camera.read()
            if not ok:
                continue
            try:
                self._fila.get_nowait()   # descarta o frame velho
            except queue.Empty:
                pass
            self._fila.put_nowait(frame)

    def ler(self, timeout=None):
        """Frame BGR mais recente, ou None se a câmera parou de entregar."""
        try:
            return self._fila.get(timeout=timeout or self.timeout)
        except queue.Empty:
            return None

    def parar(self):
        self._rodando.clear()
        if self._thread:
            self._thread.join(timeout=2)
        if self._camera:
            self._camera.release()

    def __enter__(self):
        return self.iniciar()

    def __exit__(self, *_):
        self.parar()
