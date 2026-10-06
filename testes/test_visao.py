"""Pré-processamento, portão de qualidade e LBPH (1:N, 1:1, persistência cifrada)."""
import cv2
import numpy as np
from cryptography.fernet import Fernet

from visao.extracao import _GZIP, ReconhecedorLBPH
from visao.preprocessamento import PreProcessador
from visao.qualidade import PortaoQualidade, nitidez, ruido


def _textura(semente, ruido_px=0, tamanho=200):
    """'Face' sintética: padrão fixo por identidade + ruído por amostra."""
    base = cv2.resize(np.random.RandomState(semente).randint(40, 215, (60, 60)).astype(np.uint8),
                      (tamanho, tamanho), interpolation=cv2.INTER_CUBIC)
    if ruido_px:
        base = np.clip(base + np.random.normal(0, ruido_px, base.shape), 0, 255).astype(np.uint8)
    return base


def test_preprocessamento_normaliza_200x200_cinza():
    pre = PreProcessador()
    frame = np.random.randint(0, 255, (480, 640, 3), np.uint8)
    realcado = pre.realcar(frame)
    assert realcado.ndim == 2 and realcado.shape == (480, 640)
    face = pre.recortar_face(realcado, (100, 100, 150, 170))
    assert face.shape == (200, 200)


def test_recorte_fora_da_imagem_devolve_none():
    assert PreProcessador().recortar_face(np.zeros((100, 100), np.uint8), (200, 200, 10, 10)) is None


def test_portao_rejeita_desfocada_escura_e_multiplas():
    portao = PortaoQualidade()
    boa = _textura(1)
    assert portao.avaliar(boa).aprovado
    # borra e restaura o contraste: isola a nitidez (num rosto real o borrão não zera o contraste)
    desfocada = cv2.normalize(cv2.GaussianBlur(boa, (15, 15), 0), None, 20, 235, cv2.NORM_MINMAX)
    assert portao.avaliar(desfocada).motivo == "DESFOCADO"
    assert portao.avaliar((boa * 0.15).astype(np.uint8)).motivo == "ESCURO"
    assert portao.avaliar(None, n_faces=2).motivo == "MULTIPLAS_FACES"
    assert portao.avaliar(None, n_faces=0).motivo == "SEM_FACE"


def test_medidas_de_nitidez_e_ruido():
    boa = _textura(1)
    assert nitidez(boa) > nitidez(cv2.GaussianBlur(boa, (15, 15), 0))
    assert ruido(_textura(1, ruido_px=20)) > ruido(boa)


def _modelo():
    rec = ReconhecedorLBPH()
    faces, rotulos = [], []
    for ident in (1, 2, 3):
        for k in range(6):
            faces.append(_textura(ident, ruido_px=6))
            rotulos.append(ident)
    rec.treinar(faces, rotulos)
    return rec


def test_lbph_identifica_1_para_n():
    rec = _modelo()
    for ident in (1, 2, 3):
        rotulo, distancia = rec.identificar(_textura(ident, ruido_px=6))
        assert rotulo == ident and distancia >= 0


def test_lbph_verifica_1_para_1_com_menor_distancia_para_a_identidade_certa():
    rec = _modelo()
    amostra = _textura(2, ruido_px=6)
    assert rec.verificar(amostra, 2) < rec.verificar(amostra, 1)
    assert rec.verificar(amostra, 99) == float("inf")      # identidade sem amostras


def test_update_incremental_inclui_identidade_nova():
    rec = _modelo()
    rec.atualizar([_textura(4, ruido_px=6) for _ in range(6)], [4] * 6)
    assert rec.identificar(_textura(4, ruido_px=6))[0] == 4
    assert rec.rotulos_cadastrados() == {1, 2, 3, 4}


def test_sem_modelo_falha_segura():
    rec = ReconhecedorLBPH()
    assert rec.identificar(_textura(1)) == (None, float("inf"))
    assert rec.verificar(_textura(1), 1) == float("inf")


def test_modelo_cifrado_em_repouso(tmp_path):
    rec = _modelo()
    chave = Fernet.generate_key()
    caminho = tmp_path / "lbph.yml.enc"
    rec.salvar(caminho, chave)
    conteudo = caminho.read_bytes()
    assert b"opencv_lbphfaces" not in conteudo                  # nada em texto claro
    assert list(tmp_path.iterdir()) == [caminho]               # temporário removido
    outro = ReconhecedorLBPH().carregar(caminho, chave)
    amostra = _textura(3, ruido_px=6)
    assert outro.identificar(amostra) == rec.identificar(amostra)



# ------------------------------------------------------------------ otimizações do LBPH
def _verificar_como_antes(rec, face, usuario_id):
    """O 1:1 da versão anterior, mantido aqui como referência: mede contra a
    galeria inteira e filtra depois. A otimização só vale se der o MESMO número."""
    coletor = cv2.face.StandardCollector_create()
    rec.modelo.predict_collect(face, coletor)
    distancias = [d for rotulo, d in coletor.getResults() if rotulo == usuario_id]
    return min(distancias) if distancias else float("inf")


def test_1_para_1_otimizado_da_a_mesma_distancia_que_o_opencv():
    """Os limiares de [limiares] foram pensados para a distância do OpenCV.

    Se a conta otimizada divergisse, um usuário poderia passar a ser aceito ou
    recusado só por causa da troca de implementação — sem nenhuma mudança na
    face nem no limiar. A tolerância é de arredondamento de float32.
    """
    rec = _modelo()
    for ident in (1, 2, 3):
        for alegado in (1, 2, 3):
            face = _textura(ident, ruido_px=6)
            antes = _verificar_como_antes(rec, face, alegado)
            agora = rec.verificar(face, alegado)
            assert abs(agora - antes) <= 1e-4 * max(1.0, antes), (ident, alegado, antes, agora)


def test_cadastro_novo_aparece_no_1_para_1_sem_reiniciar():
    """O 1:1 guarda os histogramas em cache; um cadastro novo tem de invalidá-lo,
    senão a pessoa recém-cadastrada só seria reconhecida após reabrir o programa."""
    rec = _modelo()
    face = _textura(4, ruido_px=6)
    assert rec.verificar(face, 4) == float("inf")           # monta o cache sem a identidade 4
    rec.atualizar([_textura(4, ruido_px=6) for _ in range(6)], [4] * 6)
    assert rec.verificar(face, 4) < rec.verificar(face, 1)


def test_modelo_gravado_no_formato_texto_antigo_continua_abrindo(tmp_path):
    """Quem cadastrou rostos antes da otimização não pode perder o modelo:
    as faces já foram descartadas (LGPD), então não haveria como retreinar."""
    rec = _modelo()
    texto = tmp_path / "antigo.yml"
    rec.modelo.write(str(texto))                              # o formato de antes
    chave = Fernet.generate_key()
    cifrado = tmp_path / "lbph.yml.enc"
    cifrado.write_bytes(Fernet(chave).encrypt(texto.read_bytes()))
    texto.unlink()

    outro = ReconhecedorLBPH().carregar(cifrado, chave)
    amostra = _textura(2, ruido_px=6)
    assert outro.identificar(amostra) == rec.identificar(amostra)
    assert outro.verificar(amostra, 2) == rec.verificar(amostra, 2)


def test_modelo_novo_e_binario_comprimido_e_bem_menor(tmp_path):
    """O ganho da otimização, fixado em teste para não regredir em silêncio."""
    rec = _modelo()
    chave = Fernet.generate_key()
    novo = tmp_path / "novo.enc"
    rec.salvar(novo, chave)
    assert Fernet(chave).decrypt(novo.read_bytes())[:2] == _GZIP          # gzip

    texto = tmp_path / "texto.yml"
    rec.modelo.write(str(texto))
    assert len(Fernet(chave).decrypt(novo.read_bytes())) * 4 < texto.stat().st_size
