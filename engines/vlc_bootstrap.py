"""Configura libVLC bundled prima dell'import python-vlc (macOS frozen)."""

import os
import sys
from pathlib import Path


def configure_vlc_library() -> None:
    """Imposta PYTHON_VLC_LIB_PATH sul bundle interno; evita VLC.app di architettura errata."""
    if sys.platform != "darwin" or not getattr(sys, "frozen", False):
        return

    vlc_dir = Path(sys.executable).resolve().parent / "vlc"
    libvlc = vlc_dir / "libvlc.dylib"
    libvlccore = vlc_dir / "libvlccore.dylib"

    if not libvlc.is_file() or not libvlccore.is_file():
        raise RuntimeError(
            "libVLC non trovato dentro KaraokeManager.app.\n"
            "Scarica l'artifact GitHub corretto:\n"
            "  • Mac M1/M2/M3 → KaraokeManager-macos-arm64\n"
            "  • Mac Intel → KaraokeManager-macos-x86_64"
        )

    os.environ["PYTHON_VLC_LIB_PATH"] = str(libvlc)
    os.environ["VLC_PLUGIN_PATH"] = str(vlc_dir / "plugins")

    # Verifica che le dylib bundled siano caricabili (architettura compatibile).
    import ctypes

    try:
        ctypes.CDLL(str(libvlccore))
        ctypes.CDLL(str(libvlc))
    except OSError as exc:
        machine = os.uname().machine
        raise RuntimeError(
            f"libVLC nel bundle non compatibile con questo Mac ({machine}).\n"
            f"Probabilmente hai installato l'artifact sbagliato o VLC Intel in "
            f"/Applications/VLC.app.\n"
            f"Dettaglio: {exc}"
        ) from exc
