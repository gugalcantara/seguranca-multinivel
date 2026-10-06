"""RF-05, RF-07, RF-08 e princípio de falha segura."""
import pytest

from autenticacao.politica import ConfirmadorFrames, Evidencias, Motivo, decidir

LIMIARES = {1: 70.0, 2: 60.0, 3: 50.0}
JANELA = 120


def ev_n1(**kw):
    base = dict(nivel_solicitado=1, usuario_id=7, usuario_nivel=1, usuario_ativo=True, consentimento_ok=True,
                qualidade_ok=True, distancia=40.0)
    return Evidencias(**{**base, **kw})


def ev_n2(**kw):
    base = dict(nivel_solicitado=2, usuario_id=7, usuario_nivel=2, usuario_ativo=True, consentimento_ok=True, bloqueado=False,
                senha_ok=True, qualidade_ok=True, distancia=40.0)
    return Evidencias(**{**base, **kw})


def ev_n3(**kw):
    base = dict(nivel_solicitado=3, usuario_id=7, usuario_nivel=3, usuario_ativo=True, consentimento_ok=True, bloqueado=False,
                senha_ok=True, senha_forte=True, qualidade_ok=True, distancia=30.0, vivacidade_ok=True,
                segundo_usuario_id=8, segundo_usuario_nivel=3, segundo_autenticado=True,
                segundos_desde_primeiro=30)
    return Evidencias(**{**base, **kw})


def test_n1_concede_face_reconhecida():
    assert decidir(ev_n1(), LIMIARES, JANELA).concedido


def test_lbph_e_distancia_menor_e_melhor():
    # distância ACIMA do limiar é rejeição — inverter isto inverte a política inteira
    d = decidir(ev_n1(distancia=70.01), LIMIARES, JANELA)
    assert not d.concedido and d.motivo == Motivo.FACE_NAO_RECONHECIDA
    assert decidir(ev_n1(distancia=70.0), LIMIARES, JANELA).concedido


def test_falha_segura_evidencia_ausente_nega():
    for campo in ("distancia", "qualidade_ok", "usuario_ativo", "usuario_nivel"):
        assert not decidir(ev_n1(**{campo: None}), LIMIARES, JANELA).concedido, campo


def test_nivel_invalido():
    assert decidir(ev_n1(nivel_solicitado=4), LIMIARES, JANELA).motivo == Motivo.NIVEL_INVALIDO


def test_n2_senha_incorreta():
    assert decidir(ev_n2(senha_ok=False), LIMIARES, JANELA).motivo == Motivo.SENHA_INCORRETA


def test_n2_senha_certa_face_errada_e_credencial_alheia():
    assert decidir(ev_n2(distancia=90.0), LIMIARES, JANELA).motivo == Motivo.CREDENCIAL_ALHEIA


def test_n2_bloqueado():
    assert decidir(ev_n2(bloqueado=True), LIMIARES, JANELA).motivo == Motivo.BLOQUEADO


def test_nivel_insuficiente():
    assert decidir(ev_n2(usuario_nivel=1), LIMIARES, JANELA).motivo == Motivo.NIVEL_INSUFICIENTE


def test_nivel_superior_ve_niveis_abaixo():
    assert decidir(ev_n2(usuario_nivel=3), LIMIARES, JANELA).concedido


def test_limiar_mais_restrito_no_n3():
    # 55 passa no N2 (limiar 60) mas não no N3 (limiar 50)
    assert decidir(ev_n2(distancia=55.0), LIMIARES, JANELA).concedido
    assert not decidir(ev_n3(distancia=55.0), LIMIARES, JANELA).concedido


def test_n3_completo_concede():
    d = decidir(ev_n3(), LIMIARES, JANELA)
    assert d.concedido
    assert d.fatores_avaliados == ["SENHA", "SENHA_FORTE", "FACE", "VIVACIDADE", "REGRA_DOIS"]


def test_n3_senha_fraca():
    assert decidir(ev_n3(senha_forte=False), LIMIARES, JANELA).motivo == Motivo.SENHA_FRACA


def test_n3_sem_vivacidade():
    assert decidir(ev_n3(vivacidade_ok=False), LIMIARES, JANELA).motivo == Motivo.VIVACIDADE_NAO_CONFIRMADA


def test_n3_regra_dois_uma_pessoa_so():
    assert decidir(ev_n3(segundo_usuario_id=None), LIMIARES, JANELA).motivo == Motivo.SEGUNDA_PESSOA_AUSENTE


def test_n3_regra_dois_mesma_pessoa_duas_vezes():
    assert decidir(ev_n3(segundo_usuario_id=7), LIMIARES, JANELA).motivo == Motivo.SEGUNDA_PESSOA_INVALIDA


def test_n3_regra_dois_segunda_pessoa_nivel_baixo():
    assert decidir(ev_n3(segundo_usuario_nivel=2), LIMIARES, JANELA).motivo == Motivo.SEGUNDA_PESSOA_INVALIDA


def test_n3_regra_dois_janela_expirada():
    assert decidir(ev_n3(segundos_desde_primeiro=121), LIMIARES, JANELA).motivo == Motivo.JANELA_EXPIRADA


def test_n3_etapa_individual_dispensa_regra_dois():
    ev = ev_n3(segundo_usuario_id=None)
    assert decidir(ev, LIMIARES, JANELA, exigir_regra_dois=False).concedido


def test_confirmador_exige_frames_coerentes_seguidos():
    c = ConfirmadorFrames(3, 60)
    assert c.alimentar(1, 40) is None
    assert c.alimentar(1, 45) is None
    assert c.alimentar(2, 40) is None          # identidade divergente zera
    assert c.alimentar(2, 41) is None
    assert c.alimentar(2, 80) is None          # acima do limiar zera
    for _ in range(2):
        assert c.alimentar(2, 50) is None
    rotulo, media = c.alimentar(2, 50)
    assert rotulo == 2 and media == 50


# ------------------------------------------------------------------ o que a mensagem revela
def test_falha_de_identidade_responde_sempre_o_mesmo():
    """Regressão de vazamento: a tela não pode confirmar que a senha estava certa.

    Antes, CREDENCIAL_ALHEIA dizia "não confere com a matrícula informada" — quem
    tivesse a senha e não o rosto sabia que acertara metade. O motivo distinto
    continua existindo, mas só na trilha, onde serve à auditoria.
    """
    from autenticacao.politica import MENSAGENS
    assert MENSAGENS[Motivo.CREDENCIAL_ALHEIA] == MENSAGENS[Motivo.FACE_NAO_RECONHECIDA]
    texto = MENSAGENS[Motivo.CREDENCIAL_ALHEIA].lower()
    for revelador in ("senha", "matrícula", "confere", "correta"):
        assert revelador not in texto, f"a mensagem deixa deduzir: {revelador}"

    # a distinção segue viva para a auditoria
    alheia = decidir(ev_n2(distancia=90.0), LIMIARES, JANELA)
    desconhecida = decidir(ev_n1(distancia=90.0), LIMIARES, JANELA)
    assert alheia.motivo == Motivo.CREDENCIAL_ALHEIA
    assert desconhecida.motivo == Motivo.FACE_NAO_RECONHECIDA
    assert alheia.mensagem == desconhecida.mensagem        # ...mas a tela não distingue


def test_matricula_inexistente_e_senha_errada_sao_indistinguiveis():
    """Enumerar usuários pela mensagem seria tão eficaz quanto pelo tempo."""
    from autenticacao.politica import MENSAGENS
    assert MENSAGENS[Motivo.USUARIO_INEXISTENTE] == MENSAGENS[Motivo.SENHA_INCORRETA]


def test_toda_mensagem_de_negacao_diz_o_que_fazer():
    """Mensagem que só nega deixa a pessoa sem saída — e gera chamado ao suporte."""
    from autenticacao.politica import MENSAGENS
    sem_acao = {Motivo.CONCEDIDO, Motivo.NIVEL_INVALIDO}
    verbos = ("confira", "aguarde", "procure", "tente", "use", "refaça", "recomece",
              "posicione", "melhore", "precisa", "solicite", "exige")
    for motivo, mensagem in MENSAGENS.items():
        if motivo in sem_acao:
            continue
        assert any(v in mensagem.lower() for v in verbos), f"{motivo.value} não orienta: {mensagem}"


# ------------------------------------------------------------------ regra dos dois desligada
def test_fatores_do_nivel_remove_a_regra_dos_dois_quando_desligada():
    from autenticacao.politica import Fator, fatores_do_nivel
    assert Fator.REGRA_DOIS in fatores_do_nivel(3)
    assert Fator.REGRA_DOIS not in fatores_do_nivel(3, exigir_segunda_pessoa=False)
    # os demais fatores do N3 continuam todos lá
    assert len(fatores_do_nivel(3, exigir_segunda_pessoa=False)) == len(fatores_do_nivel(3)) - 1
    # e os outros níveis não são tocados
    assert fatores_do_nivel(1, exigir_segunda_pessoa=False) == fatores_do_nivel(1)
    assert fatores_do_nivel(2, exigir_segunda_pessoa=False) == fatores_do_nivel(2)
    assert fatores_do_nivel(9) is None


def test_n3_de_uma_pessoa_concede_com_a_regra_desligada():
    d = decidir(ev_n3(segundo_usuario_id=None), LIMIARES, JANELA, exigir_segunda_pessoa=False)
    assert d.concedido


def test_regra_desligada_nao_lista_REGRA_DOIS_entre_os_fatores_avaliados():
    """O que a trilha grava precisa refletir o que foi de fato exigido."""
    d = decidir(ev_n3(segundo_usuario_id=None), LIMIARES, JANELA, exigir_segunda_pessoa=False)
    assert d.fatores_avaliados == ["SENHA", "SENHA_FORTE", "FACE", "VIVACIDADE"]


@pytest.mark.parametrize("quebra, motivo", [
    ({"senha_ok": False}, Motivo.SENHA_INCORRETA),
    ({"senha_forte": False}, Motivo.SENHA_FRACA),
    ({"vivacidade_ok": False}, Motivo.VIVACIDADE_NAO_CONFIRMADA),
    ({"qualidade_ok": False}, Motivo.QUALIDADE_INSUFICIENTE),
    ({"usuario_ativo": False}, Motivo.USUARIO_INATIVO),
    ({"usuario_nivel": 2}, Motivo.NIVEL_INSUFICIENTE),
])
def test_desligar_a_regra_nao_afrouxa_nenhum_outro_fator(quebra, motivo):
    """Dispensar a segunda pessoa não pode virar uma porta lateral para o N3."""
    d = decidir(ev_n3(segundo_usuario_id=None, **quebra), LIMIARES, JANELA,
                exigir_segunda_pessoa=False)
    assert not d.concedido and d.motivo == motivo
