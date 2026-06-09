"""Orchestrazione playback per la modalità DJ (scheletro Fase 1)."""

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, pyqtSignal

if TYPE_CHECKING:
    from services.app_mode_service import AppModeService
    from services.dj_runtime_service import DjRuntimeService
    from services.player_service import PlayerService

logger = logging.getLogger(__name__)


class DjPlaybackFlow(QObject):
    """Coordina runtime DJ e player; logica completa in Fase 3.

    I comandi sono no-op se AppModeService.get_mode() != 'dj'.
    MainWindow e DjConsoleWindow possono invocare i metodi senza
    branching esterno: il guard è interno a questo flow.
    """

    track_info_updated = pyqtSignal(str, object)

    def __init__(
        self,
        dj_runtime_service: "DjRuntimeService",
        app_mode_service: "AppModeService",
        player_service: "PlayerService | None" = None,
    ) -> None:
        """Inizializza il flow DJ con dipendenze iniettate."""
        super().__init__()
        self._runtime = dj_runtime_service
        self._app_mode = app_mode_service
        self._player = player_service

    def set_player(self, player_service: "PlayerService | None") -> None:
        """Collega o scollega il PlayerService dopo il bootstrap."""
        self._player = player_service

    def play_pause(self) -> None:
        """Avvia o mette in pausa (stub Fase 1)."""
        if not self._is_dj_active():
            return
        logger.info("DJ play_pause (stub Fase 1)")

    def stop(self) -> None:
        """Ferma la riproduzione DJ (stub Fase 1)."""
        if not self._is_dj_active():
            return
        logger.info("DJ stop (stub Fase 1)")

    def skip(self) -> None:
        """Salta al brano successivo (stub Fase 1)."""
        if not self._is_dj_active():
            return
        logger.info("DJ skip (stub Fase 1)")

    def on_track_started(self, track: dict) -> None:
        """Gestisce l'avvio riproduzione quando la modalità DJ è attiva."""
        if not self._is_dj_active():
            return
        logger.debug("DJ track_started: %s", track.get("title"))

    def on_track_ended(self) -> None:
        """Gestisce la fine brano (stub Fase 3)."""
        if not self._is_dj_active():
            return
        logger.debug("DJ track_ended (stub Fase 3)")

    def on_track_failed(self, track: dict, reason: str) -> None:
        """Gestisce un brano non riproducibile (stub Fase 3)."""
        if not self._is_dj_active():
            return
        logger.warning("DJ track_failed: %s — %s", track.get("title"), reason)

    def _is_dj_active(self) -> bool:
        """True se la modalità attiva è DJ."""
        return self._app_mode.get_mode() == "dj"
