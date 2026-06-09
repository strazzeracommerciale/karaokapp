"""Musica di sottofondo durante le pause della serata.

Usa un player VLC dedicato (istanza separata, solo audio, output indipendente) che
riproduce a volume ridotto quando non c'è un brano in riproduzione. Sorgenti
supportate: file singolo, brano DJ singolo (loop VLC) o playlist DJ (sequenza o
shuffle con crossfade tra brani). Quando parte/riprende un brano in coda il
sottofondo viene messo in PAUSA con dissolvenza (mantenendo la posizione) e
ripreso da lì alla pausa successiva.
"""

import logging
import random
from pathlib import Path
from typing import Literal

from PyQt6.QtCore import QObject, QTimer

import config
from engines.vlc_engine import VlcEngine

logger = logging.getLogger(__name__)

FillerSourceMode = Literal["file", "dj_track", "dj_playlist"]
_TRACK_TRANSITION_MS = 800


class FillerService(QObject):
    """Player di sottofondo: loop file, playlist DJ con shuffle e fade."""

    def __init__(self, engine: VlcEngine) -> None:
        """Inizializza con un motore VLC dedicato (idealmente solo-audio)."""
        super().__init__()
        self._engine = engine
        self._source_mode: FillerSourceMode = "file"
        self._single_source_path: str | None = None
        self._source_label: str = ""
        self._playlist_id: int | None = None
        self._playlist_tracks: list[dict] = []
        self._playback_paths: list[str] = []
        self._playlist_index: int = -1
        self._playlist_shuffle: bool = False
        self._volume = config.FILLER_DEFAULT_VOLUME
        self._enabled = False
        self._state = "stopped"  # stopped | playing | paused
        self._cur_volume = 0
        self._fade_target = 0
        self._fade_duration_ms = config.FILLER_FADE_MS
        self._fade_on_complete = None
        self._fade_timer = QTimer(self)
        self._fade_timer.setInterval(config.FILLER_FADE_STEP_MS)
        self._fade_timer.timeout.connect(self._fade_step)
        self._engine.set_end_callback(self._on_media_ended)

    def set_track(self, path: str) -> None:
        """Imposta un file singolo come sottofondo (alias retrocompatibile)."""
        self.set_file_source(path)

    def set_file_source(self, path: str) -> None:
        """Imposta un file locale come sottofondo in loop."""
        new_path = path or None
        if new_path != self._single_source_path or self._source_mode != "file":
            self.stop()
        self._clear_playlist_state()
        self._source_mode = "file"
        self._single_source_path = new_path
        self._source_label = Path(new_path).name if new_path else ""
        logger.info("Sottofondo file impostato: %s", path)

    def set_dj_track(self, track: dict) -> None:
        """Imposta un brano DJ singolo come sottofondo in loop."""
        path = self._resolve_track_path(track)
        if not path:
            logger.warning(
                "Brano DJ non valido come sottofondo: %s",
                track.get("title"),
            )
            return
        if path != self._single_source_path or self._source_mode != "dj_track":
            self.stop()
        self._clear_playlist_state()
        self._source_mode = "dj_track"
        self._single_source_path = path
        self._source_label = track.get("title") or Path(path).name
        logger.info("Sottofondo brano DJ impostato: %s", self._source_label)

    def set_dj_playlist(
        self,
        tracks: list[dict],
        *,
        shuffle: bool = False,
        label: str = "",
        playlist_id: int | None = None,
    ) -> None:
        """Imposta una playlist DJ come sottofondo continuo (sequenza o shuffle)."""
        resolved = self._tracks_to_paths(tracks)
        if not resolved:
            logger.warning("Playlist DJ filler vuota o senza file locali: %s", label)
            return
        self.stop()
        self._single_source_path = None
        self._source_mode = "dj_playlist"
        self._playlist_tracks = list(tracks)
        self._playlist_shuffle = shuffle
        self._playlist_id = playlist_id
        self._source_label = label or f"Playlist DJ ({len(resolved)} brani)"
        self._rebuild_playback_paths(resolved)
        self._playlist_index = -1
        logger.info(
            "Sottofondo playlist DJ impostato: %s (%d brani, shuffle=%s)",
            self._source_label,
            len(self._playback_paths),
            shuffle,
        )

    def set_playlist_shuffle(self, enabled: bool) -> None:
        """Imposta shuffle filler per la playlist DJ (indipendente dal runtime sidebar)."""
        if self._source_mode != "dj_playlist":
            return
        if enabled == self._playlist_shuffle:
            return
        current_path = self._current_playlist_path()
        self._playlist_shuffle = enabled
        self._rebuild_playback_paths(self._tracks_to_paths(self._playlist_tracks))
        self._restore_playlist_path(current_path)
        logger.info("Filler playlist shuffle %s", "ON" if enabled else "OFF")

    def get_source_mode(self) -> FillerSourceMode:
        """Restituisce la modalità sorgente attiva."""
        return self._source_mode

    def get_source_label(self) -> str:
        """Restituisce l'etichetta descrittiva della sorgente attiva."""
        return self._source_label

    def is_playlist_shuffle(self) -> bool:
        """True se lo shuffle filler playlist DJ è attivo."""
        return self._playlist_shuffle

    def has_track(self) -> bool:
        """True se è configurata una sorgente sottofondo valida."""
        if self._source_mode in ("file", "dj_track"):
            return bool(self._single_source_path)
        return bool(self._playback_paths)

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
        if not self._enabled or not self.has_track() or self._state == "playing":
            return
        self._fade_timer.stop()
        self._fade_on_complete = None
        self._cur_volume = 0
        if self._state == "paused":
            self._engine.set_volume(0)
            self._engine.play()
        elif self._source_mode in ("file", "dj_track"):
            self._start_single_source()
        else:
            self._start_playlist_source()
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
        if self._source_mode == "dj_playlist":
            self._playlist_index = -1

    def _start_single_source(self) -> None:
        """Carica e avvia un file singolo in loop VLC."""
        self._engine.set_mute(False)
        self._engine.load(self._single_source_path or "", loop=True)
        self._engine.play()
        self._engine.set_volume(0)

    def _start_playlist_source(self) -> None:
        """Avvia il primo brano (o quello corrente) di una playlist filler."""
        if self._playlist_index < 0:
            self._playlist_index = 0
        self._load_current_playlist_track()

    def _load_current_playlist_track(self) -> None:
        """Carica il brano playlist corrente senza loop."""
        path = self._current_playlist_path()
        if not path:
            logger.warning("Filler playlist: nessun brano valido all'indice %s", self._playlist_index)
            return
        self._engine.set_mute(False)
        self._engine.load(path, loop=False)
        self._engine.play()
        self._engine.set_volume(0)

    def _on_media_ended(self) -> None:
        """Avanza alla traccia successiva in modalità playlist DJ."""
        if self._source_mode != "dj_playlist" or self._state != "playing":
            return
        self._begin_fade(
            0,
            on_complete=self._after_playlist_track_fade_out,
            duration_ms=_TRACK_TRANSITION_MS,
        )

    def _after_playlist_track_fade_out(self) -> None:
        """Dopo fade-out, passa al brano successivo con fade-in."""
        self._engine.stop()
        if not self._advance_playlist_index():
            return
        self._load_current_playlist_track()
        self._state = "playing"
        self._begin_fade(self._volume, duration_ms=_TRACK_TRANSITION_MS)

    def _advance_playlist_index(self) -> bool:
        """Avanza l'indice playlist; a fine coda riparte dall'inizio silenziosamente."""
        if not self._playback_paths:
            return False
        attempts = len(self._playback_paths)
        for _ in range(attempts):
            next_index = self._playlist_index + 1
            if next_index >= len(self._playback_paths):
                if self._playlist_shuffle:
                    self._rebuild_playback_paths(list(self._playback_paths))
                next_index = 0
                logger.debug("Filler playlist: nuovo ciclo (shuffle=%s)", self._playlist_shuffle)
            self._playlist_index = next_index
            if self._current_playlist_path():
                return True
        logger.warning("Filler playlist: nessun brano riproducibile in coda")
        return False

    def _current_playlist_path(self) -> str | None:
        """Restituisce il path del brano playlist corrente, se valido."""
        if not (0 <= self._playlist_index < len(self._playback_paths)):
            return None
        path = self._playback_paths[self._playlist_index]
        return path if Path(path).exists() else None

    def _rebuild_playback_paths(self, paths: list[str]) -> None:
        """Costruisce l'ordine di riproduzione, con shuffle Fisher-Yates se attivo."""
        if self._playlist_shuffle:
            self._playback_paths = self._fisher_yates(paths)
        else:
            self._playback_paths = list(paths)

    def _restore_playlist_path(self, path: str | None) -> None:
        """Riposiziona l'indice playlist dopo un riordino shuffle."""
        if path is None:
            self._playlist_index = -1
            return
        for index, candidate in enumerate(self._playback_paths):
            if candidate == path:
                self._playlist_index = index
                return
        self._playlist_index = -1

    def _clear_playlist_state(self) -> None:
        """Azzera lo stato interno della playlist filler."""
        self._playlist_tracks = []
        self._playback_paths = []
        self._playlist_index = -1
        self._playlist_id = None
        self._playlist_shuffle = False

    def _do_pause(self) -> None:
        """Mette in pausa il player mantenendo la posizione corrente."""
        self._engine.pause()
        self._state = "paused"

    def _begin_fade(
        self,
        target: int,
        on_complete=None,
        *,
        duration_ms: int | None = None,
    ) -> None:
        """Avvia una dissolvenza del volume verso `target`."""
        self._fade_target = max(0, min(100, int(target)))
        self._fade_duration_ms = duration_ms or config.FILLER_FADE_MS
        self._fade_on_complete = on_complete
        self._engine.set_volume(self._cur_volume)
        self._fade_timer.start()

    def _fade_step(self) -> None:
        """Avvicina il volume corrente al target di uno step e gestisce la fine."""
        step = max(1, round(100 * config.FILLER_FADE_STEP_MS / self._fade_duration_ms))
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

    @staticmethod
    def _resolve_track_path(track: dict) -> str | None:
        """Restituisce il path locale se il file esiste."""
        local_path = track.get("local_path", "") or ""
        if local_path and Path(local_path).exists():
            return local_path
        return None

    @staticmethod
    def _tracks_to_paths(tracks: list[dict]) -> list[str]:
        """Estrae i path locali validi da una lista di brani."""
        paths: list[str] = []
        for track in tracks:
            path = FillerService._resolve_track_path(track)
            if path is not None:
                paths.append(path)
        return paths

    @staticmethod
    def _fisher_yates(items: list[str]) -> list[str]:
        """Restituisce una permutazione casuale (Fisher-Yates) dei path."""
        result = list(items)
        for index in range(len(result) - 1, 0, -1):
            swap_index = random.randint(0, index)
            result[index], result[swap_index] = result[swap_index], result[index]
        return result
