#!/usr/bin/env python3
"""
Verificação de ambiente — APS PIVC 2026/2
Valida a premissa PRE-01 (máquina com webcam funcional) e o ambiente Python
antes de escrever qualquer código. (PRE-02, autorização dos voluntários, é
documental — termos assinados — e não pode ser checada por script.)

Uso:
    python -m venv .venv
    .venv\\Scripts\\activate          (Windows)   |   source .venv/bin/activate (Linux)
    pip install -r requirements.txt
    python verificar_ambiente.py [--sem-camera]

Cada integrante roda na própria máquina e cola o resultado no grupo.
"""
import platform
import sys
import time

OK, FALHA, AVISO = "[ OK ]", "[FALHA]", "[AVISO]"
problemas = []
SEM_CAMERA = "--sem-camera" in sys.argv


def secao(titulo):
    print(f"\n{titulo}\n" + "-" * len(titulo))


# ---------------------------------------------------------------- Python
secao("1. Python")
v = sys.version_info
print(f"{OK if v[:2] == (3, 11) else AVISO} Python {v.major}.{v.minor}.{v.micro} — {platform.system()} {platform.machine()}")
if v[:2] != (3, 11):
    print("       A ETP fixa 3.11. Outra versão pode não ter wheel pronto do opencv-contrib.")

# ---------------------------------------------------------------- OpenCV
secao("2. OpenCV, módulo face (LBPH) e rastreador KCF")
try:
    import cv2
    print(f"{OK} OpenCV {cv2.__version__} importado")
except ImportError:
    print(f"{FALHA} OpenCV não instalado. Rode: pip install -r requirements.txt")
    sys.exit(1)

# o pacote errado é a armadilha nº 1 do projeto
try:
    reconhecedor = cv2.face.LBPHFaceRecognizer_create()
    print(f"{OK} cv2.face disponível — LBPHFaceRecognizer criado")
    print(f"       radius={reconhecedor.getRadius()} neighbors={reconhecedor.getNeighbors()} "
          f"grid={reconhecedor.getGridX()}x{reconhecedor.getGridY()}")
except AttributeError:
    print(f"{FALHA} cv2.face NÃO existe — está instalado o 'opencv-python' comum, que não traz o LBPH.")
    print("       Corrija com:  pip uninstall -y opencv-python opencv-contrib-python")
    print("                     pip install opencv-contrib-python==4.10.0.84")
    problemas.append("pacote errado do OpenCV (sem cv2.face)")

if hasattr(cv2, "TrackerKCF_create") or hasattr(getattr(cv2, "legacy", None), "TrackerKCF_create"):
    print(f"{OK} Rastreador KCF disponível (D-02)")
else:
    print(f"{FALHA} Rastreador KCF ausente")
    problemas.append("KCF indisponível")

# os dois pacotes no mesmo ambiente causam conflito silencioso
try:
    from importlib.metadata import distributions
    instalados = {d.metadata["Name"].lower() for d in distributions()}
    conflito = {"opencv-python", "opencv-contrib-python"} & instalados
    if len(conflito) > 1:
        print(f"{FALHA} opencv-python e opencv-contrib-python instalados juntos — remova o primeiro.")
        problemas.append("dois pacotes de OpenCV no mesmo ambiente")
    elif conflito:
        print(f"{OK} Apenas {conflito.pop()} instalado")
except Exception:
    pass

import numpy as np
marca = OK if np.__version__.startswith("1.26") else AVISO
print(f"{marca} numpy {np.__version__} (a ETP fixa 1.26.x, abaixo de 2.0)")

# ---------------------------------------------------------------- Haar
secao("3. Classificadores Haar")
for arquivo in ("haarcascade_frontalface_default.xml", "haarcascade_eye.xml"):
    haar = cv2.CascadeClassifier(cv2.data.haarcascades + arquivo)
    if haar.empty():
        print(f"{FALHA} Não foi possível carregar {arquivo}")
        problemas.append(f"{arquivo} não carregou")
    else:
        print(f"{OK} {arquivo} carregado")
haar = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

# ---------------------------------------------------------------- Webcam
secao("4. Webcam (PRE-01: 640x480 a 15 FPS ou mais)")
if SEM_CAMERA:
    print(f"{AVISO} Teste de câmera pulado (--sem-camera)")
else:
    cam = cv2.VideoCapture(0, cv2.CAP_DSHOW) if platform.system() == "Windows" else cv2.VideoCapture(0)
    if not cam.isOpened():
        print(f"{FALHA} Webcam não abriu no índice 0. Feche outros aplicativos que usem a câmera.")
        problemas.append("webcam indisponível")
    else:
        cam.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cam.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        larg = int(cam.get(cv2.CAP_PROP_FRAME_WIDTH))
        alt = int(cam.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"{OK} Webcam aberta em {larg}x{alt}")

        for _ in range(5):           # descarta os primeiros frames (aquecimento do sensor)
            cam.read()

        N = 60
        inicio = time.time()
        lidos = faces_vistas = 0
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        for _ in range(N):
            ok, frame = cam.read()
            if not ok:
                continue
            lidos += 1
            cinza = clahe.apply(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
            if len(haar.detectMultiScale(cinza, 1.1, 5, minSize=(80, 80))):
                faces_vistas += 1
        fps = lidos / (time.time() - inicio)

        marca = OK if fps >= 15 else (AVISO if fps >= 10 else FALHA)
        print(f"{marca} {fps:.1f} FPS com captura + cinza + CLAHE + detecção Haar (sem thread)")
        if fps < 10:
            print("       Abaixo do mínimo para tempo real. A thread de captura (D-01) e o KCF (D-02) são obrigatórios.")
            problemas.append(f"desempenho baixo ({fps:.1f} FPS)")
        elif fps < 15:
            print("       Abaixo da meta, mas utilizável. A thread de captura (D-01) deve resolver.")

        if faces_vistas:
            print(f"{OK} Face detectada em {faces_vistas} de {lidos} frames "
                  f"(esperado se alguém estava diante da câmera)")
        else:
            print(f"{AVISO} Nenhuma face detectada — normal se ninguém estava na frente da câmera.")
        cam.release()

# ---------------------------------------------------------------- Demais pacotes
secao("5. Demais dependências da ETP")
for nome, pacote in [("mysql-connector-python", "mysql.connector"), ("bcrypt", "bcrypt"),
                     ("cryptography", "cryptography"), ("python-dotenv", "dotenv"), ("Pillow", "PIL"),
                     ("pandas", "pandas"), ("matplotlib", "matplotlib"), ("pytest", "pytest")]:
    try:
        __import__(pacote)
        print(f"{OK} {nome}")
    except ImportError:
        print(f"{AVISO} {nome} ausente — pip install -r requirements.txt")
try:
    import tkinter
    print(f"{OK} tkinter (Tk {tkinter.TkVersion})")
except ImportError:
    print(f"{FALHA} tkinter ausente — reinstale o Python marcando 'tcl/tk and IDLE'")
    problemas.append("tkinter ausente")

# ---------------------------------------------------------------- MySQL (opcional)
secao("6. Banco de dados (opcional — precisa do .env)")
try:
    import configuracao
    from dados.conexao import Banco
    linhas = Banco().consultar("SELECT COUNT(*) AS n FROM nivel")
    print(f"{OK} MySQL acessível — tabela nivel com {linhas[0]['n']} linhas")
except Exception as erro:
    print(f"{AVISO} MySQL não verificado: {erro}")

# ---------------------------------------------------------------- Veredicto
secao("Resultado")
if problemas:
    print(f"{FALHA} Pendências a resolver antes de começar:")
    for p in problemas:
        print(f"       - {p}")
    sys.exit(1)
if SEM_CAMERA:
    print(f"{OK} Ambiente Python válido. PRE-01 NÃO verificada (rode de novo sem --sem-camera).")
else:
    print(f"{OK} Ambiente válido. PRE-01 confirmada nesta máquina.")
print("       Próximo passo: python esqueleto.py SeuNome")
