"""Limpeza dos dados de operação preservando o acervo (ferramentas limpar-operacao).

Roda contra o banco DESCARTÁVEL, nunca o de demonstração — é justamente o tipo
de operação que não deve ser exercitada no banco que vai para a apresentação.
"""
import mysql.connector
import pytest

import configuracao
from dados.auditoria import TrilhaAuditoria, novo_registro
from dados.manutencao import TABELAS_DE_OPERACAO, TABELAS_PRESERVADAS, contar, limpar_operacao
from dados.repositorio import RepositorioUsuarios
from dados.conexao import Banco, BancoIndisponivel
from testes.test_integracao_banco import _recriar_banco_de_teste


@pytest.fixture
def banco():
    nome = configuracao.banco_de_teste()
    if not nome:
        pytest.skip("DB_NOME_TESTE ausente no .env")
    try:
        _recriar_banco_de_teste(nome)
        b = Banco(configuracao.credenciais_banco(nome))
        b.consultar("SELECT 1")
        return b
    except (BancoIndisponivel, RuntimeError, mysql.connector.Error) as erro:
        pytest.skip(f"MySQL não disponível: {erro}")


def _povoar(banco):
    """Um usuário com trilha e amostras — o resíduo típico de uma execução."""
    uid = RepositorioUsuarios(banco).criar("TESTE-LIMPEZA", "Fulano", 2, "$2b$12$" + "x" * 53, "SP")
    RepositorioUsuarios(banco).registrar_amostras(uid, 1, [0.8, 0.9], "imagem")
    trilha = TrilhaAuditoria(banco)
    for i in range(3):
        trilha.registrar(novo_registro("AUTENTICACAO", 2, "NEGADO", "SENHA_INCORRETA",
                                       usuario_id=uid, distancia=50 + i))
    return uid


def test_limpa_operacao_e_preserva_o_acervo(banco):
    from acervo.repositorio_acervo import RepositorioAcervo
    RepositorioAcervo(banco).importar_metadados(configuracao.caminho("acervo_metadados"))
    _povoar(banco)

    with banco.transacao() as cur:
        antes_operacao = contar(cur, TABELAS_DE_OPERACAO)
        antes_acervo = contar(cur, TABELAS_PRESERVADAS)
    assert antes_operacao["usuario"] >= 1 and antes_operacao["log_acesso"] >= 3

    with banco.transacao() as cur:
        removidos = limpar_operacao(cur)
        depois_operacao = contar(cur, TABELAS_DE_OPERACAO)
        depois_acervo = contar(cur, TABELAS_PRESERVADAS)

    assert all(n == 0 for n in depois_operacao.values()), depois_operacao
    assert removidos["usuario"] == antes_operacao["usuario"]
    assert depois_acervo == antes_acervo          # o acervo não é tocado
    assert depois_acervo["item_acervo"] == 9


def test_trilha_zerada_volta_a_verificar_integra(banco):
    """Apagar a cadeia inteira é seguro; apagar do meio é que deixaria ELO_ROMPIDO."""
    _povoar(banco)
    with banco.transacao() as cur:
        limpar_operacao(cur)

    trilha = TrilhaAuditoria(banco)
    assert trilha.verificar().integra
    trilha.registrar(novo_registro("VERIFICACAO", 1, "CONCEDIDO", "APOS_LIMPEZA"))
    resultado = trilha.verificar()
    assert resultado.integra and resultado.total == 1


def test_ordem_das_tabelas_respeita_as_chaves_estrangeiras():
    """usuario sai por último: log_acesso e amostra o referenciam."""
    ordem = list(TABELAS_DE_OPERACAO)
    assert ordem.index("tentativa_negada") < ordem.index("log_acesso")
    assert ordem.index("log_acesso") < ordem.index("usuario")
    assert ordem.index("amostra") < ordem.index("usuario")
    assert "item_acervo" not in ordem and "pendencia" not in ordem
