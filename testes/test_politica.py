"""RF-05, RF-07, RF-08 e princípio de falha segura."""
from autenticacao.politica import ConfirmadorFrames, Evidencias, Motivo, decidir

LIMIARES = {1: 70.0, 2: 60.0, 3: 50.0}
JANELA = 120


def ev_n1(**kw):
    base = dict(nivel_solicitado=1, usuario_id=7, usuario_nivel=1, usuario_ativo=True,
                qualidade_ok=True, distancia=40.0)
    return Evidencias(**{**base, **kw})


def ev_n2(**kw):
    base = dict(nivel_solicitado=2, usuario_id=7, usuario_nivel=2, usuario_ativo=True, bloqueado=False,
                senha_ok=True, qualidade_ok=True, distancia=40.0)
    return Evidencias(**{**base, **kw})


def ev_n3(**kw):
    base = dict(nivel_solicitado=3, usuario_id=7, usuario_nivel=3, usuario_ativo=True, bloqueado=False,
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
