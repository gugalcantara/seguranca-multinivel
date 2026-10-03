"""Painel de gerenciamento: monta, lê os indicadores e audita a mudança de situação.

Não precisa de MySQL nem de câmera. O banco é um dublê que responde às
consultas reconhecendo a própria consulta por um trecho do SQL. O que se
verifica aqui é o comportamento da TELA — que número aparece em cada cartão, o
que vai para a trilha quando alguém é desativado. O SQL de verdade é exercido
em test_integracao_banco.py, contra o MySQL.
"""
from contextlib import contextmanager
from datetime import datetime

import pytest

from dados.auditoria import GENESIS, calcular_hash, novo_registro
from dados.repositorio import RepositorioUsuarios
import configuracao

# o módulo inteiro depende de Tk; a raiz em si vem do conftest
pytest.importorskip("tkinter")

from interface import tema                                  # noqa: E402
from interface.comum import Contexto                         # noqa: E402
from interface.painel import JanelaPainel                    # noqa: E402

USUARIOS = [
    # ativo vem do MySQL como 0/1, não como bool — é assim que o painel o recebe
    {"id": 1, "matricula": "S-7781", "nome": "Caio Lima", "nivel_id": 1, "uf": None,
     "ativo": 1, "criado_em": datetime(2026, 9, 20, 10, 0), "amostras": 80},
    {"id": 2, "matricula": "D-1042", "nome": "Ana Ribeiro", "nivel_id": 2, "uf": "SP",
     "ativo": 1, "criado_em": datetime(2026, 9, 21, 11, 0), "amostras": 80},
    {"id": 3, "matricula": "M-0001", "nome": "J. Moreira", "nivel_id": 3, "uf": None,
     "ativo": 0, "criado_em": datetime(2026, 9, 22, 9, 0), "amostras": 76},
]


def cadeia(n=4):
    """Trilha encadeada válida, como o banco a devolveria."""
    registros, anterior = [], GENESIS
    for i in range(1, n + 1):
        negado = i == 2
        registro = novo_registro("AUTENTICACAO", 2, "NEGADO" if negado else "CONCEDIDO",
                                 "CREDENCIAL_ALHEIA" if negado else "CONCEDIDO",
                                 usuario_id=i, distancia=40 + i)
        registro.update(id=i, hash_anterior=anterior,
                        hash_registro=calcular_hash(anterior, registro))
        anterior = registro["hash_registro"]
        registros.append(registro)
    return registros


class CursorDuble:
    def __init__(self, banco):
        self.banco = banco
        self.lastrowid = 1

    def execute(self, sql, parametros=()):
        self.banco.execucoes.append((" ".join(sql.split()), parametros))

    def executemany(self, sql, sequencia):
        self.banco.execucoes.append((" ".join(sql.split()), list(sequencia)))

    def fetchone(self):
        return {}

    def fetchall(self):
        return []

    def close(self):
        pass


class BancoDuble:
    """Responde cada consulta do painel pelo trecho de SQL que a identifica."""

    def __init__(self, usuarios=None, log=None):
        self.usuarios = [dict(u) for u in (usuarios if usuarios is not None else USUARIOS)]
        self.log = log if log is not None else cadeia()
        self.execucoes = []

    @contextmanager
    def transacao(self):
        yield CursorDuble(self)

    def consultar(self, sql, parametros=()):
        s = " ".join(sql.split())
        if "LEFT JOIN amostra" in s:                      # RepositorioUsuarios.listar
            return [dict(u) for u in self.usuarios]
        if "FROM usuario WHERE matricula" in s:           # por_matricula (unicidade)
            return [dict(u) for u in self.usuarios if u["matricula"] == parametros[0]]
        if "FROM usuario WHERE id" in s:                  # por_id
            return [dict(u) for u in self.usuarios if u["id"] == parametros[0]]
        if "GROUP BY nivel_id" in s:                      # contagem_usuarios
            niveis = {}
            for u in self.usuarios:
                n = niveis.setdefault(u["nivel_id"], {"nivel": u["nivel_id"], "usuarios": 0, "ativos": 0})
                n["usuarios"] += 1
                n["ativos"] += int(bool(u["ativo"]))
            return [niveis[k] for k in sorted(niveis)]
        if "FROM amostra" in s:                           # contagem_amostras
            return [{"amostras": sum(u["amostras"] for u in self.usuarios),
                     "identidades": len(self.usuarios), "qualidade_media": 0.812}]
        if "AS negadas" in s:                             # contagem_negadas
            return [{"negadas": sum(r["resultado"] == "NEGADO" for r in self.log)}]
        if "ORDER BY eventos DESC" in s:                  # motivos_de_negacao
            return [{"motivo": "CREDENCIAL_ALHEIA", "nivel": 2, "eventos": 1, "distancia_media": 88.4}]
        if "FROM bloqueio" in s:                          # s03_bloqueios_ativos
            return [{"matricula": "D-1042", "bloqueado_ate": datetime(2026, 10, 1, 15, 0)}]
        # ATENÇÃO à ordem: "FROM log_acesso ORDER BY id" é substring de
        # "... ORDER BY id DESC", então o caso mais específico vem primeiro.
        if "FROM log_acesso ORDER BY id DESC" in s:       # s01_log_acessos
            # o SELECT real faz "nivel_solicitado AS nivel"; o dublê precisa
            # devolver a coluna com o mesmo nome, senão a tela recebe outra coisa
            return [dict(r, nivel=r["nivel_solicitado"]) for r in reversed(self.log)]
        if "FROM log_acesso ORDER BY id" in s:            # TrilhaAuditoria.ler (S-04)
            return [dict(r) for r in self.log]
        raise AssertionError(f"consulta não prevista no dublê: {s[:90]}")


class ReconhecedorDuble:
    def __init__(self, rotulos=(1, 2, 3)):
        self._rotulos = set(rotulos)
        self.treinado = bool(rotulos)

    def rotulos_cadastrados(self):
        return set(self._rotulos)


class TrilhaDuble:
    def __init__(self):
        self.registros = []

    def registrar(self, registro):
        self.registros.append(registro)
        return len(self.registros)


# a raiz Tk e a limpeza das janelas vivem em testes/conftest.py: um interpretador
# para a sessão inteira, porque criar e destruir vários Tk() quebra o ttk::Style


def montar(raiz, banco=None, reconhecedor=None):
    banco = banco or BancoDuble()
    ctx = Contexto(cfg=configuracao.carregar(), banco=banco, trilha=TrilhaDuble(),
                   reconhecedor=reconhecedor or ReconhecedorDuble(), motor=None, acervo=None,
                   usuarios=RepositorioUsuarios(banco))
    painel = JanelaPainel(raiz, ctx)
    painel.withdraw()
    return painel, ctx, banco


# ------------------------------------------------------------------ indicadores
def test_painel_monta_e_preenche_os_indicadores(raiz):
    painel, _, _ = montar(raiz)
    cartoes = painel.cartoes
    assert cartoes["usuarios"].valor == "3"
    assert "N1·1" in cartoes["usuarios"].detalhe and "1 inativo(s)" in cartoes["usuarios"].detalhe
    assert cartoes["amostras"].valor == "236"
    assert cartoes["negadas"].valor == "1"
    assert cartoes["bloqueios"].valor == "1"
    assert len(painel.tabela_usuarios.arvore.get_children()) == 3
    assert len(painel.tabela_eventos.arvore.get_children()) == 4
    assert len(painel.tabela_motivos.arvore.get_children()) == 1


def test_tabela_de_eventos_traz_as_colunas_do_select(raiz):
    """A tela lê 'nivel' (alias de nivel_solicitado) — coluna vazia passaria batido."""
    painel, _, _ = montar(raiz)
    primeira = painel.tabela_eventos.arvore.item("0", "values")
    colunas = {c.chave: v for c, v in zip(painel.tabela_eventos.colunas, primeira)}
    assert colunas["nivel"] == "2"                    # não "—"
    assert colunas["evento"] == "AUTENTICACAO"
    assert colunas["id"] == "4"                       # mais recente primeiro (ORDER BY id DESC)
    assert "usuario_id" not in colunas                # resumo não carrega essa coluna


def test_cartao_da_trilha_mostra_integra_e_localiza_a_ruptura(raiz):
    painel, _, _ = montar(raiz)
    assert painel.cartoes["trilha"].valor == "ÍNTEGRA"
    assert "4 registros" in painel.cartoes["trilha"].detalhe

    adulterada = cadeia()
    adulterada[2]["resultado"] = "NEGADO"          # mexe no conteúdo, não no hash
    painel2, _, _ = montar(raiz, BancoDuble(log=adulterada))
    assert painel2.cartoes["trilha"].valor == "RUPTURA"
    assert "id=3" in painel2.cartoes["trilha"].detalhe


def test_cartao_do_modelo_avisa_quando_amostra_ficou_fora(raiz):
    """Divergência entre amostras no banco e rótulos no modelo = modelo defasado."""
    painel, _, _ = montar(raiz, reconhecedor=ReconhecedorDuble(rotulos=(1, 2)))
    assert painel.cartoes["modelo"].valor == "2"
    assert "1 com amostra fora do modelo" in painel.cartoes["modelo"].detalhe
    assert painel.cartoes["modelo"].cor == tema.AVISO

    completo, _, _ = montar(raiz)
    assert completo.cartoes["modelo"].detalhe == "modelo cifrado carregado"
    assert completo.cartoes["modelo"].cor == tema.OK


def test_indicador_indisponivel_nao_derruba_o_painel(raiz):
    """Falha de consulta vira travessão no cartão, não exceção na abertura."""
    class BancoQuebrado(BancoDuble):
        def consultar(self, sql, parametros=()):
            if "FROM amostra" in " ".join(sql.split()):
                raise RuntimeError("privilégio negado")
            return super().consultar(sql, parametros)

    painel, _, _ = montar(raiz, BancoQuebrado())
    assert painel.cartoes["amostras"].valor == "—"
    assert painel.cartoes["usuarios"].valor == "3"      # os demais seguem funcionando


# ------------------------------------------------------------------ ações
def selecionar(raiz, painel, indice):
    """Seleciona uma linha e deixa o Tk processar o <<TreeviewSelect>>.

    O update() é necessário: eventos virtuais só são entregues dentro do loop de
    eventos, e é justamente o binding que atualiza a ficha e o botão.
    """
    painel.tabela_usuarios.arvore.selection_set(str(indice))
    raiz.update()


def test_desativar_usuario_grava_update_e_entra_na_trilha(raiz, monkeypatch):
    painel, ctx, banco = montar(raiz)
    monkeypatch.setattr("interface.painel.messagebox.askyesno", lambda *a, **k: True)

    selecionar(raiz, painel, 0)                          # Caio Lima, ativo
    assert painel.botao_situacao.cget("text") == "Desativar"
    assert painel.ficha._valores["nome"].cget("text") == "Caio Lima"
    painel._alternar_situacao()

    updates = [e for e in banco.execucoes if "UPDATE usuario SET ativo" in e[0]]
    assert updates and updates[0][1] == (False, 1)
    registrado = ctx.trilha.registros[-1]
    assert registrado["motivo"] == "USUARIO_DESATIVADO"
    assert registrado["usuario_id"] == 1 and registrado["evento"] == "CADASTRO"


def test_reativar_usuario_inativo_usa_o_motivo_oposto(raiz, monkeypatch):
    painel, ctx, _ = montar(raiz)
    monkeypatch.setattr("interface.painel.messagebox.askyesno", lambda *a, **k: True)

    selecionar(raiz, painel, 2)                          # J. Moreira, inativo
    assert painel.botao_situacao.cget("text") == "Reativar"
    painel._alternar_situacao()
    assert ctx.trilha.registros[-1]["motivo"] == "USUARIO_REATIVADO"


def test_cancelar_a_confirmacao_nao_altera_nada(raiz, monkeypatch):
    painel, ctx, banco = montar(raiz)
    monkeypatch.setattr("interface.painel.messagebox.askyesno", lambda *a, **k: False)
    selecionar(raiz, painel, 0)
    painel._alternar_situacao()
    assert not [e for e in banco.execucoes if "UPDATE usuario" in e[0]]
    assert ctx.trilha.registros == []


def test_situacao_do_usuario_aparece_como_texto(raiz):
    """ativo vem como 0/1 do MySQL; a tela não pode mostrar o número cru."""
    painel, _, _ = montar(raiz)
    colunas = [c.chave for c in painel.tabela_usuarios.colunas]
    situacao = colunas.index("ativo")
    assert painel.tabela_usuarios.arvore.item("0", "values")[situacao] == "ativo"
    assert painel.tabela_usuarios.arvore.item("2", "values")[situacao] == "inativo"
    selecionar(raiz, painel, 2)
    assert painel.ficha._valores["ativo"].cget("text") == "inativo"


def test_ficha_mostra_o_registro_selecionado(raiz):
    painel, _, _ = montar(raiz)
    selecionar(raiz, painel, 1)
    assert painel.ficha._valores["nome"].cget("text") == "Ana Ribeiro"
    assert painel.ficha._valores["uf"].cget("text") == "SP"
    painel._selecionar_usuario(None)
    assert painel.ficha._valores["nome"].cget("text") == "—"
    assert str(painel.botao_situacao.cget("state")) == "disabled"


# ------------------------------------------------------------------ revogação (LGPD art. 8º, §5º)
class ConsentimentosDuble:
    """Registra a ORDEM das chamadas, que é o que importa aqui."""

    def __init__(self, ordem, falhar=False):
        self.ordem = ordem
        self.falhar = falhar

    def revogar(self, usuario_id, momento=None):
        self.ordem.append("revogar")
        if self.falhar:
            raise RuntimeError("banco caiu no meio da revogação")
        return 1


def montar_com_revogacao(raiz, monkeypatch, falhar=False):
    painel, ctx, banco = montar(raiz)
    ordem = []
    ctx.consentimentos = ConsentimentosDuble(ordem, falhar=falhar)
    original = ctx.usuarios.definir_ativo

    def definir_ativo(usuario_id, ativo):
        ordem.append("desativar")
        return original(usuario_id, ativo)

    monkeypatch.setattr(ctx.usuarios, "definir_ativo", definir_ativo)
    monkeypatch.setattr("interface.painel.messagebox.askyesno", lambda *a, **k: True)
    monkeypatch.setattr("interface.painel.messagebox.showinfo", lambda *a, **k: None)
    monkeypatch.setattr("interface.painel.messagebox.showerror", lambda *a, **k: None)
    return painel, ctx, ordem


def test_revogar_consentimento_desativa_ANTES_de_revogar(raiz, monkeypatch):
    """A ordem é a própria salvaguarda.

    Revogando primeiro, uma falha ao desativar deixaria o cadastro ATIVO com o
    consentimento já baixado — tratamento de dado biométrico sem base legal,
    exatamente o que este botão existe para impedir. Na ordem correta, o pior
    desfecho é um cadastro inativo com consentimento vivo: reversível.
    """
    painel, ctx, ordem = montar_com_revogacao(raiz, monkeypatch)
    selecionar(raiz, painel, 0)                          # Caio Lima, ativo

    painel._revogar_consentimento()
    assert ordem == ["desativar", "revogar"]
    assert ctx.trilha.registros[-1]["motivo"] == "CONSENTIMENTO_REVOGADO"


def test_falha_na_revogacao_nao_registra_desfecho_falso_na_trilha(raiz, monkeypatch):
    """Se a revogação não concluiu, a trilha não pode dizer que concluiu."""
    painel, ctx, ordem = montar_com_revogacao(raiz, monkeypatch, falhar=True)
    antes = len(ctx.trilha.registros)
    selecionar(raiz, painel, 0)

    painel._revogar_consentimento()
    motivos = [r["motivo"] for r in ctx.trilha.registros[antes:]]
    assert "CONSENTIMENTO_REVOGADO" not in motivos


def test_revogar_sem_selecionar_ninguem_nao_faz_nada(raiz, monkeypatch):
    painel, ctx, ordem = montar_com_revogacao(raiz, monkeypatch)
    painel.tabela_usuarios.arvore.selection_remove(
        *painel.tabela_usuarios.arvore.selection())

    painel._revogar_consentimento()
    assert ordem == []
