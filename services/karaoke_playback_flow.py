"""Orchestrazione playback per la modalità karaoke."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, pyqtSignal

from utils.text import clean_title

if TYPE_CHECKING:
    from services.app_mode_service import AppModeService
    from services.dj_playback_flow import DjPlaybackFlow
    from services.filler_service import FillerService
    from services.library_service import LibraryService
    from services.player_service import PlayerService
    from services.queue_service import QueueService
    from services.search_service import SearchService

logger = logging.getLogger(__name__)


class KaraokePlaybackFlow(QObject):
    """Coordina coda, player e sottofondo nel flusso karaoke annuncio → play.

    I comandi sono no-op se AppModeService.get_mode() != 'karaoke' oppure se
    DjPlaybackFlow possiede il player (ownership indipendente dalla modalità).
    Gli handler eventi player ignorano gli eventi quando il DJ possiede il
    playback, così auto-advance e filler restano gestiti dal flow DJ.
    """

    player_reset_requested = pyqtSignal()
    track_info_updated = pyqtSignal(str, object)
    start_save_enabled_changed = pyqtSignal(bool)
    track_failed = pyqtSignal(dict, str)

    def __init__(
        self,
        queue_service: "QueueService",
        app_mode_service: "AppModeService",
        player_service: "PlayerService | None" = None,
        search_service: "SearchService | None" = None,
        filler_service: "FillerService | None" = None,
        library_service: "LibraryService | None" = None,
    ) -> None:
        """Inizializza il flow con dipendenze iniettate."""
        super().__init__()
        self._queue = queue_service
        self._app_mode = app_mode_service
        self._player = player_service
        self._search = search_service
        self._filler = filler_service
        self._library = library_service
        self._dj_flow: "DjPlaybackFlow | None" = None
        self._pending_track: dict | None = None
        self._current_playing_track: dict | None = None

    def set_player(self, player_service: "PlayerService | None") -> None:
        """Collega o scollega il PlayerService dopo il bootstrap."""
        self._player = player_service

    def set_search(self, search_service: "SearchService | None") -> None:
        """Collega o scollega il SearchService dopo il bootstrap."""
        self._search = search_service

    def set_filler(self, filler_service: "FillerService | None") -> None:
        """Collega o scollega il FillerService dopo il bootstrap."""
        self._filler = filler_service

    def set_dj_flow(self, dj_playback_flow: "DjPlaybackFlow | None") -> None:
        """Collega il flow DJ per verificare l'ownership condivisa del player."""
        self._dj_flow = dj_playback_flow

    def pending_track(self) -> dict | None:
        """Restituisce il brano annunciato in attesa di Play."""
        return self._pending_track

    def current_playing_track(self) -> dict | None:
        """Restituisce il brano attualmente in riproduzione."""
        return self._current_playing_track

    def is_track_playing(self) -> bool:
        """True se il player sta riproducendo un brano."""
        return bool(self._player is not None and self._player.get_state().get("is_playing"))

    def play_pause(self) -> None:
        """Avvia il brano annunciato se presente, altrimenti alterna pausa/ripresa."""
        if not self._is_karaoke_active() or self._is_dj_playback_active():
            return
        if self._player is None:
            return
        if self._pending_track is not None:
            track = self._pending_track
            self._pending_track = None
            self._player.play_track(track)
            return
        was_playing = self.is_track_playing()
        self._player.pause_resume()
        if self._filler is not None:
            if was_playing:
                self._filler.start()
            else:
                self._filler.interrupt()

    def preview_track(self, track: dict) -> None:
        """Riproduce anteprima senza accodare né avviare download."""
        if not self._is_karaoke_active() or self._is_dj_playback_active():
            return
        if self._player is None:
            return
        self._pending_track = None
        self._player.play_track(track)

    def stop(self) -> None:
        """Ferma la riproduzione e avvia il sottofondo."""
        if not self._is_karaoke_active() or self._is_dj_playback_active():
            return
        if self._player is not None:
            self._player.stop()
        self.player_reset_requested.emit()
        if self._filler is not None:
            self._filler.start()

    def skip(self) -> None:
        """Avanza al prossimo cantante in coda."""
        if not self._is_karaoke_active() or self._is_dj_playback_active():
            return
        self._do_advance_next()

    def queue_play(self, queue_id: int) -> None:
        """Riproduce un brano arbitrario richiamato dalla coda."""
        if not self._is_karaoke_active() or self._is_dj_playback_active():
            return
        if self._player is None:
            return
        self._player.stop()
        item = self._queue.play_at(queue_id)
        if item is not None:
            self._pending_track = None
            self._player.play_track(item)
            self._trigger_download_if_needed(item)

    def advance_next(self) -> None:
        """Annuncia il prossimo cantante senza avviare il brano."""
        if not self._is_karaoke_active() or self._is_dj_playback_active():
            return
        self._do_advance_next()

    def on_track_started(self, track: dict) -> None:
        """Gestisce l'avvio riproduzione: sottofondo e contatori libreria."""
        if self._is_dj_playback_active():
            return
        if self._filler is not None:
            self._filler.interrupt()
        self._current_playing_track = track
        self._pending_track = None
        self.track_info_updated.emit(
            clean_title(track.get("title", "")),
            track.get("artist"),
        )
        self.start_save_enabled_changed.emit(self._can_save_start_offset(track))
        track_id = track.get("id")
        if self._library is not None and track_id is not None:
            self._library.record_play(track_id)

    def on_track_ended(self) -> None:
        """Avanza automaticamente alla fine del brano."""
        if self._is_dj_playback_active():
            return
        self.player_reset_requested.emit()
        if self._filler is not None:
            self._filler.start()
        self._do_advance_next()

    def on_track_failed(self, track: dict, reason: str) -> None:
        """Gestisce un brano non riproducibile."""
        if self._is_dj_playback_active():
            return
        self.player_reset_requested.emit()
        if self._filler is not None:
            self._filler.start()
        self.track_failed.emit(track, reason)

    def save_start_offset_here(self) -> float | None:
        """Salva la posizione corrente come punto di inizio del brano locale.

        Restituisce la posizione salvata in secondi, o None se non applicabile.
        """
        if not self._is_karaoke_active():
            return None
        track = self._current_playing_track
        if self._library is None or not self._can_save_start_offset(track):
            return None
        state = self._player.get_state() if self._player is not None else {}
        position = float(state.get("position", 0.0))
        self._library.set_start_offset(track["id"], position)
        track["start_offset_sec"] = position
        return position

    def _do_advance_next(self) -> None:
        """Logica interna di avanzamento coda, senza guard sulla modalità."""
        if self._player is None:
            return
        self._player.stop()
        self.player_reset_requested.emit()
        if self._filler is not None:
            self._filler.start()
        next_item = self._queue.advance()
        self._pending_track = next_item
        if next_item is not None:
            self.track_info_updated.emit(
                clean_title(next_item.get("title", "")),
                next_item.get("singer_name"),
            )
            self._trigger_download_if_needed(next_item)
            logger.info(
                "Annunciato: %s — %s (in attesa di Play)",
                next_item.get("singer_name"),
                clean_title(next_item.get("title", "")),
            )

    def _is_karaoke_active(self) -> bool:
        """True se la modalità attiva è karaoke."""
        return self._app_mode.get_mode() == "karaoke"

    def _is_dj_playback_active(self) -> bool:
        """True se il flow DJ possiede il player condiviso."""
        return self._dj_flow is not None and self._dj_flow.is_playback_active()

    def _trigger_download_if_needed(self, item: dict) -> None:
        """Avvia download silenzioso per risultati YouTube non ancora locali."""
        if (
            self._search is not None
            and item.get("source") == "youtube"
            and not item.get("local_path")
        ):
            self._search.trigger_download_for_track(item)

    def _can_save_start_offset(self, track: dict | None) -> bool:
        """True se il brano ha id e sta riproducendo (o è) un file locale."""
        if not track or track.get("id") is None:
            return False
        if self._track_has_local_file(track):
            return True
        return self._player is not None and self._player.current_local_path() is not None

    @staticmethod
    def _track_has_local_file(track: dict) -> bool:
        """True se il dict track punta a un file locale esistente."""
        local_path = track.get("local_path") or ""
        return bool(local_path) and Path(local_path).exists()

    @staticmethod
    def _is_local_track(track: dict | None) -> bool:
        """True se il brano è un file locale con id valido."""
        return bool(track) and track.get("id") is not None and KaraokePlaybackFlow._track_has_local_file(
            track
        )
