"""Motor de autenticação multifator (INC-03): orquestra senha, face, vivacidade,
regra dos dois, bloqueio e trilha de auditoria.

O motor não abre câmera nem janela: a interface alimenta frames e lê o estado.
Fluxo:
    N1:  iniciar_face(1) -> alimentar(frame)... -> concluída
    N2:  validar_credenciais -> iniciar_face(2, usuario) -> alimentar... -> concluída
    N3:  pessoa A: validar_credenciais(senha forte) -> face -> vivacidade -> etapa individual
         pessoa B: idem, dentro da janela -> concluir_regra_dois(A, B)

Com `exigir_segunda_pessoa = false` no config.ini, o N3 termina na etapa
individual: não há pessoa B, e concluir_regra_dois() não chega a ser chamado.
Atenção a quem mexer nesse caminho — é concluir_regra_dois() quem registra o
desfecho do N3 na trilha quando a regra está ligada. Sem ele, o registro precisa
sair de finalizar_individual(), senão o nível mais sensível do sistema concede
acesso sem deixar rastro. Quem responde "ainda há segunda etapa?" é
aguarda_segunda_pessoa().

Toda decisão final passa por politica.decidir() e vai para a trilha encadeada.
Toda exceção vira NEGADO (falha segura).
"""
import time
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

import cv2

import configuracao
from acervo.tarja import AcessoNegado
from autenticacao import politica, senha
from autenticacao.politica import ConfirmadorFrames, Decisao, Evidencias, Motivo
from autenticacao.vivacidade import DesafioVivacidade, Estado
from dados.auditoria import novo_registro
from dados.repositorio import RepositorioBloqueio, RepositorioUsuarios
from visao.pipeline import PipelineFacial


@dataclass
class SessaoAutenticada:
    usuario_id: int
    nome: str
    nivel: int
    uf: str | None
    inicio: datetime
    expira_em: datetime | None = None
    usuario2_id: int | None = None

    def exigir_valida(self):
        if self.expira_em and datetime.now() > self.expira_em:
            raise AcessoNegado("Sessão de nível 3 expirada — autentique-se novamente")


@dataclass
class Status:
    fase: str                      # FACE | VIVACIDADE | CONCLUIDA
    mensagem: str
    analise: object = None
    decisao: Decisao | None = None


class TentativaFacial:
    """Estado de uma tentativa facial em curso, alimentada frame a frame."""

    def __init__(self, motor, evidencias, usuario=None):
        self.motor = motor
        self.ev = evidencias
        self.usuario = usuario
        nivel = evidencias.nivel_solicitado
        self.confirmador = ConfirmadorFrames(motor.cfg.getint("autenticacao", "frames_confirmacao"),
                                             configuracao.limiar(nivel))
        self.prazo = time.monotonic() + motor.cfg.getfloat("autenticacao", "timeout_face")
        self.desafio = DesafioVivacidade(motor.cfg) if nivel == 3 else None
        self.fase = "FACE"
        self.ultimo_frame = None
        self.ultima_qualidade = None
        motor.pipeline.segmentador.reiniciar()

    @property
    def segundos_restantes(self):
        """Tempo que resta na etapa facial, para a tela poder mostrar a contagem."""
        return max(0.0, self.prazo - time.monotonic())

    def alimentar(self, frame):
        self.ultimo_frame = frame
        alegado = self.usuario["id"] if self.usuario else None
        analise = self.motor.pipeline.analisar(frame, usuario_alegado=alegado)
        if analise.qualidade.escore:
            self.ultima_qualidade = analise.qualidade

        if self.fase == "FACE":
            if time.monotonic() > self.prazo:
                return self._encerrar_facial(analise)
            if not analise.qualidade.aprovado:
                self.confirmador.reiniciar()
                return Status("FACE", analise.qualidade.mensagem, analise)
            confirmado = self.confirmador.alimentar(analise.rotulo, analise.distancia)
            if not confirmado:
                return Status("FACE", "Analisando… mantenha o rosto parado.", analise)
            self.ev.usuario_id, self.ev.distancia = confirmado
            self.ev.qualidade_ok = True
            if self.desafio is None:
                return self._concluir(analise)
            self.desafio.sortear()
            self.fase = "VIVACIDADE"
            return Status("VIVACIDADE", self.desafio.instrucao, analise)

        # fase VIVACIDADE (N3)
        estado = self.desafio.alimentar(analise.cinza, analise.retangulo)
        if estado == Estado.EM_ANDAMENTO:
            return Status("VIVACIDADE", self.desafio.instrucao, analise)
        self.ev.vivacidade_ok = estado == Estado.CONFIRMADO
        return self._concluir(analise)

    def _encerrar_facial(self, analise):
        """Tempo esgotado sem confirmação: nega com o melhor diagnóstico disponível."""
        self.ev.qualidade_ok = bool(self.ultima_qualidade and self.ultima_qualidade.aprovado)
        if analise.distancia is not None:
            self.ev.distancia = analise.distancia
        return self._concluir(analise)

    def _concluir(self, analise):
        self.fase = "CONCLUIDA"
        decisao = self.motor.finalizar_individual(self.ev, self.usuario, self.ultimo_frame,
                                                  self.ultima_qualidade)
        return Status("CONCLUIDA", decisao.mensagem, analise, decisao)


class MotorAutenticacao:
    def __init__(self, banco, reconhecedor, trilha, cfg=None):
        self.cfg = cfg or configuracao.carregar()
        self.usuarios = RepositorioUsuarios(banco)
        self.bloqueios = RepositorioBloqueio(banco)
        self.trilha = trilha
        self.pipeline = PipelineFacial(reconhecedor, self.cfg)
        self.limiares = {n: configuracao.limiar(n) for n in (1, 2, 3)}
        self.janela = self.cfg.getfloat("autenticacao", "janela_regra_dois")
        # ligada, o N3 só concede com DUAS pessoas; desligada, uma basta (ver config.ini)
        self.exigir_segunda_pessoa = self.cfg.getboolean(
            "autenticacao", "exigir_segunda_pessoa", fallback=True)

    def aguarda_segunda_pessoa(self, nivel):
        """True quando a autenticação deste nível ainda terá uma segunda etapa.

        Um só lugar responde a essa pergunta, e tanto o motor quanto a tela a
        consultam. Espalhar `nivel == 3` pelo código foi o que fez a regra dos
        dois ficar difícil de desligar: a condição aparecia escrita de formas
        diferentes em cada camada.
        """
        return nivel == 3 and self.exigir_segunda_pessoa

    # ------------------------------------------------------------ etapa 1: conhecimento
    def validar_credenciais(self, nivel, matricula, senha_digitada):
        """N2/N3. Devolve (usuario, evidencias, decisao_negativa_ou_None)."""
        ev = Evidencias(nivel_solicitado=nivel)
        try:
            ev.bloqueado = self.bloqueios.esta_bloqueado(matricula)
            usuario = None if ev.bloqueado else self.usuarios.por_matricula(matricula)
            if not ev.bloqueado:
                # a verificação roda mesmo sem usuário: senha.verificar() compara
                # contra um hash fictício para que o TEMPO de resposta não revele
                # se a matrícula existe (medido: 26 ms contra 243 ms antes disso)
                ev.senha_ok = senha.verificar(senha_digitada,
                                              usuario["senha_hash"] if usuario else None)
            if usuario:
                ev.usuario_id = usuario["id"]
                if nivel == 3:
                    minimo = self.cfg.getint("autenticacao", "senha_forte_min_caracteres")
                    ev.senha_forte = not senha.avaliar_senha_forte(senha_digitada, minimo)
            # decisão parcial: só os fatores de conhecimento
            parcial = politica.decidir(ev, self.limiares, self.janela)
            if parcial.motivo in (Motivo.BLOQUEADO, Motivo.USUARIO_INEXISTENTE,
                                  Motivo.SENHA_INCORRETA, Motivo.SENHA_FRACA):
                if parcial.motivo in (Motivo.SENHA_INCORRETA, Motivo.USUARIO_INEXISTENTE):
                    self.bloqueios.registrar_falha(
                        matricula, self.cfg.getint("autenticacao", "tentativas_senha"),
                        self.cfg.getint("autenticacao", "bloqueio_minutos"))
                self._registrar(ev, parcial, matricula=matricula)
                return None, ev, parcial
            self.bloqueios.zerar(matricula)
            return usuario, ev, None
        except Exception:
            return None, ev, self._erro(ev, matricula)

    # ------------------------------------------------------------ etapa 2: inerência
    def iniciar_face(self, nivel, evidencias=None, usuario=None):
        return TentativaFacial(self, evidencias or Evidencias(nivel_solicitado=nivel), usuario)

    def finalizar_individual(self, ev, usuario, frame, qualidade):
        """Fecha a tentativa de UMA pessoa. No N3 isso ainda não concede a sessão."""
        try:
            if usuario is None and ev.usuario_id is not None:          # N1: identidade veio do 1:N
                usuario = self.usuarios.por_id(ev.usuario_id)
                if usuario is None:
                    ev.usuario_id = None
            if usuario:
                ev.usuario_nivel = usuario["nivel_id"]
                ev.usuario_ativo = bool(usuario["ativo"])
            # exigir_segunda_pessoa aqui é redundante POR CONSTRUÇÃO: com
            # exigir_regra_dois=False o bloco da regra já não roda, e o resultado
            # é idêntico com qualquer valor. Fica explícito mesmo assim, para que
            # a chamada continue correta se um dia esta etapa passar a avaliar a
            # regra — e para que ninguém leia a ausência como "aqui a config não vale".
            decisao = politica.decidir(ev, self.limiares, self.janela, exigir_regra_dois=False,
                                       exigir_segunda_pessoa=self.exigir_segunda_pessoa)
            # No N3 com a regra dos dois LIGADA, o desfecho ainda não existe: quem
            # registra é concluir_regra_dois(), depois da segunda pessoa. Em todo
            # outro caso esta é a decisão final e precisa entrar na trilha aqui —
            # senão um acesso de nível 3 concedido a uma pessoa só não deixaria rastro.
            if not decisao.concedido or not self.aguarda_segunda_pessoa(ev.nivel_solicitado):
                self._registrar(ev, decisao, qualidade=qualidade, frame=frame)
            return decisao
        except Exception:
            return self._erro(ev)

    # ------------------------------------------------------------ etapa 3: sessão
    def abrir_sessao(self, ev, segundo=None):
        usuario = self.usuarios.por_id(ev.usuario_id)
        agora = datetime.now()
        expira = None
        if ev.nivel_solicitado == 3:
            expira = agora + timedelta(minutes=self.cfg.getint("autenticacao", "sessao_n3_minutos"))
        return SessaoAutenticada(usuario["id"], usuario["nome"], ev.nivel_solicitado, usuario["uf"],
                                 agora, expira, segundo.usuario_id if segundo else None)

    def concluir_regra_dois(self, ev_a, instante_a, ev_b=None, instante_b=None):
        """N3: combina as duas etapas individuais. ev_b=None registra a ausência da segunda pessoa.
        instante_* vêm de time.monotonic()."""
        ev = replace(ev_a)
        if ev_b is not None:
            ev.segundo_usuario_id = ev_b.usuario_id
            ev.segundo_usuario_nivel = ev_b.usuario_nivel
            ev.segundo_autenticado = politica.decidir(ev_b, self.limiares, self.janela,
                                                      exigir_regra_dois=False).concedido
            ev.segundos_desde_primeiro = instante_b - instante_a
        decisao = politica.decidir(ev, self.limiares, self.janela,
                                   exigir_segunda_pessoa=self.exigir_segunda_pessoa)
        self._registrar(ev, decisao)
        return decisao, (self.abrir_sessao(ev, ev_b) if decisao.concedido else None)

    # ------------------------------------------------------------ trilha
    def _registrar(self, ev, decisao, matricula=None, qualidade=None, frame=None):
        registro = novo_registro(
            "AUTENTICACAO", ev.nivel_solicitado, "CONCEDIDO" if decisao.concedido else "NEGADO",
            decisao.motivo, usuario_id=ev.usuario_id, usuario2_id=ev.segundo_usuario_id,
            matricula_informada=matricula, fatores_avaliados=decisao.fatores_avaliados,
            distancia=ev.distancia, qualidade=qualidade.escore if qualidade else None)
        log_id = self.trilha.registrar(registro)
        if not decisao.concedido and frame is not None:
            chave = configuracao.env("CHAVE_CIFRAGEM", obrigatorio=False)
            if chave:
                ok, jpeg = cv2.imencode(".jpg", frame)
                if ok:
                    self.trilha.anexar_foto_negada(log_id, jpeg.tobytes(), chave,
                                                   self.cfg.getint("auditoria", "retencao_foto_negada_dias"))
        return log_id

    def _erro(self, ev, matricula=None):
        decisao = Decisao(False, Motivo.ERRO_INTERNO)
        try:
            self._registrar(ev, decisao, matricula=matricula)
        except Exception:
            pass   # banco fora do ar: a negação vale mesmo sem log
        return decisao
