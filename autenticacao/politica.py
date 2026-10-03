"""Política de fatores por nível — o coração da decisão de acesso.

Função pura: recebe as evidências já coletadas (senha conferida, distância
facial, desafio, segunda pessoa) e devolve CONCEDIDO ou NEGADO com o motivo.
Não toca em câmera nem em banco, por isso é testável isoladamente.

Princípio de falha segura: evidência ausente (None) conta como fator NÃO
cumprido. Nunca há caminho em que a falta de informação conceda acesso.

| Nível | Fatores                                                   | Modo  |
|-------|-----------------------------------------------------------|-------|
| 1     | face                                                      | 1:N   |
| 2     | matrícula + senha, depois face                            | 1:1   |
| 3     | matrícula + senha forte + face + desafio + regra dos dois | 1:1   |
"""
from dataclasses import dataclass, field
from enum import Enum


class Fator(str, Enum):
    FACE = "FACE"
    SENHA = "SENHA"
    SENHA_FORTE = "SENHA_FORTE"
    VIVACIDADE = "VIVACIDADE"
    REGRA_DOIS = "REGRA_DOIS"


FATORES_POR_NIVEL = {
    1: (Fator.FACE,),
    2: (Fator.SENHA, Fator.FACE),
    3: (Fator.SENHA, Fator.SENHA_FORTE, Fator.FACE, Fator.VIVACIDADE, Fator.REGRA_DOIS),
}


class Motivo(str, Enum):
    CONCEDIDO = "CONCEDIDO"
    NIVEL_INVALIDO = "NIVEL_INVALIDO"
    USUARIO_INEXISTENTE = "USUARIO_INEXISTENTE"
    USUARIO_INATIVO = "USUARIO_INATIVO"
    BLOQUEADO = "BLOQUEADO"
    SENHA_INCORRETA = "SENHA_INCORRETA"
    SENHA_FRACA = "SENHA_FRACA"
    QUALIDADE_INSUFICIENTE = "QUALIDADE_INSUFICIENTE"
    FACE_NAO_RECONHECIDA = "FACE_NAO_RECONHECIDA"
    CREDENCIAL_ALHEIA = "CREDENCIAL_ALHEIA"          # senha certa, face de outra pessoa
    NIVEL_INSUFICIENTE = "NIVEL_INSUFICIENTE"
    VIVACIDADE_NAO_CONFIRMADA = "VIVACIDADE_NAO_CONFIRMADA"
    SEGUNDA_PESSOA_AUSENTE = "SEGUNDA_PESSOA_AUSENTE"
    SEGUNDA_PESSOA_INVALIDA = "SEGUNDA_PESSOA_INVALIDA"
    JANELA_EXPIRADA = "JANELA_EXPIRADA"
    ERRO_INTERNO = "ERRO_INTERNO"


# Uma falha de identidade responde SEMPRE o mesmo, venha ela de face
# desconhecida ou de rosto que não casa com a matrícula. Dizer "não confere com
# a matrícula" confirmaria ao atacante que a SENHA estava certa — ele saberia
# que só falta o rosto. A distinção existe, mas apenas no motivo gravado na
# trilha, onde serve à auditoria e não a quem tenta entrar.
_IDENTIDADE_NAO_CONFIRMADA = ("Não foi possível confirmar a sua identidade. "
                              "Posicione o rosto no centro, com boa luz, e tente de novo.")

MENSAGENS = {
    Motivo.CONCEDIDO: "Acesso concedido.",
    Motivo.NIVEL_INVALIDO: "Nível de acesso inválido.",
    Motivo.USUARIO_INEXISTENTE: "Matrícula ou senha incorretas. Confira os dois campos.",
    Motivo.USUARIO_INATIVO: ("Este cadastro está inativo. Procure o administrador para reativá-lo."),
    Motivo.BLOQUEADO: ("Matrícula bloqueada por tentativas seguidas. Aguarde alguns minutos "
                       "ou procure o administrador."),
    Motivo.SENHA_INCORRETA: "Matrícula ou senha incorretas. Confira os dois campos.",
    Motivo.SENHA_FRACA: ("O nível 3 exige senha forte: ao menos 12 caracteres, com maiúscula, "
                         "minúscula, número e símbolo."),
    Motivo.QUALIDADE_INSUFICIENTE: ("Não foi possível obter uma imagem nítida o bastante. "
                                    "Melhore a iluminação e fique parado por um instante."),
    Motivo.FACE_NAO_RECONHECIDA: _IDENTIDADE_NAO_CONFIRMADA,
    Motivo.CREDENCIAL_ALHEIA: _IDENTIDADE_NAO_CONFIRMADA,
    Motivo.NIVEL_INSUFICIENTE: ("Seu nível de permissão não alcança este conteúdo. "
                                "Use um nível compatível ou solicite elevação ao administrador."),
    Motivo.VIVACIDADE_NAO_CONFIRMADA: ("Desafio não confirmado. Refaça o gesto pedido olhando "
                                       "para a câmera, sem sair do enquadramento."),
    Motivo.SEGUNDA_PESSOA_AUSENTE: ("O nível 3 exige uma segunda pessoa autorizada, que precisa "
                                    "se autenticar logo em seguida."),
    Motivo.SEGUNDA_PESSOA_INVALIDA: ("A segunda pessoa precisa ser outra identidade, também "
                                     "de nível 3."),
    Motivo.JANELA_EXPIRADA: ("O tempo para a segunda pessoa se autenticar terminou. "
                             "Recomece a autenticação."),
    Motivo.ERRO_INTERNO: ("Falha interna — acesso negado por segurança. "
                          "Procure o administrador e informe o horário da tentativa."),
}


@dataclass
class Evidencias:
    """O que o motor coletou durante a tentativa. None = não avaliado."""
    nivel_solicitado: int
    usuario_id: int | None = None          # identidade alegada (N2/N3) ou identificada (N1)
    usuario_nivel: int | None = None
    usuario_ativo: bool | None = None
    bloqueado: bool | None = None
    senha_ok: bool | None = None
    senha_forte: bool | None = None
    qualidade_ok: bool | None = None
    distancia: float | None = None          # LBPH: menor = mais parecido
    vivacidade_ok: bool | None = None
    segundo_usuario_id: int | None = None
    segundo_usuario_nivel: int | None = None
    segundo_autenticado: bool | None = None
    segundos_desde_primeiro: float | None = None


@dataclass
class Decisao:
    concedido: bool
    motivo: Motivo
    fatores_avaliados: list = field(default_factory=list)

    @property
    def mensagem(self):
        return MENSAGENS[self.motivo]


def decidir(ev: Evidencias, limiares: dict, janela_regra_dois: float, exigir_regra_dois=True) -> Decisao:
    """exigir_regra_dois=False avalia UMA pessoa no N3 (etapa individual da regra dos dois)."""
    avaliados = []

    def negar(motivo):
        return Decisao(False, motivo, avaliados)

    fatores = FATORES_POR_NIVEL.get(ev.nivel_solicitado)
    if fatores is None:
        return negar(Motivo.NIVEL_INVALIDO)

    # --- Fator de conhecimento (N2/N3): senha ANTES da face, transforma 1:N em 1:1
    if Fator.SENHA in fatores:
        if ev.bloqueado:
            return negar(Motivo.BLOQUEADO)
        if ev.usuario_id is None:
            return negar(Motivo.USUARIO_INEXISTENTE)
        avaliados.append(Fator.SENHA.value)
        if ev.senha_ok is not True:
            return negar(Motivo.SENHA_INCORRETA)
    if Fator.SENHA_FORTE in fatores:
        avaliados.append(Fator.SENHA_FORTE.value)
        if ev.senha_forte is not True:
            return negar(Motivo.SENHA_FRACA)

    # --- Fator de inerência
    avaliados.append(Fator.FACE.value)
    if ev.qualidade_ok is not True:
        return negar(Motivo.QUALIDADE_INSUFICIENTE)
    limiar = limiares.get(ev.nivel_solicitado)
    if ev.distancia is None or limiar is None or ev.distancia > limiar:
        # senha conferiu mas o rosto não: possível uso de credencial alheia
        if Fator.SENHA in fatores:
            return negar(Motivo.CREDENCIAL_ALHEIA)
        return negar(Motivo.FACE_NAO_RECONHECIDA)
    if ev.usuario_id is None:
        return negar(Motivo.FACE_NAO_RECONHECIDA)

    # --- Situação cadastral e nível (cada nível vê o que os de baixo veem)
    if ev.usuario_ativo is not True:
        return negar(Motivo.USUARIO_INATIVO)
    if ev.usuario_nivel is None or ev.usuario_nivel < ev.nivel_solicitado:
        return negar(Motivo.NIVEL_INSUFICIENTE)

    # --- Vivacidade (N3)
    if Fator.VIVACIDADE in fatores:
        avaliados.append(Fator.VIVACIDADE.value)
        if ev.vivacidade_ok is not True:
            return negar(Motivo.VIVACIDADE_NAO_CONFIRMADA)

    # --- Regra dos dois (N3): outra identidade, nível 3, autenticada dentro da janela
    if Fator.REGRA_DOIS in fatores and exigir_regra_dois:
        avaliados.append(Fator.REGRA_DOIS.value)
        if ev.segundo_usuario_id is None or ev.segundo_autenticado is not True:
            return negar(Motivo.SEGUNDA_PESSOA_AUSENTE)
        if ev.segundo_usuario_id == ev.usuario_id or (ev.segundo_usuario_nivel or 0) < 3:
            return negar(Motivo.SEGUNDA_PESSOA_INVALIDA)
        if ev.segundos_desde_primeiro is None or ev.segundos_desde_primeiro > janela_regra_dois:
            return negar(Motivo.JANELA_EXPIRADA)

    return Decisao(True, Motivo.CONCEDIDO, avaliados)


class ConfirmadorFrames:
    """Pós-processamento: só decide após N frames coerentes seguidos.

    Coerente = mesma identidade e distância dentro do limiar. Qualquer frame
    divergente zera a contagem. Devolve (usuario_id, distancia_media) quando
    confirmado, ou None enquanto não houver confirmação.
    """

    def __init__(self, n_frames, limiar):
        self.n = n_frames
        self.limiar = limiar
        self._rotulo = None
        self._distancias = []

    def alimentar(self, rotulo, distancia):
        if rotulo is None or distancia > self.limiar or rotulo != self._rotulo:
            self._rotulo = rotulo if (rotulo is not None and distancia <= self.limiar) else None
            self._distancias = [distancia] if self._rotulo is not None else []
        else:
            self._distancias.append(distancia)
        if self._rotulo is not None and len(self._distancias) >= self.n:
            return self._rotulo, sum(self._distancias) / len(self._distancias)
        return None

    @property
    def confirmados(self):
        """Quantos frames coerentes seguidos já entraram — a tela usa para
        mostrar o progresso em vez de um 'aguarde' indefinido."""
        return len(self._distancias)

    def reiniciar(self):
        self._rotulo = None
        self._distancias = []
