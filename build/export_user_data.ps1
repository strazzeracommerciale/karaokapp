# Esporta database + libreria media per trasferimento su altro PC.
#
# Uso (PC sorgente, con KaraokeManager chiuso):
#   cd karaoke_manager
#   .\build\export_user_data.ps1
#
# Output: dist\user_data_backup_YYYYMMDD-HHmmss.zip
# Contiene: data\ (DB) e media\ (download karaoke + DJ)

param(
    [string]$SourceRoot = "",
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$Root = if ($SourceRoot) { $SourceRoot } else { Split-Path -Parent $PSScriptRoot }
$Out = if ($OutputDir) { $OutputDir } else { Join-Path $Root "dist" }

$dataDir = Join-Path $Root "data"
$mediaDir = Join-Path $Root "media"
$dbFile = Join-Path $dataDir "karaoke.db"

if (-not (Test-Path $dbFile)) {
    throw "Database non trovato: $dbFile (KaraokeManager è mai stato avviato qui?)"
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$zipName = "user_data_backup_$stamp.zip"
$zipPath = Join-Path $Out $zipName
New-Item -ItemType Directory -Force -Path $Out | Out-Null

$staging = Join-Path $env:TEMP "km_export_$stamp"
if (Test-Path $staging) {
    Remove-Item -Recurse -Force $staging
}
New-Item -ItemType Directory -Force -Path $staging | Out-Null

Write-Host "==> Esportazione dati utente"
Write-Host "    Origine: $Root"

Copy-Item -Recurse -Force $dataDir (Join-Path $staging "data")
if (Test-Path $mediaDir) {
    Copy-Item -Recurse -Force $mediaDir (Join-Path $staging "media")
}

$manifest = @{
    exported_at  = (Get-Date -Format "o")
    source_root  = (Resolve-Path $Root).Path
    app_version  = "KaraokeManager"
    migrate_hint = "Sul PC destinazione, dopo l'import, eseguire: KaraokeManager.exe --migrate-paths `"$(Resolve-Path $Root).Path`""
}
$manifest | ConvertTo-Json | Set-Content (Join-Path $staging "manifest.json") -Encoding UTF8

if (Test-Path $zipPath) {
    Remove-Item -Force $zipPath
}
Compress-Archive -Path (Join-Path $staging "*") -DestinationPath $zipPath -CompressionLevel Optimal
Remove-Item -Recurse -Force $staging

$sizeMb = [math]::Round((Get-Item $zipPath).Length / 1MB, 1)
Write-Host ""
Write-Host "Backup creato: $zipPath ($sizeMb MB)"
Write-Host ""
Write-Host "Prossimi passi:"
Write-Host "  1. Copia lo zip sul portatile (USB, rete, ecc.)"
Write-Host "  2. Chiudi KaraokeManager sul portatile"
Write-Host "  3. Estrai data\ e media\ nella cartella di installazione"
Write-Host "  4. Esegui la migrazione percorsi (vedi README o istruzioni agente)"
