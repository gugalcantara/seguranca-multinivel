"""Fases 4 e 5 — Extração (histograma LBP) e classificação (distância ao modelo).

LBPH DEVOLVE DISTÂNCIA, NÃO SIMILARIDADE: menor = mais parecido.
Aceitar quando distancia <= limiar. Inverter isso inverte a política inteira.

- identificar(face)            -> 1:N, compara com toda a galeria (nível 1)
- verificar(face, usuario_id)  -> 1:1, distância só contra a identidade informada (níveis 2 e 3)
- atualizar(...)               -> D-04, inclui identidade nova sem retreino global

O modelo é persistido cifrado (Fernet) — o .yml em texto claro só existe em
arquivo temporário durante a gravação/leitura.
"""
import os
import tempfile
from pathlib import Path

import cv2
import numpy as np
from cryptography.fernet import Fernet

import configuracao

DISTANCIA_INFINITA = float("inf")


class ReconhecedorLBPH:
    def __init__(self, cfg=None):
        cfg = cfg or configuracao.carregar()
        grade_x, grade_y = cfg.gettupla("lbph", "grid")
        self.modelo = cv2.face.LBPHFaceRecognizer_create(
            radius=cfg.getint("lbph", "radius"),
            neighbors=cfg.getint("lbph", "neighbors"),
            grid_x=grade_x, grid_y=grade_y,
        )
        self.treinado = False

    # ------------------------------------------------------------ treino
    def treinar(self, faces, rotulos):
        self.modelo.train(list(faces), np.asarray(rotulos, dtype=np.int32))
        self.treinado = True

    def atualizar(self, faces, rotulos):
        if not self.treinado:
            return self.treinar(faces, rotulos)
        self.modelo.update(list(faces), np.asarray(rotulos, dtype=np.int32))

    def rotulos_cadastrados(self):
        if not self.treinado:
            return set()
        return {int(r) for r in np.asarray(self.modelo.getLabels()).ravel()}

    # ------------------------------------------------------------ decisão
    def identificar(self, face):
        """1:N -> (usuario_id, distancia). Sem modelo: (None, inf) — falha segura."""
        if not self.treinado:
            return None, DISTANCIA_INFINITA
        rotulo, distancia = self.modelo.predict(face)
        return int(rotulo), float(distancia)

    def verificar(self, face, usuario_id):
        """1:1 -> menor distância entre a face e as amostras de usuario_id.

        Usa o StandardCollector para obter a distância a todas as amostras e
        filtra pela identidade informada. Identidade sem amostras: inf.
        """
        if not self.treinado:
            return DISTANCIA_INFINITA
        coletor = cv2.face.StandardCollector_create()
        self.modelo.predict_collect(face, coletor)
        distancias = [d for rotulo, d in coletor.getResults() if rotulo == usuario_id]
        return float(min(distancias)) if distancias else DISTANCIA_INFINITA

    # ------------------------------------------------------------ persistência cifrada
    def salvar(self, caminho, chave):
        caminho = Path(caminho)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        fd, temporario = tempfile.mkstemp(suffix=".yml", dir=caminho.parent)
        os.close(fd)
        try:
            self.modelo.write(temporario)
            dados = Path(temporario).read_bytes()
        finally:
            os.remove(temporario)
        caminho.write_bytes(Fernet(chave).encrypt(dados))

    def carregar(self, caminho, chave):
        dados = Fernet(chave).decrypt(Path(caminho).read_bytes())
        fd, temporario = tempfile.mkstemp(suffix=".yml", dir=Path(caminho).parent)
        os.close(fd)
        try:
            Path(temporario).write_bytes(dados)
            self.modelo.read(temporario)
        finally:
            os.remove(temporario)
        self.treinado = True
        return self
