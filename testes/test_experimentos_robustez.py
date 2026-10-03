"""Experimentos de robustez da marca d'água e do inspetor (ETP 7.1 e 7.2).

Os testes fixam as CONCLUSÕES medidas, não apenas a execução dos scripts: se
amanhã alguém mexer no DCT e ele parar de resistir ao JPEG, o capítulo de
resultados fica errado — e é melhor descobrir aqui.
"""
from datetime import datetime

import numpy as np
import pytest

import configuracao
from acervo import marca_dagua
from experimentos import inspecao_pares, marca


@pytest.fixture(scope="module")
def imagem():
    imagens = marca.imagens_do_acervo(1)
    if not imagens:
        pytest.skip("acervo não gerado: rode python -m ferramentas gerar-acervo")
    return imagens[0][1]


MOMENTO = datetime(2026, 10, 1, 14, 30, 5)


# ------------------------------------------------------------------ marca d'água
def test_dct_resiste_a_recompressao_jpeg(imagem):
    """Meta da ETP 7.1: ≥ 90% de recuperação sob recompressão JPEG."""
    marcada = marca_dagua.inserir_dct(imagem, 4242, MOMENTO)
    for qualidade in (95, 85, 75, 60, 50):
        degradada = marca._jpeg(marcada, qualidade)
        assert marca_dagua.extrair_dct(degradada) == (4242, MOMENTO), f"falhou em q={qualidade}"


def test_lsb_nao_resiste_a_jpeg(imagem):
    """Resultado esperado, não defeito: o JPEG descarta justamente o bit menos
    significativo. É o contraponto que justifica o DCT (risco R-09)."""
    marcada = marca_dagua.inserir_lsb(imagem, 4242, MOMENTO)
    assert marca_dagua.extrair_lsb(marcada) == (4242, MOMENTO)       # intacta, recupera
    assert marca_dagua.extrair_lsb(marca._jpeg(marcada, 95)) is None  # recomprimida, não


def test_recorte_derruba_os_dois_metodos(imagem):
    """A marca depende da grade 8×8; recortar desloca os blocos.

    Limite declarado do método — e o motivo de a exportação do N3 ser bloqueada
    em vez de apenas marcada.
    """
    for inserir, extrair in ((marca_dagua.inserir_lsb, marca_dagua.extrair_lsb),
                             (marca_dagua.inserir_dct, marca_dagua.extrair_dct)):
        marcada = inserir(imagem, 4242, MOMENTO)
        assert extrair(marca._recortar(marcada, 0.90)) is None


def test_dct_sobrevive_a_captura_de_tela(imagem):
    """Capturar a tela é o contorno óbvio do bloqueio de exportação; a marca
    precisa sobreviver a ele para que o rastreio tenha valor."""
    marcada = marca_dagua.inserir_dct(imagem, 777, MOMENTO)
    assert marca_dagua.extrair_dct(marca._captura_de_tela(marcada)) == (777, MOMENTO)


def test_experimento_cobre_as_degradacoes_que_a_etp_exige():
    nomes = " ".join(nome for nome, _ in marca.DEGRADACOES).lower()
    assert nomes.count("jpeg") >= 3          # "três qualidades"
    assert "redimensionar" in nomes
    assert "recorte" in nomes
    assert "captura de tela" in nomes


def test_avaliacao_produz_taxa_por_metodo_e_degradacao(imagem):
    linhas = marca.avaliar(repeticoes=3, imagens=[("teste", imagem)])
    assert len(linhas) == len(marca.METODOS) * len(marca.DEGRADACOES)
    assert all(0.0 <= l["taxa"] <= 1.0 for l in linhas)
    sem_degradacao = [l for l in linhas if l["degradacao"] == "sem degradação"]
    assert all(l["taxa"] == 1.0 for l in sem_degradacao)    # sem degradar, tudo recupera


# ------------------------------------------------------------------ inspeção
def test_pares_vem_metade_alterados():
    """Medir só sensibilidade esconde o detector que acusa tudo."""
    pares = inspecao_pares.gerar_pares(20)
    assert len(pares) == 20
    assert sum(p["alterado"] for p in pares) == 10


def test_inspetor_atinge_a_meta_da_etp():
    """ETP 7.1: detecção ≥ 90%, sem inventar alteração onde não há."""
    resumo = inspecao_pares.resumir(inspecao_pares.avaliar(inspecao_pares.gerar_pares(20)))
    assert resumo["sensibilidade"] >= 0.90, f"abaixo da meta: {resumo['sensibilidade']:.1%}"
    assert resumo["falso_positivo"] <= 0.10, f"acusa demais: {resumo['falso_positivo']:.1%}"
    assert resumo["alinhamento"] == 1.0      # ORB absorve o tremor de câmera


def test_quem_detecta_e_a_analise_de_regioes_nao_o_ssim():
    """Achado do experimento, fixado aqui para não se perder.

    O SSIM é uma MÉDIA sobre a imagem inteira: um lacre rompido quase não o move
    (0,98 contra limiar de 0,90). Quem acusa é a limiarização das regiões. O
    limiar de SSIM, como está, só pegaria degradação do quadro todo — e isso
    precisa estar no relatório, não escondido atrás da acurácia de 100%.
    """
    linhas = inspecao_pares.avaliar(inspecao_pares.gerar_pares(20))
    resumo = inspecao_pares.resumir(linhas)
    assert resumo["detecoes_por_regiao"] == 10
    assert resumo["detecoes_por_ssim"] == 0
    assert resumo["ssim_alterados"] > resumo["limiar_ssim"]


def test_tremor_de_camera_nao_conta_como_alteracao():
    """O alinhamento ORB existe para isto: deslocamento não é violação."""
    linhas = inspecao_pares.avaliar(inspecao_pares.gerar_pares(20))
    integros = [l for l in linhas if not l["alterado"]]
    assert all(not l["detectado"] for l in integros)
    assert all(l["regioes"] == 0 for l in integros)


def test_tipos_de_alteracao_sao_variados():
    """Um só tipo de violação não mede detector nenhum."""
    tipos = {p["tipo"] for p in inspecao_pares.gerar_pares(20) if p["alterado"]}
    assert len(tipos) >= 4
