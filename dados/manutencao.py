"""Manutenção do banco: zerar os dados de OPERAÇÃO preservando o acervo.

Serve a duas situações reais:
- limpar resíduo de teste antes de uma demonstração;
- recomeçar a operação sem reimportar o acervo (ETP 12.3, descarte).

O que sai: usuários, amostras, bloqueios, trilha e fotos de tentativas negadas.
O que fica: acervo, pendências, responsáveis e a taxonomia da camada causal.

Por que apagar a trilha INTEIRA e não só os registros de teste: a cadeia de
hash encadeia cada registro no anterior, então remover alguns do meio deixaria
ELO_ROMPIDO em todos os seguintes. Zerada, a cadeia recomeça do GENESIS e volta
a ser íntegra — o que é honesto, porque a trilha de uma demonstração anterior
não deve ser apresentada como se fosse da atual.

Esta operação exige conta ADMINISTRATIVA: a conta da aplicação não tem DELETE
em log_acesso nem em usuario, e é justamente isso que o RF-13 demonstra.
"""

# ordem importa: cada tabela só é apagada depois de quem a referencia
TABELAS_DE_OPERACAO = ("tentativa_negada", "log_acesso", "amostra", "bloqueio", "usuario")

TABELAS_PRESERVADAS = ("item_acervo", "regiao_sensivel", "pendencia", "responsavel",
                       "atividade_geradora", "motivo_permanencia", "nivel")


def limpar_operacao(cursor):
    """Apaga os dados de operação. Devolve {tabela: linhas removidas}."""
    removidos = {}
    for tabela in TABELAS_DE_OPERACAO:
        cursor.execute(f"DELETE FROM {tabela}")
        removidos[tabela] = cursor.rowcount
    return removidos


def contar(cursor, tabelas):
    """Contagem por tabela.

    Serve tanto ao cursor em dicionário do Banco quanto ao cursor comum da
    conexão administrativa da ferramenta — por isso lê o resultado pelos dois
    formatos em vez de assumir um.
    """
    contagens = {}
    for tabela in tabelas:
        cursor.execute(f"SELECT COUNT(*) AS n FROM {tabela}")
        linha = cursor.fetchone()
        contagens[tabela] = linha["n"] if isinstance(linha, dict) else linha[0]
    return contagens
