"""Pool de conexões MySQL.

Falha do banco = BancoIndisponivel. Quem chama trata como negação de acesso
(ETP 6.6: "acesso bloqueado por padrão"), nunca como liberação.
"""
from contextlib import contextmanager

import mysql.connector
from mysql.connector import pooling

import configuracao


class BancoIndisponivel(RuntimeError):
    pass


class Banco:
    def __init__(self, credenciais=None, tamanho_pool=4):
        credenciais = credenciais or configuracao.credenciais_banco()
        try:
            self._pool = pooling.MySQLConnectionPool(
                # o nome do pool deriva do banco: fixo, abrir um segundo banco no
                # mesmo processo (aplicação + banco de teste) colidiria com o primeiro
                pool_name=f"aps_{credenciais['database']}", pool_size=tamanho_pool,
                autocommit=False, **credenciais,
            )
        except mysql.connector.Error as erro:
            raise BancoIndisponivel(f"Não foi possível conectar ao MySQL: {erro}") from erro

    @contextmanager
    def transacao(self):
        """Cursor em dicionário; commit ao sair, rollback em exceção."""
        try:
            conexao = self._pool.get_connection()
        except mysql.connector.Error as erro:
            raise BancoIndisponivel(str(erro)) from erro
        cursor = conexao.cursor(dictionary=True)
        try:
            yield cursor
            conexao.commit()
        except Exception:
            conexao.rollback()
            raise
        finally:
            cursor.close()
            conexao.close()

    def consultar(self, sql, parametros=()):
        with self.transacao() as cur:
            cur.execute(sql, parametros)
            return cur.fetchall()
