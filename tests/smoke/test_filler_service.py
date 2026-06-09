"""Smoke test FillerService con motore VLC mock."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PyQt6.QtWidgets import QApplication

from services.filler_service import FillerService

_app = QApplication.instance() or QApplication([])


class _MockEngine:
    """Motore VLC fittizio per verificare load/play/stop e end callback."""

    def __init__(self) -> None:
        """Inizializza lo stato del mock."""
        self.loaded: list[tuple[str, bool]] = []
        self.end_callback = None
        self.playing = False
        self.volume = 0
        self.stopped = 0

    def set_end_callback(self, callback) -> None:
        """Registra il callback di fine brano."""
        self.end_callback = callback

    def load(self, path_or_url: str, loop: bool = False, start_time: float = 0.0) -> None:
        """Registra il caricamento media."""
        self.loaded.append((path_or_url, loop))

    def play(self) -> None:
        """Simula avvio riproduzione."""
        self.playing = True

    def stop(self) -> None:
        """Simula stop."""
        self.stopped += 1
        self.playing = False

    def pause(self) -> None:
        """Simula pausa."""
        self.playing = False

    def set_mute(self, _mute: bool) -> None:
        """No-op."""

    def set_volume(self, volume: int) -> None:
        """Registra il volume."""
        self.volume = volume

    def simulate_end(self) -> None:
        """Simula la fine naturale del brano."""
        if self.end_callback is not None:
            self.end_callback()


def _drain_fades(service: FillerService, max_steps: int = 200) -> None:
    """Esegue gli step del fade fino al completamento."""
    for _ in range(max_steps):
        if not service._fade_timer.isActive():
            break
        service._fade_step()


def _make_temp_files(count: int) -> list[Path]:
    """Crea file temporanei per simulare brani locali."""
    directory = Path(tempfile.mkdtemp())
    paths = []
    for index in range(count):
        path = directory / f"track_{index}.mp3"
        path.write_bytes(b"x")
        paths.append(path)
    return paths


def _tracks_from_paths(paths: list[Path]) -> list[dict]:
    """Converte path temporanei in dict brano."""
    return [
        {"id": index, "title": f"Brano {index}", "local_path": str(path)}
        for index, path in enumerate(paths)
    ]


def test_set_track_alias_uses_file_mode() -> None:
    """set_track() resta alias retrocompatibile di set_file_source()."""
    engine = _MockEngine()
    service = FillerService(engine)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as handle:
        path = handle.name
        handle.write(b"a")
    service.set_track(path)
    assert service.get_source_mode() == "file"
    assert service.has_track() is True


def test_file_mode_start_interrupt_resume() -> None:
    """Regressione karaoke: start, interrupt con fade e ripresa in pausa."""
    engine = _MockEngine()
    service = FillerService(engine)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as handle:
        path = handle.name
        handle.write(b"a")
    service.set_file_source(path)
    service.set_enabled(True)
    service.start()
    _drain_fades(service)
    assert engine.loaded[-1] == (path, True)
    assert service._state == "playing"

    service.interrupt()
    _drain_fades(service)
    assert service._state == "paused"

    service.start()
    _drain_fades(service)
    assert service._state == "playing"
    assert len(engine.loaded) == 1


def test_dj_track_single_source() -> None:
    """Brano DJ singolo usa loop VLC come un file."""
    engine = _MockEngine()
    service = FillerService(engine)
    paths = _make_temp_files(1)
    track = _tracks_from_paths(paths)[0]
    service.set_dj_track(track)
    assert service.get_source_mode() == "dj_track"
    assert service.get_source_label() == "Brano 0"
    service.set_enabled(True)
    service.start()
    _drain_fades(service)
    assert engine.loaded[-1] == (str(paths[0]), True)


def test_playlist_sequential_advance_on_end() -> None:
    """Playlist DJ avanza al brano successivo con crossfade, senza loop VLC."""
    engine = _MockEngine()
    service = FillerService(engine)
    paths = _make_temp_files(3)
    service.set_dj_playlist(_tracks_from_paths(paths), label="Test playlist")
    service.set_enabled(True)
    service.start()
    _drain_fades(service)
    assert engine.loaded[-1][0] == str(paths[0])
    assert engine.loaded[-1][1] is False

    engine.simulate_end()
    _drain_fades(service)
    assert engine.loaded[-1][0] == str(paths[1])


def test_playlist_wraps_silently() -> None:
    """A fine playlist riparte dal primo brano."""
    engine = _MockEngine()
    service = FillerService(engine)
    paths = _make_temp_files(2)
    service.set_dj_playlist(_tracks_from_paths(paths), label="Loop playlist")
    service.set_enabled(True)
    service.start()
    _drain_fades(service)
    engine.simulate_end()
    _drain_fades(service)
    engine.simulate_end()
    _drain_fades(service)
    assert engine.loaded[-1][0] == str(paths[0])


def test_playlist_shuffle_reorders_paths() -> None:
    """Shuffle filler produce un ordine diverso dal canonico."""
    engine = _MockEngine()
    service = FillerService(engine)
    paths = _make_temp_files(6)
    service.set_dj_playlist(
        _tracks_from_paths(paths),
        shuffle=True,
        label="Shuffle playlist",
    )
    assert service.is_playlist_shuffle() is True
    playback_order = service._playback_paths
    canonical = [str(path) for path in paths]
    assert sorted(playback_order) == sorted(canonical)
    assert playback_order != canonical


def test_playlist_skips_missing_path() -> None:
    """Brani senza file locale vengono ignorati in fase di configurazione."""
    engine = _MockEngine()
    service = FillerService(engine)
    paths = _make_temp_files(2)
    tracks = _tracks_from_paths(paths)
    tracks.append({"id": 99, "title": "Fantasma", "local_path": "/non/esiste.mp3"})
    service.set_dj_playlist(tracks, label="Filtrata")
    assert len(service._playback_paths) == 2


if __name__ == "__main__":
    test_set_track_alias_uses_file_mode()
    test_file_mode_start_interrupt_resume()
    test_dj_track_single_source()
    test_playlist_sequential_advance_on_end()
    test_playlist_wraps_silently()
    test_playlist_shuffle_reorders_paths()
    test_playlist_skips_missing_path()
    print("OK")
