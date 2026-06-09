"""Musica di sottofondo durante le pause della serata.

Usa un player VLC dedicato (istanza separata, solo audio, output indipendente) che
riproduce in loop un singolo brano a volume ridotto quando non c'è un brano karaoke
in riproduzione. Quando parte/riprende un brano in coda il sottofondo viene messo in
PAUSA con una dissolvenza (mantenendo la posizione) e ripreso da lì alla pausa
successiva. Il loop è gestito da libVLC (opzione input-repeat).
"""

import logging

from PyQt6.QtCore import QObject, QTimer

import config
from engines.vlc_engine import VlcEngine

logger = logging.getLogger(__name__)


class FillerService(QObject):
    """Player di sottofondo: loop, volume ridotto, pausa/ripresa con fade."""

    def __init__(self, engine: VlcEngine) -> None:
        """Inizializza con un motore VLC dedicato (idealmente solo-audio)."""
        super().__init__()
        self._engine = engine
        self._path: str | None = None
        self._volume = config.FILLER_DEFAULT_VOLUME
        self._enabled = False
        self._state = "stopped"  # stopped | playing | paused
        self._cur_volume = 0
        self._fade_target = 0
        self._fade_on_complete = None
        self._fade_timer = QTimer(self)
        self._fade_timer.setInterval(config.FILLER_FADE_STEP_MS)
        self._fade_timer.timeout.connect(self._fade_step)

    def set_track(self, path: str) -> None:
        """Imposta il file del sottofondo; se cambia, azzera lo stato corrente."""
        new_path = path or None
        if new_path != self._path:
            self.stop()
        self._path = new_path
        logger.info("Brano di sottofondo impostato: %s", path)

    def has_track(self) -> bool:
        """True se è stato scelto un brano di sottofondo."""
        return bool(self._path)

    def set_volume(self, volume: int) -> None:
        """Imposta il volume del sottofondo (0-100), senza interferire col fade."""
        self._volume = max(0, min(100, int(volume)))
        if self._state == "playing" and not self._fade_timer.isActive():
            self._cur_volume = self._volume
            self._engine.set_volume(self._volume)

    def set_enabled(self, enabled: bool) -> None:
        """Abilita o disabilita la funzione; se disabilitata ferma il sottofondo."""
        self._enabled = bool(enabled)
        if not self._enabled:
            self.stop()

    def is_enabled(self) -> bool:
        """True se il sottofondo è abilitato."""
        return self._enabled

    def start(self) -> None:
        """Avvia il sottofondo, o lo riprende dalla posizione di pausa, con fade-in."""
        if not self._enabled or not self._path or self._state == "playing":
            return
        self._fade_timer.stop()
        self._fade_on_complete = None
        self._cur_volume = 0
        if self._state == "paused":
            self._engine.set_volume(0)
            self._engine.play()
        else:
            self._engine.set_mute(False)
            self._engine.load(self._path, loop=True)
            self._engine.play()
            self._engine.set_volume(0)
        self._state = "playing"
        self._begin_fade(self._volume)
        logger.debug("Sottofondo avviato/ripreso (vol target=%d)", self._volume)

    def interrupt(self) -> None:
        """Sfuma e mette in PAUSA il sottofondo mantenendo la posizione."""
        if self._state != "playing":
            return
        self._begin_fade(0, on_complete=self._do_pause)
        logger.debug("Sottofondo in dissolvenza verso pausa")

    def stop(self) -> None:
        """Ferma completamente il sottofondo (posizione azzerata)."""
        self._fade_timer.stop()
        self._fade_on_complete = None
        if self._state != "stopped":
            self._engine.stop()
        self._state = "stopped"
        self._cur_volume = 0

    def _do_pause(self) -> None:
        """Mette in pausa il player mantenendo la posizione corrente."""
        self._engine.pause()
        self._state = "paused"

    def _begin_fade(self, target: int, on_complete=None) -> None:
        """Avvia una dissolvenza del volume verso `target`."""
        self._fade_target = max(0, min(100, int(target)))
        self._fade_on_complete = on_complete
        self._engine.set_volume(self._cur_volume)
        self._fade_timer.start()

    def _fade_step(self) -> None:
        """Avvicina il volume corrente al target di uno step e gestisce la fine."""
        step = max(1, round(100 * config.FILLER_FADE_STEP_MS / config.FILLER_FADE_MS))
        if self._cur_volume < self._fade_target:
            self._cur_volume = min(self._fade_target, self._cur_volume + step)
        elif self._cur_volume > self._fade_target:
            self._cur_volume = max(self._fade_target, self._cur_volume - step)
        self._engine.set_volume(self._cur_volume)
        if self._cur_volume == self._fade_target:
            self._fade_timer.stop()
            callback = self._fade_on_complete
            self._fade_on_complete = None
            if callback is not None:
                callback()
