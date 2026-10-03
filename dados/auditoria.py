"""Trilha de auditoria encadeada por SHA-256 (D-05, RF-12, RF-13).

    hash_registro = SHA-256( hash_anterior + forma_canônica(registro) )

Cada registro carrega o hash do anterior. Alterar um campo muda o hash daquele
registro (HASH_ALTERADO); apagar ou inserir um registro no meio quebra o elo
com o seguinte (ELO_ROMPIDO). A verificação percorre a tabela e aponta o
primeiro ponto de ruptura.

Cuidados para a recomputação bater:
- `momento` é definido aqui, com microssegundos, e gravado tal qual (DATETIME(6));
- números passam por Decimal com 4 casas antes do hash e do INSERT (DECIMAL no banco);
- a forma canônica é JSON com campos em ordem fixa.
"""
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from cryptography.fernet import Fernet

GENESIS = "0" * 64

CAMPOS_HASH = (
    "momento", "evento", "usuario_id", "usuario2_id", "matricula_informada",
    "nivel_solicitado", "item_id", "fatores_avaliados", "resultado", "motivo",
    "distancia", "qualidade",
)
_DECIMAIS = {"distancia", "qualidade"}
_INTEIROS = {"usuario_id", "usuario2_id", "nivel_solicitado", "item_id"}
_QUATRO_CASAS = Decimal("0.0001")


def _normalizar(campo, valor):
    if valor is None:
        return None
    if campo == "momento":
        return valor.isoformat(sep=" ", timespec="microseconds")
    if campo in _DECIMAIS:
        if valor == float("inf"):
            return None   # distância "infinita" (sem modelo) não é gravável
        return str(Decimal(str(valor)).quantize(_QUATRO_CASAS, rounding=ROUND_HALF_UP))
    if campo in _INTEIROS:
        return int(valor)
    return str(valor)


def forma_canonica(registro):
    return json.dumps([[c, _normalizar(c, registro.get(c))] for c in CAMPOS_HASH],
                      ensure_ascii=False, separators=(",", ":"))


def calcular_hash(hash_anterior, registro):
    return hashlib.sha256((hash_anterior + forma_canonica(registro)).encode("utf-8")).hexdigest()


def novo_registro(evento, nivel_solicitado, resultado, motivo, **extras):
    """Monta o registro já normalizado, com o momento definido pela aplicação."""
    registro = dict.fromkeys(CAMPOS_HASH)
    registro.update(extras, evento=evento, nivel_solicitado=nivel_solicitado,
                    resultado=resultado, motivo=str(getattr(motivo, "value", motivo)),
                    momento=datetime.now())
    if isinstance(registro.get("fatores_avaliados"), (list, tuple)):
        registro["fatores_avaliados"] = ",".join(registro["fatores_avaliados"])
    for campo in _DECIMAIS:
        valor = _normalizar(campo, registro[campo])
        registro[campo] = Decimal(valor) if valor is not None else None
    return registro


@dataclass
class ResultadoVerificacao:
    integra: bool
    total: int
    id_ruptura: int | None = None
    tipo: str | None = None         # HASH_ALTERADO | ELO_ROMPIDO
    detalhe: str = ""


def verificar_cadeia(registros):
    """Função pura: recebe os registros em ordem de id e localiza a 1ª ruptura.

    Percorre a cadeia INTEIRA, recomputando cada hash — custo linear (~8 ms por
    mil registros). Verificar só um trecho recente seria mais barato e não
    provaria nada: é justamente o elo com todo o passado que dá valor à cadeia.
    """
    anterior = GENESIS
    for i, reg in enumerate(registros):
        if reg["hash_anterior"] != anterior:
            return ResultadoVerificacao(False, len(registros), reg.get("id", i), "ELO_ROMPIDO",
                                        "hash_anterior não corresponde ao registro precedente "
                                        "(registro apagado, inserido ou reordenado)")
        if calcular_hash(anterior, reg) != reg["hash_registro"]:
            return ResultadoVerificacao(False, len(registros), reg.get("id", i), "HASH_ALTERADO",
                                        "conteúdo do registro não corresponde ao hash gravado")
        anterior = reg["hash_registro"]
    return ResultadoVerificacao(True, len(registros))


class TrilhaAuditoria:
    _TRAVA = "aps_pivc_log_acesso"

    def __init__(self, banco):
        self.banco = banco

    def registrar(self, registro):
        """Encadeia e grava. Devolve o id do log.

        A trava nomeada (GET_LOCK) serializa a leitura do último hash e o INSERT,
        sem exigir UPDATE na tabela — a conta da aplicação só tem SELECT/INSERT.
        """
        with self.banco.transacao() as cur:
            cur.execute("SELECT GET_LOCK(%s, 10) AS ok", (self._TRAVA,))
            if cur.fetchone()["ok"] != 1:
                raise RuntimeError("Não foi possível obter a trava da trilha de auditoria")
            try:
                cur.execute("SELECT hash_registro FROM log_acesso ORDER BY id DESC LIMIT 1")
                ultimo = cur.fetchone()
                anterior = ultimo["hash_registro"] if ultimo else GENESIS
                colunas = list(CAMPOS_HASH) + ["hash_anterior", "hash_registro"]
                valores = [registro.get(c) for c in CAMPOS_HASH] + [anterior, calcular_hash(anterior, registro)]
                cur.execute(
                    f"INSERT INTO log_acesso ({', '.join(colunas)}) VALUES ({', '.join(['%s'] * len(colunas))})",
                    valores,
                )
                log_id = cur.lastrowid
            finally:
                cur.execute("SELECT RELEASE_LOCK(%s)", (self._TRAVA,))
                cur.fetchall()
        return log_id

    def ler(self, limite=None):
        sql = "SELECT * FROM log_acesso ORDER BY id"
        if limite:
            sql = f"SELECT * FROM (SELECT * FROM log_acesso ORDER BY id DESC LIMIT {int(limite)}) t ORDER BY id"
        return self.banco.consultar(sql)

    def verificar(self):
        """Relatório S-04."""
        return verificar_cadeia(self.ler())

    # ---------------------------------------------------- foto de tentativa negada
    def anexar_foto_negada(self, log_id, jpeg, chave, dias_retencao):
        with self.banco.transacao() as cur:
            cur.execute(
                "INSERT INTO tentativa_negada (log_id, imagem, expira_em) VALUES (%s, %s, %s)",
                (log_id, Fernet(chave).encrypt(jpeg), datetime.now() + timedelta(days=dias_retencao)),
            )

    def expurgar_fotos_expiradas(self):
        with self.banco.transacao() as cur:
            cur.execute("DELETE FROM tentativa_negada WHERE expira_em < NOW()")
            return cur.rowcount
