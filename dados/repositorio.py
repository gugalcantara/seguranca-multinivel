"""CRUD de usuários, amostras e bloqueios. SQL explícito — sem ORM (ETP 6.4)."""
import secrets
from datetime import datetime, timedelta

import configuracao

# Sem I, O, 0 e 1: a matrícula é DIGITADA no login dos níveis 2 e 3, e esses
# quatro caracteres são os que mais se confundem ao ler de um papel ou crachá.
LETRAS_MATRICULA = "ABCDEFGHJKLMNPQRSTUVWXYZ"
DIGITOS_MATRICULA = "23456789"


def gerar_codigo_matricula(tamanho=7, rng=None):
    """Código curto e legível, com ao menos uma letra e um dígito.

    A mistura é garantida para o código não sair só numérico nem só alfabético,
    o que o faria parecer outra coisa (um CPF, uma sigla).
    """
    rng = rng or secrets.SystemRandom()
    todos = LETRAS_MATRICULA + DIGITOS_MATRICULA
    caracteres = [rng.choice(LETRAS_MATRICULA), rng.choice(DIGITOS_MATRICULA)]
    caracteres += [rng.choice(todos) for _ in range(max(0, tamanho - 2))]
    rng.shuffle(caracteres)
    return "".join(caracteres[:tamanho])


class RepositorioUsuarios:
    def __init__(self, banco):
        self.banco = banco

    def nova_matricula(self, tamanho=None, tentativas=20):
        """Matrícula inédita, gerada pelo sistema.

        A coluna é UNIQUE no schema, então o INSERT é a garantia final contra
        colisão; esta consulta só evita que o erro apareça no caminho normal.
        """
        tamanho = tamanho or configuracao.carregar().getint("cadastro", "tamanho_matricula")
        for _ in range(tentativas):
            codigo = gerar_codigo_matricula(tamanho)
            if not self.por_matricula(codigo):
                return codigo
        raise RuntimeError("Não foi possível gerar uma matrícula inédita — "
                           "aumente tamanho_matricula no config.ini")

    def criar(self, matricula, nome, nivel_id, senha_hash, uf=None):
        with self.banco.transacao() as cur:
            cur.execute(
                "INSERT INTO usuario (matricula, nome, nivel_id, uf, senha_hash) VALUES (%s, %s, %s, %s, %s)",
                (matricula, nome, nivel_id, uf, senha_hash),
            )
            return cur.lastrowid

    def por_matricula(self, matricula):
        linhas = self.banco.consultar("SELECT * FROM usuario WHERE matricula = %s", (matricula,))
        return linhas[0] if linhas else None

    def por_id(self, usuario_id):
        linhas = self.banco.consultar("SELECT * FROM usuario WHERE id = %s", (usuario_id,))
        return linhas[0] if linhas else None

    def listar(self):
        return self.banco.consultar(
            "SELECT u.id, u.matricula, u.nome, u.nivel_id, u.uf, u.ativo, u.criado_em, "
            "COUNT(a.id) AS amostras FROM usuario u LEFT JOIN amostra a ON a.usuario_id = u.id "
            "GROUP BY u.id ORDER BY u.id"
        )

    def definir_ativo(self, usuario_id, ativo):
        with self.banco.transacao() as cur:
            cur.execute("UPDATE usuario SET ativo = %s WHERE id = %s", (ativo, usuario_id))

    def registrar_amostras(self, usuario_id, sessao, qualidades, origem="webcam"):
        """Grava só o METADADO de cada amostra; a imagem é descartada após o treino."""
        with self.banco.transacao() as cur:
            cur.executemany(
                "INSERT INTO amostra (usuario_id, sessao, origem, qualidade) VALUES (%s, %s, %s, %s)",
                [(usuario_id, sessao, origem, round(q, 4)) for q in qualidades],
            )


class RepositorioBloqueio:
    """RF-06: três erros de senha consecutivos bloqueiam a matrícula temporariamente."""

    def __init__(self, banco):
        self.banco = banco

    def esta_bloqueado(self, matricula, agora=None):
        agora = agora or datetime.now()
        linhas = self.banco.consultar("SELECT bloqueado_ate FROM bloqueio WHERE matricula = %s", (matricula,))
        return bool(linhas and linhas[0]["bloqueado_ate"] and linhas[0]["bloqueado_ate"] > agora)

    def registrar_falha(self, matricula, maximo, minutos, agora=None):
        """Incrementa o contador; devolve True se a matrícula acabou de ser bloqueada."""
        agora = agora or datetime.now()
        with self.banco.transacao() as cur:
            cur.execute(
                "INSERT INTO bloqueio (matricula, tentativas) VALUES (%s, 1) "
                "ON DUPLICATE KEY UPDATE tentativas = tentativas + 1",
                (matricula,),
            )
            cur.execute("SELECT tentativas FROM bloqueio WHERE matricula = %s", (matricula,))
            if cur.fetchone()["tentativas"] >= maximo:
                cur.execute(
                    "UPDATE bloqueio SET tentativas = 0, bloqueado_ate = %s WHERE matricula = %s",
                    (agora + timedelta(minutes=minutos), matricula),
                )
                return True
        return False

    def zerar(self, matricula):
        with self.banco.transacao() as cur:
            cur.execute("UPDATE bloqueio SET tentativas = 0 WHERE matricula = %s", (matricula,))

    def ativos(self, agora=None):
        """Relatório S-03."""
        return self.banco.consultar(
            "SELECT matricula, bloqueado_ate FROM bloqueio WHERE bloqueado_ate > %s ORDER BY bloqueado_ate",
            (agora or datetime.now(),),
        )
