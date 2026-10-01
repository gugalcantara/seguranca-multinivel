"""Carga única de config.ini (parâmetros) e .env (credenciais).

Todo módulo lê parâmetros por aqui — nenhum valor fica fixo no código.
"""
import configparser
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent


def _tupla(texto):
    return tuple(int(x.strip()) for x in texto.split(","))


def _lista(texto):
    return [x.strip() for x in texto.split(",") if x.strip()]


@lru_cache(maxsize=None)
def carregar(caminho=None):
    """Devolve o config.ini como ConfigParser com getters extras:
    cfg.gettupla(secao, chave) -> (int, int) e cfg.getlista(secao, chave) -> [str]."""
    cfg = configparser.ConfigParser(converters={"tupla": _tupla, "lista": _lista})
    arquivo = Path(caminho) if caminho else RAIZ / "config.ini"
    if not cfg.read(arquivo, encoding="utf-8"):
        raise FileNotFoundError(f"config.ini não encontrado em {arquivo}")
    return cfg


def caminho(chave):
    """Caminho absoluto de uma entrada da seção [caminhos]."""
    return RAIZ / carregar().get("caminhos", chave)


def limiar(nivel):
    """Limiar de distância LBPH do nível (menor = mais restritivo)."""
    return carregar().getfloat("limiares", f"nivel_{nivel}")


def env(nome, obrigatorio=True):
    load_dotenv(RAIZ / ".env")
    valor = os.getenv(nome)
    if obrigatorio and not valor:
        raise RuntimeError(f"Variável {nome} ausente no .env (ver .env.exemplo)")
    return valor


def credenciais_banco(nome=None):
    """Credenciais do MySQL. `nome` troca só o banco — é como os testes de
    integração apontam para o banco descartável sem tocar no de demonstração."""
    return {
        "host": env("DB_HOST"),
        "port": int(env("DB_PORTA")),
        "database": nome or env("DB_NOME"),
        "user": env("DB_USUARIO"),
        "password": env("DB_SENHA"),
    }


def banco_de_teste():
    """Nome do banco descartável dos testes de integração (DB_NOME_TESTE).

    Ausente: os testes de integração são PULADOS, em vez de caírem no banco de
    demonstração e deixarem usuários e trilha de teste para trás.
    """
    return env("DB_NOME_TESTE", obrigatorio=False)
