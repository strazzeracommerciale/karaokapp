# Scarica il motore mpv usato dalla 3.0.0.
# Build shinchiro del 28 settembre 2026, variante x86_64 (senza AVX2):
# il Celeron del portatile non esegue i binari x86_64-v3.
# Gli hash sono quelli del motore ascoltato in prova.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Dest = Join-Path $Root "mpv"
New-Item -ItemType Directory -Force -Path $Dest | Out-Null

$Expected = @{
    "mpv.exe"            = "1156426aa36a2046bfdb2d772020f8dc2f50debc638b7cd0fe8fc977fe079b86"
    "d3dcompiler_43.dll" = "4b074a3976399dc735484f5d43d04b519b7bdee8ac719d9ab8ed6bd4e6be0345"
    "vulkan-1.dll"       = "8644669401d2c080ea10cfea2ba8a7c63d76e10a4e7ae8246837df1dfd157ea8"
}

function Test-MpvReady {
    foreach ($name in $Expected.Keys) {
        $path = Join-Path $Dest $name
        if (-not (Test-Path -LiteralPath $path)) {
            return $false
        }
        $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLower()
        if ($hash -ne $Expected[$name]) {
            return $false
        }
    }
    return $true
}

if (Test-MpvReady) {
    Write-Host "mpv gia presente, hash verificati."
    exit 0
}

$work = Join-Path $env:TEMP "karokapp-mpv-fetch"
if (Test-Path $work) {
    Remove-Item -Recurse -Force $work
}
New-Item -ItemType Directory -Force -Path $work | Out-Null

$mpvArchive = Join-Path $work "mpv.7z"
$mpvUrl = "https://github.com/shinchiro/mpv-winbuild-cmake/releases/download/20260928/mpv-x86_64-20260928-git-e470f8986e.7z"
Write-Host "Scarico mpv..."
curl.exe -L --fail --retry 3 -o $mpvArchive $mpvUrl
if ($LASTEXITCODE -ne 0) {
    throw "Download mpv fallito"
}

$sevenZip = @(
    "C:\Program Files\7-Zip\7z.exe",
    "C:\Program Files (x86)\7-Zip\7z.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
$extracted = Join-Path $work "mpv"
New-Item -ItemType Directory -Force -Path $extracted | Out-Null
if ($sevenZip) {
    & $sevenZip e $mpvArchive "-o$extracted" "mpv.exe" "d3dcompiler_43.dll" -y | Out-Null
} else {
    tar.exe -xf $mpvArchive -C $extracted "mpv.exe" "d3dcompiler_43.dll"
    if ($LASTEXITCODE -ne 0) {
        throw "Estrazione mpv fallita: serve 7-Zip oppure tar in grado di aprire i .7z"
    }
}

$vulkanZip = Join-Path $work "VulkanRT.zip"
$vulkanUrl = "https://sdk.lunarg.com/sdk/download/1.3.296.0/windows/VulkanRT-1.3.296.0-Components.zip"
Write-Host "Scarico vulkan-1.dll..."
curl.exe -L --fail --retry 3 -o $vulkanZip $vulkanUrl
if ($LASTEXITCODE -ne 0) {
    throw "Download Vulkan runtime fallito"
}
tar.exe -xf $vulkanZip -C $work "VulkanRT-1.3.296.0-Components/x64/vulkan-1.dll"
Copy-Item -Force (Join-Path $work "VulkanRT-1.3.296.0-Components\x64\vulkan-1.dll") (Join-Path $extracted "vulkan-1.dll")

foreach ($name in $Expected.Keys) {
    $src = Join-Path $extracted $name
    if (-not (Test-Path -LiteralPath $src)) {
        throw "File mpv mancante dopo l'estrazione: $name"
    }
    Copy-Item -Force $src (Join-Path $Dest $name)
}

if (-not (Test-MpvReady)) {
    throw "Gli hash di mpv non coincidono con il motore provato."
}
Write-Host "mpv pronto in $Dest"
