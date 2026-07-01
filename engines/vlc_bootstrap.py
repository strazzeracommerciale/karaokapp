"""Configura libVLC bundled prima dell'import python-vlc."""

import os
import sys
from pathlib import Path


def _install_dir() -> Path:
    """Cartella dell'eseguibile (PyInstaller) o del repo in sviluppo."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def configure_vlc_library() -> None:
    """Imposta PYTHON_VLC_LIB_PATH sul bundle interno (Windows e macOS frozen)."""
    if not getattr(sys, "frozen", False):
        return

    vlc_dir = _install_dir() / "vlc"

    if sys.platform == "win32":
        libvlc = vlc_dir / "libvlc.dll"
        libvlccore = vlc_dir / "libvlccore.dll"
        if not libvlc.is_file() or not libvlccore.is_file():
            raise RuntimeError(
                "libVLC non trovato nella cartella di installazione.\n\n"
                f"Percorso atteso:\n  {vlc_dir}\n\n"
                "Reinstalla con KaraokeManager-Setup.exe (non copiare solo il .exe).\n"
                "La cartella deve contenere la sottocartella vlc\\ con libvlc.dll."
            )
        os.environ["PYTHON_VLC_LIB_PATH"] = str(libvlc)
        os.environ["VLC_PLUGIN_PATH"] = str(vlc_dir / "plugins")
        os.add_dll_directory(str(vlc_dir))
        import ctypes

        try:
            ctypes.WinDLL(str(libvlccore))
            ctypes.WinDLL(str(libvlc))
        except OSError as exc:
            raise RuntimeError(
                f"libVLC non caricabile su questo PC.\nDettaglio: {exc}"
            ) from exc
        return

    if sys.platform == "darwin":
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
        import ctypes

        try:
            ctypes.CDLL(str(libvlccore))
            ctypes.CDLL(str(libvlc))
        except OSError as exc:
            machine = os.uname().machine
            raise RuntimeError(
                f"libVLC nel bundle non compatibile con questo Mac ({machine}).\n"
                f"Dettaglio: {exc}"
            ) from exc
