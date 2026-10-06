"""Fases 4 e 5 — Extração (histograma LBP) e classificação (distância ao modelo).

LBPH DEVOLVE DISTÂNCIA, NÃO SIMILARIDADE: menor = mais parecido.
Aceitar quando distancia <= limiar. Inverter isso inverte a política inteira.

- identificar(face)            -> 1:N, compara com toda a galeria (nível 1)
- verificar(face, usuario_id)  -> 1:1, distância só contra a identidade informada (níveis 2 e 3)
- atualizar(...)               -> D-04, inclui identidade nova sem retreino global

O modelo é persistido cifrado (Fernet) — o .yml em texto claro só existe em
arquivo temporário durante a gravação/leitura.

DESEMPENHO (medido com 8 identidades x 80 amostras, a escala da base da ETP):

- Persistência em YAML texto custava ~2 s para gravar, ~1,8 s para ler e
  110-215 MB em disco: dez milhões de floats escritos como texto decimal. O
  OpenCV grava os mesmos dados em binário quando o nome termina em `?base64`, e
  comprime quando termina em `.gz`. Com os dois: ~0,8 s, ~0,9 s e ~10 MB, com
  os histogramas idênticos bit a bit. Modelos antigos, em texto, continuam
  sendo lidos — o formato é reconhecido pelos primeiros bytes.
- O 1:1 usava predict_collect, que mede a distância a TODAS as amostras da
  galeria para depois filtrar a identidade alegada: ~42 ms por quadro com 8
  pessoas e ~150 ms com 30, crescendo com cada cadastro. Agora a distância é
  calculada só contra as amostras do alegado, com a mesma fórmula do OpenCV
  (qui-quadrado alternativo): ~10 ms, constante. As distâncias coincidem com as
  do OpenCV até a 7ª casa significativa, então os limiares continuam valendo.
- O 1:N continua no predict do OpenCV: reproduzido em numpy, ficou mais lento
  (54 ms contra 41 ms), e otimizar à custa de exatidão não é opção aqui.
"""
import os
import tempfile
from pathlib import Path

import cv2
import numpy as np
from cryptography.fernet import Fernet

import configuracao

DISTANCIA_INFINITA = float("inf")

# assinatura do gzip: distingue o formato binário novo do YAML texto antigo
_GZIP = b"\x1f\x8b"


class ReconhecedorLBPH:
    def __init__(self, cfg=None):
        cfg = cfg or configuracao.carregar()
        grade_x, grade_y = cfg.gettupla("lbph", "grid")
        self._parametros = dict(radius=cfg.getint("lbph", "radius"),
                                neighbors=cfg.getint("lbph", "neighbors"),
                                grid_x=grade_x, grid_y=grade_y)
        self.modelo = cv2.face.LBPHFaceRecognizer_create(**self._parametros)
        # calcula o histograma de UMA face com os mesmos parâmetros do modelo,
        # sem tocar nele: treinar um reconhecedor de uma amostra só é a forma
        # que a API expõe de obter o histograma de uma imagem
        self._calculadora = cv2.face.LBPHFaceRecognizer_create(**self._parametros)
        self._por_rotulo = None          # cache dos histogramas, por identidade
        self.treinado = False

    # ------------------------------------------------------------ treino
    def treinar(self, faces, rotulos):
        self.modelo.train(list(faces), np.asarray(rotulos, dtype=np.int32))
        self._por_rotulo = None
        self.treinado = True

    def atualizar(self, faces, rotulos):
        if not self.treinado:
            return self.treinar(faces, rotulos)
        self.modelo.update(list(faces), np.asarray(rotulos, dtype=np.int32))
        self._por_rotulo = None

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

        A face é comparada só com as amostras da identidade alegada — as demais
        não interessam à pergunta "esta pessoa é quem diz ser?". Identidade sem
        amostras: inf (falha segura).
        """
        if not self.treinado:
            return DISTANCIA_INFINITA
        amostras = self._histogramas_de(usuario_id)
        if amostras is None:
            return DISTANCIA_INFINITA
        return float(qui_quadrado_alternativo(self._histograma(face), amostras).min())

    def _histograma(self, face):
        self._calculadora.train([face], np.array([0], dtype=np.int32))
        return self._calculadora.getHistograms()[0].reshape(-1).astype(np.float32, copy=False)

    def _histogramas_de(self, usuario_id):
        """Matriz (amostras x bins) da identidade, montada uma vez por modelo.

        getHistograms() copia a galeria inteira, então copiá-la a cada quadro
        anularia o ganho. O cache é invalidado em treinar/atualizar/carregar.
        """
        if self._por_rotulo is None:
            rotulos = np.asarray(self.modelo.getLabels()).ravel()
            todos = np.vstack([h.reshape(1, -1) for h in self.modelo.getHistograms()])
            todos = todos.astype(np.float32, copy=False)
            self._por_rotulo = {int(r): todos[rotulos == r] for r in np.unique(rotulos)}
        return self._por_rotulo.get(int(usuario_id))

    # ------------------------------------------------------------ persistência cifrada
    def salvar(self, caminho, chave):
        caminho = Path(caminho)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        fd, temporario = tempfile.mkstemp(suffix=".yml.gz", dir=caminho.parent)
        os.close(fd)
        try:
            # ?base64 grava as matrizes em binário; .gz comprime. Ver o topo.
            self.modelo.write(temporario + "?base64")
            dados = Path(temporario).read_bytes()
        finally:
            os.remove(temporario)
        caminho.write_bytes(Fernet(chave).encrypt(dados))

    def carregar(self, caminho, chave):
        dados = Fernet(chave).decrypt(Path(caminho).read_bytes())
        # o OpenCV escolhe o leitor pela extensão: .gz para o formato atual,
        # .yml para o texto puro dos modelos gravados antes desta otimização.
        # (O zlib até leria o texto puro por um nome .gz, porque o gzread aceita
        # entrada não comprimida — mas é um detalhe de biblioteca, não um contrato;
        # a escolha explícita não depende dele.)
        sufixo = ".yml.gz" if dados[:2] == _GZIP else ".yml"
        fd, temporario = tempfile.mkstemp(suffix=sufixo, dir=Path(caminho).parent)
        os.close(fd)
        try:
            Path(temporario).write_bytes(dados)
            self.modelo.read(temporario)
        finally:
            os.remove(temporario)
        self._por_rotulo = None
        self.treinado = True
        return self


def qui_quadrado_alternativo(consulta, amostras):
    """Distância do LBPH do OpenCV (HISTCMP_CHISQR_ALT) entre uma consulta e N amostras.

    2 · Σ (a − b)² / (a + b), ignorando os bins em que a + b = 0 — a mesma
    regra do compareHist. A soma final é acumulada em float64, como lá.
    """
    soma = amostras + consulta
    diferenca = amostras - consulta
    np.multiply(diferenca, diferenca, out=diferenca)
    # onde a + b = 0 os dois bins são zero (histogramas não têm valor negativo),
    # então (a − b)² já é 0 ali: basta não dividir
    np.divide(diferenca, soma, out=diferenca, where=soma > 0)
    return 2.0 * diferenca.sum(axis=1, dtype=np.float64)
