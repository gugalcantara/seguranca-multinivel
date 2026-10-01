"""RF-12 / RF-13: a cadeia detecta e localiza adulteração (sem precisar de MySQL)."""
from decimal import Decimal

from dados.auditoria import GENESIS, calcular_hash, novo_registro, verificar_cadeia


def _cadeia(n=5):
    registros, anterior = [], GENESIS
    for i in range(1, n + 1):
        r = novo_registro("AUTENTICACAO", 2, "CONCEDIDO" if i % 2 else "NEGADO", "CONCEDIDO",
                          usuario_id=i, distancia=40 + i / 3, qualidade=0.81234567,
                          fatores_avaliados=["SENHA", "FACE"])
        r.update(id=i, hash_anterior=anterior, hash_registro=calcular_hash(anterior, r))
        anterior = r["hash_registro"]
        registros.append(r)
    return registros


def test_cadeia_integra():
    r = verificar_cadeia(_cadeia())
    assert r.integra and r.total == 5


def test_alteracao_de_campo_e_localizada():
    cadeia = _cadeia()
    cadeia[2]["resultado"] = "CONCEDIDO" if cadeia[2]["resultado"] == "NEGADO" else "NEGADO"
    r = verificar_cadeia(cadeia)
    assert not r.integra and r.id_ruptura == 3 and r.tipo == "HASH_ALTERADO"


def test_remocao_de_registro_quebra_o_elo():
    cadeia = _cadeia()
    del cadeia[1]
    r = verificar_cadeia(cadeia)
    assert not r.integra and r.id_ruptura == 3 and r.tipo == "ELO_ROMPIDO"


def test_recalcular_um_hash_nao_basta_para_esconder():
    cadeia = _cadeia()
    cadeia[1]["usuario_id"] = 99
    cadeia[1]["hash_registro"] = calcular_hash(cadeia[1]["hash_anterior"], cadeia[1])
    r = verificar_cadeia(cadeia)
    assert not r.integra and r.id_ruptura == 3 and r.tipo == "ELO_ROMPIDO"


def test_valores_lidos_do_banco_recomputam_o_mesmo_hash():
    """Simula a volta do MySQL: DECIMAL(10,4) devolve Decimal com 4 casas."""
    r = novo_registro("AUTENTICACAO", 1, "CONCEDIDO", "CONCEDIDO", usuario_id=1, distancia=47.123456)
    h = calcular_hash(GENESIS, r)
    lido = dict(r, distancia=Decimal("47.1235"))
    assert calcular_hash(GENESIS, lido) == h


def test_distancia_infinita_vira_nulo():
    r = novo_registro("AUTENTICACAO", 1, "NEGADO", "FACE_NAO_RECONHECIDA", distancia=float("inf"))
    assert r["distancia"] is None
