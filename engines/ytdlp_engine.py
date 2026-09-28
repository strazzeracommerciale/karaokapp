"""Download e risoluzione stream YouTube via yt-dlp."""

import logging
from collections.abc import Callable
from pathlib import Path

import yt_dlp

import config

logger = logging.getLogger(__name__)

# Prima un file unico con audio (come il vecchio itag 18). Se YouTube offre solo
# flussi separati, video H.264 + audio m4a: VLC li riproduce insieme subito,
# mentre il download in background li unisce in un mp4.
_STREAM_FORMAT = (
    "b[vcodec^=avc1][acodec^=mp4a]/"
    "b[acodec!=none][vcodec!=none]/"
    "bv*[vcodec^=avc1][height<=?720][ext=mp4]+ba[ext=m4a]/"
    "bv*[vcodec^=avc1][ext=mp4]+ba[ext=m4a]/"
    "bv*[ext=mp4]+ba/b"
)


def playback_urls_from_info(info: dict) -> tuple[str, str | None]:
    """Estrae URL video e, se l'audio è un flusso a parte, URL audio.

    Un file progressivo restituisce solo l'URL video (l'audio è già dentro).
    """
    requested = info.get("requested_formats") or []
    video_url = ""
    audio_url = ""
    for fmt in requested:
        url = fmt.get("url") or ""
        if not url:
            continue
        vcodec = fmt.get("vcodec") or "none"
        acodec = fmt.get("acodec") or "none"
        if vcodec != "none" and not video_url:
            video_url = url
        if acodec != "none" and vcodec == "none" and not audio_url:
            audio_url = url
    if video_url and audio_url:
        return video_url, audio_url
    single = info.get("url") or video_url or audio_url
    if not single:
        raise ValueError("Nessuno stream URL")
    return single, None


def _base_ydl_opts() -> dict:
    """Opzioni yt-dlp comuni, incluso ffmpeg bundled nell'installer Windows."""
    # YouTube risponde spesso 403 sugli URL dei flussi se la richiesta esce in IPv6.
    opts: dict = {"quiet": True, "no_warnings": True, "source_address": "0.0.0.0"}
    ffmpeg = Path(config.FFMPEG_BIN)
    if ffmpeg.is_file():
        opts["ffmpeg_location"] = str(ffmpeg.parent)
    return opts


class YtdlpEngine:
    """Motore yt-dlp per stream URL, download e metadati."""

    def resolve_stream(self, youtube_id: str) -> tuple[str, str | None]:
        """Ritorna l'URL video e, se serve, l'URL audio separato.

        YouTube spesso non ha più un mp4 unico con audio. In quel caso il video
        H.264 e l'audio m4a vanno riprodotti insieme, senza aspettare il download.
        """
        url = f"https://www.youtube.com/watch?v={youtube_id}"
        ydl_opts = {**_base_ydl_opts(), "format": _STREAM_FORMAT}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if not info:
            raise ValueError(f"Nessuno stream URL per {youtube_id}")
        try:
            return playback_urls_from_info(info)
        except ValueError as exc:
            raise ValueError(f"Nessuno stream URL per {youtube_id}") from exc

    def get_stream_url(self, youtube_id: str) -> str:
        """Ritorna l'URL video da riprodurre subito, anche a download incompleto."""
        video_url, _audio_url = self.resolve_stream(youtube_id)
        return video_url

    def download(
        self,
        youtube_id: str,
        output_path: str,
        progress_hook: Callable[[dict], None] | None = None,
        basename: str | None = None,
    ) -> str:
        """Scarica il video in output_path e invoca progress_hook."""
        url = f"https://www.youtube.com/watch?v={youtube_id}"
        out_dir = Path(output_path)
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = basename or youtube_id
        target_path = out_dir / f"{stem}.mp4"
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
            "artist": info.get("artist") or "",
            "track": info.get("track") or "",
            "creator": info.get("creator") or info.get("uploader", ""),
            "uploader": info.get("uploader", ""),
            "duration": info.get("duration"),
            "thumbnail_url": info.get("thumbnail", ""),
        }
