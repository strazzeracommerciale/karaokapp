# -*- mode: python ; coding: utf-8 -*-
"""Spec PyInstaller per KaraokeManager (.app macOS).

Eseguire via build/build_macos.sh su un Mac.
Impostare KM_TARGET_ARCH=universal2|arm64|x86_64 (default: universal2).
"""

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).resolve().parent
sys.path.insert(0, str(ROOT))

import config as km_config

APP_VERSION = km_config.APP_VERSION
TARGET_ARCH = os.environ.get("KM_TARGET_ARCH", "universal2")
_arch = None if TARGET_ARCH in ("", "native") else TARGET_ARCH

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
    runtime_hooks=[str(ROOT / "build" / "runtime_hook_darwin.py")],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)

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
    argv_emulation=True,
    target_arch=_arch,
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
    target_arch=_arch,
)

app = BUNDLE(
    coll,
    name="KaraokeManager.app",
    icon=None,
    bundle_identifier="local.karaokemanager.app",
    info_plist={
        "CFBundleShortVersionString": APP_VERSION,
        "CFBundleVersion": APP_VERSION,
        "CFBundleDisplayName": "KaraokeManager",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "13.0",
    },
)
