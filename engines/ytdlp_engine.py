"""Download e risoluzione stream YouTube via yt-dlp."""

import logging
from collections.abc import Callable
from pathlib import Path

import yt_dlp

import config

logger = logging.getLogger(__name__)


def _base_ydl_opts() -> dict:
    """Opzioni yt-dlp comuni, incluso ffmpeg bundled nell'installer Windows."""
    opts: dict = {"quiet": True, "no_warnings": True}
    ffmpeg = Path(config.FFMPEG_BIN)
    if ffmpeg.is_file():
        opts["ffmpeg_location"] = str(ffmpeg.parent)
    return opts


class YtdlpEngine:
    """Motore yt-dlp per stream URL, download e metadati."""

    def get_stream_url(self, youtube_id: str) -> str:
        """Ritorna URL diretto del miglior flusso audio+video pre-merged."""
        url = f"https://www.youtube.com/watch?v={youtube_id}"
        # Preferisci un flusso unico H.264 con audio (es. itag 18): leggero da decodificare
        # e con audio incluso, a differenza degli stream AV1/VP9 video-only.
        ydl_opts = {
            **_base_ydl_opts(),
            "format": "best[vcodec^=avc1][ext=mp4]/best[ext=mp4]/best",
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        stream_url = info.get("url", "")
        if not stream_url:
            raise ValueError(f"Nessuno stream URL per {youtube_id}")
        return stream_url

    def download(
        self,
        youtube_id: str,
        output_path: str,
        progress_hook: Callable[[dict], None] | None = None,
    ) -> str:
        """Scarica il video in output_path e invoca progress_hook."""
        url = f"https://www.youtube.com/watch?v={youtube_id}"
        out_dir = Path(output_path)
        out_dir.mkdir(parents=True, exist_ok=True)
        target_path = out_dir / f"{youtube_id}.mp4"
        # Forza H.264 (avc1): l'AV1/VP9 non ha decodifica hardware su GPU datate e,
        # con due output video, manda in errore il converter VLC (schermo nero, niente
        # audio). avc1 fino a 720p è leggero e si decodifica in hardware.
        ydl_opts: dict = {
            **_base_ydl_opts(),
            "format": (
                "bestvideo[vcodec^=avc1][height<=?720]+bestaudio[ext=m4a]/"
                "best[vcodec^=avc1][height<=?720]/"
                "best[ext=mp4]/best"
            ),
            "outtmpl": str(target_path.with_suffix("")),
            "merge_output_format": "mp4",
        }
        if progress_hook is not None:
            ydl_opts["progress_hooks"] = [progress_hook]
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        if not target_path.exists():
            raise FileNotFoundError(f"Download non trovato: {target_path}")
        return str(target_path)

    def extract_metadata(self, youtube_id: str) -> dict:
        """Estrae metadati base dal video YouTube."""
        url = f"https://www.youtube.com/watch?v={youtube_id}"
        ydl_opts = {**_base_ydl_opts(), "skip_download": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        return {
            "title": info.get("title", ""),
            "uploader": info.get("uploader", ""),
            "duration": info.get("duration"),
            "thumbnail_url": info.get("thumbnail", ""),
        }
