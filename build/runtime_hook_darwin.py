"""Hook PyInstaller (macOS): libVLC bundled e certificati SSL per yt-dlp."""

import os
import sys
from pathlib import Path

if sys.platform == "darwin" and getattr(sys, "frozen", False):
    try:
        from engines.vlc_bootstrap import configure_vlc_library

        configure_vlc_library()
    except Exception:
        pass  # messaggio completo al primo import vlc_engine
    macos_dir = Path(sys.executable).resolve().parent
    vlc_dir = macos_dir / "vlc"
    libvlc = vlc_dir / "libvlc.dylib"
    if libvlc.is_file():
        os.environ["PYTHON_VLC_LIB_PATH"] = str(libvlc)
        os.environ["VLC_PLUGIN_PATH"] = str(vlc_dir / "plugins")
        fallback = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
        vlc_lib = str(vlc_dir)
        os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = (
            f"{vlc_lib}:{fallback}" if fallback else vlc_lib
        )

try:
    import certifi

    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
except ImportError:
    pass
