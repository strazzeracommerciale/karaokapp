"""Riproduzione VLC dedicata alla consolle DJ (singolo output video+audio)."""

import logging
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QWidget

from engines.vlc_engine import VlcEngine
from engines.ytdlp_engine import YtdlpEngine

logger = logging.getLogger(__name__)


class DjPlayerService(QObject):
    """Player DJ indipendente dal PlayerService karaoke."""

    track_started = pyqtSignal(dict)
    track_ended = pyqtSignal()
    track_failed = pyqtSignal(dict, str)
    position_updated = pyqtSignal(float, float)

    def __init__(
        self,
        vlc_engine: VlcEngine,
        ytdlp_engine: YtdlpEngine | None = None,
    ) -> None:
        """Inizializza il player DJ con un motore VLC dedicato."""
        super().__init__()
        self._vlc = vlc_engine
        self._ytdlp = ytdlp_engine
        self._current_track: dict | None = None
        self._current_path: str | None = None
        self._volume = 100
        self._last_resolve_error = ""
        self._vlc.set_position_callback(self._on_position_changed)
        self._vlc.set_end_callback(self._on_playback_ended)

    def bind_output_widget(self, widget: QWidget) -> None:
        """Collega l'output video+audio al widget della consolle DJ."""
        self._vlc.set_output_widget(widget)
        logger.debug("Output VLC DJ collegato al widget")

    def play_track(self, track: dict) -> None:
        """Carica e riproduce un brano nel player DJ."""
        path = self._resolve_path(track)
        if not path:
            logger.error("Track DJ senza path o stream_url: %s", track.get("title"))
            self.track_failed.emit(track, self._resolve_failure_reason(track))
            return

        self.stop()
        self._current_track = track
        self._current_path = path
        self._vlc.set_end_callback(self._on_playback_ended)
        self._vlc.set_mute(False)
        self._vlc.load(path)
        self._vlc.play()
        self._vlc.set_mute(False)
        self._vlc.set_volume(self._volume)
        self.track_started.emit(track)
        logger.info("DJ riproduzione avviata: %s", track.get("title"))

    def pause_resume(self) -> None:
        """Alterna tra pausa e ripresa."""
        if self._vlc.is_playing():
            self._vlc.pause()
        else:
            self._vlc.play()

    def stop(self) -> None:
        """Ferma la riproduzione corrente."""
        self._vlc.set_end_callback(None)
        self._vlc.stop()
        self._current_track = None
        self._current_path = None

    def seek(self, seconds: float) -> None:
        """Salta alla posizione indicata in secondi."""
        self._vlc.seek(seconds)

    def set_volume(self, volume: int) -> None:
        """Imposta il volume audio (0-100)."""
        self._volume = max(0, min(100, int(volume)))
        self._vlc.set_mute(False)
        self._vlc.set_volume(self._volume)

    def get_state(self) -> dict:
        """Restituisce lo stato corrente del player DJ."""
        duration = self._vlc.get_duration()
        position_ratio = self._vlc.get_position()
        position_sec = position_ratio * duration if duration > 0 else 0.0
        return {
            "is_playing": self._vlc.is_playing(),
            "current_track": self._current_track,
            "position": position_sec,
            "duration": duration,
        }

    def _resolve_path(self, track: dict) -> str:
        """Restituisce il file locale se presente, altrimenti uno stream URL YouTube."""
        local_path = track.get("local_path", "")
        if local_path and Path(local_path).exists():
            return local_path
        stream_url = track.get("stream_url", "") or ""
        if stream_url:
            return stream_url
        if track.get("source") == "youtube" and self._ytdlp is not None:
            youtube_id = track.get("youtube_id", "")
            logger.info("Risoluzione stream URL DJ per %s", youtube_id)
            try:
                return self._ytdlp.get_stream_url(youtube_id)
            except Exception as exc:  # noqa: BLE001 - errore di rete, log e abort
                logger.error("Stream URL DJ non risolvibile: %s", exc)
                self._last_resolve_error = str(exc)
                return ""
        return ""

    def _resolve_failure_reason(self, track: dict) -> str:
        """Messaggio d'errore leggibile quando la riproduzione non parte."""
        if track.get("source") == "youtube":
            detail = self._last_resolve_error
            if detail:
                return (
                    "Impossibile aprire lo stream YouTube.\n"
                    f"Dettaglio: {detail}\n\n"
                    "Attendi che il download in background termini oppure "
                    "riprova tra qualche secondo."
                )
            return "Video YouTube non disponibile (rimosso o privato)."
        return "File non trovato o non riproducibile."

    def _on_position_changed(self, ratio: float) -> None:
        """Propaga aggiornamenti posizione alla UI DJ."""
        duration = self._vlc.get_duration()
        position_sec = ratio * duration if duration > 0 else 0.0
        self.position_updated.emit(position_sec, duration)

    def _on_playback_ended(self) -> None:
        """Gestisce la fine naturale del brano."""
        self._current_track = None
        self.track_ended.emit()
