# Funções compartilhadas por instalar.ps1 e executar.ps1.
#
# Este arquivo é gravado em UTF-8 COM BOM de propósito: o PowerShell 5.1 do
# Windows lê .ps1 sem BOM como ANSI, e todo acento das mensagens sairia
# embaralhado. (É o oposto do .env, que precisa ser SEM BOM — ver preparacao.py.)

# Programas externos (python, docker) sinalizam falha pelo código de saída, que
# é conferido em $LASTEXITCODE. Com "Stop", o PowerShell 5.1 transforma qualquer
# texto em stderr numa exceção, mesmo quando o programa terminou bem.
$ErrorActionPreference = "Continue"

# O docker compose lê sozinho o .env da pasta para interpolar variáveis — e o
# hash bcrypt da senha de admin ($2b$12$...) tem cifrões, que ele toma por
# variáveis inexistentes e despeja avisos assustadores na tela. O compose do
# projeto não usa nada do .env, então a leitura automática é desligada aqui.
$env:COMPOSE_DISABLE_ENV_FILE = "1"

$Raiz = Split-Path -Parent $PSScriptRoot
Set-Location $Raiz
$VenvPython = Join-Path $Raiz ".venv\Scripts\python.exe"

function Etapa($texto) { Write-Host ""; Write-Host "== $texto" -ForegroundColor Cyan }
function Ok($texto)    { Write-Host "   $texto" -ForegroundColor Green }
function Info($texto)  { Write-Host "   $texto" }
function Falhar($texto) {
    Write-Host ""
    Write-Host "[!] $texto" -ForegroundColor Red
    exit 1
}

# Um Python só serve se for 3.11 E conseguir carregar o tkinter. A segunda
# condição não é detalhe: no Windows 11 com Smart App Control, o Python baixado
# pelo uv é bloqueado justamente na DLL do tkinter — e a aplicação inteira é Tk.
function Testar-Python($exe) {
    if (-not $exe -or -not (Test-Path $exe)) { return $false }
    & $exe -c "import sys, tkinter; sys.exit(0 if sys.version_info[:2] == (3, 11) else 1)" 2>$null
    return ($LASTEXITCODE -eq 0)
}

function Encontrar-Python311 {
    $candidatos = @("$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
                    "$env:ProgramFiles\Python311\python.exe")
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $achado = & py -3.11 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $achado) { $candidatos += "$achado".Trim() }
    }
    foreach ($c in $candidatos) { if (Testar-Python $c) { return $c } }
    return $null
}

function Garantir-Python {
    $py = Encontrar-Python311
    if ($py) { Ok "Python 3.11 encontrado: $py"; return $py }
    Info "Python 3.11 utilizável não encontrado (ausente, ou bloqueado pelo Smart App Control)."
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Info "Instalando o Python 3.11 oficial com o winget (assinado, o Windows não bloqueia)..."
        winget install --id Python.Python.3.11 --exact --silent --accept-source-agreements --accept-package-agreements
        $py = Encontrar-Python311
    }
    if (-not $py) {
        Falhar ("Instale o Python 3.11 de https://www.python.org/downloads/release/python-3119/ " +
                "e rode o instalar.bat de novo.")
    }
    Ok "Python 3.11 instalado: $py"
    return $py
}

function Garantir-Venv($py) {
    if (Testar-Python $VenvPython) { Ok "ambiente .venv já existe e funciona"; return }
    if (Test-Path ".venv") {
        # renomeia em vez de apagar: é recriável, mas não é decisão do script descartar
        $antigo = ".venv-antigo-" + (Get-Date -Format "yyyyMMdd-HHmmss")
        Rename-Item ".venv" $antigo
        Info "o .venv existente não servia (outra versão do Python, ou bloqueado) — guardado como $antigo"
    }
    & $py -m venv .venv
    if ($LASTEXITCODE -ne 0) { Falhar "não consegui criar o ambiente .venv" }
    Ok "ambiente .venv criado"
}

function Garantir-Docker([switch]$Silencioso) {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Falhar ("O Docker Desktop não está instalado. Ele roda o banco de dados do projeto.`n" +
                "    Instale com:  winget install Docker.DockerDesktop`n" +
                "    reinicie o computador, abra o Docker Desktop uma vez e rode de novo.")
    }
    docker info *> $null
    if ($LASTEXITCODE -eq 0) { if (-not $Silencioso) { Ok "Docker em execução" }; return }
    $exe = @("$env:ProgramFiles\Docker\Docker\Docker Desktop.exe",
             "$env:LOCALAPPDATA\Programs\DockerDesktop\Docker Desktop.exe") |
           Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $exe) { Falhar "Abra o Docker Desktop e rode de novo." }
    Info "abrindo o Docker Desktop (pode levar até um minuto)..."
    Start-Process $exe
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Seconds 3
        docker info *> $null
        if ($LASTEXITCODE -eq 0) { Ok "Docker em execução"; return }
    }
    Falhar "O Docker Desktop não ficou pronto em 3 minutos. Abra-o, espere ficar 'running' e rode de novo."
}

function Subir-Banco([switch]$Silencioso) {
    if ($Silencioso) { docker compose up -d *> $null } else { docker compose up -d }
    if ($LASTEXITCODE -ne 0) {
        Falhar "Não consegui subir o MySQL do projeto. Rode 'docker compose up -d' para ver a mensagem completa."
    }
    if (-not $Silencioso) { Ok "contêiner do MySQL no ar" }
}
