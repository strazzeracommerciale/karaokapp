"""Orchestrazione playback per la modalità DJ."""

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, pyqtSignal

from utils.text import clean_title

if TYPE_CHECKING:
    from services.app_mode_service import AppModeService
    from services.dj_runtime_service import DjRuntimeService
    from services.filler_service import FillerService
    from services.player_service import PlayerService

logger = logging.getLogger(__name__)


class DjPlaybackFlow(QObject):
    """Coordina runtime DJ, player e sottofondo.

    I comandi utente sono no-op se AppModeService.get_mode() != 'dj'.
    Gli handler degli eventi player usano l'ownership del playback
    (_dj_owns_playback), non la modalità attiva: il brano DJ deve
    completarsi anche dopo uno switch a karaoke.
    """

    track_info_updated = pyqtSignal(str, object)
    status_message = pyqtSignal(str)

    def __init__(
        self,
        dj_runtime_service: "DjRuntimeService",
        app_mode_service: "AppModeService",
        player_service: "PlayerService | None" = None,
        filler_service: "FillerService | None" = None,
    ) -> None:
        """Inizializza il flow DJ con dipendenze iniettate."""
        super().__init__()
        self._runtime = dj_runtime_service
        self._app_mode = app_mode_service
        self._player = player_service
        self._filler = filler_service
        self._dj_owns_playback = False

    def set_player(self, player_service: "PlayerService | None") -> None:
        """Collega o scollega il PlayerService dopo il bootstrap."""
        self._player = player_service

    def set_filler(self, filler_service: "FillerService | None") -> None:
        """Collega o scollega il FillerService dopo il bootstrap."""
        self._filler = filler_service

    def is_playback_active(self) -> bool:
        """True se il flow DJ ha avviato il brano corrente o in pausa sul runtime."""
        return self._dj_owns_playback

    def play_pause(self) -> None:
        """Avvia il runtime, riprende dalla pausa o mette in pausa il brano corrente."""
        if not self._is_dj_active():
            return
        if self._player is None:
            return
        if not self._runtime.get_runtime_queue():
            self.status_message.emit("Nessun brano in runtime")
            return

        if self._dj_owns_playback:
            self._player.pause_resume()
            return

        current = self._runtime.get_current_track()
        if current is not None:
            self._play_track(current)
            return

        track = self._runtime.advance()
        if track is not None:
            self._play_track(track)
        else:
            self.status_message.emit("Nessun brano in runtime")

    def stop(self) -> None:
        """Ferma il player senza resettare l'indice runtime."""
        if not self._is_dj_active():
            return
        if self._player is not None:
            self._player.stop()
        self._dj_owns_playback = False
        if self._filler is not None:
            self._filler.start()
        logger.info("DJ stop")

    def skip(self) -> None:
        """Salta al brano successivo nel runtime."""
        if not self._is_dj_active():
            return
        self._advance_and_play(start_filler_on_end=True)

    def preview_track(self, track: dict) -> None:
        """Riproduce anteprima senza aggiungere al runtime né avviare download."""
        if self._player is None:
            return
        self._dj_owns_playback = True
        if self._filler is not None:
            self._filler.interrupt()
        self._player.play_track(track)
        self.track_info_updated.emit(
            clean_title(track.get("title", "")),
            track.get("artist"),
        )
        logger.info("DJ anteprima: %s", track.get("title"))

    def on_track_started(self, track: dict) -> None:
        """Interrompe il filler e aggiorna le info brano se il DJ possiede il playback."""
        if not self._dj_owns_playback:
            return
        if self._filler is not None:
            self._filler.interrupt()
        self.track_info_updated.emit(
            clean_title(track.get("title", "")),
            track.get("artist"),
        )

    def on_track_ended(self) -> None:
        """Avanza automaticamente al brano successivo; filler solo a runtime esaurito."""
        if not self._dj_owns_playback:
            return
        if self._runtime.has_next_after_current():
            self._advance_and_play(start_filler_on_end=False)
            return
        self._end_playback_session(start_filler=True)

    def on_track_failed(self, track: dict, reason: str) -> None:
        """Salta automaticamente al successivo dopo un brano non riproducibile."""
        if not self._dj_owns_playback:
            return
        logger.warning(
            "DJ track_failed: %s — %s, skip automatico",
            track.get("title"),
            reason,
        )
        self._advance_and_play(start_filler_on_end=True)

    def _advance_and_play(self, *, start_filler_on_end: bool) -> None:
        """Avanza nel runtime e riproduce; opzionalmente avvia il filler a fine coda."""
        if self._player is None:
            return
        track = self._runtime.advance()
        if track is None:
            self._end_playback_session(start_filler=start_filler_on_end)
            return
        self._play_track(track)

    def _play_track(self, track: dict) -> None:
        """Avvia la riproduzione di un brano runtime impostando l'ownership DJ."""
        if self._player is None:
            return
        self._dj_owns_playback = True
        if self._filler is not None:
            self._filler.interrupt()
        self._player.play_track(track)
        logger.info("DJ play: %s", track.get("title"))

    def _end_playback_session(self, *, start_filler: bool) -> None:
        """Termina la sessione DJ corrente e opzionalmente avvia il sottofondo."""
        if self._player is not None:
            self._player.stop()
        self._dj_owns_playback = False
        self.track_info_updated.emit("Nessun brano", "")
        if start_filler and self._filler is not None:
            self._filler.start()
        logger.debug("DJ playback session ended (filler=%s)", start_filler)

    def _is_dj_active(self) -> bool:
        """True se la modalità attiva è DJ."""
        return self._app_mode.get_mode() == "dj"
