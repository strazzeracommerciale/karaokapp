"""Coordina la riproduzione VLC nativa su due monitor.

Un unico file viene riprodotto da due player VLC (stessa istanza libvlc): il primario,
embeddato nel pannello operatore, porta anche l'audio; il secondario, embeddato nella
finestra HDMI fullscreen, è muto per non duplicare il suono verso l'impianto. VLC
gestisce internamente la sincronia audio/video di ciascun player. Nessun pitch/tempo.
"""

import logging
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

from engines.vlc_engine import VlcEngine
from engines.ytdlp_engine import YtdlpEngine

logger = logging.getLogger(__name__)


class PlayerService(QObject):
    """Service di riproduzione con segnali verso la UI."""

    track_started = pyqtSignal(dict)
    track_ended = pyqtSignal()
    track_failed = pyqtSignal(dict, str)
    position_updated = pyqtSignal(float, float)

    def __init__(
        self,
        vlc_engine: VlcEngine,
        ytdlp_engine: YtdlpEngine | None = None,
        vlc_engine_secondary: VlcEngine | None = None,
    ) -> None:
        """Inizializza il player con i motori VLC primario e (opzionale) secondario."""
        super().__init__()
        self._vlc = vlc_engine
        self._ytdlp = ytdlp_engine
        self._vlc2 = vlc_engine_secondary
        self._current_track: dict | None = None
        self._current_path: str | None = None
        self._secondary_active = False
        self._volume = 100
        self._vlc.set_position_callback(self._on_position_changed)
        self._vlc.set_end_callback(self._on_playback_ended)

    def play_track(self, track: dict, *_ignored, **_kwargs) -> None:
        """Carica e riproduce un brano sui due monitor.

        Accetta argomenti extra (es. pitch/tempo) per compatibilità con i chiamanti,
        ma li ignora: pitch e tempo non sono più supportati.
        """
        path = self._resolve_path(track)
        if not path:
            logger.error("Track senza path o stream_url: %s", track.get("title"))
            if track.get("source") == "youtube":
                reason = "Video YouTube non disponibile (rimosso o privato)."
            else:
                reason = "File non trovato o non riproducibile."
            self.track_failed.emit(track, reason)
            return

        start_time = 0.0
        if path == track.get("local_path"):
            start_time = float(track.get("start_offset_sec") or 0.0)

        self.stop()
        self._current_track = track
        self._current_path = path
        self._vlc.set_end_callback(self._on_playback_ended)
        self._vlc.set_mute(False)
        self._vlc.load(path, start_time=start_time)
        self._vlc.play()
        self._vlc.set_mute(False)
        self._vlc.set_volume(self._volume)
        if self._vlc2 is not None and self._secondary_active:
            self._vlc2.load(path, start_time=start_time)
            self._vlc2.play()
        self.track_started.emit(track)
        logger.info("Riproduzione avviata: %s", track.get("title"))

    def bind_secondary_output(self, widget: object) -> None:
        """(Ri)collega l'output video del deck secondario al widget HDMI.

        Il secondario usa --no-audio per costruzione: nessun mute
        runtime necessario.
        """
        if self._vlc2 is not None:
            self._vlc2.set_output_widget(widget)

    def enable_secondary(self, active: bool) -> None:
        """Attiva/disattiva il deck secondario (monitor esterno).

        Quando il monitor esterno è spento il player secondario NON deve riprodurre:
        renderizzerebbe verso una finestra nascosta e VLC fallirebbe ripetutamente la
        creazione dell'output video. All'accensione, se un brano è in corso, lo
        sincronizza alla posizione corrente del primario.
        """
        self._secondary_active = active
        if self._vlc2 is None:
            return
        if not active:
            self._vlc2.stop()
            return
        if self._current_path and self._vlc.is_playing():
            self._vlc2.load(self._current_path)
            self._vlc2.play()
            self._vlc2.seek(self._vlc.get_time() / 1000.0)

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
            logger.info("Risoluzione stream URL per %s", youtube_id)
            try:
                return self._ytdlp.get_stream_url(youtube_id)
            except Exception as exc:  # noqa: BLE001 - errore di rete, log e abort
                logger.error("Stream URL non risolvibile: %s", exc)
                return ""
        return ""

    def pause_resume(self) -> None:
        """Alterna tra pausa e ripresa su entrambi i monitor."""
        if self._vlc.is_playing():
            self._vlc.pause()
            if self._vlc2 is not None and self._secondary_active:
                self._vlc2.pause()
        else:
            self._vlc.play()
            if self._vlc2 is not None and self._secondary_active:
                self._vlc2.play()

    def stop(self) -> None:
        """Ferma la riproduzione corrente su entrambi i monitor."""
        self._vlc.set_end_callback(None)
        self._vlc.stop()
        if self._vlc2 is not None:
            self._vlc2.stop()
        self._current_track = None
        self._current_path = None

    def seek(self, seconds: float) -> None:
        """Salta alla posizione indicata in secondi su entrambi i monitor."""
        self._vlc.seek(seconds)
        if self._vlc2 is not None and self._secondary_active:
            self._vlc2.seek(seconds)

    def set_volume(self, volume: int) -> None:
        """Imposta il volume dell'audio (player primario)."""
        self._volume = max(0, min(100, int(volume)))
        self._vlc.set_mute(False)
        self._vlc.set_volume(self._volume)

    def get_state(self) -> dict:
        """Restituisce lo stato corrente del player."""
        duration = self._vlc.get_duration()
        position_ratio = self._vlc.get_position()
        position_sec = position_ratio * duration if duration > 0 else 0.0
        return {
            "is_playing": self._vlc.is_playing(),
            "current_track": self._current_track,
            "position": position_sec,
            "duration": duration,
        }

    def _on_position_changed(self, ratio: float) -> None:
        """Propaga aggiornamenti posizione alla UI."""
        duration = self._vlc.get_duration()
        position_sec = ratio * duration if duration > 0 else 0.0
        self.position_updated.emit(position_sec, duration)

    def _on_playback_ended(self) -> None:
        """Gestisce la fine naturale del brano."""
        self._current_track = None
        self.track_ended.emit()
