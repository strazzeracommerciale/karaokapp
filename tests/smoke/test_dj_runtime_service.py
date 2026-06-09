"""Smoke test DjRuntimeService."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PyQt6.QtCore import QObject

from services.dj_runtime_service import DjRuntimeService


class _RuntimeListener(QObject):
    """Raccoglie gli eventi runtime_updated per il test."""

    def __init__(self) -> None:
        """Inizializza il contatore aggiornamenti."""
        super().__init__()
        self.updates = 0

    def on_updated(self) -> None:
        """Incrementa il contatore."""
        self.updates += 1


def _make_tracks(count: int) -> list[dict]:
    """Crea una lista di brani di prova con id distinti."""
    return [{"id": index, "title": f"Brano {index}", "artist": f"Artista {index}"} for index in range(count)]


def test_dj_runtime_load_add_advance() -> None:
    """Verifica caricamento, aggiunta, rimozione e advance senza player."""
    service = DjRuntimeService()
    listener = _RuntimeListener()
    service.runtime_updated.connect(listener.on_updated)

    track_a = {"id": 1, "title": "Brano A", "artist": "Artista A"}
    track_b = {"id": 2, "title": "Brano B", "artist": "Artista B"}

    service.load_tracks([track_a])
    assert service.get_runtime_queue() == [track_a]
    assert listener.updates == 1

    service.add_track(track_b)
    assert len(service.get_runtime_queue()) == 2
    assert listener.updates == 2

    service.remove_at(0)
    assert service.get_runtime_queue() == [track_b]
    assert listener.updates == 3

    advanced = service.advance()
    assert advanced == track_b
    assert service.get_current_index() == 0

    assert service.advance() is None
    assert service.get_current_index() == 0

    service.set_loop(True)
    assert service.is_loop_enabled() is True
    wrapped = service.advance()
    assert wrapped == track_b
    assert service.get_current_index() == 0


def test_dj_runtime_shuffle_fisher_yates() -> None:
    """Verifica permutazione shuffle, ripristino ordine canonico e brano corrente."""
    tracks = _make_tracks(10)
    service = DjRuntimeService()

    service.set_shuffle(True)
    service.load_tracks(tracks)
    queue = service.get_runtime_queue()
    assert len(queue) == len(tracks)
    assert {track["id"] for track in queue} == {track["id"] for track in tracks}

    permutations: set[tuple[int, ...]] = set()
    for _ in range(20):
        service.set_shuffle(False)
        service.set_shuffle(True)
        permutations.add(tuple(track["id"] for track in service.get_runtime_queue()))
    assert len(permutations) > 1

    service.set_shuffle(False)
    assert [track["id"] for track in service.get_runtime_queue()] == [
        track["id"] for track in tracks
    ]


def test_dj_runtime_has_next_after_current() -> None:
    """Verifica has_next_after_current per primo play, metà coda e fine con/senza loop."""
    tracks = _make_tracks(3)
    service = DjRuntimeService()
    service.load_tracks(tracks)

    assert service.has_next_after_current() is True

    service.advance()
    assert service.has_next_after_current() is True

    service.advance()
    service.advance()
    assert service.get_current_index() == 2
    assert service.has_next_after_current() is False

    service.set_loop(True)
    assert service.has_next_after_current() is True


def test_dj_runtime_shuffle_loop_reshuffles_each_cycle() -> None:
    """Con shuffle+loop, ogni ciclo genera una nuova permutazione Fisher-Yates."""
    tracks = _make_tracks(8)
    service = DjRuntimeService()
    service.set_shuffle(True)
    service.set_loop(True)
    service.load_tracks(tracks)

    first_cycle: list[int] = []
    for _ in range(8):
        track = service.advance()
        assert track is not None
        first_cycle.append(track["id"])

    second_cycle: list[int] = []
    for _ in range(8):
        track = service.advance()
        assert track is not None
        second_cycle.append(track["id"])

    assert set(first_cycle) == {track["id"] for track in tracks}
    assert set(second_cycle) == {track["id"] for track in tracks}
    assert first_cycle != second_cycle


def test_dj_runtime_shuffle_preserves_current_track() -> None:
    """Verifica che il toggle shuffle mantenga il brano corrente evidenziato."""
    tracks = _make_tracks(5)
    service = DjRuntimeService()
    service.load_tracks(tracks)
    current = service.advance()
    assert current is not None

    service.set_shuffle(True)
    current_index = service.get_current_index()
    assert 0 <= current_index < len(service.get_runtime_queue())
    assert service.get_runtime_queue()[current_index]["id"] == current["id"]

    service.set_shuffle(False)
    assert service.get_runtime_queue()[service.get_current_index()]["id"] == current["id"]


if __name__ == "__main__":
    test_dj_runtime_load_add_advance()
    test_dj_runtime_shuffle_fisher_yates()
    test_dj_runtime_has_next_after_current()
    test_dj_runtime_shuffle_loop_reshuffles_each_cycle()
    test_dj_runtime_shuffle_preserves_current_track()
    print("OK")
