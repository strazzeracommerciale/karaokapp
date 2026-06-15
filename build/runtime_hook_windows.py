"""Hook PyInstaller: libVLC bundled, certificati SSL per yt-dlp."""

import os
import sys
from pathlib import Path

if sys.platform == "win32" and getattr(sys, "frozen", False):
    vlc_dir = Path(sys.executable).resolve().parent / "vlc"
    if vlc_dir.is_dir():
        os.add_dll_directory(str(vlc_dir))
        os.environ["VLC_PLUGIN_PATH"] = str(vlc_dir / "plugins")

try:
    import certifi

    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
except ImportError:
    pass
