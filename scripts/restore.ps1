<#
Restauration DataZen : base de donnees + repertoire media/.

Restaure une archive produite par scripts/backup.ps1. La base et media/
doivent etre restaures ensemble : un DataFile sans son fichier est
inutilisable.

Par securite, la base n'est jamais ecrasee sans -Force. Par defaut, la
restauration SQLite ecrit dans un fichier separe, et la restauration
PostgreSQL dans une base suffixee _restaure, pour verification.

Exemples :
    # Lister les archives disponibles
    .\scripts\restore.ps1 -List

    # Restaurer dans une base jetable pour verifier l'archive
    .\scripts\restore.ps1 -DbArchive .\backups\datazen-db-20260115-030000.dump
    .\scripts\restore.ps1 -MediaArchive .\backups\datazen-media-20260115-030000.tar.gz

    # Restaurer reellement (ecrase la base cible)
    .\scripts\restore.ps1 -DbArchive ... -Target datazen -Force
#>
[CmdletBinding()]
param(
    [string] $DbArchive = "",
    [string] $MediaArchive = "",
    [string] $Source = "",
    [string] $Target = "",
    [switch] $List,
    [switch] $Force,
    [switch] $SkipMedia
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($Source)) { $Source = Join-Path $Root "backups" }

function Write-Step { param([string] $Message) Write-Host "==> $Message" -ForegroundColor Cyan }
function Write-Warn { param([string] $Message) Write-Host "    $Message" -ForegroundColor Yellow }
function Write-Fail { param([string] $Message) Write-Host "ERREUR : $Message" -ForegroundColor Red; exit 1 }

function Read-DotEnv {
    param([string] $Path)
    $values = @{}
    if (-not (Test-Path -LiteralPath $Path)) { return $values }
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
            $key = $matches[1]
            $val = $matches[2].Trim()
            if ($val -match '^"(.*)"$' -or $val -match "^'(.*)'$") { $val = $matches[1] }
            $values[$key] = $val
        }
    }
    return $values
}

function Get-Setting {
    param([hashtable] $Env, [string] $Key, [string] $Default = "")
    $fromProcess = [Environment]::GetEnvironmentVariable($Key)
    if (-not [string]::IsNullOrWhiteSpace($fromProcess)) { return $fromProcess }
    if ($Env.ContainsKey($Key) -and $Env[$Key] -ne "") { return $Env[$Key] }
    return $Default
}

function Resolve-PgTool {
    param([string] $Name)
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($candidate in @(
        "C:\Program Files\PostgreSQL\17\bin\$Name.exe",
        "C:\Program Files\PostgreSQL\16\bin\$Name.exe",
        "C:\Program Files\PostgreSQL\15\bin\$Name.exe"
    )) {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    return $null
}

# --- Mode liste -------------------------------------------------------------

if ($List) {
    if (-not (Test-Path -LiteralPath $Source)) { Write-Fail "Aucun repertoire de sauvegarde : $Source" }
    $archives = Get-ChildItem -LiteralPath $Source -File |
                Where-Object { $_.Name -like "datazen-db-*" -or $_.Name -like "datazen-media-*" } |
                Sort-Object LastWriteTime -Descending
    if ($archives.Count -eq 0) { Write-Fail "Aucune archive dans $Source" }
    Write-Host "Archives disponibles dans $Source :" -ForegroundColor Cyan
    foreach ($a in $archives) {
        $kind = if ($a.Name -like "datazen-db-*") { "base   " } else { "medias " }
        Write-Host ("  {0} {1,-46} {2,9:N0} Ko  {3:yyyy-MM-dd HH:mm}" -f $kind, $a.Name, ($a.Length / 1KB), $a.LastWriteTime)
    }
    exit 0
}

if ($DbArchive -eq "" -and $MediaArchive -eq "") {
    Write-Fail "Indiquez -DbArchive et/ou -MediaArchive (ou -List pour voir les archives)."
}

$dotenv = Read-DotEnv (Join-Path $Root ".env")

# --- Restauration de la base ------------------------------------------------

if ($DbArchive -ne "") {
    if (-not (Test-Path -LiteralPath $DbArchive)) { Write-Fail "Archive introuvable : $DbArchive" }
    $DbArchive = (Resolve-Path -LiteralPath $DbArchive).Path

    if ($DbArchive.EndsWith(".sqlite3")) {
        $targetPath = if ($Target -ne "") { $Target } else { Join-Path $Root "db-restaure.sqlite3" }
        if (Test-Path -LiteralPath $targetPath) {
            if (-not $Force) { Write-Fail "$targetPath existe deja. Utilisez -Force pour l'ecraser, ou -Target pour un autre nom." }
            Copy-Item -LiteralPath $targetPath -Destination "$targetPath.avant-restauration" -Force
            Write-Warn "Ancienne base conservee : $targetPath.avant-restauration"
        }
        Write-Step "Restauration de la base SQLite vers $targetPath"
        Copy-Item -LiteralPath $DbArchive -Destination $targetPath -Force

        $py = @"
import sqlite3, sys
c = sqlite3.connect(r'$targetPath')
print('integrity:', c.execute('PRAGMA integrity_check').fetchone()[0])
print('users:', c.execute('SELECT COUNT(*) FROM auth_user').fetchone()[0])
"@
        $python = Join-Path $Root "venv\Scripts\python.exe"
        if (Test-Path -LiteralPath $python) { & $python -c $py }
        else { Write-Warn "venv absent : integrite non verifiee." }

        if ($targetPath -ne (Join-Path $Root "db.sqlite3")) {
            Write-Warn "La base active est db.sqlite3. Renommez $targetPath si la restauration est valide."
        }
    }
    elseif ($DbArchive.EndsWith(".dump")) {
        $pgRestore = Resolve-PgTool "pg_restore"
        $createdb  = Resolve-PgTool "createdb"
        if (-not $pgRestore) { Write-Fail "pg_restore introuvable. Ajoutez le dossier bin de PostgreSQL au PATH." }

        $pgHost = Get-Setting $dotenv "DJANGO_DB_HOST" "127.0.0.1"
        $pgPort = Get-Setting $dotenv "DJANGO_DB_PORT" "5432"
        $dbUser = Get-Setting $dotenv "DJANGO_DB_USER" "datazen"
        $dbPass = Get-Setting $dotenv "DJANGO_DB_PASSWORD" ""
        $dbName = Get-Setting $dotenv "DJANGO_DB_NAME" "datazen"

        if ($Target -ne "") { $dbName = $Target }
        elseif (-not $Force) { $dbName = "${dbName}_restaure" }

        if ($dbName -eq (Get-Setting $dotenv "DJANGO_DB_NAME" "datazen") -and -not $Force) {
            Write-Fail "Refus d'ecraser la base de production sans -Force."
        }

        Write-Step "Restauration PostgreSQL vers la base « $dbName »"

        $previous = $env:PGPASSWORD
        if ($dbPass -ne "") { $env:PGPASSWORD = $dbPass }
        try {
            if ($createdb) {
                & $createdb --host=$pgHost --port=$pgPort --username=$dbUser --owner=$dbUser $dbName 2>&1 | Out-Null
            }
            & $pgRestore --host=$pgHost --port=$pgPort --username=$dbUser `
                         --no-owner --no-acl --dbname=$dbName $DbArchive
            if ($LASTEXITCODE -ne 0) { Write-Fail "pg_restore a echoue (code $LASTEXITCODE)." }
        }
        finally { $env:PGPASSWORD = $previous }

        Write-Host "    Base restaurée : $dbName" -ForegroundColor Green
        if ($dbName -ne (Get-Setting $dotenv "DJANGO_DB_NAME" "datazen")) {
            Write-Warn "Pointez DJANGO_DB_NAME sur « $dbName » pour utiliser cette restauration."
        }
    }
    else {
        Write-Fail "Format d'archive non reconnu (attendu .dump ou .sqlite3) : $DbArchive"
    }
}

# --- Restauration des medias ------------------------------------------------

if ($SkipMedia -or $MediaArchive -eq "") {
    if ($MediaArchive -eq "" -and -not $SkipMedia) {
        Write-Warn "Aucune archive de medias fournie : les DataFile peuvent pointer vers des fichiers absents."
    }
}
else {
    if (-not (Test-Path -LiteralPath $MediaArchive)) { Write-Fail "Archive introuvable : $MediaArchive" }
    $MediaArchive = (Resolve-Path -LiteralPath $MediaArchive).Path

    $mediaDir = Join-Path $Root "media"
    Write-Step "Restauration de media/ depuis $(Split-Path -Leaf $MediaArchive)"

    if (Test-Path -LiteralPath $mediaDir) {
        $existing = (Get-ChildItem -LiteralPath $mediaDir -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count
        if ($existing -gt 0) {
            if (-not $Force) {
                Write-Fail "media/ contient deja $existing fichiers. Utilisez -Force pour fusionner par-dessus."
            }
            $safety = Join-Path $Root ("media-avant-restauration-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
            Write-Warn "Copie de securite de media/ vers $safety"
            Move-Item -LiteralPath $mediaDir -Destination $safety
        }
    }

    New-Item -ItemType Directory -Path $mediaDir -Force | Out-Null

    if ($MediaArchive.EndsWith(".tar.gz")) {
        $tarExe = Get-Command "tar.exe" -ErrorAction SilentlyContinue
        if (-not $tarExe) { Write-Fail "tar.exe introuvable : impossible de decompresser l'archive." }
        & $tarExe.Source -xzf $MediaArchive -C $mediaDir
        if ($LASTEXITCODE -ne 0) { Write-Fail "tar a echoue (code $LASTEXITCODE)." }
    }
    elseif ($MediaArchive.EndsWith(".zip")) {
        Expand-Archive -LiteralPath $MediaArchive -DestinationPath $mediaDir -Force
    }
    else {
        Write-Fail "Format d'archive non reconnu (attendu .tar.gz ou .zip) : $MediaArchive"
    }

    $restored = (Get-ChildItem -LiteralPath $mediaDir -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count
    Write-Host "    Fichiers restaures : $restored" -ForegroundColor Green
}

Write-Host ""
Write-Host "Restauration terminee." -ForegroundColor Cyan
Write-Host "Etape suivante : python manage.py migrate, puis python manage.py check --deploy." -ForegroundColor Cyan
