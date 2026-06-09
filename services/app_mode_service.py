"""Stato condiviso della modalità operativa (karaoke / DJ)."""

import logging
from typing import Literal

from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)

AppMode = Literal["karaoke", "dj"]


class AppModeService(QObject):
    """Tiene traccia della modalità attiva e notifica le finestre collegate."""

    mode_changed = pyqtSignal(str)

    def __init__(self, initial_mode: AppMode = "karaoke") -> None:
        """Inizializza con la modalità di partenza (default karaoke)."""
        super().__init__()
        self._mode: AppMode = initial_mode

    def get_mode(self) -> AppMode:
        """Restituisce la modalità attualmente attiva."""
        return self._mode

    def set_mode(self, mode: AppMode) -> None:
        """Imposta la modalità attiva senza alterare coda, runtime o playback."""
        if mode not in ("karaoke", "dj"):
            logger.warning("Modalità non valida ignorata: %s", mode)
            return
        if mode == self._mode:
            return
        self._mode = mode
        logger.info("Modalità attiva: %s", mode)
        self.mode_changed.emit(mode)

    def is_karaoke(self) -> bool:
        """True se la modalità attiva è karaoke."""
        return self._mode == "karaoke"

    def is_dj(self) -> bool:
        """True se la modalità attiva è DJ."""
        return self._mode == "dj"
