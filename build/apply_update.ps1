# Applica un delta dopo la chiusura di KaraokeManager.
# Non tocca data\, media\, logs\ né github_update_token.txt.
param(
    [Parameter(Mandatory = $true)][string]$Staging,
    [Parameter(Mandatory = $true)][string]$InstallDir,
    [Parameter(Mandatory = $true)][int]$WaitPid
)

$ErrorActionPreference = "Stop"
$logDir = Join-Path $InstallDir "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir "update.log"

function Write-Log([string]$Message) {
    Add-Content -Path $log -Value ("{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message)
}

function Assert-SafeRelative([string]$Relative) {
    $norm = ($Relative -replace "\\", "/").TrimStart("/")
    if (-not $norm -or $norm.Contains("..")) {
        throw "Path non ammesso: $Relative"
    }
    $top = $norm.Split("/")[0]
    if ($top -in @("data", "media", "logs") -or $norm -eq "github_update_token.txt") {
        throw "Path protetto, aggiornamento annullato: $Relative"
    }
    return $norm
}

try {
    Write-Log "Attendo la chiusura del processo $WaitPid"
    $deadline = (Get-Date).AddSeconds(45)
    while ((Get-Process -Id $WaitPid -ErrorAction SilentlyContinue) -and (Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 400
    }
    $still = Get-Process -Id $WaitPid -ErrorAction SilentlyContinue
    if ($still) {
        Stop-Process -Id $WaitPid -Force
        Start-Sleep -Seconds 1
    }
    Get-Process KaraokeManager -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 1

    $planPath = Join-Path $Staging "plan.json"
    $plan = Get-Content -Raw -Path $planPath | ConvertFrom-Json
    $payload = Join-Path $Staging "payload"
    foreach ($item in @($plan.files)) {
        $rel = Assert-SafeRelative $item.path
        $src = Join-Path $payload ($rel -replace "/", "\")
        $dst = Join-Path $InstallDir ($rel -replace "/", "\")
        if (-not (Test-Path -LiteralPath $src)) {
            throw "File delta mancante: $rel"
        }
        $hash = (Get-FileHash -LiteralPath $src -Algorithm SHA256).Hash.ToLower()
        if ($hash -ne [string]$item.sha256.ToLower()) {
            throw "Hash non valido, aggiornamento annullato: $rel"
        }
        $parent = Split-Path -Parent $dst
        if ($parent) {
            New-Item -ItemType Directory -Force -Path $parent | Out-Null
        }
        Copy-Item -LiteralPath $src -Destination $dst -Force
        $copied = (Get-FileHash -LiteralPath $dst -Algorithm SHA256).Hash.ToLower()
        if ($copied -ne $hash) {
            throw "Copia non verificata: $rel"
        }
        Write-Log "Aggiornato $rel"
    }
    foreach ($removed in @($plan.removed)) {
        if (-not $removed) { continue }
        $rel = Assert-SafeRelative $removed
        $dst = Join-Path $InstallDir ($rel -replace "/", "\")
        if (Test-Path -LiteralPath $dst) {
            Remove-Item -LiteralPath $dst -Force
            Write-Log "Rimosso $rel"
        }
    }
    $manifestSrc = Join-Path $Staging "manifest.json"
    if (Test-Path -LiteralPath $manifestSrc) {
        Copy-Item -LiteralPath $manifestSrc -Destination (Join-Path $InstallDir "manifest.json") -Force
    }
    Write-Log "Aggiornamento applicato, riavvio"
    Start-Process -FilePath (Join-Path $InstallDir "KaraokeManager.exe") -WorkingDirectory $InstallDir
    exit 0
}
catch {
    Write-Log "ERRORE: $($_.Exception.Message)"
    $exe = Join-Path $InstallDir "KaraokeManager.exe"
    if (Test-Path -LiteralPath $exe) {
        Start-Process -FilePath $exe -WorkingDirectory $InstallDir
    }
    exit 1
}
