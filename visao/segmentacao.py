"""Fase 3 — Segmentação.

Haar Cascade (Viola-Jones) localiza e recorta a ROI da face.
D-02: o Haar roda a cada N frames; entre duas detecções, o KCF acompanha a ROI,
que custa uma fração da detecção e estabiliza o recorte.
"""
import cv2

import configuracao


def _criar_kcf():
    if hasattr(cv2, "TrackerKCF_create"):
        return cv2.TrackerKCF_create()
    return cv2.legacy.TrackerKCF_create()


class DetectorFacial:
    def __init__(self, cfg=None):
        cfg = cfg or configuracao.carregar()
        caminho = cv2.data.haarcascades + cfg.get("haar", "arquivo")
        self.classificador = cv2.CascadeClassifier(caminho)
        if self.classificador.empty():
            raise RuntimeError(f"Haar Cascade não carregou: {caminho}")
        self.scale_factor = cfg.getfloat("haar", "scale_factor")
        self.min_neighbors = cfg.getint("haar", "min_neighbors")
        self.min_size = cfg.gettupla("haar", "min_size")

    def detectar(self, cinza):
        faces = self.classificador.detectMultiScale(
            cinza, scaleFactor=self.scale_factor,
            minNeighbors=self.min_neighbors, minSize=self.min_size,
        )
        return [tuple(int(v) for v in f) for f in faces]


class SegmentadorRastreado:
    """Combina detecção periódica e rastreamento KCF.

    segmentar() devolve a lista de retângulos do frame atual. Com exatamente
    uma face, o rastreador é (re)inicializado; com zero ou várias, o
    rastreamento é descartado e quem chama trata o caso (EXC-02: uma pessoa por vez).
    """

    def __init__(self, detector=None, cfg=None):
        cfg = cfg or configuracao.carregar()
        self.detector = detector or DetectorFacial(cfg)
        self.detectar_a_cada = cfg.getint("rastreamento", "detectar_a_cada")
        self._contador = 0
        self._rastreador = None

    def segmentar(self, frame_bgr, cinza):
        usar_rastreio = self._rastreador is not None and self._contador % self.detectar_a_cada != 0
        self._contador += 1
        if usar_rastreio:
            ok, caixa = self._rastreador.update(frame_bgr)
            if ok:
                return [tuple(int(v) for v in caixa)]
            self._rastreador = None

        faces = self.detector.detectar(cinza)
        if len(faces) == 1:
            self._rastreador = _criar_kcf()
            self._rastreador.init(frame_bgr, faces[0])
        else:
            self._rastreador = None
        return faces

    def reiniciar(self):
        self._contador = 0
        self._rastreador = None
