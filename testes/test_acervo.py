"""Tarja (RF-09, RF-10), entrega (RF-18), marca d'água (RF-11) e inspeção (RF-16)."""
from datetime import datetime

import cv2
import numpy as np
import pytest

from acervo import marca_dagua
from acervo.entrega import preparar_imagem
from acervo.gerar_exemplos import _tambores
from acervo.inspecao import inspecionar
from acervo.tarja import AcessoNegado, Regiao, aplicar_tarja, autorizar_item
from acervo.texto import escrever

MOMENTO = datetime(2026, 10, 1, 14, 30, 5)


def _documento():
    img = np.full((480, 640, 3), 250, np.uint8)
    linhas = [(30, 40 + 28 * i, f"Linha {i:02d} — Gerador: Empresa Fictícia {i} Ltda., 12,5 t") for i in range(14)]
    return escrever(img, linhas, tamanho=18)


REGIOES = [Regiao(30, 40, 400, 26, nivel_minimo=2, rotulo="RESPONSAVEL"),
           Regiao(30, 96, 400, 26, nivel_minimo=3, rotulo="CUSTODIA")]


def _variancia(img, r):
    return float(img[r.y:r.y + r.altura, r.x:r.x + r.largura].var())


# ------------------------------------------------------------------ tarja
def test_tarja_por_nivel():
    doc = _documento()
    n1, n2, n3 = (aplicar_tarja(doc, REGIOES, n) for n in (1, 2, 3))
    assert _variancia(n1, REGIOES[0]) < _variancia(doc, REGIOES[0]) / 5      # N1 não vê responsável
    assert np.array_equal(n2[40:66, 30:430], doc[40:66, 30:430])             # N2 vê responsável
    assert _variancia(n2, REGIOES[1]) < _variancia(doc, REGIOES[1]) / 5      # N2 não vê custódia
    assert np.array_equal(n3, doc)                                           # N3 vê tudo


def test_tarja_nao_altera_o_original_nem_fora_da_regiao():
    doc = _documento()
    copia = doc.copy()
    saida = aplicar_tarja(doc, REGIOES, 1)
    assert np.array_equal(doc, copia)
    assert np.array_equal(saida[200:], doc[200:])


def test_item_sem_regioes_revisadas_so_no_n3():
    with pytest.raises(AcessoNegado):
        autorizar_item(1, False, 2)
    autorizar_item(1, False, 3)
    with pytest.raises(AcessoNegado):
        autorizar_item(3, True, 2)


# ------------------------------------------------------------------ entrega
ITEM = {"nivel_minimo": 1, "regioes_revisadas": True, "sintetico": True}


def test_entrega_aplica_supressao_antes_da_interface():
    """RF-10: o objeto entregue já tem os pixels suprimidos."""
    entregue = preparar_imagem(_documento(), ITEM, REGIOES, 1)
    assert _variancia(entregue, REGIOES[0]) < _variancia(_documento(), REGIOES[0]) / 5


def test_entrega_carimba_conteudo_sintetico():
    entregue = preparar_imagem(_documento(), ITEM, [], 1)
    faixa = entregue[26:29, :, :]                       # abaixo do texto, dentro da faixa
    assert faixa[:, :, 2].mean() > 150 and faixa[:, :, 0].mean() < 80   # vermelha


def test_entrega_n2_leva_marca_dagua_recuperavel():
    entregue = preparar_imagem(_documento(), ITEM, REGIOES, 2, usuario_id=42, momento=MOMENTO)
    metodo, usuario, momento = marca_dagua.extrair(entregue)
    assert (usuario, momento) == (42, MOMENTO)


def test_entrega_n2_sem_identidade_e_negada():
    with pytest.raises(AcessoNegado):
        preparar_imagem(_documento(), ITEM, REGIOES, 2)


# ------------------------------------------------------------------ marca d'água
def _jpeg(img, qualidade):
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, qualidade])
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def test_carga_util_e_crc():
    bits = marca_dagua.montar_carga(123456, MOMENTO)
    assert len(bits) == marca_dagua.BITS
    assert marca_dagua.interpretar_carga(bits) == (123456, MOMENTO)
    bits[3] ^= 1
    assert marca_dagua.interpretar_carga(bits) is None


def test_lsb_exato_mas_fragil_a_jpeg():
    doc = _documento()
    marcada = marca_dagua.inserir_lsb(doc, 7, MOMENTO)
    assert np.abs(marcada.astype(int) - doc.astype(int)).max() <= 1          # invisível
    assert marca_dagua.extrair_lsb(marcada) == (7, MOMENTO)
    assert marca_dagua.extrair_lsb(_jpeg(marcada, 90)) is None               # frágil (R-09)


@pytest.mark.parametrize("qualidade", [95, 85, 75])
def test_dct_resiste_a_recompressao_jpeg(qualidade):
    marcada = marca_dagua.inserir_dct(_documento(), 7, MOMENTO)
    assert marca_dagua.extrair_dct(_jpeg(marcada, qualidade)) == (7, MOMENTO)


def test_dct_sem_marca_nao_inventa_identidade():
    assert marca_dagua.extrair_dct(_documento()) is None


# ------------------------------------------------------------------ inspeção
def test_inspecao_ignora_deslocamento_de_camera():
    fundo = np.full((640, 900, 3), 250, np.uint8)
    r = inspecionar(_tambores(fundo.copy()), _tambores(fundo.copy(), deslocamento=(12, -8), angulo=1.5))
    assert r.alinhado and not r.alterado


def test_inspecao_detecta_lacre_rompido():
    fundo = np.full((640, 900, 3), 250, np.uint8)
    r = inspecionar(_tambores(fundo.copy()),
                    _tambores(fundo.copy(), deslocamento=(12, -8), angulo=1.5, lacre_rompido=True))
    assert r.alterado and len(r.regioes) >= 1
    x, y, w, h = r.regioes[0]
    assert 440 < x + w / 2 < 520 and 170 < y + h / 2 < 230      # lacre do tambor do meio


# ------------------------------------------------------------------ RF-20: sem localização no N1
def _mapa_e_regioes():
    """Carrega o A1-05 real do acervo e as regiões declaradas no metadados.json."""
    import json
    from pathlib import Path
    import configuracao
    dados = json.loads(configuracao.caminho("acervo_metadados").read_text(encoding="utf-8"))
    item = next(i for i in dados["itens"] if i["codigo"] == "A1-05")
    imagem = cv2.imread(str(configuracao.caminho("acervo") / item["arquivo"]))
    regioes = [Regiao(r["x"], r["y"], r["largura"], r["altura"], r["nivel_minimo"], r.get("rotulo"))
               for r in item["regioes"]]
    return imagem, regioes


def test_nivel_1_nao_enxerga_a_distribuicao_geografica_do_mapa():
    """RF-20: suprimir só os rótulos deixaria a localização visível na FORMA do gráfico.

    Os pontos plotados revelam a posição aproximada mesmo sem as coordenadas
    escritas ao lado — por isso a área de plotagem inteira é sensível.
    """
    mapa, regioes = _mapa_e_regioes()
    assert mapa is not None, "acervo não gerado: rode python -m ferramentas gerar-acervo"
    assert any(r.rotulo == "DISTRIBUICAO_GEOGRAFICA" for r in regioes)

    area = next(r for r in regioes if r.rotulo == "DISTRIBUICAO_GEOGRAFICA")
    custodia = next(r for r in regioes if r.rotulo == "CUSTODIA")
    n1 = aplicar_tarja(mapa, regioes, 1)
    n2 = aplicar_tarja(mapa, regioes, 2)
    # faixa dentro da área de plotagem e ACIMA da custódia, que é nível 3 e
    # continua suprimida no nível 2 — comparar a área inteira misturaria as duas regras
    faixa = (slice(area.y, custodia.y - 10), slice(area.x, area.x + area.largura))

    assert _variancia(n1, area) < _variancia(mapa, area) / 5   # N1: vira borrão
    assert np.array_equal(n2[faixa], mapa[faixa])              # N2: chega intacta
    assert _variancia(n2, custodia) < _variancia(mapa, custodia) / 5   # ...menos a custódia


def test_titulo_do_mapa_continua_legivel_no_nivel_1():
    """Suprimir a área não pode esconder o que o item É: o N1 precisa saber que
    existe um mapa de densidade ao qual ele não tem acesso."""
    mapa, regioes = _mapa_e_regioes()
    n1 = aplicar_tarja(mapa, regioes, 1)
    faixa_do_titulo = (slice(30, 90), slice(0, mapa.shape[1]))
    assert np.array_equal(n1[faixa_do_titulo], mapa[faixa_do_titulo])


def test_supressao_de_posicao_nao_deixa_residuo_localizavel():
    """O borrão gaussiano preserva o CENTROIDE: medindo o resíduo de cor do mapa
    borrado, o pico caía exatamente sobre um ponto original (0 px de distância).

    Para texto o gaussiano basta — o conteúdo fica ilegível. Para posição não:
    a informação está na forma, não nos caracteres. Daí a supressão total para
    rótulos de área, e este teste exige que a região fique sem estrutura alguma.
    """
    mapa, regioes = _mapa_e_regioes()
    area = next(r for r in regioes if r.rotulo == "DISTRIBUICAO_GEOGRAFICA")
    n1 = aplicar_tarja(mapa, regioes, 1)
    recorte = n1[area.y:area.y + area.altura, area.x:area.x + area.largura]
    assert float(recorte.var()) == 0.0, "sobrou estrutura na área suprimida"


def test_texto_continua_com_supressao_borrada():
    """A supressão total é só para os rótulos de posição; o texto segue borrado,
    que preserva a diagramação da página e já o torna ilegível."""
    doc = _documento()
    suprimido = aplicar_tarja(doc, REGIOES, 1)
    assert _variancia(suprimido, REGIOES[0]) < _variancia(doc, REGIOES[0]) / 5
    assert float(suprimido[40:66, 30:430].var()) > 0.0      # não virou bloco sólido



# ------------------------------------------------------------------ nível 2 sem UF (auditoria)
class _RepoUmItem:
    """Repositório mínimo: um item regional de SP, sem regiões sensíveis."""

    def __init__(self, uf_item):
        self.uf_item = uf_item
        self.sqls = []

    def item(self, item_id):
        return {"id": 1, "codigo": "A2-01", "titulo": "x", "arquivo": "a2-01.png",
                "nivel_minimo": 2, "regioes_revisadas": True, "sintetico": True, "uf": self.uf_item}

    def regioes(self, item_id):
        return []

    def consultar(self, sql, parametros=()):
        self.sqls.append((" ".join(sql.split()), list(parametros)))
        return []


class _TrilhaMuda:
    def __init__(self):
        self.registros = []

    def registrar(self, r):
        self.registros.append(r)


def test_diretor_sem_uf_nao_abre_item_regional():
    """Antes, "and sessao.uf" pulava a checagem: sem UF, abria-se qualquer região."""
    from acervo.entrega import ServicoAcervo
    from autenticacao.motor import SessaoAutenticada
    servico = ServicoAcervo(_RepoUmItem("SP"), _TrilhaMuda())
    with pytest.raises(AcessoNegado):
        servico.abrir(SessaoAutenticada(1, "Sem região", 2, None, datetime.now()), 1)


def test_listagem_do_nivel_2_sempre_filtra_a_regiao():
    """Com ou sem UF, o SQL do N2 carrega o filtro regional."""
    from acervo.repositorio_acervo import RepositorioAcervo
    banco = _RepoUmItem(None)
    repo = RepositorioAcervo(banco)
    for uf in ("SP", None):
        repo.itens_para_nivel(2, uf)
    assert all("uf = %s" in sql for sql, _ in banco.sqls)
    assert banco.sqls[1][1][-1] is None          # sem UF, compara com NULL: nunca casa
