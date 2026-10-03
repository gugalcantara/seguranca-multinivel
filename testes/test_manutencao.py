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


# ------------------------------------------------------------------ recriação do acervo
def test_limpa_acervo_quando_a_trilha_nao_o_referencia(banco):
    from acervo.repositorio_acervo import RepositorioAcervo
    from dados.manutencao import acervo_em_uso, limpar_acervo
    RepositorioAcervo(banco).importar_metadados(configuracao.caminho("acervo_metadados"))

    with banco.transacao() as cur:
        assert acervo_em_uso(cur) == 0
        removidos = limpar_acervo(cur)
        restantes = contar(cur, ("item_acervo", "pendencia", "regiao_sensivel", "responsavel"))
    assert removidos["item_acervo"] == 9 and removidos["pendencia"] == 20
    assert all(n == 0 for n in restantes.values())

    # e a importação volta a funcionar do zero
    pend, itens = RepositorioAcervo(banco).importar_metadados(
        configuracao.caminho("acervo_metadados"))
    assert (pend, itens) == (20, 9)


def test_acervo_em_uso_detecta_referencia_da_trilha(banco):
    """Com uma consulta registrada sobre um item, recriar o acervo exigiria
    apagar o registro — a ferramenta precisa enxergar isso e recusar."""
    from acervo.repositorio_acervo import RepositorioAcervo
    from dados.manutencao import acervo_em_uso
    RepositorioAcervo(banco).importar_metadados(configuracao.caminho("acervo_metadados"))
    item = banco.consultar("SELECT id FROM item_acervo LIMIT 1")[0]["id"]
    TrilhaAuditoria(banco).registrar(
        novo_registro("CONSULTA", 1, "CONCEDIDO", "CONCEDIDO", item_id=item))

    with banco.transacao() as cur:
        assert acervo_em_uso(cur) == 1


def test_taxonomia_da_camada_causal_nao_sai_com_o_acervo(banco):
    """atividade_geradora e motivo_permanencia vêm do sql/02, não do JSON:
    apagá-las deixaria a importação seguinte sem a que referenciar."""
    from dados.manutencao import TABELAS_DE_ACERVO
    assert "atividade_geradora" not in TABELAS_DE_ACERVO
    assert "motivo_permanencia" not in TABELAS_DE_ACERVO
    with banco.transacao() as cur:
        limpar_operacao(cur)
        assert contar(cur, ("atividade_geradora", "motivo_permanencia")) == \
            {"atividade_geradora": 8, "motivo_permanencia": 8}
