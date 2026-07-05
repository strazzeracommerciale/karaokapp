"""Smoke test LibraryBrowseWindow."""

import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from PyQt6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.library_service import LibraryService
from ui.library_browse_window import LibraryBrowseWindow

_app = QApplication.instance() or QApplication([])


def test_library_browse_window_emits_on_double_click_path() -> None:
    """La finestra emette track_chosen e si nasconde alla selezione."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE tracks (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            artist TEXT,
            local_path TEXT,
            track_type TEXT NOT NULL DEFAULT 'karaoke'
        );
        """
    )
    conn.execute(
        "INSERT INTO tracks (title, artist, local_path) VALUES (?, ?, ?)",
        ("Test Song", "Artist", "/tmp/x.mp4"),
    )
    conn.commit()
    library = LibraryService(conn)
    window = LibraryBrowseWindow(library)
    chosen: list[dict] = []
    window.track_chosen.connect(chosen.append)
    track = {"id": 1, "title": "Test Song", "artist": "Artist", "local_path": "/tmp/x.mp4"}
    window._on_track_chosen(track)
    assert chosen == [track]
    assert not window.isVisible()


if __name__ == "__main__":
    test_library_browse_window_emits_on_double_click_path()
    print("OK")
