"""Integração com MySQL real, num banco DESCARTÁVEL.

Rodar com o MySQL do docker-compose e o .env apontando para ele:
    docker compose up -d
    python -m pytest testes/test_integracao_banco.py -v

O banco usado é o `DB_NOME_TESTE` do .env, recriado do zero a cada execução a
partir de sql/01 e sql/02. O banco de demonstração NUNCA é tocado: antes disso,
cada execução deixava para trás dois usuários TESTE-* e a trilha das tentativas
deles, que iam se acumulando e apareciam no painel.

Derivar o schema dos mesmos arquivos SQL da aplicação (em vez de manter uma
cópia) garante que o teste rode contra a estrutura real — se o schema mudar e
algo quebrar, quebra aqui, não na apresentação.

Sem DB_NOME_TESTE no .env, estes testes são PULADOS, nunca redirecionados para
o banco de demonstração.
"""
import time
from datetime import datetime

import mysql.connector
import pytest

import configuracao
from acervo.entrega import ServicoAcervo
from acervo.repositorio_acervo import RepositorioAcervo
from acervo.tarja import AcessoNegado
from autenticacao import senha
from autenticacao.motor import MotorAutenticacao, SessaoAutenticada
from autenticacao.politica import Motivo
from dados.auditoria import TrilhaAuditoria, novo_registro
from dados.conexao import Banco, BancoIndisponivel
from dados.repositorio import RepositorioBloqueio, RepositorioUsuarios
from visao.extracao import ReconhecedorLBPH


def _recriar_banco_de_teste(nome):
    """Apaga e recria o banco descartável com o schema e os dados de referência.

    O replace do nome funciona porque sql/01 e sql/02 só citam o banco no
    CREATE DATABASE e no USE. O multi=True deixa o próprio conector separar os
    comandos — dividir por ';' na mão quebraria, porque há ';' dentro de
    literais de texto no sql/02.
    """
    credenciais = configuracao.credenciais_banco()
    credenciais.pop("database")
    conexao = mysql.connector.connect(**credenciais)
    try:
        cursor = conexao.cursor()
        cursor.execute(f"DROP DATABASE IF EXISTS `{nome}`")
        for arquivo in ("01_schema.sql", "02_dados_iniciais.sql"):
            script = (configuracao.RAIZ / "sql" / arquivo).read_text(encoding="utf-8")
            for _ in cursor.execute(script.replace("aps_pivc", nome), multi=True):
                pass
        conexao.commit()
    finally:
        conexao.close()


@pytest.fixture(scope="module")
def banco():
    nome = configuracao.banco_de_teste()
    if not nome:
        pytest.skip("DB_NOME_TESTE ausente no .env — ver .env.exemplo. "
                    "Sem banco descartável, os testes de integração não rodam.")
    try:
        _recriar_banco_de_teste(nome)
        b = Banco(configuracao.credenciais_banco(nome))
        b.consultar("SELECT 1")
        return b
    except (BancoIndisponivel, RuntimeError, mysql.connector.Error) as erro:
        pytest.skip(f"MySQL não disponível: {erro}")


@pytest.fixture(scope="module")
def acervo_importado(banco):
    repo = RepositorioAcervo(banco)
    if not banco.consultar("SELECT id FROM item_acervo LIMIT 1"):
        repo.importar_metadados(configuracao.caminho("acervo_metadados"))
    return repo


def _matricula():
    return f"TESTE-{time.time_ns() % 10**12}"


def test_trilha_encadeia_e_verifica(banco):
    trilha = TrilhaAuditoria(banco)
    for i in range(3):
        trilha.registrar(novo_registro("VERIFICACAO", 1, "CONCEDIDO", "TESTE_INTEGRACAO", distancia=40 + i / 7))
    r = trilha.verificar()
    assert r.integra, r


@pytest.fixture(scope="module")
def banco_demonstracao():
    """O banco REAL — único lugar onde o privilégio restrito do RF-13 vale.

    No banco descartável a conta tem privilégio total (precisa, para recriar o
    schema), então o teste de privilégio só faz sentido aqui. Nada é escrito:
    o UPDATE é negado antes de tocar em qualquer linha.
    """
    try:
        b = Banco()
        b.consultar("SELECT 1")
        return b
    except (BancoIndisponivel, RuntimeError) as erro:
        pytest.skip(f"MySQL não disponível: {erro}")


def test_conta_da_aplicacao_nao_altera_a_trilha(banco_demonstracao):
    """RF-13: nem a própria aplicação consegue reescrever o passado.

    O WHERE não casa nenhuma linha de propósito: o privilégio é verificado antes
    da cláusula, então o erro 1142 vem igual — e se um dia a permissão for
    afrouxada por engano, este teste falha sem ter adulterado a trilha real.
    """
    with pytest.raises(mysql.connector.Error) as erro:
        with banco_demonstracao.transacao() as cur:
            cur.execute("UPDATE log_acesso SET motivo = 'ADULTERADO' WHERE id = -1")
    assert erro.value.errno == 1142        # UPDATE command denied


def test_usuario_e_bloqueio_apos_tres_erros(banco):
    usuarios, bloqueios = RepositorioUsuarios(banco), RepositorioBloqueio(banco)
    matricula = _matricula()
    uid = usuarios.criar(matricula, "Usuário de Teste", 2, senha.gerar_hash("Teste#2026abc", custo=4), "SP")
    assert usuarios.por_matricula(matricula)["id"] == uid

    motor = MotorAutenticacao(banco, ReconhecedorLBPH(), TrilhaAuditoria(banco))
    motivos = [motor.validar_credenciais(2, matricula, "errada")[2].motivo for _ in range(4)]
    assert motivos == [Motivo.SENHA_INCORRETA] * 3 + [Motivo.BLOQUEADO]
    assert bloqueios.esta_bloqueado(matricula)
    # mesmo com a senha certa, continua bloqueado
    assert motor.validar_credenciais(2, matricula, "Teste#2026abc")[2].motivo == Motivo.BLOQUEADO


def test_senha_correta_libera_para_etapa_facial(banco):
    usuarios = RepositorioUsuarios(banco)
    matricula = _matricula()
    usuarios.criar(matricula, "Outro Teste", 2, senha.gerar_hash("Teste#2026abc", custo=4), "SP")
    motor = MotorAutenticacao(banco, ReconhecedorLBPH(), TrilhaAuditoria(banco))
    usuario, ev, negada = motor.validar_credenciais(2, matricula, "Teste#2026abc")
    assert negada is None and usuario["matricula"] == matricula and ev.senha_ok


def test_acervo_filtrado_por_nivel_na_consulta(acervo_importado):
    repo = acervo_importado
    n1 = {i["codigo"] for i in repo.itens_para_nivel(1)}
    n2_sp = {i["codigo"] for i in repo.itens_para_nivel(2, "SP")}
    n3 = {i["codigo"] for i in repo.itens_para_nivel(3)}
    assert n1 == {"A1-01", "A1-02", "A1-05"}
    assert {"A2-01", "A2-06"} <= n2_sp and "A2-04" not in n2_sp      # A2-04 é do RJ
    assert not any(c.startswith("A3") for c in n2_sp)
    assert "A3-05" in n3                                              # sem revisão: só N3


def test_nivel_1_nao_le_responsaveis(acervo_importado, banco):
    pendencia = banco.consultar("SELECT id FROM pendencia LIMIT 1")[0]["id"]
    assert acervo_importado.responsaveis(pendencia, 1) == []
    assert len(acervo_importado.responsaveis(pendencia, 2)) >= 1
    assert acervo_importado.ficha_pendencia(pendencia, 1) is None


def test_entrega_registra_e_n3_nao_exporta(acervo_importado, banco):
    trilha = TrilhaAuditoria(banco)
    servico = ServicoAcervo(acervo_importado, trilha)
    uid = banco.consultar("SELECT id FROM usuario LIMIT 1")[0]["id"]
    item = banco.consultar("SELECT id FROM item_acervo WHERE codigo = 'A1-05'")[0]["id"]

    sessao_n3 = SessaoAutenticada(uid, "Teste", 3, None, datetime.now())
    _, imagem = servico.abrir(sessao_n3, item)
    with pytest.raises(AcessoNegado):
        servico.exportar(sessao_n3, item, imagem)

    sessao_n1 = SessaoAutenticada(uid, "Teste", 1, None, datetime.now())
    restrito = banco.consultar("SELECT id FROM item_acervo WHERE codigo = 'A3-01'")[0]["id"]
    with pytest.raises(AcessoNegado):
        servico.abrir(sessao_n1, restrito)

    ultimos = banco.consultar("SELECT evento, resultado, motivo FROM log_acesso ORDER BY id DESC LIMIT 3")
    assert [u["motivo"] for u in ultimos] == ["ACESSO_NEGADO_ITEM", "EXPORTACAO_BLOQUEADA_N3", "CONCEDIDO"]
    assert trilha.verificar().integra
