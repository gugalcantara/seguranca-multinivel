"""Consultas ao acervo filtradas pelo nível JÁ NA CONSULTA (controle de acesso no SQL).

- N1: só itens de nivel_minimo 1 e agregados sem localização (RF-20);
- N2: itens até o nível 2 da própria UF do diretor;
- N3: tudo, inclusive itens sem regiões revisadas (falha segura do conteúdo).
A cadeia de responsabilidade nunca é consultada no nível 1 (RF-21).
"""
import json
from pathlib import Path

from acervo.tarja import Regiao


class RepositorioAcervo:
    def __init__(self, banco):
        self.banco = banco

    # ------------------------------------------------------------ itens
    def itens_para_nivel(self, nivel, uf=None):
        sql = ("SELECT * FROM item_acervo WHERE nivel_minimo <= %s "
               "AND (regioes_revisadas = TRUE OR %s >= 3)")
        parametros = [nivel, nivel]
        if nivel == 2 and uf:
            sql += " AND (uf IS NULL OR uf = %s)"
            parametros.append(uf)
        return self.banco.consultar(sql + " ORDER BY nivel_minimo, codigo", parametros)

    def item(self, item_id):
        linhas = self.banco.consultar("SELECT * FROM item_acervo WHERE id = %s", (item_id,))
        return linhas[0] if linhas else None

    def regioes(self, item_id):
        return [Regiao.de_linha(l) for l in
                self.banco.consultar("SELECT * FROM regiao_sensivel WHERE item_id = %s", (item_id,))]

    # ------------------------------------------------------------ camada causal
    def agregado_por_atividade(self):
        return self.banco.consultar("SELECT * FROM vw_n1_por_atividade ORDER BY uf, atividade")

    def agregado_por_motivo(self):
        return self.banco.consultar("SELECT * FROM vw_n1_por_motivo ORDER BY motivo")

    def ficha_pendencia(self, pendencia_id, nivel):
        """A2-01 — ficha causal completa (N2+)."""
        if nivel < 2:
            return None
        linhas = self.banco.consultar(
            "SELECT p.*, a.codigo AS atividade, a.descricao AS atividade_descricao, "
            "m.codigo AS motivo, m.descricao AS motivo_descricao, m.base_legal, m.acao_institucional "
            "FROM pendencia p JOIN atividade_geradora a ON a.id = p.atividade_id "
            "JOIN motivo_permanencia m ON m.id = p.motivo_id WHERE p.id = %s", (pendencia_id,))
        return linhas[0] if linhas else None

    def responsaveis(self, pendencia_id, nivel):
        if nivel < 2:          # RF-21: nível 1 não toca na tabela
            return []
        return self.banco.consultar(
            "SELECT nome, vinculo, situacao_cadastral FROM responsavel "
            "WHERE pendencia_id = %s AND nivel_minimo <= %s", (pendencia_id, nivel))

    def pendencias_vencidas(self, nivel, uf=None):
        """RF-15. N1 recebe só contagem por UF; N2 a lista da própria UF; N3 tudo."""
        if nivel == 1:
            return self.banco.consultar(
                "SELECT uf, COUNT(*) AS vencidas FROM pendencia WHERE prazo_coleta < CURRENT_DATE GROUP BY uf")
        sql = ("SELECT p.codigo, p.substancia, p.uf, p.municipio, p.prazo_coleta, "
               "DATEDIFF(CURRENT_DATE, p.prazo_coleta) AS dias_atraso, m.codigo AS motivo "
               "FROM pendencia p JOIN motivo_permanencia m ON m.id = p.motivo_id "
               "WHERE p.prazo_coleta < CURRENT_DATE")
        parametros = []
        if nivel == 2:
            sql += " AND p.uf = %s"
            parametros.append(uf)
        return self.banco.consultar(sql + " ORDER BY dias_atraso DESC", parametros)

    # ------------------------------------------------------------ importação
    def importar_metadados(self, caminho_json):
        """Carrega acervo/itens/metadados.json (montado pelo Integrante 3) no banco."""
        dados = json.loads(Path(caminho_json).read_text(encoding="utf-8"))
        with self.banco.transacao() as cur:
            ids_pendencia = {}
            for p in dados.get("pendencias", []):
                cur.execute(
                    "INSERT INTO pendencia (codigo, substancia, classe_risco, quantidade, unidade, uf, municipio, "
                    "latitude, longitude, prazo_coleta, situacao, atividade_id, motivo_id, sintetico, fonte, "
                    "data_acesso_fonte) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,"
                    "(SELECT id FROM atividade_geradora WHERE codigo=%s),"
                    "(SELECT id FROM motivo_permanencia WHERE codigo=%s),%s,%s,%s)",
                    (p["codigo"], p["substancia"], p["classe_risco"], p.get("quantidade"), p.get("unidade"),
                     p["uf"], p.get("municipio"), p.get("latitude"), p.get("longitude"), p.get("prazo_coleta"),
                     p["situacao"], p["atividade"], p["motivo"], p.get("sintetico", True), p.get("fonte"),
                     p.get("data_acesso_fonte")))
                ids_pendencia[p["codigo"]] = cur.lastrowid
                for r in p.get("responsaveis", []):
                    cur.execute(
                        "INSERT INTO responsavel (pendencia_id, nome, vinculo, situacao_cadastral, nivel_minimo) "
                        "VALUES (%s,%s,%s,%s,%s)",
                        (ids_pendencia[p["codigo"]], r["nome"], r["vinculo"],
                         r.get("situacao_cadastral"), r.get("nivel_minimo", 2)))
            for item in dados.get("itens", []):
                cur.execute(
                    "INSERT INTO item_acervo (codigo, titulo, tipo, arquivo, nivel_minimo, regioes_revisadas, "
                    "sintetico, uf, pendencia_id, fonte, data_acesso_fonte) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (item["codigo"], item["titulo"], item["tipo"], item["arquivo"], item["nivel_minimo"],
                     item.get("regioes_revisadas", False), item.get("sintetico", True), item.get("uf"),
                     ids_pendencia.get(item.get("pendencia")), item.get("fonte"), item.get("data_acesso_fonte")))
                item_id = cur.lastrowid
                for r in item.get("regioes", []):
                    cur.execute(
                        "INSERT INTO regiao_sensivel (item_id, x, y, largura, altura, rotulo, nivel_minimo) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (item_id, r["x"], r["y"], r["largura"], r["altura"], r.get("rotulo"), r["nivel_minimo"]))
        return len(dados.get("pendencias", [])), len(dados.get("itens", []))
