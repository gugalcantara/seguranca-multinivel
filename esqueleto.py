"""Esqueleto ponta a ponta — passo 3 do Handoff. NÃO usa banco.

Prova que a cadeia das cinco fases funciona:
    webcam -> cinza + CLAHE -> Haar (+KCF) -> portão de qualidade -> LBPH -> nome na tela

Tudo em memória: as faces capturadas viram modelo e somem quando o programa fecha.

Uso:
    python esqueleto.py Gustavo            # uma pessoa
    python esqueleto.py Gustavo Ana Bruno  # várias, uma de cada vez

Na janela: ESPAÇO inicia a captura da próxima pessoa; q encerra.
"""
import sys
import time

import cv2

import configuracao
from visao.aquisicao import CapturaThread, WebcamIndisponivel
from visao.coleta import ColetorAmostras
from visao.extracao import ReconhecedorLBPH
from visao.pipeline import PipelineFacial

VERDE, VERMELHO, AMARELO, BRANCO = (0, 200, 0), (0, 0, 220), (0, 200, 220), (255, 255, 255)


def _faixa(frame, texto, cor=BRANCO):
    cv2.rectangle(frame, (0, 0), (frame.shape[1], 36), (30, 30, 30), -1)
    cv2.putText(frame, texto, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.65, cor, 2)


def capturar(camera, pipeline, nome):
    coletor = ColetorAmostras(sessao=1)
    iniciado = False
    while not coletor.completa:
        frame = camera.ler()
        if frame is None:
            raise WebcamIndisponivel("A câmera parou de entregar frames")
        if iniciado:
            analise = pipeline.analisar(frame, reconhecer=False)
            aceito = coletor.alimentar(analise)
            for (x, y, w, h) in analise.retangulos:
                cv2.rectangle(frame, (x, y), (x + w, y + h), VERDE if aceito else VERMELHO, 2)
            _faixa(frame, f"{nome}: {len(coletor.faces)}/{coletor.alvo}  [{analise.qualidade.motivo}]"
                          f"  mova a cabeca devagar")
        else:
            _faixa(frame, f"Proxima pessoa: {nome} — pressione ESPACO para capturar", AMARELO)
        cv2.imshow("Esqueleto APS PIVC", frame)
        tecla = cv2.waitKey(1) & 0xFF
        if tecla == ord("q"):
            sys.exit(0)
        if tecla == ord(" "):
            iniciado = True
    print(f"  {nome}: {len(coletor.faces)} amostras aceitas; descartes {coletor.descartes}")
    return coletor.faces


def main(nomes):
    limiar = configuracao.limiar(1)
    pipeline = PipelineFacial()
    reconhecedor = ReconhecedorLBPH()

    with CapturaThread() as camera:
        for rotulo, nome in enumerate(nomes, start=1):
            faces = capturar(camera, pipeline, nome)
            reconhecedor.atualizar(faces, [rotulo] * len(faces))   # D-04: update() incremental
            faces.clear()                                          # nenhuma imagem persiste
        pipeline.reconhecedor = reconhecedor
        print(f"Modelo treinado com {len(nomes)} identidade(s). Limiar N1 = {limiar} (provisório).")

        anterior = time.perf_counter()
        while True:
            frame = camera.ler()
            if frame is None:
                break
            inicio = time.perf_counter()
            analise = pipeline.analisar(frame)
            ms = (time.perf_counter() - inicio) * 1000
            fps = 1 / max(1e-6, inicio - anterior)
            anterior = inicio

            if analise.distancia is not None:
                aceito = analise.distancia <= limiar          # DISTÂNCIA: menor é melhor
                nome = nomes[analise.rotulo - 1] if aceito else "desconhecido"
                cor = VERDE if aceito else VERMELHO
                texto = f"{nome}  dist={analise.distancia:.1f}  ({ms:.0f} ms, {fps:.0f} fps)"
            else:
                cor, texto = AMARELO, analise.qualidade.mensagem
            for (x, y, w, h) in analise.retangulos:
                cv2.rectangle(frame, (x, y), (x + w, y + h), cor, 2)
            _faixa(frame, texto, cor)
            cv2.imshow("Esqueleto APS PIVC", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    cv2.destroyAllWindows()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    try:
        main(sys.argv[1:])
    except WebcamIndisponivel as erro:
        print(f"[FALHA] {erro}")
        sys.exit(1)
