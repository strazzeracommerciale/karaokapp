# Build KaraokeManager per Windows: eseguibile + dipendenze + installer opzionale.
#
# Prerequisiti sul PC di build:
#   - Python 3.11+ con pip
#   - VLC 64-bit (default: C:\Program Files\VideoLAN\VLC)
#   - ffmpeg nel PATH (winget install Gyan.FFmpeg)
#   - (opzionale) Inno Setup 6 per generare KaraokeManager-Setup.exe
#
# Uso:
#   cd karaoke_manager
#   .\build\build_windows.ps1
#
# Output:
#   dist\KaraokeManager\           cartella portabile pronta all'uso
#   dist\KaraokeManager-Setup.exe  installer (se Inno Setup è installato)

param(
    [string]$VlcPath = "C:\Program Files\VideoLAN\VLC",
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "==> KaraokeManager build (root: $Root)"

Write-Host "==> Installazione dipendenze Python..."
python -m pip install --upgrade pip | Out-Null
python -m pip install -r requirements.txt -r requirements-dev.txt

Write-Host "==> PyInstaller..."
python -m PyInstaller build/KaraokeManager.spec --noconfirm --clean

$Dist = Join-Path $Root "dist\KaraokeManager"
if (-not (Test-Path (Join-Path $Dist "KaraokeManager.exe"))) {
    throw "Build fallita: KaraokeManager.exe non trovato in $Dist"
}

Write-Host "==> Copia ffmpeg..."
$ffmpeg = (Get-Command ffmpeg -ErrorAction SilentlyContinue).Source
if (-not $ffmpeg) {
    throw "ffmpeg non trovato nel PATH. Installalo con: winget install Gyan.FFmpeg"
}
$binDir = Join-Path $Dist "bin"
New-Item -ItemType Directory -Force -Path $binDir | Out-Null
Copy-Item -Force $ffmpeg (Join-Path $binDir "ffmpeg.exe")
$ffprobe = (Get-Command ffprobe -ErrorAction SilentlyContinue).Source
if ($ffprobe) {
    Copy-Item -Force $ffprobe (Join-Path $binDir "ffprobe.exe")
}

Write-Host "==> Copia librerie VLC..."
if (-not (Test-Path $VlcPath)) {
    throw "VLC non trovato in '$VlcPath'. Passa -VlcPath se installato altrove."
}
$vlcDest = Join-Path $Dist "vlc"
if (Test-Path $vlcDest) {
    Remove-Item -Recurse -Force $vlcDest
}
New-Item -ItemType Directory -Force -Path $vlcDest | Out-Null
foreach ($dll in @("libvlc.dll", "libvlccore.dll")) {
    $src = Join-Path $VlcPath $dll
    if (-not (Test-Path $src)) {
        throw "File VLC mancante: $src"
    }
    Copy-Item -Force $src $vlcDest
}
Copy-Item -Recurse -Force (Join-Path $VlcPath "plugins") (Join-Path $vlcDest "plugins")

Write-Host "==> Cartelle dati utente..."
foreach ($dir in @("data", "media\downloads", "media\dj\downloads", "logs")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $Dist $dir) | Out-Null
}

Write-Host ""
Write-Host "Build completata: $Dist"
Write-Host "  Avvio test: .\dist\KaraokeManager\KaraokeManager.exe"

if ($SkipInstaller) {
    Write-Host "Installer saltato (-SkipInstaller)."
    exit 0
}

$isccCandidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
)
$iscc = $isccCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    Write-Host ""
    Write-Host "Inno Setup non trovato: distribuisci la cartella dist\KaraokeManager oppure"
    Write-Host "installa Inno Setup 6 e rilancia questo script per KaraokeManager-Setup.exe"
    exit 0
}

Write-Host "==> Inno Setup..."
& $iscc (Join-Path $Root "build\installer.iss")
$setup = Join-Path $Root "dist\KaraokeManager-Setup.exe"
if (Test-Path $setup) {
    Write-Host "Installer creato: $setup"
} else {
    throw "ISCC terminato senza produrre $setup"
}
