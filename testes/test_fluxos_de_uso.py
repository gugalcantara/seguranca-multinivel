"""O cadastro do começo ao fim: o caminho certo e os caminhos que a pessoa
realmente faz quando desiste, fecha a janela errada ou clica duas vezes.

Por que este módulo existe: `DialogoNovoUsuario._concluir` grava o usuário,
treina o modelo e apaga a biometria — as três coisas mais sensíveis do sistema —
e não tinha nenhum teste. As falhas abaixo foram encontradas sondando a tela,
não lendo o código, e cada teste nomeia o desfecho ruim que ele impede.

A regra que atravessa o módulo: imagem de rosto é dado pessoal SENSÍVEL (LGPD
art. 5º, II) e só pode existir enquanto for necessária (art. 6º, III e V; ETP
4.3). Toda saída da tela — concluir, cancelar, Esc, o X, fechar a janela de
trás, falhar no meio — tem de terminar sem face nenhuma em memória.
"""
from datetime import datetime

import numpy as np
import pytest

import configuracao
from visao.coleta import ColetorAmostras

# o módulo inteiro depende de Tk; a raiz em si vem do conftest
pytest.importorskip("tkinter")

import tkinter as tk                                         # noqa: E402
from interface.comum import Contexto                         # noqa: E402
from testes.test_painel import TrilhaDuble                   # noqa: E402

CHAVE = "chave-de-teste"


# ------------------------------------------------------------------ dublês
class UsuariosDuble:
    def __init__(self):
        self.criados = []
        self.desativados = []
        self.amostras = []
        self.falhar_ao_criar = False

    def nova_matricula(self):
        return "R0902G8"

    def por_matricula(self, matricula):
        return None

    def criar(self, matricula, nome, nivel_id, senha_hash, uf=None):
        if self.falhar_ao_criar:
            raise RuntimeError("banco indisponível")
        self.criados.append({"matricula": matricula, "nome": nome, "nivel": nivel_id, "uf": uf})
        return 42

    def definir_ativo(self, usuario_id, ativo):
        self.desativados.append((usuario_id, ativo))

    def registrar_amostras(self, usuario_id, sessao, qualidades, origem="webcam"):
        self.amostras.append((usuario_id, sessao, len(qualidades), origem))


class ConsentimentosDuble:
    def __init__(self):
        self.registros = []

    def registrar(self, titular_nome, versao, hash_termo, momento=None, usuario_id=None):
        self.registros.append({"nome": titular_nome, "versao": versao, "hash": hash_termo,
                               "momento": momento, "usuario_id": usuario_id})
        return 1


class ReconhecedorDuble:
    """Guarda o que recebeu para treino; pode falhar ao salvar, como um disco cheio."""

    def __init__(self, falhar_ao_salvar=False):
        self.treinado = True
        self.faces_recebidas = 0
        self.salvo = False
        self.falhar_ao_salvar = falhar_ao_salvar

    def atualizar(self, faces, rotulos):
        self.faces_recebidas = len(faces)

    def salvar(self, caminho, chave):
        if self.falhar_ao_salvar:
            raise OSError("não foi possível gravar o modelo")
        self.salvo = True


class MensagensDuble:
    """Captura os modais para que o teste leia o que a pessoa veria na tela."""

    def __init__(self):
        self.mostradas = []

    def _registrar(self, tipo):
        def mostrar(titulo, texto, **kw):
            self.mostradas.append((tipo, titulo, texto))
        return mostrar

    def __getattr__(self, nome):
        return self._registrar(nome)

    @property
    def textos(self):
        """Título e corpo juntos — a pessoa lê os dois, o teste também."""
        return " ".join(f"{titulo} {texto}" for _, titulo, texto in self.mostradas)


class MotorMinimo:
    """Só o que a tela de autenticação consulta ao se construir.

    A janela pergunta ao motor se o nível ainda terá uma segunda etapa — antes
    de montar qualquer widget. Um `motor=None` quebraria na construção, longe do
    que o teste quer verificar.
    """

    def __init__(self, exigir_segunda_pessoa=True):
        self.exigir_segunda_pessoa = exigir_segunda_pessoa

    def aguarda_segunda_pessoa(self, nivel):
        return nivel == 3 and self.exigir_segunda_pessoa


# ------------------------------------------------------------------ fixtures
@pytest.fixture
def ctx():
    usuarios = UsuariosDuble()
    contexto = Contexto(cfg=configuracao.carregar(), banco=None, trilha=TrilhaDuble(),
                        reconhecedor=ReconhecedorDuble(), motor=MotorMinimo(), acervo=None,
                        usuarios=usuarios, consentimentos=ConsentimentosDuble())
    from visao.aquisicao import WebcamIndisponivel
    contexto.camera = lambda: (_ for _ in ()).throw(WebcamIndisponivel("sem câmera no teste"))
    return contexto


@pytest.fixture
def mensagens(monkeypatch):
    duble = MensagensDuble()
    monkeypatch.setattr("interface.cadastro.messagebox", duble)
    return duble


@pytest.fixture
def com_chave(monkeypatch):
    monkeypatch.setattr(configuracao, "env",
                        lambda nome, obrigatorio=True: CHAVE if "CHAVE" in nome else None)


@pytest.fixture
def dialogo(raiz, ctx):
    from interface.cadastro import DialogoNovoUsuario
    janela = DialogoNovoUsuario(raiz, ctx)
    janela.withdraw()
    janela.campos["nome"].insert(0, "Ana Ribeiro Salles")
    for chave in ("senha", "confirmacao"):
        janela.campos[chave].insert(0, "Aps#2026forte")
    janela._consentimento = {"momento": datetime(2026, 10, 2, 14, 30), "nome": "Ana Ribeiro Salles"}
    return janela


def coletores(quantidade=2, por_sessao=5):
    saida = []
    for sessao in range(1, quantidade + 1):
        c = ColetorAmostras(sessao, configuracao.carregar())
        c.faces.extend(np.zeros((200, 200), np.uint8) for _ in range(por_sessao))
        c.qualidades.extend([0.8] * por_sessao)
        saida.append(c)
    return saida


def faces_vivas(lista):
    return sum(len(c.faces) for c in lista)


# ================================================================== caminho padrão
def test_cadastro_completo_grava_usuario_consentimento_e_amostras(dialogo, ctx, mensagens,
                                                                  com_chave):
    lotes = coletores()
    dialogo._concluir({"matricula": "R0902G8", "nome": "Ana Ribeiro Salles",
                       "senha": "Aps#2026forte"}, 2, lotes)

    assert ctx.usuarios.criados == [{"matricula": "R0902G8", "nome": "Ana Ribeiro Salles",
                                     "nivel": 2, "uf": None}]
    assert ctx.reconhecedor.faces_recebidas == 10        # as faces chegaram ao treino
    assert ctx.reconhecedor.salvo
    assert [(u, s, n) for u, s, n, _ in ctx.usuarios.amostras] == [(42, 1, 5), (42, 2, 5)]
    assert ctx.consentimentos.registros[0]["usuario_id"] == 42
    assert ctx.consentimentos.registros[0]["momento"] == datetime(2026, 10, 2, 14, 30)
    assert ctx.trilha.registros[-1]["motivo"] == "CADASTRO_USUARIO"
    assert "R0902G8" in mensagens.textos                 # a matrícula é dita à pessoa


def test_cadastro_bem_sucedido_nao_deixa_face_em_memoria(dialogo, ctx, mensagens, com_chave):
    """O desfecho feliz também apaga: treinar não autoriza a guardar."""
    lotes = coletores()
    dialogo._concluir({"matricula": "R0902G8", "nome": "Ana", "senha": "Aps#2026forte"}, 1, lotes)
    assert faces_vivas(lotes) == 0


def test_entrega_dos_coletores_preserva_as_faces_ate_o_treino(raiz, ctx):
    """Regressão do gancho de descarte: ele não pode apagar antes da hora.

    A captura passou a apagar as faces em <Destroy> para cobrir o fechamento
    pela janela de trás. Como concluir também destrói a janela, o descarte
    precisava abrir exceção para a entrega — senão o cadastro treinaria com zero
    amostras e ninguém seria reconhecido depois.
    """
    from interface.cadastro import JanelaCaptura
    recebidos = []
    janela = JanelaCaptura(raiz, ctx, recebidos.append)
    janela.withdraw()
    janela.coletores.extend(coletores(quantidade=1))
    janela._entregues = True
    janela.destroy()
    assert recebidos == [] and faces_vivas(janela.coletores) == 5


# ================================================================== fora do roteiro
def test_falha_ao_salvar_o_modelo_desativa_o_usuario(dialogo, ctx, mensagens, com_chave):
    """Usuário no banco sem rosto no modelo é o pior estado possível: o sistema
    diz que ele existe e só descobriria o contrário na próxima tentativa dele."""
    ctx.reconhecedor.falhar_ao_salvar = True
    lotes = coletores()
    dialogo._concluir({"matricula": "R0902G8", "nome": "Ana", "senha": "Aps#2026forte"}, 2, lotes)

    assert ctx.usuarios.desativados == [(42, False)]
    assert ctx.trilha.registros[-1]["motivo"] == "CADASTRO_FALHOU"
    assert "DESATIVADO" in mensagens.textos
    assert faces_vivas(lotes) == 0                      # falhar não autoriza reter


def test_falha_ao_criar_o_usuario_tambem_apaga_as_faces(dialogo, ctx, mensagens, com_chave):
    ctx.usuarios.falhar_ao_criar = True
    lotes = coletores()
    dialogo._concluir({"matricula": "R0902G8", "nome": "Ana", "senha": "Aps#2026forte"}, 1, lotes)

    assert ctx.usuarios.criados == [] and ctx.usuarios.desativados == []
    assert faces_vivas(lotes) == 0
    assert "não concluído" in mensagens.textos.lower()


def test_sem_chave_de_cifragem_nada_e_criado_e_nada_fica_retido(dialogo, ctx, mensagens,
                                                                monkeypatch):
    monkeypatch.setattr(configuracao, "env", lambda nome, obrigatorio=True: None)
    lotes = coletores()
    dialogo._concluir({"matricula": "R0902G8", "nome": "Ana", "senha": "Aps#2026forte"}, 1, lotes)

    assert ctx.usuarios.criados == []
    assert faces_vivas(lotes) == 0
    assert "CHAVE_CIFRAGEM" in mensagens.textos


def test_importacao_entrega_as_faces_ao_cadastro_sem_apaga_las(raiz, ctx):
    """A entrega tem de escapar do gancho de descarte, como na captura ao vivo.

    Sem essa ressalva, concluir o cadastro por arquivos destruiria a janela,
    o <Destroy> apagaria as faces e o treino receberia zero amostras — o
    cadastro "daria certo" e ninguem seria reconhecido depois.
    """
    from interface.cadastro import JanelaImportarImagens
    recebidos = []
    janela = JanelaImportarImagens(raiz, ctx, recebidos.append)
    janela.withdraw()
    janela.coletores.extend(coletores(quantidade=1, por_sessao=janela.minimo))

    janela._concluir()
    assert len(recebidos) == 1
    assert faces_vivas(recebidos[0]) == janela.minimo


def test_importacao_nao_conclui_abaixo_do_minimo(raiz, ctx):
    """Botao desabilitado nao e garantia: o metodo tambem precisa recusar."""
    from interface.cadastro import JanelaImportarImagens
    recebidos = []
    janela = JanelaImportarImagens(raiz, ctx, recebidos.append)
    janela.withdraw()
    janela.coletores.extend(coletores(quantidade=1, por_sessao=1))

    janela._concluir()
    assert recebidos == [] and janela.winfo_exists()
    janela._cancelar()


def test_fechar_a_importacao_de_imagens_pelo_x_apaga_as_faces(raiz, ctx):
    """Antes, só o botão «Cancelar» descartava: fechar pelo X retinha tudo."""
    from interface.cadastro import JanelaImportarImagens
    janela = JanelaImportarImagens(raiz, ctx, lambda c: None)
    janela.withdraw()
    janela.coletores.extend(coletores(quantidade=1))
    assert janela.protocol("WM_DELETE_WINDOW"), "o X precisa estar ligado ao cancelamento"

    janela.destroy()                                     # o X, no limite, cai aqui
    assert faces_vivas(janela.coletores) == 0


def test_escape_na_importacao_de_imagens_cancela_e_apaga(raiz, ctx):
    """As duas telas de cadastro respondem ao Esc do mesmo jeito.

    A captura ao vivo ja fechava com Esc; a importacao por arquivos, nao — e
    teclar Esc numa e esperar o mesmo da outra e o reflexo natural de quem usa
    as duas no mesmo cadastro.
    """
    from interface.cadastro import JanelaImportarImagens
    janela = JanelaImportarImagens(raiz, ctx, lambda c: None)
    janela.coletores.extend(coletores(quantidade=1))
    guardados = list(janela.coletores)
    # a raiz da suíte fica oculta, e uma janela transient de raiz oculta não
    # chega a ser mapeada — o foco ficaria na raiz e o Esc nunca chegaria aqui.
    # Desfazer o vínculo reproduz o que o aplicativo real tem: janela visível e
    # com foco. Sem isto o teste passaria por engano, testando nada.
    janela.transient("")
    janela.deiconify()
    janela.focus_force()
    raiz.update()

    janela.event_generate("<Escape>", when="now")
    raiz.update()
    assert not janela.winfo_exists() and faces_vivas(guardados) == 0


def test_fechar_a_janela_de_tras_durante_a_captura_apaga_as_faces(raiz, ctx):
    """A pessoa fecha o formulário de cadastro e a captura morre junto.

    Esse caminho não passa por _cancelar, então o descarte precisa estar
    pendurado no <Destroy> da própria janela.
    """
    from interface.cadastro import JanelaCaptura
    pai = tk.Toplevel(raiz)
    pai.withdraw()
    janela = JanelaCaptura(pai, ctx, lambda c: None)
    janela.withdraw()
    janela.coletores.extend(coletores(quantidade=2))
    guardados = list(janela.coletores)

    pai.destroy()
    assert faces_vivas(guardados) == 0


def test_escape_na_captura_cancela_e_apaga(raiz, ctx):
    from interface.cadastro import JanelaCaptura
    janela = JanelaCaptura(raiz, ctx, lambda c: None)
    janela.coletores.extend(coletores(quantidade=1))
    guardados = list(janela.coletores)
    janela.deiconify()
    janela.focus_force()
    raiz.update()

    janela.event_generate("<Escape>", when="now")
    raiz.update()
    assert not janela.winfo_exists() and faces_vivas(guardados) == 0


def test_cancelar_duas_vezes_nao_levanta_erro(raiz, ctx):
    """Esc e o X em sequência rápida: o segundo cancelamento não pode estourar."""
    from interface.cadastro import JanelaCaptura
    janela = JanelaCaptura(raiz, ctx, lambda c: None)
    janela.withdraw()
    janela._cancelar()
    janela._cancelar()


def test_iniciar_sessao_duas_vezes_nao_abre_sessao_dupla(raiz, ctx, monkeypatch):
    """Duas sessões simultâneas disputariam o mesmo laço de vídeo."""
    from interface.cadastro import JanelaCaptura

    class CameraFalsa:
        def ler(self, timeout=0.5):
            return np.full((480, 640, 3), 90, np.uint8)

    ctx.camera = lambda: CameraFalsa()
    janela = JanelaCaptura(raiz, ctx, lambda c: None)
    janela.withdraw()
    janela._iniciar_sessao()
    janela._iniciar_sessao()
    assert len(janela.coletores) == 1
    janela._cancelar()


def test_captura_sem_webcam_explica_e_deixa_tentar_de_novo(raiz, ctx, mensagens):
    """Falhar a câmera não pode travar a tela: a pessoa precisa poder repetir."""
    from interface.cadastro import JanelaCaptura
    janela = JanelaCaptura(raiz, ctx, lambda c: None)
    janela.withdraw()
    janela._iniciar_sessao()

    assert str(janela.botao.cget("state")) == "normal"
    assert janela.preparo.winfo_manager() == "pack"       # o checklist continua à vista
    assert "Privacidade" in mensagens.textos              # diz onde o Windows bloqueia
    janela._cancelar()


# ------------------------------------------------------------------ termo
def test_duplo_clique_em_concordo_dispara_um_cadastro_so(raiz):
    """Sem a guarda, o callback abria DUAS capturas para a mesma pessoa."""
    from interface.termo import DialogoTermo
    decisoes = []
    dialogo = DialogoTermo(raiz, "Ana Ribeiro Salles", lambda ok, m: decisoes.append(ok))
    dialogo.withdraw()
    dialogo.grab_release()

    dialogo._aceitar()
    dialogo._aceitar()
    assert decisoes == [True]


def test_fechar_o_termo_pelo_x_vale_como_recusa(raiz):
    """O silêncio não é consentimento (LGPD art. 8º): fechar é recusar."""
    from interface.termo import DialogoTermo
    decisoes = []
    dialogo = DialogoTermo(raiz, "Ana Ribeiro Salles", lambda ok, m: decisoes.append((ok, m)))
    dialogo.withdraw()
    dialogo.grab_release()

    dialogo.tk.call(dialogo.protocol("WM_DELETE_WINDOW"))
    assert decisoes == [(False, None)]


def test_aceite_so_libera_depois_de_rolar_o_termo(raiz):
    """Um «li e concordo» que nunca pôde ser lido é consentimento duvidoso."""
    from interface.termo import DialogoTermo
    dialogo = DialogoTermo(raiz, "Ana Ribeiro Salles", lambda ok, m: None)
    dialogo.withdraw()
    dialogo.grab_release()
    raiz.update()

    assert str(dialogo.caixa.cget("state")) == "disabled"
    assert str(dialogo.botao_aceitar.cget("state")) == "disabled"


def test_recusar_o_termo_registra_na_trilha_e_nao_abre_captura(dialogo, ctx, mensagens):
    """A recusa é um evento auditável — e não pode custar nada a quem recusa."""
    abertas = []
    dialogo._com_consentimento(lambda dados, nivel: abertas.append((dados, nivel)))
    termo = [f for f in dialogo.winfo_children() if f.winfo_class() == "Toplevel"][-1]
    termo.withdraw()
    termo.grab_release()

    termo._recusar()
    assert abertas == []
    assert ctx.trilha.registros[-1]["motivo"] == "CONSENTIMENTO_RECUSADO"
    assert "prejuízo" in mensagens.textos


# ------------------------------------------------------------------ validação do formulário
@pytest.mark.parametrize("campos, nivel, uf, trecho", [
    ({"nome": "", "senha": "Aps#2026forte", "confirmacao": "Aps#2026forte"}, 1, "", "nome"),
    ({"nome": "Ana", "senha": "Aps#2026forte", "confirmacao": "outra"}, 1, "", "não conferem"),
    ({"nome": "Ana", "senha": "123", "confirmacao": "123"}, 1, "", "fraca"),
    ({"nome": "Ana", "senha": "Aps#2026forte", "confirmacao": "Aps#2026forte"}, 2, "", "UF"),
])
def test_formulario_recusa_entrada_invalida_antes_de_abrir_a_camera(raiz, ctx, mensagens,
                                                                    campos, nivel, uf, trecho):
    """Validar antes da captura evita gastar 40 frames para só então recusar."""
    from interface.cadastro import DialogoNovoUsuario
    janela = DialogoNovoUsuario(raiz, ctx)
    janela.withdraw()
    for chave, valor in campos.items():
        janela.campos[chave].delete(0, "end")
        janela.campos[chave].insert(0, valor)
    janela.nivel.set(str(nivel))
    janela._ajustar_uf()
    if uf:
        janela.uf.set(uf)

    assert janela._validar() is None
    assert trecho.lower() in mensagens.textos.lower()


# ------------------------------------------------------------------ regra dos dois (N3)
class MotorRegraDois:
    """Registra se a tentativa da primeira pessoa chegou a ser encerrada."""

    def __init__(self, exigir_segunda_pessoa=True):
        self.encerramentos = []
        self.exigir_segunda_pessoa = exigir_segunda_pessoa

    def aguarda_segunda_pessoa(self, nivel):
        return nivel == 3 and self.exigir_segunda_pessoa

    def concluir_regra_dois(self, ev_a, instante_a, ev_b=None, instante_b=None):
        self.encerramentos.append(ev_a)

        class Final:
            mensagem = "janela da regra dos dois expirou"
        return Final(), None

    def validar_credenciais(self, *argumentos):
        return None, None, None


def autenticacao_aguardando_segunda_pessoa(raiz, ctx):
    """Estado real do nível 3 logo após a primeira pessoa passar."""
    from interface.autenticacao import JanelaAutenticacao
    janela = JanelaAutenticacao(raiz, ctx, 3, lambda sessao: None)
    janela.withdraw()
    janela.primeira_pessoa = ("evento-da-primeira-pessoa", 0.0)
    return janela


@pytest.mark.parametrize("como_sai", ["cancelar", "x_da_janela", "janela_de_tras"])
def test_desistir_da_regra_dos_dois_encerra_a_tentativa(raiz, ctx, como_sai):
    """Uma tentativa de nível 3 não pode ficar em aberto na trilha.

    A primeira pessoa já se autenticou e o sistema espera a segunda. Se alguém
    simplesmente fecha a janela, o acesso iniciado precisa receber um desfecho —
    na auditoria, acesso em aberto é indistinguível de acesso concedido.
    """
    ctx.motor = MotorRegraDois()
    if como_sai == "janela_de_tras":
        pai = tk.Toplevel(raiz)
        pai.withdraw()
        autenticacao_aguardando_segunda_pessoa(pai, ctx)
        pai.destroy()
    else:
        janela = autenticacao_aguardando_segunda_pessoa(raiz, ctx)
        if como_sai == "cancelar":
            janela.fechar()
        else:
            janela.tk.call(janela.protocol("WM_DELETE_WINDOW"))

    assert ctx.motor.encerramentos == ["evento-da-primeira-pessoa"]


def test_regra_dos_dois_e_encerrada_ANTES_de_a_janela_ser_destruida(raiz, ctx):
    """Nao basta encerrar; tem de encerrar com a janela ainda inteira.

    Deixar isso so para o gancho de <Destroy> significaria falar com o motor no
    meio da desmontagem dos widgets. Funciona, mas e o pior momento possivel
    para uma escrita de auditoria: se algo falhar ali, nao ha mais tela para
    avisar ninguem.
    """
    estados = []

    class MotorQueObserva(MotorRegraDois):
        def concluir_regra_dois(self, ev_a, instante_a, ev_b=None, instante_b=None):
            estados.append(bool(janela.winfo_exists()))
            return super().concluir_regra_dois(ev_a, instante_a, ev_b, instante_b)

    ctx.motor = MotorQueObserva()
    janela = autenticacao_aguardando_segunda_pessoa(raiz, ctx)
    janela.fechar()
    assert estados == [True], "o encerramento ocorreu durante a destruicao da janela"


def test_encerramento_da_regra_dos_dois_nao_repete(raiz, ctx):
    """Fechar depois de já ter encerrado não pode registrar o desfecho duas vezes."""
    ctx.motor = MotorRegraDois()
    janela = autenticacao_aguardando_segunda_pessoa(raiz, ctx)
    janela.fechar()
    janela._encerrar_regra_dois_pendente()
    assert len(ctx.motor.encerramentos) == 1


def test_falha_do_motor_ao_encerrar_nao_impede_fechar_a_janela(raiz, ctx, caplog):
    """A janela está fechando: o erro não tem para onde subir, mas tem de ficar no log."""
    class MotorQuebrado(MotorRegraDois):
        def concluir_regra_dois(self, *argumentos, **nomeados):
            raise RuntimeError("banco caiu durante o encerramento")

    ctx.motor = MotorQuebrado()
    janela = autenticacao_aguardando_segunda_pessoa(raiz, ctx)
    janela.fechar()

    assert not janela.winfo_exists()
    assert "regra dos dois" in caplog.text


def test_autenticacao_sem_webcam_nega_e_deixa_repetir(raiz, ctx):
    """Nível 1 vai direto à câmera; sem ela, o acesso é negado — e não travado."""
    from interface.autenticacao import JanelaAutenticacao
    janela = JanelaAutenticacao(raiz, ctx, 1, lambda sessao: None)
    janela.withdraw()

    assert "negado" in str(janela.status.cget("text")).lower()
    assert janela.tentar.winfo_manager() == ""      # só aparece após uma negação de fato


# ------------------------------------------------------------------ portão administrativo
class BloqueiosDuble:
    def __init__(self, bloqueado=False):
        self.bloqueado = bloqueado
        self.falhas = []
        self.zeramentos = []

    def esta_bloqueado(self, matricula, agora=None):
        return self.bloqueado

    def registrar_falha(self, matricula, maximo, minutos, agora=None):
        self.falhas.append(matricula)
        return len(self.falhas) >= maximo

    def zerar(self, matricula):
        self.zeramentos.append(matricula)


@pytest.fixture
def portao(monkeypatch, ctx):
    """Monta o portao administrativo com senha, dialogo e bloqueio dublados."""
    from autenticacao import senha as modulo_senha
    bloqueios = BloqueiosDuble()
    mensagens = MensagensDuble()
    digitado = {"valor": "correta"}

    ctx.banco = object()                       # basta nao ser None
    monkeypatch.setattr("interface.comum._bloqueios", lambda c: bloqueios)
    monkeypatch.setattr("interface.comum.messagebox", mensagens)
    monkeypatch.setattr("interface.comum.simpledialog",
                        type("D", (), {"askstring": staticmethod(
                            lambda *a, **k: digitado["valor"])})())
    monkeypatch.setattr(configuracao, "env",
                        lambda nome, obrigatorio=True: "hash-de-admin")
    monkeypatch.setattr(modulo_senha, "verificar",
                        lambda digitada, hash_admin: digitada == "correta")
    return {"bloqueios": bloqueios, "mensagens": mensagens, "digitado": digitado, "ctx": ctx}


def test_senha_de_admin_correta_entra_zera_tentativas_e_fica_na_trilha(raiz, portao):
    from interface.comum import exigir_administrador
    assert exigir_administrador(raiz, portao["ctx"]) is True
    assert portao["bloqueios"].zeramentos == ["@ADMIN"]
    assert portao["ctx"].trilha.registros[-1]["motivo"] == "ADMIN_AUTENTICADO"


def test_senha_de_admin_errada_conta_tentativa_e_fica_na_trilha(raiz, portao):
    """O portao do painel era a unica porta sem contador e sem rastro."""
    from interface.comum import exigir_administrador
    portao["digitado"]["valor"] = "chute"

    assert exigir_administrador(raiz, portao["ctx"]) is False
    assert portao["bloqueios"].falhas == ["@ADMIN"]
    assert portao["ctx"].trilha.registros[-1]["motivo"] == "ADMIN_SENHA_INCORRETA"
    assert portao["ctx"].trilha.registros[-1]["resultado"] == "NEGADO"


def test_admin_bloqueado_nem_chega_a_pedir_a_senha(raiz, portao, monkeypatch):
    from interface.comum import exigir_administrador
    portao["bloqueios"].bloqueado = True
    pedidas = []
    monkeypatch.setattr("interface.comum.simpledialog",
                        type("D", (), {"askstring": staticmethod(
                            lambda *a, **k: pedidas.append(1) or "correta")})())

    assert exigir_administrador(raiz, portao["ctx"]) is False
    assert pedidas == [], "senha nao deve nem ser solicitada durante o bloqueio"
    assert "bloqueado" in portao["mensagens"].textos.lower()


def test_cancelar_o_dialogo_nao_conta_como_tentativa(raiz, portao):
    """Desistir nao e errar: contar a desistencia bloquearia quem so se enganou de janela."""
    from interface.comum import exigir_administrador
    portao["digitado"]["valor"] = None          # askstring devolve None no Cancelar

    assert exigir_administrador(raiz, portao["ctx"]) is False
    assert portao["bloqueios"].falhas == []
    assert portao["mensagens"].mostradas == []


def test_portao_funciona_sem_banco_apenas_sem_contar(raiz, monkeypatch, ctx):
    """Se o banco caiu, negar o painel esconderia justamente o que ha para diagnosticar."""
    from autenticacao import senha as modulo_senha
    from interface.comum import exigir_administrador
    mensagens = MensagensDuble()
    monkeypatch.setattr("interface.comum.messagebox", mensagens)
    monkeypatch.setattr("interface.comum.simpledialog",
                        type("D", (), {"askstring": staticmethod(lambda *a, **k: "correta")})())
    monkeypatch.setattr(configuracao, "env", lambda nome, obrigatorio=True: "hash-de-admin")
    monkeypatch.setattr(modulo_senha, "verificar", lambda d, h: d == "correta")
    ctx.banco = None

    assert exigir_administrador(raiz, ctx) is True


def test_sem_hash_configurado_o_painel_nao_abre(raiz, monkeypatch, ctx):
    from interface.comum import exigir_administrador
    mensagens = MensagensDuble()
    monkeypatch.setattr("interface.comum.messagebox", mensagens)
    monkeypatch.setattr(configuracao, "env", lambda nome, obrigatorio=True: None)

    assert exigir_administrador(raiz, ctx) is False
    assert "ADMIN_SENHA_HASH" in mensagens.textos


# ------------------------------------------------------------------ sessao travada
def test_dica_aponta_o_motivo_que_mais_barrou_amostras():
    """A sugestao segue o descarte dominante, nao o primeiro que apareceu."""
    from interface.cadastro import dica_para_destravar
    assert "luz" in dica_para_destravar({"ESCURO": 9, "DESFOCADO": 2})
    assert "lente" in dica_para_destravar({"ESCURO": 1, "DESFOCADO": 7})
    assert dica_para_destravar({}) == ""
    assert dica_para_destravar({"MOTIVO_NOVO": 5}) == ""      # sem dica, sem inventar


def test_captura_so_sugere_ajuste_depois_de_travar(raiz, ctx, monkeypatch):
    """Enquanto a contagem sobe, a tela nao enche a instrucao de palpite.

    A sessao nao tem prazo de proposito — ninguem deve ser barrado por demorar.
    O preco disso e que uma pessoa com a luz atras de si ficaria olhando um
    contador parado sem saber o que mudar; passados alguns segundos, a dica entra.
    """
    import interface.cadastro as cadastro
    from interface.cadastro import JanelaCaptura
    janela = JanelaCaptura(raiz, ctx, lambda c: None)
    janela.withdraw()
    coletor = ColetorAmostras(1, configuracao.carregar())
    coletor.descartes["ESCURO"] = 20

    relogio = {"agora": 1000.0}
    monkeypatch.setattr(cadastro.time, "monotonic", lambda: relogio["agora"])
    janela._amostras_vistas = -1
    assert janela._dica_se_travou(coletor) == ""          # primeira passada: marca o tempo

    relogio["agora"] += cadastro.SEGUNDOS_SEM_AVANCO - 1
    assert janela._dica_se_travou(coletor) == ""          # ainda dentro da tolerancia

    relogio["agora"] += 2
    assert "acenda mais luz" in janela._dica_se_travou(coletor)

    coletor.faces.append(np.zeros((200, 200), np.uint8))  # voltou a avancar
    assert janela._dica_se_travou(coletor) == ""
    janela._cancelar()


# ------------------------------------------------------------------ regra dos dois desligada
def janela_n3(raiz, ctx, exigir_segunda_pessoa):
    from interface.autenticacao import JanelaAutenticacao
    ctx.motor = MotorRegraDois(exigir_segunda_pessoa=exigir_segunda_pessoa)
    janela = JanelaAutenticacao(raiz, ctx, 3, lambda sessao: None)
    janela.withdraw()
    return janela


def test_faixa_de_etapas_esconde_a_segunda_pessoa_quando_a_regra_esta_desligada(raiz, ctx):
    """A tela não pode anunciar uma etapa que a decisão não vai cobrar."""
    from autenticacao.politica import Fator
    com = janela_n3(raiz, ctx, True)
    assert Fator.REGRA_DOIS in com.etapas.fatores
    com.destroy()

    sem = janela_n3(raiz, ctx, False)
    assert Fator.REGRA_DOIS not in sem.etapas.fatores
    assert Fator.VIVACIDADE in sem.etapas.fatores        # o resto do N3 continua anunciado
    assert len(sem.etapas.fatores) == len(com.etapas.fatores) - 1


def test_janela_consulta_o_motor_sobre_a_segunda_etapa(raiz, ctx):
    """Um `nivel == 3` escrito na tela voltaria a divergir da política no dia
    seguinte; a pergunta tem um dono só."""
    assert janela_n3(raiz, ctx, True).aguarda_segunda is True
    assert janela_n3(raiz, ctx, False).aguarda_segunda is False


def test_n3_sem_segunda_pessoa_nao_abre_o_formulario_de_espera(raiz, ctx, monkeypatch):
    """Com a regra desligada, concluir a etapa individual já concede a sessão.

    Antes esta era a bifurcação `if self.nivel < 3`, que mandava TODO N3 esperar
    por uma segunda pessoa que agora pode não existir — a tela ficaria presa num
    formulário cujo prazo nunca seria cumprido.
    """
    concedidas = []
    janela = janela_n3(raiz, ctx, False)
    janela.ao_conceder = concedidas.append
    monkeypatch.setattr(janela.motor, "abrir_sessao", lambda ev, segundo=None: "sessao-aberta",
                        raising=False)

    class DecisaoOk:
        concedido = True
        mensagem = ""

    janela.tentativa = type("T", (), {"ev": object()})()
    janela._concluida(DecisaoOk())

    assert concedidas == ["sessao-aberta"]
    assert janela.primeira_pessoa is None, "não pode ficar aguardando segunda pessoa"


def test_cartao_do_nivel_3_na_tela_inicial_acompanha_a_configuracao():
    """A porta de entrada não pode prometer uma exigência que foi dispensada."""
    import configparser

    import main
    cfg = configparser.ConfigParser()
    cfg.read_dict({"autenticacao": {"exigir_segunda_pessoa": "true"}})
    assert "segunda pessoa" in main.fatores_do_nivel_3(cfg)

    cfg["autenticacao"]["exigir_segunda_pessoa"] = "false"
    texto = main.fatores_do_nivel_3(cfg)
    assert "segunda pessoa" not in texto
    assert "desafio na câmera" in texto        # o que continua valendo segue anunciado
