"""Captura de uma sessão para a BASE EXPERIMENTAL (não para o cadastro do sistema).

Salva as faces já pré-processadas (200x200, cinza) em
dados_faciais/<grupo>/<id>/<sessao>/ — pasta fora do Git, a ser apagada após
os experimentos, com registro em ata (ETP 4.5). Só capturar quem assinou o termo.

Uso:  python -m experimentos.capturar --id 1 --sessao 1 [--grupo impostores]
"""
import argparse

import cv2

import configuracao
from visao.aquisicao import CapturaThread
from visao.coleta import ColetorAmostras
from visao.pipeline import PipelineFacial


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", type=int, required=True)
    parser.add_argument("--sessao", type=int, required=True)
    parser.add_argument("--grupo", choices=["cadastrados", "impostores"], default="cadastrados")
    args = parser.parse_args()

    destino = configuracao.RAIZ / "dados_faciais" / args.grupo / str(args.id) / str(args.sessao)
    destino.mkdir(parents=True, exist_ok=True)
    pipeline = PipelineFacial()
    coletor = ColetorAmostras(args.sessao)

    with CapturaThread() as camera:
        while not coletor.completa:
            frame = camera.ler()
            if frame is None:
                break
            analise = pipeline.analisar(frame, reconhecer=False)
            aceito = coletor.alimentar(analise)
            for (x, y, w, h) in analise.retangulos:
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 200, 0) if aceito else (0, 0, 220), 2)
            cv2.putText(frame, f"{len(coletor.faces)}/{coletor.alvo}  {analise.qualidade.motivo}",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
            cv2.imshow("Captura experimental — mova a cabeca devagar (q sai)", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    cv2.destroyAllWindows()

    for i, face in enumerate(coletor.faces):
        cv2.imwrite(str(destino / f"{i:03d}.png"), face)
    print(f"{len(coletor.faces)} faces salvas em {destino}; descartes: {coletor.descartes}")


if __name__ == "__main__":
    main()
