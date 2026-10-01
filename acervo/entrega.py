"""Pipeline do acervo: entrada -> supressão -> carimbo -> marcação -> entrega/exportação.

Toda consulta e toda exportação entram na trilha encadeada (RF-12, S-07).
Política de exportação (RF-14): N1 livre; N2 com marca d'água; N3 não exporta.
"""
from datetime import datetime

import cv2

import configuracao
from acervo import marca_dagua
from acervo.tarja import AcessoNegado, aplicar_tarja, autorizar_item
from acervo.texto import carimbar_ficticio
from dados.auditoria import novo_registro

POLITICA_EXPORTACAO = {1: "LIVRE", 2: "COM_MARCA_DAGUA", 3: "BLOQUEADA"}


def preparar_imagem(imagem, item, regioes, nivel, usuario_id=None, momento=None, cfg=None):
    """Função pura do pipeline — o que sai daqui é exatamente o que a UI recebe."""
    autorizar_item(item["nivel_minimo"], item["regioes_revisadas"], nivel)
    saida = aplicar_tarja(imagem, regioes, nivel, cfg)
    if item["sintetico"]:
        saida = carimbar_ficticio(saida)
    if nivel >= 2:
        if usuario_id is None:
            raise AcessoNegado("Entrega de nível 2+ exige identidade para a marca d'água")
        saida = marca_dagua.inserir(saida, usuario_id, momento or datetime.now(), cfg=cfg)
    return saida


class ServicoAcervo:
    def __init__(self, repositorio, trilha, cfg=None):
        self.repo = repositorio
        self.trilha = trilha
        self.cfg = cfg or configuracao.carregar()

    def listar(self, sessao):
        return self.repo.itens_para_nivel(sessao.nivel, sessao.uf)

    def abrir(self, sessao, item_id):
        """Imagem já tratada para o nível da sessão. Registra CONSULTA."""
        sessao.exigir_valida()
        item = self.repo.item(item_id)
        momento = datetime.now()
        try:
            if item is None:
                raise AcessoNegado("Item inexistente")
            if sessao.nivel == 2 and item["uf"] and sessao.uf and item["uf"] != sessao.uf:
                raise AcessoNegado("Item de outra região")
            original = cv2.imread(str(configuracao.caminho("acervo") / item["arquivo"]))
            if original is None:
                raise AcessoNegado("Arquivo do item não encontrado")
            imagem = preparar_imagem(original, item, self.repo.regioes(item_id), sessao.nivel,
                                     sessao.usuario_id, momento, self.cfg)
        except AcessoNegado as erro:
            self._registrar("CONSULTA", sessao, item_id, "NEGADO", "ACESSO_NEGADO_ITEM")
            raise erro
        self._registrar("CONSULTA", sessao, item_id, "CONCEDIDO", "CONCEDIDO")
        return item, imagem

    def exportar(self, sessao, item_id, imagem_entregue):
        """Grava a imagem JÁ tratada (nunca o original). Registra EXPORTACAO."""
        politica = POLITICA_EXPORTACAO[sessao.nivel]
        if politica == "BLOQUEADA":
            self._registrar("EXPORTACAO", sessao, item_id, "NEGADO", "EXPORTACAO_BLOQUEADA_N3")
            raise AcessoNegado("Nível 3 não exporta — apenas visualização em sessão")
        destino_dir = configuracao.caminho("exportacoes")
        destino_dir.mkdir(parents=True, exist_ok=True)
        destino = destino_dir / f"item{item_id}_u{sessao.usuario_id}_{datetime.now():%Y%m%d_%H%M%S}.png"
        cv2.imwrite(str(destino), imagem_entregue)
        self._registrar("EXPORTACAO", sessao, item_id, "CONCEDIDO", politica)
        return destino

    def _registrar(self, evento, sessao, item_id, resultado, motivo):
        self.trilha.registrar(novo_registro(
            evento, sessao.nivel, resultado, motivo,
            usuario_id=sessao.usuario_id, usuario2_id=sessao.usuario2_id, item_id=item_id))
