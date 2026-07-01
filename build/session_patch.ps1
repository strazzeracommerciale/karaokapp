# Sessione di sviluppo: log granulare delle modifiche + patch unica finale.
#
# Uso (dalla root karaoke_manager):
#   .\build\session_patch.ps1 -Start -Message "Fix UI sottofondo"
#   .\build\session_patch.ps1 -Log -Message "Spostato nome file su seconda riga"
#   .\build\session_patch.ps1 -Log -Message "Test layout filler aggiornato"
#   .\build\session_patch.ps1 -Finish
#
# Output in dist/patches/:
#   karokapp-<sessione>.patch   patch unica (git diff dal baseline)
#   karokapp-<sessione>.md      riepilogo con log e file toccati

param(
    [switch]$Start,
    [switch]$Log,
    [switch]$Finish,
    [switch]$Status,
    [string]$Message = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$SessionDir = Join-Path $Root ".session"
$StatePath = Join-Path $SessionDir "active.json"
$PatchOutDir = Join-Path $Root "dist\patches"

function Get-GitRoot {
    $top = git -C $Root rev-parse --show-toplevel 2>$null
    if (-not $top) {
        throw "Git non disponibile o repo non inizializzato in $Root"
    }
    return $top.Trim()
}

function Read-SessionState {
    if (-not (Test-Path $StatePath)) {
        return $null
    }
    return Get-Content $StatePath -Raw | ConvertFrom-Json
}

function Write-SessionState($state) {
    New-Item -ItemType Directory -Force -Path $SessionDir | Out-Null
    $state | ConvertTo-Json -Depth 6 | Set-Content -Path $StatePath -Encoding UTF8
}

function Get-ChangedFiles($baseline) {
    if ($baseline -eq "EMPTY") {
        return @(git -C $Root diff --name-only)
    }
    $names = git -C $Root diff --name-only $baseline
    return @($names | Where-Object { $_ })
}

function Write-PatchFile($baseline, $targetPath) {
    if ($baseline -eq "EMPTY") {
        git -C $Root diff | Set-Content -Path $targetPath -Encoding UTF8
        return
    }
    git -C $Root diff $baseline | Set-Content -Path $targetPath -Encoding UTF8
}

Set-Location $Root
Get-GitRoot | Out-Null

if ($Status) {
    $state = Read-SessionState
    if (-not $state) {
        Write-Host "Nessuna sessione attiva."
        exit 0
    }
    Write-Host "Sessione: $($state.id)"
    Write-Host "Inizio:   $($state.started_at)"
    Write-Host "Baseline: $($state.baseline)"
    Write-Host "Voci log: $($state.entries.Count)"
    foreach ($entry in $state.entries) {
        Write-Host "  [$($entry.at)] $($entry.message)"
        if ($entry.files -and $entry.files.Count -gt 0) {
            Write-Host "           -> $($entry.files -join ', ')"
        }
    }
    exit 0
}

if ($Start) {
    $existing = Read-SessionState
    if ($existing) {
        throw "Sessione già attiva ($($existing.id)). Esegui -Finish prima di -Start."
    }
    $baseline = git -C $Root rev-parse HEAD 2>$null
    if (-not $baseline) {
        $baseline = "EMPTY"
    }
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $state = [ordered]@{
        id         = "karokapp-$stamp"
        started_at = (Get-Date -Format "o")
        baseline   = $baseline
        entries    = @()
    }
    if ($Message) {
        $state.entries += [ordered]@{
            at      = (Get-Date -Format "o")
            message = $Message
            files   = @(Get-ChangedFiles $baseline)
        }
    }
    Write-SessionState $state
    Write-Host "Sessione avviata: $($state.id)"
    Write-Host "Baseline git: $baseline"
    Write-Host "Registra modifiche con: .\build\session_patch.ps1 -Log -Message '...'"
    exit 0
}

if ($Log) {
    if (-not $Message) {
        throw "Specifica -Message per ogni voce di log."
    }
    $state = Read-SessionState
    if (-not $state) {
        throw "Nessuna sessione attiva. Esegui prima -Start."
    }
    $files = @(Get-ChangedFiles $state.baseline)
    $state.entries += [ordered]@{
        at      = (Get-Date -Format "o")
        message = $Message
        files   = $files
    }
    Write-SessionState $state
    Write-Host "Log: $Message"
    if ($files.Count -gt 0) {
        Write-Host "  File (delta sessione): $($files -join ', ')"
    }
    exit 0
}

if ($Finish) {
    $state = Read-SessionState
    if (-not $state) {
        throw "Nessuna sessione attiva. Esegui prima -Start."
    }
    New-Item -ItemType Directory -Force -Path $PatchOutDir | Out-Null
    $patchPath = Join-Path $PatchOutDir "$($state.id).patch"
    $summaryPath = Join-Path $PatchOutDir "$($state.id).md"

    Write-PatchFile $state.baseline $patchPath
    $allFiles = @(Get-ChangedFiles $state.baseline)
    $patchSize = (Get-Item $patchPath).Length

    $lines = @(
        "# Sessione $($state.id)",
        "",
        "- Inizio: $($state.started_at)",
        "- Fine: $(Get-Date -Format 'o')",
        "- Baseline git: ``$($state.baseline)``",
        "- Patch: ``$($state.id).patch`` ($patchSize byte)",
        "",
        "## Log modifiche",
        ""
    )
    $index = 1
    foreach ($entry in $state.entries) {
        $lines += "### $index. $($entry.message)"
        $lines += ""
        $lines += "- Quando: $($entry.at)"
        if ($entry.files -and $entry.files.Count -gt 0) {
            $lines += "- File al momento della voce:"
            foreach ($f in $entry.files) {
                $lines += "  - ``$f``"
            }
        }
        $lines += ""
        $index++
    }
    $lines += "## File nel patch finale"
    $lines += ""
    if ($allFiles.Count -eq 0) {
        $lines += "_Nessuna modifica rispetto al baseline._"
    } else {
        foreach ($f in $allFiles) {
            $lines += "- ``$f``"
        }
    }
    $lines += ""
    $lines += "## Applicare la patch"
    $lines += ""
    $lines += "``````powershell"
    $lines += "cd <root-repo>"
    $lines += "git apply --check dist/patches/$($state.id).patch"
    $lines += "git apply dist/patches/$($state.id).patch"
    $lines += "``````"

    $lines -join "`n" | Set-Content -Path $summaryPath -Encoding UTF8
    Remove-Item -Force $StatePath

    Write-Host "Sessione chiusa: $($state.id)"
    Write-Host "  Patch:   $patchPath"
    Write-Host "  Riepilogo: $summaryPath"
    Write-Host "  File:    $($allFiles.Count)"
    exit 0
}

Write-Host @"
Uso:
  .\build\session_patch.ps1 -Start [-Message "titolo sessione"]
  .\build\session_patch.ps1 -Log -Message "descrizione modifica"
  .\build\session_patch.ps1 -Finish
  .\build\session_patch.ps1 -Status
"@
