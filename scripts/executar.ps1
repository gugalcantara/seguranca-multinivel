# Abre o programa. Chamado pelo executar.bat.
# Antes de abrir, garante o que costumava faltar: Docker aberto e banco pronto.
. "$PSScriptRoot\comum.ps1"

if (-not (Testar-Python $VenvPython)) {
    Falhar "O projeto ainda não foi instalado nesta máquina. Dê dois cliques em instalar.bat primeiro."
}
Garantir-Docker -Silencioso
Subir-Banco -Silencioso
& $VenvPython -m ferramentas preparar --silencioso
if ($LASTEXITCODE -ne 0) { exit 1 }

& $VenvPython main.py
exit $LASTEXITCODE
