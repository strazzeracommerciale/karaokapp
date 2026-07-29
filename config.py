"""Costanti globali e path del progetto KaraokeManager."""

import os as _os
import shutil as _shutil
import sys as _sys
import tempfile
from pathlib import Path

APP_NAME: str = "KaraokeManager"
APP_VERSION: str = "2.2.2"


def _install_dir() -> Path:
    """Directory dell'installazione (cartella dell'exe se frozen, repo in sviluppo)."""
    if getattr(_sys, "frozen", False):
        return Path(_sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _data_dir() -> Path:
    """Directory scrivibile per database, media e log.

    Su macOS il bundle .app in /Applications non è scrivibile: i dati utente
    restano in ~/Library/Application Support/KaraokeManager/.
    Su Windows (e in sviluppo) coincidono con la cartella dell'app.
    """
    if getattr(_sys, "frozen", False) and _sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    return _install_dir()


def _bundle_dir() -> Path:
    """Risorse read-only incluse nel pacchetto PyInstaller (_MEIPASS se frozen)."""
    if getattr(_sys, "frozen", False):
        return Path(getattr(_sys, "_MEIPASS", _install_dir()))
    return Path(__file__).resolve().parent


BASE_DIR: Path = _data_dir()
INSTALL_DIR: Path = _install_dir()
BUNDLE_DIR: Path = _bundle_dir()
ASSETS_DIR: Path = BUNDLE_DIR / "assets"
SCHEMA_PATH: Path = BUNDLE_DIR / "db" / "schema.sql"
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
ARTIST_MATCH_THRESHOLD: int = 88
ARTIST_REGISTRY_SEED_PATH: Path = BUNDLE_DIR / "data" / "seeds" / "known_artists.txt"
SEARCH_DEBOUNCE_MS: int = 400
LOCAL_SEARCH_MIN_RESULTS: int = 3

# Consolle DJ (finestra separata, Fase 1)
DJ_CONSOLE_DEFAULT_WIDTH: int = 900
DJ_CONSOLE_DEFAULT_HEIGHT: int = 700
DJ_CONSOLE_SETTINGS_GEOMETRY_KEY: str = "dj_console/geometry"

# Finestra Preparazione (libreria, scalette, strumenti batch)
PREP_WINDOW_DEFAULT_WIDTH: int = 960
PREP_WINDOW_DEFAULT_HEIGHT: int = 720
PREP_WINDOW_SETTINGS_GEOMETRY_KEY: str = "prep_window/geometry"
PREP_PLAYBACK_DEFAULT_WIDTH: int = 720
PREP_PLAYBACK_DEFAULT_HEIGHT: int = 520
PREP_PLAYBACK_SETTINGS_GEOMETRY_KEY: str = "prep_playback/geometry"

# Sfoglia libreria (finestra live serata)
LIBRARY_BROWSE_DEFAULT_WIDTH: int = 720
LIBRARY_BROWSE_DEFAULT_HEIGHT: int = 640
LIBRARY_BROWSE_SETTINGS_GEOMETRY_KEY: str = "library_browse/geometry"

# Uscita audio VLC (Windows mmdevice): ID dispositivo o "" = predefinito di sistema.
AUDIO_OUTPUT_DEVICE_SETTINGS_KEY: str = "audio/output_device_id"

# Aggiornamenti online (GitHub Releases, solo Windows standalone)
UPDATE_GITHUB_REPO: str = "strazzeracommerciale/karokapp"
UPDATE_INSTALLER_ASSET: str = "KaraokeManager-Setup.exe"
UPDATE_USER_AGENT: str = f"{APP_NAME}/{APP_VERSION}"
UPDATE_CHECK_DELAY_MS: int = 8000
UPDATE_CHECK_COOLDOWN_HOURS: int = 24
UPDATE_SETTINGS_LAST_CHECK_KEY: str = "update/last_check_ts"
UPDATE_SETTINGS_SKIP_VERSION_KEY: str = "update/skip_version"
UPDATE_GITHUB_TOKEN_FILENAME: str = "github_update_token.txt"


def resolve_update_github_token() -> str:
    """Token read-only per API GitHub (repo privato). Env o file accanto all'installazione."""
    env_token = _os.environ.get("KAROKAPP_GITHUB_TOKEN", "").strip()
    if env_token:
        return env_token
    token_path = INSTALL_DIR / UPDATE_GITHUB_TOKEN_FILENAME
    if token_path.is_file():
        try:
            return token_path.read_text(encoding="utf-8").strip()
        except OSError:
            pass
    return ""

UI_THEME_SETTINGS_KEY: str = "ui/theme"
UI_THEME_LIGHT: str = "light"
UI_THEME_DARK: str = "dark"
UI_THEME_DEFAULT: str = UI_THEME_DARK

# Sottofondo (filler) durante le pause
FILLER_DEFAULT_VOLUME: int = 30
FILLER_FADE_MS: int = 2000
FILLER_FADE_STEP_MS: int = 50

if _sys.platform == "win32":
    # DirectSound: sessione audio stabile durante resize/anteprima (set_hwnd non tocca l'aout).
    # Il filler usa la stessa backend con --no-video per volume indipendente in mixer Windows.
    KARAOKE_VLC_ARGS: tuple[str, ...] = ("--aout=directsound",)
    DJ_VLC_ARGS: tuple[str, ...] = ("--aout=directsound",)
    PREP_VLC_ARGS: tuple[str, ...] = ("--aout=directsound",)
    FILLER_VLC_ARGS: tuple[str, ...] = ("--no-video", "--aout=directsound")
else:
    KARAOKE_VLC_ARGS: tuple[str, ...] = ()
    DJ_VLC_ARGS: tuple[str, ...] = ()
    PREP_VLC_ARGS: tuple[str, ...] = ()
    FILLER_VLC_ARGS: tuple[str, ...] = ("--no-video",)

if _sys.platform == "win32":
    _bundled_vlc = INSTALL_DIR / "vlc"
    _libvlc = _bundled_vlc / "libvlc.dll"
    if _libvlc.is_file():
        _os.environ["PYTHON_VLC_LIB_PATH"] = str(_libvlc)
        _os.environ["VLC_PLUGIN_PATH"] = str(_bundled_vlc / "plugins")
        _os.add_dll_directory(str(_bundled_vlc))
    elif _bundled_vlc.is_dir():
        _os.add_dll_directory(str(_bundled_vlc))
        _os.environ["VLC_PLUGIN_PATH"] = str(_bundled_vlc / "plugins")

if _sys.platform == "darwin":
    _bundled_vlc = INSTALL_DIR / "vlc"
    _libvlc = _bundled_vlc / "libvlc.dylib"
    if _libvlc.is_file():
        _os.environ["PYTHON_VLC_LIB_PATH"] = str(_libvlc)
        _os.environ["VLC_PLUGIN_PATH"] = str(_bundled_vlc / "plugins")
    elif _bundled_vlc.is_dir():
        _os.environ["VLC_PLUGIN_PATH"] = str(_bundled_vlc / "plugins")

if _sys.platform == "win32":
    _bundled_ffmpeg = INSTALL_DIR / "bin" / "ffmpeg.exe"
    if _bundled_ffmpeg.is_file():
        FFMPEG_BIN: str = str(_bundled_ffmpeg)
    else:
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
elif _sys.platform == "darwin":
    _bundled_ffmpeg = INSTALL_DIR / "bin" / "ffmpeg"
    if _bundled_ffmpeg.is_file():
        FFMPEG_BIN: str = str(_bundled_ffmpeg)
    else:
        _ffmpeg_in_path = _shutil.which("ffmpeg")
        FFMPEG_BIN: str = _ffmpeg_in_path or "ffmpeg"
else:
    FFMPEG_BIN: str = "ffmpeg"
