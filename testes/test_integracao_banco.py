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


# ------------------------------------------------------------------ LGPD
def test_consentimento_e_registrado_e_vinculado_ao_usuario(banco):
    """Art. 8º, §2º: a evidência do consentimento precisa existir e ser recuperável."""
    from dados.repositorio import RepositorioConsentimento
    from lgpd import termo

    repo = RepositorioConsentimento(banco)
    consentimento_id = repo.registrar("Ana Ribeiro Salles", termo.VERSAO, termo.hash_termo())

    usuarios = RepositorioUsuarios(banco)
    uid = usuarios.criar(_matricula(), "Ana Ribeiro Salles", 2,
                         senha.gerar_hash("Teste#2026abc", custo=4), "SP")
    repo.vincular_usuario(consentimento_id, uid)

    registros = repo.do_usuario(uid)
    assert len(registros) == 1
    assert registros[0]["hash_termo"] == termo.hash_termo()
    assert registros[0]["versao_termo"] == termo.VERSAO
    assert registros[0]["revogado_em"] is None
    assert "APS PIVC" in registros[0]["finalidade"]      # finalidade específica, art. 9º


def test_revogacao_marca_sem_apagar_a_evidencia(banco):
    """Art. 8º, §5º: revogar é direito do titular — mas a baixa também é evidência.

    Apagar a linha destruiria a prova de que houve consentimento no período em
    que o dado foi tratado.
    """
    from dados.repositorio import RepositorioConsentimento
    from lgpd import termo

    repo = RepositorioConsentimento(banco)
    uid = RepositorioUsuarios(banco).criar(_matricula(), "Caio Lima", 1,
                                           senha.gerar_hash("Teste#2026abc", custo=4))
    repo.registrar("Caio Lima", termo.VERSAO, termo.hash_termo(), usuario_id=uid)

    assert repo.revogar(uid) == 1
    registros = repo.do_usuario(uid)
    assert len(registros) == 1                       # a linha continua lá
    assert registros[0]["revogado_em"] is not None   # marcada, não removida
    assert repo.revogar(uid) == 0                    # revogar de novo não duplica


def test_conta_da_aplicacao_nao_apaga_consentimento(banco_demonstracao):
    """A evidência do consentimento tem a mesma proteção da trilha: sem DELETE."""
    with pytest.raises(mysql.connector.Error) as erro:
        with banco_demonstracao.transacao() as cur:
            cur.execute("DELETE FROM consentimento WHERE id = -1")
    assert erro.value.errno == 1142        # DELETE command denied



# ------------------------------------------------------------------ nível 2 sem UF (auditoria)
def test_banco_recusa_diretor_de_nivel_2_sem_uf(banco):
    """A regra mora no schema: nenhum caminho — formulário, ferramenta ou SQL
    manual — consegue criar o diretor que, sem UF, veria todas as regiões."""
    with pytest.raises(mysql.connector.Error):
        RepositorioUsuarios(banco).criar(_matricula(), "Diretor sem região", 2, "$2b$12$" + "x" * 53)


def test_nivel_2_sem_uf_so_ve_itens_nacionais(acervo_importado):
    """Se um N2 sem UF existisse mesmo assim, o filtro falharia FECHADO."""
    todos = acervo_importado.itens_para_nivel(2, "SP")
    sem_uf = acervo_importado.itens_para_nivel(2, None)
    assert all(item["uf"] is None for item in sem_uf)
    assert len(sem_uf) < len(todos) or not any(i["uf"] for i in todos)



def test_consentimento_vigente_segue_o_aceite_e_a_revogacao(banco):
    """A pergunta que a decisão de acesso faz agora, contra o schema de verdade."""
    from dados.repositorio import RepositorioConsentimento
    from lgpd import termo

    repo = RepositorioConsentimento(banco)
    uid = RepositorioUsuarios(banco).criar(_matricula(), "Bia Torres", 1,
                                           senha.gerar_hash("Teste#2026abc", custo=4))
    assert repo.vigente(uid) is False                    # sem termo, sem base legal
    repo.registrar("Bia Torres", termo.VERSAO, termo.hash_termo(), usuario_id=uid)
    assert repo.vigente(uid) is True
    repo.revogar(uid)
    assert repo.vigente(uid) is False                    # revogado deixa de valer



def test_expurgo_elimina_so_as_fotos_vencidas(banco):
    """O DELETE que agora roda sozinho ao abrir o programa, contra o schema real:
    a foto vencida sai, a que ainda está no prazo fica, e a trilha não é tocada."""
    from cryptography.fernet import Fernet
    trilha = TrilhaAuditoria(banco)
    chave = Fernet.generate_key()
    vencida = trilha.registrar(novo_registro("AUTENTICACAO", 1, "NEGADO", "FACE_NAO_RECONHECIDA"))
    no_prazo = trilha.registrar(novo_registro("AUTENTICACAO", 1, "NEGADO", "FACE_NAO_RECONHECIDA"))
    trilha.anexar_foto_negada(vencida, b"jpeg-vencido", chave, dias_retencao=-1)
    trilha.anexar_foto_negada(no_prazo, b"jpeg-no-prazo", chave, dias_retencao=7)
    registros_antes = len(banco.consultar("SELECT id FROM log_acesso"))

    assert trilha.expurgar_fotos_expiradas() >= 1
    restantes = {r["log_id"] for r in banco.consultar("SELECT log_id FROM tentativa_negada")}
    assert vencida not in restantes and no_prazo in restantes
    assert len(banco.consultar("SELECT id FROM log_acesso")) == registros_antes
    assert trilha.verificar().integra
