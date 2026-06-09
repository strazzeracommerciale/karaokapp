"""Coordinamento output HDMI esterno e aggiornamenti annuncio karaoke."""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QApplication

from engines.display_manager import DisplayManager
from services.queue_service import QueueService

if TYPE_CHECKING:
    from services.player_service import PlayerService

logger = logging.getLogger(__name__)


class ExternalDisplayCoordinator(QObject):
    """Gestisce HdmiWindow, DisplayManager e segnali coda/player per il monitor esterno."""

    def __init__(
        self,
        display_manager: DisplayManager,
        hdmi_window: Any,
        queue_service: QueueService,
        set_external_available: Callable[[bool], None],
        set_external_checked: Callable[[bool], None],
        player_service: "PlayerService | None" = None,
        forced_screen_index: int | None = None,
    ) -> None:
        """Inizializza con dipendenze iniettate (hdmi_window e callback UI da main)."""
        super().__init__()
        self._display = display_manager
        self._hdmi = hdmi_window
        self._queue = queue_service
        self._player = player_service
        self._set_external_available = set_external_available
        self._set_external_checked = set_external_checked
        self._forced_screen_index = forced_screen_index

    def set_player(self, player_service: "PlayerService | None") -> None:
        """Collega il PlayerService dopo il bootstrap VLC."""
        self._player = player_service

    def connect_signals(
        self,
        app: QApplication,
        external_toggle_requested: Any,
    ) -> None:
        """Collega segnali Qt di coda, player, schermi e toggle esterno."""
        self._queue.queue_updated.connect(self.on_queue_updated)
        self._queue.next_ready.connect(self.on_next_ready)
        external_toggle_requested.connect(self.set_external)
        app.screenAdded.connect(lambda _screen: self.refresh_external_availability())
        app.screenRemoved.connect(lambda _screen: self.refresh_external_availability())
        if self._player is not None:
            self._player.track_started.connect(self._on_track_started)

    def on_queue_updated(self, queue: list) -> None:
        """Aggiorna HDMI con cantante corrente e prossimo in attesa."""
        playing = [item for item in queue if item.get("status") == "playing"]
        if playing:
            current = playing[0]
            self._hdmi.update_current(
                current.get("singer_name", ""),
                current.get("title", ""),
                current.get("artist"),
            )
        else:
            self._hdmi.show_idle()
        self._hdmi.update_next(queue)

    def on_next_ready(self, item: dict) -> None:
        """Annuncia esplicitamente il prossimo cantante sullo schermo esterno."""
        self._hdmi.announce(
            item.get("singer_name", ""),
            item.get("title", ""),
            item.get("artist"),
        )

    def set_external(self, active: bool) -> None:
        """Accende o spegne l'output a schermo intero sul monitor esterno."""
        if not active:
            if self._player is not None:
                self._player.enable_secondary(False)
            self._hdmi.set_external_active(active)
            self._hdmi.hide()
            return
        if self._forced_screen_index is not None:
            ok = self._display.move_window_to_screen(
                self._hdmi, self._forced_screen_index
            )
        else:
            ok = self._display.set_fullscreen_external(self._hdmi)
        if not ok:
            logger.warning(
                "Attivazione monitor esterno annullata: nessun secondo schermo"
            )
            self._set_external_checked(False)
            self._hdmi.set_external_active(False)
            return
        self._hdmi.set_external_active(True)
        state = self._player.get_state() if self._player is not None else {}
        if self._player is not None:
            self._player.bind_secondary_output(self._hdmi.video_output_widget())
            self._player.enable_secondary(True)
        if state.get("is_playing"):
            self._hdmi.show_video()
        else:
            self.on_queue_updated(self._queue.get_queue())

    def refresh_external_availability(self) -> None:
        """Aggiorna disponibilità del pulsante e disattiva l'esterno se scompare."""
        available = self._display.has_external_screen()
        self._set_external_available(available)
        if not available:
            self.set_external(False)

    def initialize(self) -> None:
        """Imposta disponibilità iniziale e mantiene l'esterno spento all'avvio."""
        self._set_external_available(self._display.has_external_screen())
        self.set_external(False)

    def _on_track_started(self, _track: dict) -> None:
        """Mostra il video sul monitor esterno all'avvio riproduzione."""
        self._hdmi.show_video()
