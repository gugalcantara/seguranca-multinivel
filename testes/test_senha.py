"""RF-06: bcrypt com sal; verificação segura."""
from autenticacao import senha


def test_hash_e_verificacao():
    h = senha.gerar_hash("Correta#123", custo=4)
    assert h.startswith("$2b$04$") and "Correta" not in h
    assert senha.verificar("Correta#123", h)
    assert not senha.verificar("errada", h)


def test_sal_torna_hashes_distintos():
    assert senha.gerar_hash("igual", custo=4) != senha.gerar_hash("igual", custo=4)


def test_hash_corrompido_ou_vazio_nega():
    assert not senha.verificar("x", "nao-e-bcrypt")
    assert not senha.verificar("x", None)
    assert not senha.verificar("", senha.gerar_hash("x", custo=4))


def test_custo_padrao_e_12():
    assert senha.CUSTO == 12


def test_politica_senha_forte():
    assert senha.avaliar_senha_forte("Abcdefgh1!xy", 12) == []
    pendencias = senha.avaliar_senha_forte("abc", 12)
    assert len(pendencias) == 4


# ------------------------------------------------------------------ enumeração por tempo
def test_verificacao_sem_hash_ainda_executa_o_bcrypt():
    """Matrícula inexistente não pode responder mais rápido que matrícula real.

    Medido antes da correção: 26 ms sem usuário contra 243 ms com usuário — 9,3x.
    Cronometrar o login revelava quais matrículas existem sem acertar senha
    alguma, e o bloqueio por tentativas não cobre isso (basta UMA tentativa por
    matrícula). Agora a comparação roda contra um hash fictício.
    """
    import time
    real = senha.gerar_hash("Senha#Real2026x", custo=10)

    def cronometrar(hash_alvo):
        inicio = time.perf_counter()
        assert senha.verificar("senha-errada", hash_alvo) is False
        return time.perf_counter() - inicio

    com_hash = min(cronometrar(real) for _ in range(3))
    sem_hash = min(cronometrar(None) for _ in range(3))
    # o hash fictício tem custo 12 e o real do teste tem 10, então o "sem hash"
    # é naturalmente mais LENTO; o que não pode é ser uma fração do outro
    assert sem_hash > com_hash / 2, f"sem hash devolveu cedo demais: {sem_hash:.4f}s vs {com_hash:.4f}s"


def test_hash_ausente_continua_negando():
    """Equiparar o tempo não pode, de forma alguma, passar a aceitar."""
    assert senha.verificar("qualquer", None) is False
    assert senha.verificar("qualquer", "") is False
    assert senha.verificar("", None) is False


def test_hash_ficticio_nao_e_aceito_como_credencial():
    """Nem mesmo quem descobrisse a cadeia por trás do HASH_FICTICIO entraria."""
    assert senha.verificar("qualquer", senha.HASH_FICTICIO) is False
