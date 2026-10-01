"""Cadastro facial a partir de ARQUIVOS de imagem (RF-01, alternativa à webcam).

O que se verifica: leitura do arquivo (inclusive com acento no nome, onde o
cv2.imread falha calado no Windows), redução de imagens grandes, e o laudo que
a tela usa para dizer POR QUE cada foto foi aceita ou recusada.

A detecção de rosto em si não é exercida aqui — exigiria fotos de pessoas, que
não entram no repositório (R-07). O pipeline é substituído por um dublê que
devolve análises controladas; o Haar e o portão já têm os seus testes em
test_visao.py.
"""
import cv2
import numpy as np
import pytest

from visao.coleta import ColetorAmostras, carregar_imagem, coletar_de_arquivos
from visao.qualidade import ResultadoQualidade


def _imagem(largura=640, altura=480, semente=0):
    return np.random.RandomState(semente).randint(0, 255, (altura, largura, 3), dtype=np.uint8)


def _gravar(caminho, imagem):
    ok, buf = cv2.imencode(".png", imagem)
    assert ok
    buf.tofile(str(caminho))        # tofile aceita caminho acentuado; imwrite não
    return caminho


# ------------------------------------------------------------------ leitura
def test_le_arquivo_com_acento_no_nome(tmp_path):
    """cv2.imread devolve None em caminho acentuado no Windows — por isso o
    carregar_imagem usa fromfile + imdecode."""
    caminho = _gravar(tmp_path / "fotografia-são-paulo-ação.png", _imagem())
    assert carregar_imagem(caminho) is not None


def test_reduz_imagem_grande_para_a_largura_maxima():
    grande = _imagem(largura=3024, altura=4032)          # retrato de celular
    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as d:
        caminho = _gravar(pathlib.Path(d) / "grande.png", grande)
        reduzida = carregar_imagem(caminho, largura_maxima=1280)
    assert reduzida.shape[1] == 1280
    assert reduzida.shape[0] == pytest.approx(4032 * 1280 / 3024, abs=2)   # proporção mantida


def test_imagem_pequena_nao_e_ampliada(tmp_path):
    caminho = _gravar(tmp_path / "pequena.png", _imagem(320, 240))
    assert carregar_imagem(caminho, largura_maxima=1280).shape[1] == 320


def test_arquivo_que_nao_e_imagem_devolve_none(tmp_path):
    texto = tmp_path / "nao_e_imagem.png"
    texto.write_text("isto é texto, não uma imagem", encoding="utf-8")
    assert carregar_imagem(texto) is None
    assert carregar_imagem(tmp_path / "inexistente.png") is None


# ------------------------------------------------------------------ laudo
class PipelineDuble:
    """Devolve a análise programada para cada chamada, na ordem."""

    class _Seg:
        def __init__(self):
            self.reinicios = 0

        def reiniciar(self):
            self.reinicios += 1

    def __init__(self, analises):
        self.analises = list(analises)
        self.segmentador = self._Seg()

    def analisar(self, imagem, reconhecer=True):
        return self.analises.pop(0)


class AnaliseDuble:
    def __init__(self, motivo="OK", aprovado=True, face=None, escore=0.8):
        self.qualidade = ResultadoQualidade(aprovado, motivo, "", escore=escore)
        self.face = face if face is not None else np.full((200, 200), 128, np.uint8)


def test_laudo_diz_o_motivo_de_cada_recusa(tmp_path):
    caminhos = [_gravar(tmp_path / f"f{i}.png", _imagem(semente=i)) for i in range(3)]
    pipeline = PipelineDuble([
        AnaliseDuble(face=np.full((200, 200), 10, np.uint8)),
        AnaliseDuble("DESFOCADO", aprovado=False, escore=0.1),
        AnaliseDuble("MULTIPLAS_FACES", aprovado=False, escore=0.0),
    ])
    coletor = ColetorAmostras(1, alvo=3, minimo=1)
    laudos = coletar_de_arquivos(caminhos, pipeline, coletor)

    assert [(l[1], l[2]) for l in laudos] == [
        (True, "OK"), (False, "DESFOCADO"), (False, "MULTIPLAS_FACES")]
    assert len(coletor.faces) == 1


def test_foto_quase_identica_e_recusada_como_duplicata(tmp_path):
    """Duplicata reprova no coletor, não no portão: o motivo não pode sair 'OK'."""
    caminhos = [_gravar(tmp_path / f"d{i}.png", _imagem(semente=i)) for i in range(2)]
    iguais = np.full((200, 200), 128, np.uint8)
    pipeline = PipelineDuble([AnaliseDuble(face=iguais), AnaliseDuble(face=iguais.copy())])
    coletor = ColetorAmostras(1, alvo=2, minimo=1)
    laudos = coletar_de_arquivos(caminhos, pipeline, coletor)

    assert laudos[0][1] is True
    assert (laudos[1][1], laudos[1][2]) == (False, "DUPLICATA")
    assert len(coletor.faces) == 1


def test_arquivo_ilegivel_entra_no_laudo_sem_derrubar_o_lote(tmp_path):
    ruim = tmp_path / "quebrado.png"
    ruim.write_text("não é imagem", encoding="utf-8")
    bom = _gravar(tmp_path / "bom.png", _imagem(semente=9))
    pipeline = PipelineDuble([AnaliseDuble(face=np.full((200, 200), 77, np.uint8))])
    coletor = ColetorAmostras(1, alvo=2, minimo=1)
    laudos = coletar_de_arquivos([ruim, bom], pipeline, coletor)

    assert (laudos[0][1], laudos[0][2]) == (False, "ILEGIVEL")
    assert laudos[1][1] is True
    assert len(coletor.faces) == 1


def test_rastreador_e_reiniciado_a_cada_arquivo(tmp_path):
    """Sem reiniciar, o KCF da foto anterior devolveria a ROI da pessoa errada."""
    caminhos = [_gravar(tmp_path / f"r{i}.png", _imagem(semente=i)) for i in range(3)]
    pipeline = PipelineDuble([AnaliseDuble(face=np.full((200, 200), 20 * i, np.uint8))
                              for i in range(1, 4)])
    coletar_de_arquivos(caminhos, pipeline, ColetorAmostras(1, alvo=3, minimo=1))
    assert pipeline.segmentador.reinicios == 3


def test_coletor_aceita_limites_proprios_para_imagens():
    """O cadastro por arquivo não pode herdar as 40 capturas da webcam."""
    padrao = ColetorAmostras(1)
    assert (padrao.alvo, padrao.minimo) == (40, 30)
    por_imagem = ColetorAmostras(1, alvo=6, minimo=1)
    assert (por_imagem.alvo, por_imagem.minimo) == (6, 1)
