<#
.SYNOPSIS
    Lance le serveur de developpement DataZen dans sa propre fenetre.

.DESCRIPTION
    Demarre `manage.py runserver` de facon autonome : la fenetre PowerShell
    reste ouverte et le serveur continue de tourner meme apres la fermeture de
    l'editeur ou de l'agent qui l'a lance.

    Le moteur de base de donnees suit `.env` (PostgreSQL par defaut). Si aucun
    serveur PostgreSQL n'ecoute, le script bascule sur SQLite et le signale.

.PARAMETER Port
    Port d'ecoute. 8000 par defaut.

.PARAMETER Sqlite
    Force SQLite, sans tester PostgreSQL.

.PARAMETER Postgres
    Force PostgreSQL : echoue si le serveur n'est pas joignable.

.EXAMPLE
    .\start-dev.ps1
    .\start-dev.ps1 -Port 8080
    .\start-dev.ps1 -Sqlite
#>
[CmdletBinding()]
param(
    [int]$Port = 8000,
    [switch]$Sqlite,
    [switch]$Postgres
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

function Write-Step($message) { Write-Host "==> $message" -ForegroundColor Cyan }
function Write-Warn($message) { Write-Host "!!  $message" -ForegroundColor Yellow }
function Write-Fail($message) { Write-Host "xx  $message" -ForegroundColor Red }

# --- Interpreteur Python -----------------------------------------------------
$python = Join-Path $PSScriptRoot 'venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    Write-Fail "Environnement virtuel introuvable : $python"
    Write-Host "    Creez-le avec : python -m venv venv" -ForegroundColor Gray
    Write-Host "    puis          : .\venv\Scripts\pip install -r requirements.txt" -ForegroundColor Gray
    exit 1
}

# --- Port deja occupe ? ------------------------------------------------------
$busy = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1
if ($busy) {
    $owner = Get-Process -Id $busy.OwningProcess -ErrorAction SilentlyContinue
    Write-Fail "Le port $Port est deja utilise par le PID $($busy.OwningProcess) ($($owner.ProcessName))."
    Write-Host "    Liberez-le : Stop-Process -Id $($busy.OwningProcess)" -ForegroundColor Gray
    Write-Host "    ou changez de port : .\start-dev.ps1 -Port 8081" -ForegroundColor Gray
    exit 1
}

# --- Choix du moteur de base de donnees --------------------------------------
if (-not $Sqlite -and -not $Postgres) {
    # `.env` peut deja imposer SQLite : inutile de sonder PostgreSQL.
    $configured = 'postgresql'
    $envFile = Join-Path $PSScriptRoot '.env'
    if (Test-Path -LiteralPath $envFile) {
        $line = Get-Content -LiteralPath $envFile -Encoding UTF8 |
            Where-Object { $_ -match '^\s*DJANGO_DB_ENGINE\s*=' } |
            Select-Object -First 1
        if ($line) {
            $configured = ($line -split '=', 2)[1].Trim().Trim('"', "'").ToLower()
        }
    }

    if ($configured -in @('sqlite', 'sqlite3')) {
        $Sqlite = $true
    } else {
        $dbPort = 5432
        $reachable = Test-NetConnection -ComputerName '127.0.0.1' -Port $dbPort `
            -InformationLevel Quiet -WarningAction SilentlyContinue
        if (-not $reachable) {
            Write-Warn "PostgreSQL ne repond pas sur 127.0.0.1:$dbPort : bascule sur SQLite."
            $Sqlite = $true
        }
    }
}

if ($Sqlite) {
    $env:DJANGO_DB_ENGINE = 'sqlite'
} else {
    $env:DJANGO_DB_ENGINE = 'postgresql'
}

# --- Migrations --------------------------------------------------------------
Write-Step "Application des migrations (moteur : $($env:DJANGO_DB_ENGINE))"
& $python manage.py migrate --noinput
if ($LASTEXITCODE -ne 0) {
    Write-Fail "Les migrations ont echoue : le serveur n'est pas lance."
    exit $LASTEXITCODE
}

# --- Serveur -----------------------------------------------------------------
Write-Step "Demarrage du serveur sur http://127.0.0.1:$Port/"
Write-Host "    Arret avec Ctrl+C. Cette fenetre doit rester ouverte." -ForegroundColor Gray
Write-Host ""

& $python manage.py runserver "127.0.0.1:$Port" --noreload
