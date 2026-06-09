"""Costanti globali e path del progetto KaraokeManager."""

import shutil as _shutil
import sys as _sys
import tempfile
from pathlib import Path

APP_NAME: str = "KaraokeManager"
BASE_DIR: Path = Path(__file__).resolve().parent
DB_PATH: Path = BASE_DIR / "data" / "karaoke.db"
MEDIA_DIR: Path = BASE_DIR / "media"
DOWNLOAD_DIR: Path = MEDIA_DIR / "downloads"
TEMP_DIR: Path = Path(tempfile.gettempdir()) / "karaoke_manager"
LOG_PATH: Path = BASE_DIR / "logs" / "karaoke_manager.log"

# Media DJ: cartella fisica separata, stesso database (track_type='dj').
DJ_MEDIA_DIR: Path = BASE_DIR / "media" / "dj" / "downloads"
DJ_DOWNLOAD_DIR: Path = DJ_MEDIA_DIR

YT_SEARCH_LIMIT: int = 10
YT_SEARCH_PREFIX: str = "karaoke"
DJ_YT_SEARCH_PREFIX: str = ""
FUZZY_THRESHOLD: int = 65
SEARCH_DEBOUNCE_MS: int = 400
LOCAL_SEARCH_MIN_RESULTS: int = 3

# Consolle DJ (finestra separata, Fase 1)
DJ_CONSOLE_DEFAULT_WIDTH: int = 900
DJ_CONSOLE_DEFAULT_HEIGHT: int = 700
DJ_CONSOLE_SETTINGS_GEOMETRY_KEY: str = "dj_console/geometry"

# Sottofondo (filler) durante le pause
FILLER_DEFAULT_VOLUME: int = 30
FILLER_FADE_MS: int = 2000
FILLER_FADE_STEP_MS: int = 50

if _sys.platform == "win32":
    # Il filler usa un output audio separato (DirectSound) così il suo volume
    # non muove la sessione WASAPI del karaoke nel mixer di Windows.
    FILLER_VLC_ARGS: tuple[str, ...] = ("--no-video", "--aout=directsound")
else:
    FILLER_VLC_ARGS: tuple[str, ...] = ("--no-video",)

if _sys.platform == "win32":
    # Cerca ffmpeg nel PATH di sistema prima, poi nel percorso WinGet noto.
    _ffmpeg_in_path = _shutil.which("ffmpeg")
    if _ffmpeg_in_path:
        FFMPEG_BIN: str = _ffmpeg_in_path
    else:
        FFMPEG_BIN: str = (
            str(Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet"
            / "Packages" / "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
            / "ffmpeg-8.1.1-full_build" / "bin" / "ffmpeg.exe")
        )
else:
    FFMPEG_BIN: str = "ffmpeg"
