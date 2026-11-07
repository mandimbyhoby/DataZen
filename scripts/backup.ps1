<#
Sauvegarde DataZen : base de donnees + repertoire media/.

Cree une archive horodatee par element, puis applique une rotation.
La base et media/ sont sauvegardes au meme instant : les restaurer
toujours ensemble.

Exemples :
    .\scripts\backup.ps1
    .\scripts\backup.ps1 -Keep 30
    .\scripts\backup.ps1 -Destination D:\sauvegardes-datazen
    .\scripts\backup.ps1 -Engine sqlite
#>
[CmdletBinding()]
param(
    [string] $Destination = "",
    [int]    $Keep = 14,
    [ValidateSet("auto", "postgresql", "sqlite")]
    [string] $Engine = "auto",
    [switch] $SkipMedia
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($Destination)) {
    $Destination = Join-Path $Root "backups"
}

function Write-Step { param([string] $Message) Write-Host "==> $Message" -ForegroundColor Cyan }
function Write-Warn { param([string] $Message) Write-Host "    $Message" -ForegroundColor Yellow }
function Write-Fail { param([string] $Message) Write-Host "ERREUR : $Message" -ForegroundColor Red; exit 1 }

# --- Lecture de .env --------------------------------------------------------

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
    # L'environnement du processus prime sur .env (meme regle que settings.py).
    $fromProcess = [Environment]::GetEnvironmentVariable($Key)
    if (-not [string]::IsNullOrWhiteSpace($fromProcess)) { return $fromProcess }
    if ($Env.ContainsKey($Key) -and $Env[$Key] -ne "") { return $Env[$Key] }
    return $Default
}

$dotenv = Read-DotEnv (Join-Path $Root ".env")

# --- Resolution du moteur ---------------------------------------------------

$dbEngine  = $Engine
$autoFallback = ($Engine -eq "auto")
if ($dbEngine -eq "auto") {
    $configured = Get-Setting $dotenv "DJANGO_DB_ENGINE" "postgresql"
    if ($configured -eq "sqlite") { $dbEngine = "sqlite" } else { $dbEngine = "postgresql" }
}

if ($dbEngine -eq "postgresql") {
    $pgHost = Get-Setting $dotenv "DJANGO_DB_HOST" "127.0.0.1"
    $pgPort = [int] (Get-Setting $dotenv "DJANGO_DB_PORT" "5432")
    $probe = New-Object System.Net.Sockets.TcpClient
    try {
        $probe.Connect($pgHost, $pgPort)
        $probe.Close()
    }
    catch {
        # Le repli n'est accepte que si le moteur n'a pas ete impose.
        $sqliteFile = Join-Path $Root "db.sqlite3"
        if ($autoFallback -and (Test-Path -LiteralPath $sqliteFile)) {
            Write-Warn "PostgreSQL injoignable sur ${pgHost}:${pgPort} : bascule sur SQLite."
            $dbEngine = "sqlite"
        }
        else {
            Write-Fail "PostgreSQL injoignable sur ${pgHost}:${pgPort}. Demarrez la base ou utilisez -Engine sqlite."
        }
    }
}

# --- Preparation ------------------------------------------------------------

if (-not (Test-Path -LiteralPath $Destination)) {
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    Write-Step "Repertoire de sauvegarde cree : $Destination"
}
# Chemins absolus : l'archivage des medias change de repertoire courant.
$Destination = (Resolve-Path -LiteralPath $Destination).Path

$stamp   = Get-Date -Format "yyyyMMdd-HHmmss"
$created = @()

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

# --- Sauvegarde de la base --------------------------------------------------

if ($dbEngine -eq "sqlite") {
    $sqliteFile = Join-Path $Root "db.sqlite3"
    if (-not (Test-Path -LiteralPath $sqliteFile)) { Write-Fail "Base SQLite introuvable : $sqliteFile" }

    $target = Join-Path $Destination "datazen-db-$stamp.sqlite3"
    Write-Step "Sauvegarde de la base SQLite"
    # Une copie simple peut capter une ecriture en cours : la commande .backup
    # de SQLite produit un instantane coherent.
    $sqliteExe = Get-Command "sqlite3" -ErrorAction SilentlyContinue
    if ($sqliteExe) {
        & $sqliteExe.Source $sqliteFile ".backup '$target'"
        if ($LASTEXITCODE -ne 0) { Write-Fail "sqlite3 .backup a echoue." }
    }
    else {
        Write-Warn "sqlite3 absent : copie de fichier simple (arret du serveur recommande)."
        Copy-Item -LiteralPath $sqliteFile -Destination $target -Force
    }
    $created += $target
}
else {
    $pgDump = Resolve-PgTool "pg_dump"
    if (-not $pgDump) { Write-Fail "pg_dump introuvable. Installez les outils PostgreSQL ou ajoutez son dossier bin au PATH." }

    $dbName = Get-Setting $dotenv "DJANGO_DB_NAME" "datazen"
    $dbUser = Get-Setting $dotenv "DJANGO_DB_USER" "datazen"
    $dbPass = Get-Setting $dotenv "DJANGO_DB_PASSWORD" ""
    $dbSsl  = Get-Setting $dotenv "DJANGO_DB_SSLMODE" "prefer"

    $target = Join-Path $Destination "datazen-db-$stamp.dump"
    Write-Step "Sauvegarde de la base PostgreSQL « $dbName »"

    $previous = $env:PGPASSWORD
    if ($dbPass -ne "") { $env:PGPASSWORD = $dbPass }
    try {
        & $pgDump --host=$pgHost --port=$pgPort --username=$dbUser `
                  --format=custom --no-owner --no-acl --compress=9 `
                  --file=$target $dbName
        if ($LASTEXITCODE -ne 0) { Write-Fail "pg_dump a echoue (code $LASTEXITCODE)." }
    }
    finally {
        $env:PGPASSWORD = $previous
    }
    if ($dbSsl -ne "prefer") { Write-Warn "sslmode=$dbSsl non transmis : pg_dump applique la valeur de pg_hba.conf." }
    $created += $target
}

# --- Sauvegarde des medias --------------------------------------------------

$mediaDir = Join-Path $Root "media"
if ($SkipMedia) {
    Write-Warn "Medias ignores (-SkipMedia) : la restauration sera incomplete."
}
elseif (-not (Test-Path -LiteralPath $mediaDir)) {
    Write-Warn "Repertoire media/ absent : rien a sauvegarder."
}
else {
    $fileCount = (Get-ChildItem -LiteralPath $mediaDir -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count
    if ($fileCount -eq 0) {
        Write-Warn "media/ est vide."
    }
    else {
        $target = Join-Path $Destination "datazen-media-$stamp.tar.gz"
        Write-Step "Archivage de media/ ($fileCount fichiers)"
        # Compress-Archive est lent sur des milliers de petits fichiers ;
        # bsdtar (natif depuis Windows 10) est nettement plus rapide.
        $tarExe = Get-Command "tar.exe" -ErrorAction SilentlyContinue
        if ($tarExe) {
            Push-Location -LiteralPath $mediaDir
            try {
                & $tarExe.Source -czf $target .
                if ($LASTEXITCODE -ne 0) { Write-Fail "tar a echoue (code $LASTEXITCODE)." }
            }
            finally { Pop-Location }
        }
        else {
            Write-Warn "tar absent : utilisation de Compress-Archive (plus lent)."
            $target = Join-Path $Destination "datazen-media-$stamp.zip"
            Compress-Archive -Path (Join-Path $mediaDir "*") -DestinationPath $target -CompressionLevel Optimal -Force
        }
        $created += $target
    }
}

# --- Verification -----------------------------------------------------------

foreach ($file in $created) {
    $item = Get-Item -LiteralPath $file
    if ($item.Length -le 0) { Write-Fail "Archive vide : $($item.Name)" }
    Write-Host ("    {0,-42} {1,10:N0} Ko" -f $item.Name, ($item.Length / 1KB)) -ForegroundColor Green
}

# --- Rotation ---------------------------------------------------------------

Write-Step "Rotation (conservation des $Keep dernieres archives par type)"

foreach ($pattern in @("datazen-db-*", "datazen-media-*")) {
    $old = Get-ChildItem -LiteralPath $Destination -Filter $pattern -File |
           Sort-Object LastWriteTime -Descending |
           Select-Object -Skip $Keep
    foreach ($file in $old) {
        Remove-Item -LiteralPath $file.FullName -Force
        Write-Warn "Supprime : $($file.Name)"
    }
}

Write-Host ""
Write-Host "Sauvegarde terminee dans $Destination" -ForegroundColor Cyan
Write-Host "Verifiez regulierement qu'une archive se restaure : voir README section 7." -ForegroundColor Cyan
