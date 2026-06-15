#!/usr/bin/env bash
# Build KaraokeManager per macOS: .app bundle + .dmg (uso interno, non firmato).
#
# Prerequisiti (su Mac):
#   - macOS Ventura 13+ consigliato
#   - Python 3.11 o 3.12 (universal2 da python.org per build Intel+Apple Silicon)
#   - VLC.app in /Applications (https://www.videolan.org/vlc/)
#   - ffmpeg nel PATH (brew install ffmpeg)
#
# Uso:
#   cd karaoke_manager
#   chmod +x build/build_macos.sh
#   ./build/build_macos.sh                  # universal2 (default)
#   ./build/build_macos.sh arm64            # solo Apple Silicon
#   ./build/build_macos.sh x86_64           # solo Intel
#   SKIP_DMG=1 ./build/build_macos.sh       # solo .app, senza .dmg
#
# Output:
#   dist/KaraokeManager.app
#   dist/KaraokeManager-<version>-macOS-<arch>.dmg
#
# Dati utente a runtime (non nel bundle):
#   ~/Library/Application Support/KaraokeManager/

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ARCH="${1:-universal2}"
VLC_APP="${VLC_APP:-/Applications/VLC.app}"
SKIP_DMG="${SKIP_DMG:-0}"

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "Errore: eseguire questo script su macOS." >&2
    exit 1
fi

echo "==> KaraokeManager macOS build (arch=$ARCH, root=$ROOT)"

echo "==> Dipendenze Python..."
python3 -m pip install --upgrade pip --quiet
python3 -m pip install -r requirements.txt -r requirements-dev.txt --quiet

export KM_TARGET_ARCH="$ARCH"
echo "==> PyInstaller (KM_TARGET_ARCH=$KM_TARGET_ARCH)..."
python3 -m PyInstaller build/KaraokeManager_mac.spec --noconfirm --clean

APP="$ROOT/dist/KaraokeManager.app"
MACOS="$APP/Contents/MacOS"

if [[ ! -f "$MACOS/KaraokeManager" ]]; then
    echo "Errore: build fallita, eseguibile non trovato in $MACOS" >&2
    exit 1
fi

echo "==> Copia ffmpeg..."
BIN="$MACOS/bin"
mkdir -p "$BIN"
if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "Errore: ffmpeg non trovato. Installa con: brew install ffmpeg" >&2
    exit 1
fi
cp "$(command -v ffmpeg)" "$BIN/ffmpeg"
chmod +x "$BIN/ffmpeg"
if command -v ffprobe >/dev/null 2>&1; then
    cp "$(command -v ffprobe)" "$BIN/ffprobe"
    chmod +x "$BIN/ffprobe"
fi

echo "==> Copia librerie VLC..."
if [[ ! -d "$VLC_APP" ]]; then
    echo "Errore: VLC non trovato in '$VLC_APP'." >&2
    echo "Installa VLC da https://www.videolan.org/ oppure: VLC_APP=/path/VLC.app $0" >&2
    exit 1
fi

VLC_MACOS="$VLC_APP/Contents/MacOS"
VLC_DEST="$MACOS/vlc"
rm -rf "$VLC_DEST"
mkdir -p "$VLC_DEST"

_copy_vlc_lib() {
    local name="$1"
    if [[ -f "$VLC_MACOS/lib/$name" ]]; then
        cp "$VLC_MACOS/lib/$name" "$VLC_DEST/"
    elif [[ -f "$VLC_MACOS/$name" ]]; then
        cp "$VLC_MACOS/$name" "$VLC_DEST/"
    else
        echo "Errore: file VLC mancante: $name" >&2
        exit 1
    fi
}

_copy_vlc_lib "libvlc.dylib"
_copy_vlc_lib "libvlccore.dylib"

if [[ -d "$VLC_MACOS/plugins" ]]; then
    cp -R "$VLC_MACOS/plugins" "$VLC_DEST/plugins"
else
    echo "Errore: cartella plugins VLC non trovata" >&2
    exit 1
fi

echo "==> Verifica architetture..."
_check_arch() {
    local file="$1"
    if [[ -f "$file" ]] && command -v lipo >/dev/null 2>&1; then
        local archs
        archs="$(lipo -archs "$file" 2>/dev/null || echo "?")"
        echo "    $(basename "$file"): $archs"
        if [[ "$ARCH" == "universal2" ]] && [[ "$archs" != *"x86_64"* || "$archs" != *"arm64"* ]]; then
            echo "    ⚠ non universal2 — per Intel+M1 serve Python/VLC/ffmpeg universal2" >&2
        fi
    fi
}
_check_arch "$MACOS/KaraokeManager"
_check_arch "$VLC_DEST/libvlc.dylib"
_check_arch "$BIN/ffmpeg"

echo "==> Firma ad-hoc (evita errore «app danneggiata» su Gatekeeper)..."
xattr -cr "$APP"
while IFS= read -r -d '' file; do
    codesign --force --sign - "$file" 2>/dev/null || true
done < <(find "$MACOS" -type f \( -name "*.dylib" -o -name "*.so" \) -print0)
while IFS= read -r -d '' file; do
    if [[ -x "$file" ]] || file "$file" | grep -q "Mach-O"; then
        codesign --force --sign - "$file" 2>/dev/null || true
    fi
done < <(find "$MACOS" -type f -print0)
codesign --force --deep --sign - "$APP"
xattr -cr "$APP"

APP_VERSION="$(python3 -c "import config; print(config.APP_VERSION)")"

if [[ "$SKIP_DMG" == "1" ]]; then
    echo ""
    echo "Build completata: $APP"
    echo "Dati utente: ~/Library/Application Support/KaraokeManager/"
    exit 0
fi

echo "==> Creazione .dmg..."
DMG_NAME="KaraokeManager-${APP_VERSION}-macOS-${ARCH}.dmg"
STAGING="$ROOT/dist/dmg-staging"
DMG_OUT="$ROOT/dist/$DMG_NAME"

rm -rf "$STAGING" "$DMG_OUT"
mkdir -p "$STAGING"
cp -R "$APP" "$STAGING/"
ln -s /Applications "$STAGING/Applications"

hdiutil create -volname "KaraokeManager" -srcfolder "$STAGING" -ov -format UDZO "$DMG_OUT"
rm -rf "$STAGING"

echo ""
echo "Build completata:"
echo "  App:  $APP"
echo "  DMG:  $DMG_OUT"
echo ""
echo "Installazione (uso interno, non firmato):"
echo "  1. Apri il .dmg e trascina KaraokeManager.app in Applicazioni"
echo "  2. Al primo avvio: tasto destro su KaraokeManager -> Apri -> Apri"
echo "  3. Database e download: ~/Library/Application Support/KaraokeManager/"
