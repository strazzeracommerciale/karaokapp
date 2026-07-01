"""Smoke test DjPlaybackFlow."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PyQt6.QtCore import QObject

from services.dj_playback_flow import DjPlaybackFlow
from services.dj_runtime_service import DjRuntimeService


def _make_tracks(count: int) -> list[dict]:
    """Crea brani di prova con id distinti."""
    return [
        {"id": index, "title": f"Brano {index}", "artist": f"Artista {index}"}
        for index in range(1, count + 1)
    ]


class _MockPlayer(QObject):
    """Player fittizio che registra le chiamate di riproduzione."""

    def __init__(self) -> None:
        """Inizializza lo stato del mock."""
        super().__init__()
        self.played: list[dict] = []
        self.stop_count = 0
        self.pause_resume_count = 0
        self._is_playing = False

    def play_track(self, track: dict) -> None:
        """Simula l'avvio di un brano."""
        self.played.append(track)
        self._is_playing = True

    def stop(self) -> None:
        """Simula lo stop."""
        self.stop_count += 1
        self._is_playing = False

    def pause_resume(self) -> None:
        """Simula pausa/ripresa."""
        self.pause_resume_count += 1
        self._is_playing = not self._is_playing

    def get_state(self) -> dict:
        """Restituisce lo stato corrente."""
        return {"is_playing": self._is_playing}


class _MockFiller(QObject):
    """Filler fittizio che conta start e interrupt."""

    def __init__(self) -> None:
        """Inizializza i contatori."""
        super().__init__()
        self.start_count = 0
        self.interrupt_count = 0

    def start(self) -> None:
        """Simula avvio sottofondo."""
        self.start_count += 1

    def interrupt(self) -> None:
        """Simula interruzione sottofondo."""
        self.interrupt_count += 1


class _FlowListener(QObject):
    """Raccoglie i segnali emessi dal flow DJ."""

    def __init__(self) -> None:
        """Inizializza le liste di eventi."""
        super().__init__()
        self.status_messages: list[str] = []
        self.titles: list[str] = []

    def on_status(self, message: str) -> None:
        """Registra un messaggio di stato."""
        self.status_messages.append(message)

    def on_track_info(self, title: str, _artist: object) -> None:
        """Registra un aggiornamento titolo."""
        self.titles.append(title)


def _make_flow(
    track_count: int = 2,
) -> tuple[DjPlaybackFlow, DjRuntimeService, _MockPlayer, _MockFiller]:
    """Costruisce flow DJ con dipendenze mock."""
    runtime = DjRuntimeService()
    runtime.load_tracks(_make_tracks(track_count))
    player = _MockPlayer()
    filler = _MockFiller()
    flow = DjPlaybackFlow(runtime, player, filler)
    return flow, runtime, player, filler


def test_play_empty_runtime_emits_status() -> None:
    """Play con runtime vuoto emette messaggio breve, senza toccare il player."""
    runtime = DjRuntimeService()
    player = _MockPlayer()
    flow = DjPlaybackFlow(runtime, player)
    listener = _FlowListener()
    flow.status_message.connect(listener.on_status)

    flow.play_pause()

    assert listener.status_messages == ["Nessun brano in runtime"]
    assert player.played == []


def test_play_starts_first_track() -> None:
    """Play avvia il primo brano del runtime."""
    flow, runtime, player, filler = _make_flow(2)

    flow.play_pause()

    assert len(player.played) == 1
    assert player.played[0]["id"] == 1
    assert runtime.get_current_index() == 0
    assert flow.is_playback_active() is True
    assert filler.interrupt_count == 1


def test_stop_preserves_runtime_index() -> None:
    """Stop ferma il player senza resettare l'indice runtime."""
    flow, runtime, player, filler = _make_flow(2)

    flow.play_pause()
    flow.stop()

    assert runtime.get_current_index() == 0
    assert flow.is_playback_active() is False
    assert player.stop_count == 1
    assert filler.start_count == 1


def test_skip_advances_to_next_track() -> None:
    """Skip salta al brano successivo."""
    flow, runtime, player, _filler = _make_flow(2)

    flow.play_pause()
    flow.skip()

    assert len(player.played) == 2
    assert player.played[1]["id"] == 2
    assert runtime.get_current_index() == 1


def test_on_track_ended_auto_advance_without_filler() -> None:
    """Fine brano con successivo in coda: auto-advance senza avviare il filler."""
    flow, _runtime, player, filler = _make_flow(2)

    flow.play_pause()
    flow.on_track_ended()

    assert len(player.played) == 2
    assert player.played[1]["id"] == 2
    assert filler.start_count == 0
    assert flow.is_playback_active() is True


def test_on_track_ended_exhausted_starts_filler() -> None:
    """Runtime esaurito (loop off): termina sessione e avvia il filler."""
    flow, _runtime, player, filler = _make_flow(1)
    listener = _FlowListener()
    flow.track_info_updated.connect(listener.on_track_info)

    flow.play_pause()
    flow.on_track_ended()

    assert len(player.played) == 1
    assert filler.start_count == 1
    assert flow.is_playback_active() is False
    assert listener.titles[-1] == "Nessun brano"


def test_on_track_failed_auto_skips() -> None:
    """Brano fallito: skip automatico al successivo."""
    flow, runtime, player, _filler = _make_flow(2)

    flow.play_pause()
    failed = player.played[0]
    flow.on_track_failed(failed, "File non trovato")

    assert len(player.played) == 2
    assert player.played[1]["id"] == 2
    assert runtime.get_current_index() == 1


def test_preview_ends_without_runtime_advance() -> None:
    """Fine anteprima non avanza il runtime."""
    flow, runtime, player, filler = _make_flow(2)
    preview = {"id": 99, "title": "Anteprima", "source": "youtube"}

    flow.preview_track(preview)
    flow.on_track_ended()

    assert player.played == [preview]
    assert runtime.get_current_index() == -1
    assert flow.is_playback_active() is False
    assert filler.start_count == 0


def test_preview_starts_without_mode_guard() -> None:
    """Anteprima avvia il player indipendentemente dalla modalità app."""
    flow, runtime, player, _filler = _make_flow(1)

    flow.preview_track({"id": 99, "title": "Preview"})
    assert len(player.played) == 1
    flow.stop()
    flow.play_pause()

    assert len(player.played) == 2
    assert runtime.get_current_index() == 0


if __name__ == "__main__":
    test_play_empty_runtime_emits_status()
    test_play_starts_first_track()
    test_stop_preserves_runtime_index()
    test_skip_advances_to_next_track()
    test_on_track_ended_auto_advance_without_filler()
    test_on_track_ended_exhausted_starts_filler()
    test_on_track_failed_auto_skips()
    test_preview_ends_without_runtime_advance()
    test_preview_starts_without_mode_guard()
    print("OK")
