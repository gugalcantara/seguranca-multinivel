# Instala e prepara o projeto. Chamado pelo instalar.bat.
# Pode rodar quantas vezes quiser: o que já estiver pronto é mantido.
. "$PSScriptRoot\comum.ps1"

Write-Host "Instalação do projeto — Controle de acesso multinível (APS PIVC 2026/2)"

Etapa "1/5  Python 3.11"
$py = Garantir-Python

Etapa "2/5  Ambiente virtual (.venv)"
Garantir-Venv $py

Etapa "3/5  Dependências (pode levar alguns minutos na primeira vez)"
& $VenvPython -m pip install --disable-pip-version-check --quiet -r requirements.txt
if ($LASTEXITCODE -ne 0) { Falhar "A instalação das dependências falhou. Confira a conexão com a internet e rode de novo." }
Ok "dependências instaladas"

Etapa "4/5  Docker e banco de dados"
Garantir-Docker
Subir-Banco

Etapa "5/5  Configuração, banco e acervo"
& $VenvPython -m ferramentas preparar
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host ""
Write-Host "Instalação concluída. Para abrir o programa, dê dois cliques em executar.bat." -ForegroundColor Green
Write-Host "Na primeira vez, entre no Painel de gerenciamento e cadastre as pessoas."
