"""Smoke test motore refresh metadati UI e finestra Preparazione."""

import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from PyQt6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from db import db_core
from engines.metadata_refresh_engine import MetadataRefreshEngine, MetadataRefreshOptions
from services.app_mode_service import AppModeService
from services.library_service import LibraryService
from services.metadata_refresh_service import MetadataRefreshService
from services.playlist_service import PlaylistService
from services.queue_service import QueueService
from ui.main_window import MainWindow
from ui.prep_window import PrepWindow
from ui.theme_service import ThemeService

_app = QApplication.instance() or QApplication([])


def test_refresh_all_reports_progress() -> None:
    """Il service invoca on_progress per ogni brano esaminato."""
    with tempfile.TemporaryDirectory() as tmp:
        media = Path(tmp) / "media"
        media.mkdir()
        file_a = media / "idaaaaaaaaaaa.mp4"
        file_b = media / "idbbbbbbbbbbb.mp4"
        file_a.write_bytes(b"a")
        file_b.write_bytes(b"b")

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(
            """
            CREATE TABLE tracks (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                artist TEXT,
                youtube_id TEXT,
                local_path TEXT,
                track_type TEXT NOT NULL DEFAULT 'karaoke',
                metadata_confirmed INTEGER NOT NULL DEFAULT 0,
                metadata_confirmed_at DATETIME
            );
            """
        )
        conn.executemany(
            "INSERT INTO tracks (title, artist, youtube_id, local_path) VALUES (?, ?, ?, ?)",
            [
                ("Title A", "Artist A", "idaaaaaaaaaaa", str(file_a)),
                ("Title B", "Artist B", "idbbbbbbbbbbb", str(file_b)),
            ],
        )
        conn.commit()

        seen: list[tuple[int, int, str]] = []

        def on_progress(current: int, total: int, label: str) -> None:
            seen.append((current, total, label))

        service = MetadataRefreshService(conn, ytdlp=MagicMock(), artist_registry=None)
        stats = service.refresh_all(parse_only=True, on_progress=on_progress)

        assert stats["total"] == 2
        assert len(seen) == 2
        assert seen[0][0] == 1 and seen[1][0] == 2
        assert seen[0][1] == 2


def test_metadata_refresh_engine_runs_in_background() -> None:
    """Il motore Qt completa un refresh parse-only senza bloccare."""
    with tempfile.TemporaryDirectory() as tmp:
        media = Path(tmp) / "one.mp4"
        media.write_bytes(b"x")

        conn = sqlite3.connect(":memory:", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.executescript(
            """
            CREATE TABLE tracks (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                artist TEXT,
                youtube_id TEXT,
                local_path TEXT,
                track_type TEXT NOT NULL DEFAULT 'karaoke',
                metadata_confirmed INTEGER NOT NULL DEFAULT 0,
                metadata_confirmed_at DATETIME
            );
            """
        )
        conn.execute(
            "INSERT INTO tracks (title, artist, youtube_id, local_path) VALUES (?, ?, ?, ?)",
            ("Old Title", "Old Artist", "xyz12345678", str(media)),
        )
        conn.commit()

        engine = MetadataRefreshEngine(conn, ytdlp=MagicMock(), artist_registry=None)
        finished: list[dict] = []
        engine.finished.connect(finished.append)
        assert engine.start(
            MetadataRefreshOptions(rename_files=False, parse_only=True, dry_run=True)
        )

        while engine.is_busy():
            _app.processEvents()

        assert finished
        assert finished[0]["total"] == 1


def test_prep_window_opens_with_library_and_tools() -> None:
    """La finestra Preparazione mostra libreria e pulsante metadati."""
    db_core.migrate()
    conn = db_core.get_conn()
    library = LibraryService(conn)
    playlist = PlaylistService(conn)
    window = PrepWindow(library, playlist, metadata_refresh_engine=None, transfer_service=None)
    window.show()
    _app.processEvents()

    assert window._tabs.count() == 3
    assert window._tabs.tabText(1) == "Ricerca"
    assert window._tabs.tabText(0) == "Libreria"
    assert window._library_widget._filter_artist_input is not None
    assert window._library_widget._list.count() == len(library.list_tracks())
    assert not window._metadata_refresh_btn.isEnabled()
    window.close()


def test_main_window_has_prep_button() -> None:
    """MainWindow espone il toggle Preparazione."""
    db_core.migrate()
    conn = db_core.get_conn()
    window = MainWindow(
        AppModeService(),
        None,
        None,
        QueueService(conn, 1),
        None,
        library_service=LibraryService(conn),
        theme_service=ThemeService(),
        dry_run=True,
    )
    window.show()
    _app.processEvents()
    assert window._prep_btn.text() == "Preparazione"
    window.close()


if __name__ == "__main__":
    test_refresh_all_reports_progress()
    test_metadata_refresh_engine_runs_in_background()
    test_prep_window_opens_with_library_and_tools()
    test_main_window_has_prep_button()
    print("OK prep / metadata refresh smoke")
