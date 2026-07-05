"""Smoke test ShortcutService e resolve_artist_title."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication

from services.shortcut_service import ACTION_PREVIEW_EXIT, ACTION_PREVIEW_TOGGLE, ShortcutService
from utils.track_metadata import resolve_artist_title

_app = QApplication.instance() or QApplication([])


def test_shortcut_alt_x_preview() -> None:
    service = ShortcutService()
    event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_X, Qt.KeyboardModifier.AltModifier)
    assert service.match_global(event.keyCombination(), preview_maximized=False) == ACTION_PREVIEW_TOGGLE


def test_shortcut_escape_only_when_maximized() -> None:
    service = ShortcutService()
    esc = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    combo = esc.keyCombination()
    assert service.match_global(combo, preview_maximized=False) is None
    assert service.match_global(combo, preview_maximized=True) == ACTION_PREVIEW_EXIT


def test_resolve_prefers_ytdlp_artist_track() -> None:
    artist, title = resolve_artist_title(
        "Canale Karaoke - Vasco Rossi - Albachiara (Karaoke)",
        {"artist": "Vasco Rossi", "track": "Albachiara"},
    )
    assert artist == "Vasco Rossi"
    assert title == "Albachiara"


if __name__ == "__main__":
    test_shortcut_alt_x_preview()
    test_shortcut_escape_only_when_maximized()
    test_resolve_prefers_ytdlp_artist_track()
    print("OK shortcut + track metadata smoke")
