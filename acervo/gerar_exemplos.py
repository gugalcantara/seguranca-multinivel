"""Gera o acervo mínimo SINTÉTICO de exemplo: 9 itens (3 por nível) + metadados.json.

Serve para destravar o desenvolvimento enquanto o Integrante 3 monta o acervo
real a partir das fontes públicas (ETP 4.1). Todo conteúdo aqui é fictício:
empresas, municípios e coordenadas inventados (ETP 4.4, 12.3, RF-18).

As regiões sensíveis são registradas no momento em que o texto é desenhado,
então as coordenadas do JSON sempre batem com a imagem.

Uso:  python -m ferramentas gerar-acervo
"""
import json
import random
from datetime import date, timedelta
from pathlib import Path

import cv2
import numpy as np

import configuracao
from acervo.texto import escrever, fonte

LARGURA, ALTURA = 900, 640
BRANCO = (255, 255, 255)
UFS = ["SP", "RJ", "MG", "PR", "GO", "BA", "RS", "PE"]
# distribuição inspirada no cadastro da CETESB: AG-01 domina (~70%)
PESOS_AG = {"AG-01": 70, "AG-02": 8, "AG-03": 6, "AG-04": 3, "AG-05": 3, "AG-06": 4, "AG-07": 4, "AG-08": 2}
MOTIVOS = [f"MP-0{i}" for i in range(1, 9)]
SUBSTANCIAS = {
    "AG-01": ("Hidrocarbonetos (BTEX) em solo", "Área contaminada"),
    "AG-02": ("Solventes clorados", "Classe I (NBR 10004)"),
    "AG-03": ("Lodo galvânico com cromo hexavalente", "Classe I (NBR 10004)"),
    "AG-04": ("Fonte selada de radioterapia (desativada)", "Rejeito radioativo"),
    "AG-05": ("Rejeito com radioatividade natural", "Rejeito radioativo"),
    "AG-06": ("Resíduo de limpeza de tanque", "Classe I (NBR 10004)"),
    "AG-07": ("Agrotóxico vencido", "Classe I (NBR 10004)"),
    "AG-08": ("Rejeito de baixa atividade", "Rejeito radioativo"),
}


class Tela:
    """Canvas que acumula texto e registra regiões sensíveis enquanto desenha."""

    def __init__(self, titulo, subtitulo=""):
        self.img = np.full((ALTURA, LARGURA, 3), 250, np.uint8)
        cv2.rectangle(self.img, (0, 30), (LARGURA, 90), (60, 45, 30), -1)
        self.textos = [(24, 40, titulo, BRANCO, 26, True), (24, 70, subtitulo, (210, 210, 210), 15, False)]
        self.regioes = []

    def texto(self, x, y, conteudo, tamanho=18, cor=(30, 30, 30), negrito=False, sensivel=None, rotulo=None):
        self.textos.append((x, y, conteudo, cor, tamanho, negrito))
        if sensivel:
            _, _, direita, baixo = fonte(tamanho, negrito).getbbox(conteudo)
            self.regioes.append({"x": x - 6, "y": y - 4, "largura": int(direita) + 12, "altura": int(baixo) + 10,
                                 "rotulo": rotulo, "nivel_minimo": sensivel})

    def campo(self, y, nome, valor, sensivel=None, rotulo=None):
        self.texto(40, y, nome, 17, (90, 90, 90))
        self.texto(260, y, valor, 18, sensivel=sensivel, rotulo=rotulo)

    def salvar(self, caminho):
        img = self.img
        for (x, y, t, cor, tam, neg) in self.textos:
            img = escrever(img, [(x, y, t)], cor=cor, tamanho=tam, negrito=neg)
        cv2.imwrite(str(caminho), img)


def _pendencias(rng):
    hoje = date(2026, 10, 1)
    nomes = ["Alfa", "Beta", "Gama", "Delta", "Épsilon", "Zeta", "Eta", "Teta", "Iota", "Kapa", "Lambda", "Mi",
             "Ni", "Xi", "Ômicron", "Pi", "Rô", "Sigma", "Tau", "Ípsilon"]
    pendencias = []
    for i in range(20):
        ag = rng.choices(list(PESOS_AG), weights=list(PESOS_AG.values()))[0]
        substancia, classe = SUBSTANCIAS[ag]
        uf = "SP" if i < 3 else rng.choice(UFS)
        pendencias.append({
            "codigo": f"PD-{i + 1:04d}", "substancia": substancia, "classe_risco": classe,
            "quantidade": round(rng.uniform(0.2, 40), 3), "unidade": "t", "uf": uf,
            "municipio": f"Município Fictício {nomes[i]}",
            "latitude": round(rng.uniform(-30, -5), 6), "longitude": round(rng.uniform(-55, -38), 6),
            "prazo_coleta": str(hoje + timedelta(days=rng.randint(-400, 120))),
            "situacao": "PENDENTE", "atividade": ag, "motivo": rng.choice(MOTIVOS), "sintetico": True,
            "fonte": "Sintético — gerado por acervo/gerar_exemplos.py",
            "responsaveis": [
                {"nome": f"Empresa Fictícia {nomes[i]} Ltda.", "vinculo": "GERADOR_ORIGINAL",
                 "situacao_cadastral": rng.choice(["ATIVA", "BAIXADA", "FALIDA"])},
                {"nome": f"Imobiliária Exemplo {nomes[-i - 1]} S.A.", "vinculo": "PROPRIETARIO_ATUAL",
                 "situacao_cadastral": "ATIVA"},
            ],
        })
    # força os casos usados nos itens
    pendencias[0].update(atividade="AG-03", motivo="MP-01", substancia=SUBSTANCIAS["AG-03"][0],
                         classe_risco=SUBSTANCIAS["AG-03"][1])
    pendencias[1].update(atividade="AG-02", motivo="MP-08", uf="RJ", substancia=SUBSTANCIAS["AG-02"][0],
                         classe_risco=SUBSTANCIAS["AG-02"][1])
    pendencias[2].update(atividade="AG-04", motivo="MP-05", substancia=SUBSTANCIAS["AG-04"][0],
                         classe_risco=SUBSTANCIAS["AG-04"][1])
    return pendencias


def _tambores(img, deslocamento=(0, 0), angulo=0.0, lacre_rompido=False):
    dx, dy = deslocamento
    cv2.rectangle(img, (0, 380), (LARGURA, ALTURA), (150, 150, 140), -1)
    for i, x in enumerate((180, 400, 620)):
        cv2.rectangle(img, (x, 200), (x + 150, 440), (30, 90 + 20 * i, 160), -1)
        for y in (240, 320, 400):
            cv2.line(img, (x, y), (x + 150, y), (20, 50, 90), 4)
        cv2.putText(img, f"LOTE-{i + 1}", (x + 20, 290), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        if not (lacre_rompido and i == 1):
            cv2.rectangle(img, (x + 55, 185), (x + 95, 215), (0, 200, 255), -1)   # lacre
            cv2.circle(img, (x + 75, 200), 8, (0, 0, 180), -1)
    textura = np.random.RandomState(7)   # mesma textura em referência e verificação
    for _ in range(300):   # textura para o ORB
        x, y = textura.randint(0, LARGURA), textura.randint(380, ALTURA)
        cv2.circle(img, (x, y), 2, (110, 110, 100), -1)
    m = cv2.getRotationMatrix2D((LARGURA / 2, ALTURA / 2), angulo, 1.0)
    m[:, 2] += (dx, dy)
    return cv2.warpAffine(img, m, (LARGURA, ALTURA), borderValue=(250, 250, 250))


def gerar(destino=None, semente=2026):
    rng = random.Random(semente)
    destino = Path(destino or configuracao.caminho("acervo"))
    destino.mkdir(parents=True, exist_ok=True)
    pendencias = _pendencias(rng)
    itens = []

    def registrar(tela, codigo, titulo, tipo, nivel, uf=None, pendencia=None, revisadas=True):
        arquivo = f"{codigo.lower()}.png"
        tela.salvar(destino / arquivo)
        itens.append({"codigo": codigo, "titulo": titulo, "tipo": tipo, "arquivo": arquivo,
                      "nivel_minimo": nivel, "regioes_revisadas": revisadas, "sintetico": True,
                      "uf": uf, "pendencia": pendencia, "regioes": tela.regioes if revisadas else [],
                      "fonte": "Sintético — gerado por acervo/gerar_exemplos.py"})

    # ------------------------------------------------------------ Nível 1
    t = Tela("A1-01 Panorama Nacional", "Pendências por UF — dados agregados, sem localização")
    t.texto(60, 120, "UF        Pendências      Vencidas", 20, negrito=True)
    for i, uf in enumerate(UFS):
        do_uf = [p for p in pendencias if p["uf"] == uf]
        vencidas = sum(p["prazo_coleta"] < "2026-10-01" for p in do_uf)
        t.texto(60, 160 + 36 * i, f"{uf:<10}{len(do_uf):>10}{vencidas:>16}", 20)
    registrar(t, "A1-01", "Panorama Nacional", "DOCUMENTO", 1)

    t = Tela("A1-02 Distribuição por Atividade Geradora", "Contagem por AG-01 a AG-08")
    contagem = {ag: sum(p["atividade"] == ag for p in pendencias) for ag in PESOS_AG}
    maximo = max(contagem.values()) or 1
    for i, (ag, n) in enumerate(contagem.items()):
        y = 130 + 58 * i
        cv2.rectangle(t.img, (160, y), (160 + int(600 * n / maximo), y + 36), (160, 110, 40), -1)
        t.texto(40, y + 8, ag, 18, negrito=True)
        t.texto(170 + int(600 * n / maximo), y + 8, str(n), 18)
    registrar(t, "A1-02", "Distribuição por Atividade", "DOCUMENTO", 1)

    # Item-vitrine do CA-03: mesmo mapa, supressão distinta nos três níveis
    t = Tela("A1-05 Mapa de Densidade", "Coordenadas: nível 2 · Instalação de custódia: nível 3")
    cv2.rectangle(t.img, (40, 110), (860, 600), (225, 235, 225), -1)
    for gx in range(40, 861, 82):
        cv2.line(t.img, (gx, 110), (gx, 600), (200, 210, 200), 1)
    for p in pendencias[:8]:
        x = int(60 + (p["longitude"] + 55) / 17 * 600)
        y = int(130 + (p["latitude"] + 30) / 25 * 420)
        cv2.circle(t.img, (x, y), 9, (40, 40, 200), -1)
        t.texto(x + 14, y - 10, f"{p['latitude']:.4f}, {p['longitude']:.4f}", 14, sensivel=2, rotulo="COORDENADA")
    cv2.rectangle(t.img, (700, 520), (730, 550), (0, 0, 0), -1)
    t.texto(560, 560, "Depósito intermediário (fictício) — ala B", 14, sensivel=3, rotulo="CUSTODIA")
    registrar(t, "A1-05", "Mapa de Densidade", "MAPA", 1)

    # ------------------------------------------------------------ Nível 2
    p = pendencias[0]
    t = Tela("A2-01 Ficha da Pendência", f"{p['codigo']} — ficha causal completa")
    t.campo(130, "Substância", p["substancia"])
    t.campo(165, "Classe de risco", p["classe_risco"])
    t.campo(200, "Quantidade", f"{p['quantidade']} t")
    t.campo(235, "Município / UF", f"{p['municipio']} / {p['uf']}")
    t.campo(270, "Endereço", "Rua Inexistente, 123 — Distrito Industrial", sensivel=2, rotulo="ENDERECO")
    t.campo(305, "Prazo de coleta", p["prazo_coleta"])
    t.campo(340, "Atividade geradora", f"{p['atividade']} — Metalurgia e galvanoplastia")
    t.campo(375, "Motivo da permanência", f"{p['motivo']} — Encerramento ou falência do gerador")
    t.campo(410, "Gerador original", p["responsaveis"][0]["nome"], sensivel=2, rotulo="RESPONSAVEL")
    t.campo(445, "Proprietário atual", p["responsaveis"][1]["nome"], sensivel=2, rotulo="RESPONSAVEL")
    t.campo(480, "Ação institucional", "Identificar sucessor ou proprietário atual e notificar")
    t.campo(530, "Ponto frágil de guarda", "Portão lateral sem vigilância noturna", sensivel=3, rotulo="CUSTODIA")
    registrar(t, "A2-01", "Ficha da Pendência", "DOCUMENTO", 2, uf="SP", pendencia=p["codigo"])

    p = pendencias[1]
    t = Tela("A2-04 Rastreio de Manifesto (MTR fictício)", "MP-08 — manifesto emitido sem baixa do destinador")
    t.campo(130, "Nº do manifesto", "MTR-FICT-2026-000123")
    t.campo(165, "Resíduo", p["substancia"])
    t.campo(200, "Quantidade", f"{p['quantidade']} t")
    t.campo(235, "Gerador", p["responsaveis"][0]["nome"], sensivel=2, rotulo="RESPONSAVEL")
    t.campo(270, "Transportador", "Transportes Fictícios Ômega Ltda.", sensivel=2, rotulo="RESPONSAVEL")
    t.campo(305, "Destinador", "Aterro Classe I Exemplo S.A.", sensivel=2, rotulo="RESPONSAVEL")
    t.campo(340, "Emissão", "2026-03-14")
    t.campo(375, "Baixa do destinador", "NÃO CONSTA — carga em local desconhecido")
    t.campo(410, "Placa do veículo", "XXX-0A00", sensivel=3, rotulo="RASTREIO")
    registrar(t, "A2-04", "Rastreio de Manifesto", "DOCUMENTO", 2, uf="RJ", pendencia=p["codigo"])

    t = Tela("A2-06 Foto de Acondicionamento", "Referência para o módulo de inspeção (M-03)")
    t.img = _tambores(t.img)
    registrar(t, "A2-06", "Foto de Acondicionamento", "FOTO", 2, uf="SP", pendencia=pendencias[0]["codigo"])
    inspecao = destino / "inspecao"
    inspecao.mkdir(exist_ok=True)
    fundo = np.full((ALTURA, LARGURA, 3), 250, np.uint8)
    cv2.imwrite(str(inspecao / "referencia.png"), _tambores(fundo.copy()))
    cv2.imwrite(str(inspecao / "verificacao_integra.png"),
                _tambores(fundo.copy(), deslocamento=(12, -8), angulo=1.5))
    cv2.imwrite(str(inspecao / "verificacao_violada.png"),
                _tambores(fundo.copy(), deslocamento=(12, -8), angulo=1.5, lacre_rompido=True))

    # ------------------------------------------------------------ Nível 3
    t = Tela("A3-01 Consolidado Nacional", "Visão de custódia — todas as UFs")
    t.texto(40, 120, "UF   Pendências   Rejeito radioativo   Classe I   Maior atraso (dias)", 18, negrito=True)
    for i, uf in enumerate(UFS):
        do_uf = [p for p in pendencias if p["uf"] == uf]
        radio = sum(p["classe_risco"] == "Rejeito radioativo" for p in do_uf)
        classe1 = sum(p["classe_risco"].startswith("Classe I") for p in do_uf)
        atraso = max([(date(2026, 10, 1) - date.fromisoformat(p["prazo_coleta"])).days for p in do_uf] or [0])
        t.texto(40, 160 + 34 * i, f"{uf}   {len(do_uf):>8}   {radio:>16}   {classe1:>10}   {max(atraso, 0):>14}", 18)
    registrar(t, "A3-01", "Consolidado Nacional", "DOCUMENTO", 3)

    t = Tela("A3-02 Matriz de Criticidade", "Risco da substância × motivo da permanência")
    classes = ["Rejeito radioativo", "Classe I (NBR 10004)", "Área contaminada"]
    for j, mp in enumerate(MOTIVOS):
        t.texto(230 + 80 * j, 120, mp, 14, negrito=True)
    for i, classe in enumerate(classes):
        t.texto(30, 175 + 100 * i, classe, 15, negrito=True)
        for j, mp in enumerate(MOTIVOS):
            n = sum(p["classe_risco"] == classe and p["motivo"] == mp for p in pendencias)
            cor = (60, 60, 60 + min(195, 60 * n)) if n else (225, 225, 225)
            cv2.rectangle(t.img, (225 + 80 * j, 150 + 100 * i), (295 + 80 * j, 230 + 100 * i), cor, -1)
            t.texto(250 + 80 * j, 180 + 100 * i, str(n), 20, cor=BRANCO if n else (120, 120, 120), negrito=True)
    registrar(t, "A3-02", "Matriz de Criticidade", "DOCUMENTO", 3)

    p = pendencias[2]
    t = Tela("A3-05 Dossiê Completo", "Item SEM revisão de regiões — demonstra a falha segura (só N3)")
    t.campo(130, "Pendência", p["codigo"])
    t.campo(165, "Substância", p["substancia"])
    t.campo(200, "Motivo", f"{p['motivo']} — Ausência de destino final no país")
    t.campo(235, "Responsável", p["responsaveis"][0]["nome"])
    t.campo(270, "Coordenadas", f"{p['latitude']}, {p['longitude']}")
    t.campo(305, "Cronograma", "Remoção prevista para fila do depósito intermediário — 2027")
    registrar(t, "A3-05", "Dossiê Completo", "DOCUMENTO", 3, uf="SP", pendencia=p["codigo"], revisadas=False)

    (destino / "metadados.json").write_text(
        json.dumps({"pendencias": pendencias, "itens": itens}, ensure_ascii=False, indent=2), encoding="utf-8")
    return destino, len(pendencias), len(itens)


if __name__ == "__main__":
    print(gerar())
