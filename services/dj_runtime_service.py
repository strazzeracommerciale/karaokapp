"""Runtime in memoria per la playlist DJ della serata."""

import logging
import random

from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)


class DjRuntimeService(QObject):
    """Tiene la coda DJ corrente in memoria, indipendente dalla modalità attiva."""

    runtime_updated = pyqtSignal()

    def __init__(self) -> None:
        """Inizializza un runtime vuoto."""
        super().__init__()
        self._source_tracks: list[dict] = []
        self._tracks: list[dict] = []
        self._current_index: int = -1
        self._shuffle: bool = False
        self._loop: bool = False

    def get_runtime_queue(self) -> list[dict]:
        """Restituisce una copia della coda runtime nell'ordine di riproduzione."""
        return list(self._tracks)

    def get_current_index(self) -> int:
        """Restituisce l'indice del brano corrente (-1 se nessuno)."""
        return self._current_index

    def is_shuffle_enabled(self) -> bool:
        """True se lo shuffle è attivo."""
        return self._shuffle

    def is_loop_enabled(self) -> bool:
        """True se il loop è attivo."""
        return self._loop

    def set_shuffle(self, enabled: bool) -> None:
        """Imposta shuffle e riordina con Fisher-Yates se attivato."""
        if enabled == self._shuffle:
            return
        current_track = self._current_track()
        self._shuffle = enabled
        self._rebuild_playback_order()
        self._restore_current_track(current_track)
        logger.info("Runtime DJ: shuffle %s", "ON" if enabled else "OFF")
        self.runtime_updated.emit()

    def set_loop(self, enabled: bool) -> None:
        """Imposta il flag loop (wrap indice in Fase 3)."""
        if enabled == self._loop:
            return
        self._loop = enabled
        logger.info("Runtime DJ: loop %s", "ON" if enabled else "OFF")
        self.runtime_updated.emit()

    def load_tracks(self, tracks: list[dict]) -> None:
        """Sostituisce la coda runtime; applica shuffle se attivo."""
        self._source_tracks = list(tracks)
        self._current_index = -1
        self._rebuild_playback_order()
        logger.info("Runtime DJ caricato: %s brani", len(self._source_tracks))
        self.runtime_updated.emit()

    def add_track(self, track: dict) -> None:
        """Aggiunge un brano in fondo alla coda runtime."""
        self._source_tracks.append(track)
        self._tracks.append(track)
        logger.debug("Runtime DJ: aggiunto %s", track.get("title"))
        self.runtime_updated.emit()

    def remove_at(self, index: int) -> None:
        """Rimuove un brano dalla coda runtime per indice di riproduzione."""
        if index < 0 or index >= len(self._tracks):
            logger.warning("Runtime DJ: indice non valido %s", index)
            return
        removed = self._tracks.pop(index)
        self._source_tracks = [
            track for track in self._source_tracks if not self._same_track(track, removed)
        ]
        if self._current_index == index:
            self._current_index = -1
        elif self._current_index > index:
            self._current_index -= 1
        logger.debug("Runtime DJ: rimosso %s", removed.get("title"))
        self.runtime_updated.emit()

    def advance(self) -> dict | None:
        """Avanza all'indice successivo e restituisce il brano (stub Fase 1)."""
        if not self._tracks:
            return None
        next_index = self._current_index + 1
        if next_index >= len(self._tracks):
            if not self._loop:
                return None
            next_index = 0
        self._current_index = next_index
        track = self._tracks[self._current_index]
        logger.debug("Runtime DJ: advance → %s", track.get("title"))
        self.runtime_updated.emit()
        return track

    def _current_track(self) -> dict | None:
        """Restituisce il brano corrente, se presente."""
        if 0 <= self._current_index < len(self._tracks):
            return self._tracks[self._current_index]
        return None

    def _rebuild_playback_order(self) -> None:
        """Ricostruisce l'ordine di riproduzione da sorgente, con shuffle se attivo."""
        if self._shuffle:
            self._tracks = self._fisher_yates(self._source_tracks)
        else:
            self._tracks = list(self._source_tracks)

    def _restore_current_track(self, track: dict | None) -> None:
        """Riposiziona l'indice corrente dopo un riordino."""
        if track is None:
            self._current_index = -1
            return
        for index, candidate in enumerate(self._tracks):
            if self._same_track(candidate, track):
                self._current_index = index
                return
        self._current_index = -1

    @staticmethod
    def _fisher_yates(tracks: list[dict]) -> list[dict]:
        """Restituisce una permutazione casuale (Fisher-Yates) della lista."""
        result = list(tracks)
        for index in range(len(result) - 1, 0, -1):
            swap_index = random.randint(0, index)
            result[index], result[swap_index] = result[swap_index], result[index]
        return result

    @staticmethod
    def _same_track(left: dict, right: dict) -> bool:
        """True se due dict rappresentano lo stesso brano."""
        left_id = left.get("id")
        right_id = right.get("id")
        if left_id is not None and right_id is not None:
            return left_id == right_id
        return left is right
