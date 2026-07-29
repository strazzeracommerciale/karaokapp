# -*- mode: python ; coding: utf-8 -*-
"""Spec PyInstaller per KaraokeManager (Windows onedir).

Generato/mantenuto manualmente. Eseguire via build/build_windows.ps1.
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).resolve().parent

block_cipher = None

pyqt_datas, pyqt_binaries, pyqt_hidden = collect_all("PyQt6")
yt_datas, yt_binaries, yt_hidden = collect_all("yt_dlp")

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=pyqt_binaries + yt_binaries,
    datas=[
        (str(ROOT / "assets" / "style.qss"), "assets"),
        (str(ROOT / "assets" / "style_a.qss"), "assets"),
        (str(ROOT / "assets" / "style_b.qss"), "assets"),
        (str(ROOT / "db" / "schema.sql"), "db"),
        *pyqt_datas,
        *yt_datas,
    ],
    hiddenimports=[
        "vlc",
        "rapidfuzz",
        "certifi",
        *pyqt_hidden,
        *yt_hidden,
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[
        str(ROOT / "build" / "runtime_hook_startup.py"),
        str(ROOT / "build" / "runtime_hook_win_isolate.py"),
        str(ROOT / "build" / "runtime_hook_windows.py"),
    ],
    excludes=[],
    win_no_prefer_redirects=False,
    cipher=block_cipher,
    noarchive=False,
)

# pyi_rth_multiprocessing carica socket e può prendere python3XX.dll dal PATH di sistema.
a.scripts = [entry for entry in a.scripts if "pyi_rth_multiprocessing" not in entry[0]]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="KaraokeManager",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="KaraokeManager",
)
