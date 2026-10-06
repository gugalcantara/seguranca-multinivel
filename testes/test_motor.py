"""Máquina de estados da tentativa facial (autenticacao/motor.py).

A política pura já é coberta em test_politica.py e o banco em
test_integracao_banco.py. O que falta — e é o que se testa aqui — é a
ORQUESTRAÇÃO frame a frame: quando a identidade é dada por confirmada, quando o
nível 3 entra no desafio em vez de conceder, e o que acontece ao estourar o
tempo. Tudo com dublês: sem câmera, sem banco, sem relógio real.
"""
import numpy as np
import pytest

import configuracao
from autenticacao.motor import MotorAutenticacao
from autenticacao.politica import Evidencias, Motivo
from autenticacao.vivacidade import Estado
from visao.qualidade import ResultadoQualidade

FRAME = np.zeros((480, 640, 3), np.uint8)
CINZA = np.zeros((480, 640), np.uint8)
FACE = np.full((200, 200), 128, np.uint8)

USUARIO_N2 = {"id": 7, "matricula": "AB12CD3", "nome": "Ana", "nivel_id": 2, "uf": "SP",
              "ativo": 1, "senha_hash": "x"}
USUARIO_N3 = {**USUARIO_N2, "id": 9, "nome": "Helena", "nivel_id": 3, "uf": None}


class AnaliseDuble:
    def __init__(self, aprovado=True, rotulo=7, distancia=30.0, retangulo=(10, 10, 120, 120)):
        self.qualidade = ResultadoQualidade(aprovado, "OK" if aprovado else "DESFOCADO",
                                            "", escore=0.9 if aprovado else 0.1)
        self.rotulo, self.distancia = rotulo, distancia
        self.retangulos = [retangulo] if retangulo else []
        self.face, self.cinza = FACE, CINZA

    @property
    def retangulo(self):
        return self.retangulos[0] if len(self.retangulos) == 1 else None


class PipelineDuble:
    def __init__(self, analise):
        self.analise = analise
        self.segmentador = type("S", (), {"reiniciar": lambda s: None})()
        self.chamadas = 0

    def analisar(self, frame, usuario_alegado=None, reconhecer=True):
        self.chamadas += 1
        return self.analise


class DesafioDuble:
    def __init__(self, estados):
        self.estados = list(estados)
        self.desafio = "PISCAR"
        self.instrucao = "Pisque os olhos devagar."

    def sortear(self):
        return self.desafio

    def alimentar(self, _cinza, _rf):
        return self.estados.pop(0) if self.estados else Estado.EM_ANDAMENTO


class TrilhaDuble:
    def __init__(self):
        self.registros = []

    def registrar(self, registro):
        self.registros.append(registro)
        return len(self.registros)

    def anexar_foto_negada(self, *_a, **_k):
        pass


class BancoDuble:
    def __init__(self, usuarios=(), sem_consentimento=()):
        self.usuarios = list(usuarios)
        # por padrão todo usuário consentiu; os testes de consentimento listam quem não
        self.sem_consentimento = set(sem_consentimento)

    def consultar(self, sql, parametros=()):
        s = " ".join(sql.split())
        if "FROM consentimento" in s and "revogado_em IS NULL" in s:
            return [] if parametros[0] in self.sem_consentimento else [{"vigente": 1}]
        if "FROM usuario WHERE id" in s:
            return [u for u in self.usuarios if u["id"] == parametros[0]]
        if "FROM usuario WHERE matricula" in s:
            return [u for u in self.usuarios if u["matricula"] == parametros[0]]
        if "FROM bloqueio" in s:
            return []
        raise AssertionError(f"consulta não prevista: {s[:70]}")


def ev_com_senha(nivel, usuario_id):
    """Evidências como validar_credenciais as entrega: o fator de conhecimento
    já foi conferido antes da câmera abrir (é ele que torna o N2/N3 um 1:1)."""
    return Evidencias(nivel_solicitado=nivel, usuario_id=usuario_id, bloqueado=False,
                      senha_ok=True, senha_forte=nivel == 3)


def montar(nivel, analise=None, usuario=None, usuarios_no_banco=(), ev=None,
           exigir_segunda_pessoa=True, sem_consentimento=()):
    """exigir_segunda_pessoa é EXPLÍCITO aqui de propósito.

    O config.ini pode desligar a regra dos dois, e vários testes deste módulo
    existem para verificar justamente a regra ligada. Deixá-los herdar o valor do
    arquivo faria a cobertura da regra evaporar em silêncio no dia em que alguém
    a desligasse — que foi exatamente o que aconteceu quando o padrão mudou.
    """
    banco = BancoDuble(usuarios_no_banco, sem_consentimento)
    trilha = TrilhaDuble()
    motor = MotorAutenticacao(banco, None, trilha, configuracao.carregar())
    motor.exigir_segunda_pessoa = exigir_segunda_pessoa
    motor.pipeline = PipelineDuble(analise or AnaliseDuble())
    tentativa = motor.iniciar_face(nivel, ev or Evidencias(nivel_solicitado=nivel), usuario)
    return motor, tentativa, trilha


def frames_ate_concluir(tentativa, limite=20):
    """Alimenta até a tentativa fechar; devolve o último Status."""
    for _ in range(limite):
        status = tentativa.alimentar(FRAME)
        if status.fase == "CONCLUIDA":
            return status
    return status


# ------------------------------------------------------------------ nível 1
def test_n1_so_decide_apos_frames_coerentes_seguidos():
    """Pós-processamento: um frame isolado não autentica ninguém."""
    cfg = configuracao.carregar()
    n = cfg.getint("autenticacao", "frames_confirmacao")
    _, tentativa, _ = montar(1, usuarios_no_banco=[{**USUARIO_N2, "id": 7, "nivel_id": 1}])

    for _ in range(n - 1):
        assert tentativa.alimentar(FRAME).fase == "FACE"
    assert tentativa.alimentar(FRAME).fase == "CONCLUIDA"


def test_n1_concede_quando_a_face_e_reconhecida():
    _, tentativa, trilha = montar(1, usuarios_no_banco=[{**USUARIO_N2, "id": 7, "nivel_id": 1}])
    status = frames_ate_concluir(tentativa)
    assert status.decisao.concedido
    assert trilha.registros[-1]["resultado"] == "CONCEDIDO"


def test_qualidade_ruim_zera_a_contagem():
    """Frame reprovado não só é ignorado: ele reinicia a sequência."""
    cfg = configuracao.carregar()
    n = cfg.getint("autenticacao", "frames_confirmacao")
    motor, tentativa, _ = montar(1, usuarios_no_banco=[{**USUARIO_N2, "id": 7, "nivel_id": 1}])

    for _ in range(n - 1):
        tentativa.alimentar(FRAME)
    motor.pipeline.analise = AnaliseDuble(aprovado=False)      # um frame ruim
    assert tentativa.alimentar(FRAME).fase == "FACE"
    motor.pipeline.analise = AnaliseDuble()
    for _ in range(n - 1):
        assert tentativa.alimentar(FRAME).fase == "FACE"       # recomeçou do zero
    assert tentativa.alimentar(FRAME).fase == "CONCLUIDA"


def test_distancia_acima_do_limiar_nunca_confirma():
    """LBPH devolve DISTÂNCIA: acima do limiar é rejeição, por mais frames que venham.

    A tentativa segue em FACE até o tempo acabar — não conceder é o resultado
    certo, e só o timeout a encerra.
    """
    _, tentativa, trilha = montar(1, AnaliseDuble(distancia=999.0))
    for _ in range(15):
        assert tentativa.alimentar(FRAME).fase == "FACE"
    assert trilha.registros == []


# ------------------------------------------------------------------ tempo
def test_timeout_facial_nega_sem_travar(monkeypatch):
    relogio = {"t": 1000.0}
    monkeypatch.setattr("autenticacao.motor.time.monotonic", lambda: relogio["t"])
    _, tentativa, trilha = montar(1, AnaliseDuble(aprovado=False))

    tentativa.alimentar(FRAME)
    relogio["t"] += configuracao.carregar().getfloat("autenticacao", "timeout_face") + 1
    status = tentativa.alimentar(FRAME)
    assert status.fase == "CONCLUIDA" and not status.decisao.concedido
    assert trilha.registros[-1]["resultado"] == "NEGADO"


# ------------------------------------------------------------------ nível 3
def test_n3_nao_concede_na_face_entra_no_desafio():
    """Face reconhecida no N3 é só o começo: falta vivacidade e a segunda pessoa."""
    _, tentativa, _ = montar(3, usuario=USUARIO_N3, ev=ev_com_senha(3, 9))
    tentativa.desafio = DesafioDuble([Estado.EM_ANDAMENTO])
    cfg = configuracao.carregar()

    for _ in range(cfg.getint("autenticacao", "frames_confirmacao") - 1):
        assert tentativa.alimentar(FRAME).fase == "FACE"
    status = tentativa.alimentar(FRAME)
    assert status.fase == "VIVACIDADE"
    assert "Pisque" in status.mensagem


def test_n3_vivacidade_confirmada_fecha_a_etapa_individual():
    _, tentativa, _ = montar(3, usuario=USUARIO_N3, ev=ev_com_senha(3, 9))
    tentativa.desafio = DesafioDuble([Estado.EM_ANDAMENTO, Estado.CONFIRMADO])
    status = frames_ate_concluir(tentativa)
    assert status.decisao.concedido          # individual: a regra dos dois vem depois
    assert tentativa.ev.vivacidade_ok is True


def test_n3_vivacidade_expirada_nega():
    _, tentativa, _ = montar(3, usuario=USUARIO_N3, ev=ev_com_senha(3, 9))
    tentativa.desafio = DesafioDuble([Estado.EXPIRADO])
    status = frames_ate_concluir(tentativa)
    assert not status.decisao.concedido
    assert status.decisao.motivo == Motivo.VIVACIDADE_NAO_CONFIRMADA


def test_etapa_individual_do_n3_nao_vai_sozinha_para_a_trilha():
    """Registrar a etapa individual como concedida daria a entender que o N3
    abriu sem a segunda pessoa. O registro vem no concluir_regra_dois()."""
    _, tentativa, trilha = montar(3, usuario=USUARIO_N3, ev=ev_com_senha(3, 9))
    tentativa.desafio = DesafioDuble([Estado.CONFIRMADO])
    status = frames_ate_concluir(tentativa)
    assert status.decisao.concedido
    assert trilha.registros == []


# ------------------------------------------------------------------ regra dos dois
def test_regra_dos_dois_exige_outra_identidade_de_nivel_3():
    motor, _, trilha = montar(3, usuario=USUARIO_N3,
                              usuarios_no_banco=[USUARIO_N3, {**USUARIO_N3, "id": 11}])
    ev_a = Evidencias(nivel_solicitado=3, usuario_id=9, usuario_nivel=3, usuario_ativo=True, consentimento_ok=True,
                      senha_ok=True, senha_forte=True, qualidade_ok=True, distancia=30.0,
                      vivacidade_ok=True)
    ev_b = Evidencias(**{**vars(ev_a), "usuario_id": 11})

    decisao, sessao = motor.concluir_regra_dois(ev_a, 100.0, ev_b, 130.0)
    assert decisao.concedido and sessao is not None
    assert sessao.usuario2_id == 11
    assert trilha.registros[-1]["resultado"] == "CONCEDIDO"


def test_regra_dos_dois_recusa_a_mesma_pessoa_duas_vezes():
    motor, _, _ = montar(3, usuario=USUARIO_N3, usuarios_no_banco=[USUARIO_N3])
    ev = Evidencias(nivel_solicitado=3, usuario_id=9, usuario_nivel=3, usuario_ativo=True, consentimento_ok=True,
                    senha_ok=True, senha_forte=True, qualidade_ok=True, distancia=30.0,
                    vivacidade_ok=True)
    decisao, sessao = motor.concluir_regra_dois(ev, 100.0, Evidencias(**vars(ev)), 130.0)
    assert not decisao.concedido and sessao is None
    assert decisao.motivo == Motivo.SEGUNDA_PESSOA_INVALIDA


def test_segunda_pessoa_fora_da_janela_nao_vale():
    motor, _, _ = montar(3, usuario=USUARIO_N3, usuarios_no_banco=[USUARIO_N3])
    ev_a = Evidencias(nivel_solicitado=3, usuario_id=9, usuario_nivel=3, usuario_ativo=True, consentimento_ok=True,
                      senha_ok=True, senha_forte=True, qualidade_ok=True, distancia=30.0,
                      vivacidade_ok=True)
    ev_b = Evidencias(**{**vars(ev_a), "usuario_id": 11})
    janela = configuracao.carregar().getfloat("autenticacao", "janela_regra_dois")

    decisao, sessao = motor.concluir_regra_dois(ev_a, 100.0, ev_b, 100.0 + janela + 1)
    assert not decisao.concedido and sessao is None
    assert decisao.motivo == Motivo.JANELA_EXPIRADA


def test_sessao_de_nivel_3_nasce_com_prazo():
    motor, _, _ = montar(3, usuario=USUARIO_N3, usuarios_no_banco=[USUARIO_N3])
    ev = Evidencias(nivel_solicitado=3, usuario_id=9)
    sessao = motor.abrir_sessao(ev)
    assert sessao.expira_em is not None and sessao.expira_em > sessao.inicio


def test_sessao_de_nivel_1_nao_expira():
    motor, _, _ = montar(1, usuarios_no_banco=[{**USUARIO_N2, "id": 7, "nivel_id": 1}])
    sessao = motor.abrir_sessao(Evidencias(nivel_solicitado=1, usuario_id=7))
    assert sessao.expira_em is None


# ------------------------------------------------------------------ regra dos dois DESLIGADA
def test_n3_com_uma_pessoa_concede_quando_a_regra_esta_desligada():
    """config.ini pode dispensar a segunda pessoa; o resto do N3 continua valendo."""
    _, tentativa, trilha = montar(3, usuario=USUARIO_N3, ev=ev_com_senha(3, 9),
                                  exigir_segunda_pessoa=False)
    tentativa.desafio = DesafioDuble([Estado.CONFIRMADO])
    status = frames_ate_concluir(tentativa)
    assert status.decisao.concedido


def test_n3_de_uma_pessoa_so_ENTRA_na_trilha():
    """O furo mais fácil de abrir ao desligar a regra.

    Com a regra ligada, quem registra o desfecho do N3 é concluir_regra_dois().
    Se ela não roda mais, o registro tem de passar a sair da etapa individual —
    senão o nível mais sensível do sistema concederia acesso sem deixar rastro,
    e a trilha mostraria apenas as negativas.
    """
    _, tentativa, trilha = montar(3, usuario=USUARIO_N3, ev=ev_com_senha(3, 9),
                                  exigir_segunda_pessoa=False)
    tentativa.desafio = DesafioDuble([Estado.CONFIRMADO])
    frames_ate_concluir(tentativa)

    assert trilha.registros, "acesso de nível 3 concedido sem registro na trilha"
    assert trilha.registros[-1]["resultado"] == "CONCEDIDO"
    assert trilha.registros[-1]["nivel_solicitado"] == 3


def test_regra_desligada_nao_grava_REGRA_DOIS_como_fator_avaliado():
    """Registrar um fator que não foi exigido é pior que não registrar nada:
    a auditoria leria "duas pessoas conferiram" onde houve uma só."""
    _, tentativa, trilha = montar(3, usuario=USUARIO_N3, ev=ev_com_senha(3, 9),
                                  exigir_segunda_pessoa=False)
    tentativa.desafio = DesafioDuble([Estado.CONFIRMADO])
    frames_ate_concluir(tentativa)

    assert "REGRA_DOIS" not in trilha.registros[-1]["fatores_avaliados"]
    assert "VIVACIDADE" in trilha.registros[-1]["fatores_avaliados"]   # o resto continua


def test_desligar_a_regra_nao_afrouxa_os_demais_fatores_do_n3():
    """Sem vivacidade, o N3 continua negando — a dispensa é só da segunda pessoa."""
    _, tentativa, _ = montar(3, usuario=USUARIO_N3, ev=ev_com_senha(3, 9),
                             exigir_segunda_pessoa=False)
    tentativa.desafio = DesafioDuble([Estado.EXPIRADO])
    status = frames_ate_concluir(tentativa)
    assert not status.decisao.concedido


def test_motor_responde_se_ainda_ha_segunda_etapa():
    """Uma pergunta, um lugar: tela e motor consultam a mesma resposta."""
    com, _, _ = montar(3, usuario=USUARIO_N3, exigir_segunda_pessoa=True)
    sem, _, _ = montar(3, usuario=USUARIO_N3, exigir_segunda_pessoa=False)
    assert com.aguarda_segunda_pessoa(3) and not com.aguarda_segunda_pessoa(2)
    assert not sem.aguarda_segunda_pessoa(3)



# ------------------------------------------------------------------ consentimento (auditoria)
def test_titular_que_revogou_e_negado_mesmo_ativo_e_reconhecido():
    """O achado da auditoria, como teste.

    Revogar desativava o usuário, mas o rosto continuava no modelo e o campo
    `ativo` podia ser religado. Com a face certa, a senha certa e o cadastro
    ATIVO, o acesso tem de ser negado se não houver consentimento vigente.
    """
    _, tentativa, trilha = montar(2, usuario=USUARIO_N2, ev=ev_com_senha(2, 7),
                                  usuarios_no_banco=[USUARIO_N2], sem_consentimento={7})
    status = frames_ate_concluir(tentativa)
    assert not status.decisao.concedido
    assert status.decisao.motivo == Motivo.CONSENTIMENTO_AUSENTE
    assert trilha.registros[-1]["motivo"] == "CONSENTIMENTO_AUSENTE"   # e fica na trilha


def test_consentimento_vale_tambem_no_nivel_1():
    """O N1 não pede senha, mas trata a face do mesmo jeito: a base legal é a mesma."""
    analise = AnaliseDuble(rotulo=7, distancia=20.0)
    _, tentativa, _ = montar(1, analise=analise, usuarios_no_banco=[{**USUARIO_N2, "nivel_id": 1}],
                             sem_consentimento={7})
    status = frames_ate_concluir(tentativa)
    assert status.decisao.motivo == Motivo.CONSENTIMENTO_AUSENTE
