"""Protocolo experimental (ETP 4.7 e 7.2).

Divisão treino/teste POR SESSÃO DE CAPTURA, não por frame: frames da mesma
sessão são quase idênticos, e espalhá-los entre treino e teste infla a
acurácia. Equivalente a um GroupShuffleSplit estratificado por identidade,
implementado aqui para não puxar o scikit-learn só por isso.

Estrutura esperada da base experimental (fora do Git, apagada após os testes):
    dados_faciais/
        cadastrados/<usuario_id>/<sessao>/*.png   (200x200, já pré-processadas)
        impostores/<id_qualquer>/<sessao>/*.png   (nunca entram no treino)
"""
import random
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

from experimentos import metricas


def dividir_por_sessao(identidades, sessoes, proporcao_teste, semente):
    """Devolve (indices_treino, indices_teste).

    Para cada identidade, sorteia sessões inteiras para o teste até atingir a
    proporção, mantendo ao menos uma sessão no treino. Identidade com uma única
    sessão vai inteira para o treino (e o relatório deve declarar isso).
    """
    rng = random.Random(semente)
    grupos = defaultdict(lambda: defaultdict(list))
    for i, (ident, sessao) in enumerate(zip(identidades, sessoes)):
        grupos[ident][sessao].append(i)

    treino, teste = [], []
    for ident in sorted(grupos):
        lista = sorted(grupos[ident])
        rng.shuffle(lista)
        n_teste = min(max(1, round(len(lista) * proporcao_teste)), len(lista) - 1)
        for k, sessao in enumerate(lista):
            (teste if k < n_teste else treino).extend(grupos[ident][sessao])
    return sorted(treino), sorted(teste)


def carregar_base(diretorio):
    """Lê <diretorio>/<identidade>/<sessao>/*.png -> (faces, identidades, sessoes)."""
    faces, identidades, sessoes = [], [], []
    for pasta_ident in sorted(p for p in Path(diretorio).iterdir() if p.is_dir()):
        for pasta_sessao in sorted(p for p in pasta_ident.iterdir() if p.is_dir()):
            for arquivo in sorted(pasta_sessao.glob("*.png")):
                faces.append(cv2.imread(str(arquivo), cv2.IMREAD_GRAYSCALE))
                identidades.append(int(pasta_ident.name))
                sessoes.append(pasta_sessao.name)
    return faces, identidades, sessoes


def avaliar(reconhecedor_fabrica, faces, identidades, sessoes, faces_impostoras, proporcao_teste, semente):
    """Executa o protocolo para um reconhecedor e devolve as distâncias e predições.

    reconhecedor_fabrica() deve devolver um objeto com treinar/identificar/verificar
    (ReconhecedorLBPH, ou um adaptador Eigenfaces para a linha de base).
    """
    treino, teste = dividir_por_sessao(identidades, sessoes, proporcao_teste, semente)
    rec = reconhecedor_fabrica()
    rec.treinar([faces[i] for i in treino], [identidades[i] for i in treino])
    cadastrados = sorted({identidades[i] for i in treino})
    rng = random.Random(semente)

    reais, preditos, gen_1n, gen_11 = [], [], [], []
    for i in teste:
        rotulo, dist = rec.identificar(faces[i])
        reais.append(identidades[i])
        preditos.append(rotulo)
        gen_1n.append(dist if rotulo == identidades[i] else float("inf"))
        gen_11.append(rec.verificar(faces[i], identidades[i]))

    imp_1n, imp_11 = [], []
    for face in faces_impostoras:
        imp_1n.append(rec.identificar(face)[1])               # qualquer identidade aceita = falsa aceitação
        imp_11.append(rec.verificar(face, rng.choice(cadastrados)))   # alega uma identidade ao acaso

    return {
        "acuracia_1n": metricas.acuracia(reais, preditos),
        "reais": reais, "preditos": preditos,
        "genuinas_1n": np.asarray(gen_1n), "impostoras_1n": np.asarray(imp_1n),
        "genuinas_11": np.asarray(gen_11), "impostoras_11": np.asarray(imp_11),
        "n_treino": len(treino), "n_teste": len(teste),
    }
