"""Diagnostica e ambiente Windows prima del caricamento di main (PyInstaller)."""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path


def _install_base() -> Path:
    return Path(sys.executable).resolve().parent


def _log_path() -> Path:
    return _install_base() / "logs" / "startup.log"


def _boot_log(message: str) -> None:
    try:
        path = _log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(message + "\n")
    except OSError:
        pass


def _show_error_box(text: str) -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(  # type: ignore[attr-defined]
            0,
            text[:2000],
            "KaraokeManager — errore avvio",
            0x00000010,
        )
    except OSError:
        pass


def _install_excepthook() -> None:
    crash_log = _install_base() / "logs" / "crash.log"

    def _hook(exc_type, exc, tb) -> None:
        lines = traceback.format_exception(exc_type, exc, tb)
        text = "".join(lines)
        try:
            crash_log.parent.mkdir(parents=True, exist_ok=True)
            with crash_log.open("a", encoding="utf-8") as handle:
                handle.write("\n--- crash ---\n")
                handle.write(text)
        except OSError:
            pass
        _boot_log("EXCEPTION:\n" + text)
        if getattr(sys, "frozen", False):
            _show_error_box(
                "KaraokeManager non è riuscito ad avviarsi.\n\n"
                f"{exc_type.__name__}: {exc}\n\n"
                f"Dettaglio in:\n{crash_log}"
            )
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = _hook


def _maybe_attach_console() -> None:
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return
    if "--diagnose" not in sys.argv:
        return
    try:
        import ctypes

        ctypes.windll.kernel32.AttachConsole(0xFFFFFFFF)  # ATTACH_PARENT_PROCESS
        ctypes.windll.kernel32.AllocConsole()
        sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="replace")
        sys.stderr = open("CONERR$", "w", encoding="utf-8", errors="replace")
    except OSError:
        pass


def _configure_qt_and_dlls(app_dir: Path, internal: Path) -> None:
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(str(app_dir))
        if internal.is_dir():
            os.add_dll_directory(str(internal))
        qt_bin = internal / "PyQt6" / "Qt6" / "bin"
        if qt_bin.is_dir():
            os.add_dll_directory(str(qt_bin))
        for sub in ("PyQt6", "pywin32_system32"):
            candidate = internal / sub
            if candidate.is_dir():
                os.add_dll_directory(str(candidate))

    plugins = internal / "PyQt6" / "Qt6" / "plugins"
    if plugins.is_dir():
        os.environ.setdefault("QT_PLUGIN_PATH", str(plugins))
        platforms = plugins / "platforms"
        if platforms.is_dir():
            os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", str(platforms))

    qwindows = plugins / "platforms" / "qwindows.dll"
    if not qwindows.is_file():
        _boot_log(f"WARNING: manca {qwindows}")


if sys.platform == "win32" and getattr(sys, "frozen", False):
    _boot_log("=== avvio runtime ===")
    _install_excepthook()
    _maybe_attach_console()
    app_dir = _install_base()
    internal = app_dir / "_internal"
    _configure_qt_and_dlls(app_dir, internal)
    try:
        import faulthandler

        fault_path = _install_base() / "logs" / "faulthandler.log"
        fault_path.parent.mkdir(parents=True, exist_ok=True)
        fault_file = fault_path.open("a", encoding="utf-8")
        faulthandler.enable(file=fault_file, all_threads=True)
        _boot_log("faulthandler attivo")
    except OSError as exc:
        _boot_log(f"faulthandler non attivo: {exc}")
