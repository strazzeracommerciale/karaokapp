"""Smoke test esportazione/importazione libreria."""

import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import config
from services.library_transfer_service import LibraryTransferService


def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE tracks (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            artist TEXT,
            youtube_id TEXT UNIQUE,
            local_path TEXT,
            source TEXT NOT NULL DEFAULT 'local',
            track_type TEXT NOT NULL DEFAULT 'karaoke',
            duration_sec INTEGER,
            start_offset_sec REAL DEFAULT 0,
            metadata_confirmed INTEGER NOT NULL DEFAULT 0,
            metadata_confirmed_at DATETIME
        );
        CREATE TABLE playlists (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            mode TEXT DEFAULT 'karaoke'
        );
        CREATE TABLE playlist_tracks (
            id INTEGER PRIMARY KEY,
            playlist_id INTEGER,
            track_id INTEGER,
            position INTEGER NOT NULL
        );
        CREATE TABLE known_artists (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            name_normalized TEXT NOT NULL UNIQUE,
            source TEXT NOT NULL DEFAULT 'seed',
            use_count INTEGER NOT NULL DEFAULT 1
        );
        """
    )
    return conn


def test_export_and_import_merge_without_duplicates() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        media = root / "media" / "downloads"
        media.mkdir(parents=True)
        file_a = media / "song_a [yt1111111111].mp4"
        file_a.write_bytes(b"a")

        conn = _make_conn()
        conn.execute(
            "INSERT INTO tracks (title, artist, youtube_id, local_path) VALUES (?, ?, ?, ?)",
            ("Titolo A", "Artista A", "yt1111111111", str(file_a)),
        )
        conn.execute("INSERT INTO playlists (name, mode) VALUES ('Serata', 'karaoke')")
        conn.commit()

        old_db = config.DB_PATH
        old_download = config.DOWNLOAD_DIR
        config.DB_PATH = root / "data" / "karaoke.db"
        config.DB_PATH.parent.mkdir(parents=True)
        config.DOWNLOAD_DIR = media
        shutil_db = sqlite3.connect(config.DB_PATH)
        conn.backup(shutil_db)
        shutil_db.close()

        try:
            service = LibraryTransferService(conn)
            export_dir = root / "usb"
            export_dir.mkdir()
            exported = service.export_library(export_dir)
            bundle = Path(str(exported["bundle_path"]))
            assert (bundle / "data" / "karaoke.db").is_file()
            assert (bundle / "media" / "downloads" / file_a.name).is_file()

            dest_conn = _make_conn()
            dest_media = root / "dest_media"
            dest_media.mkdir()
            config.DB_PATH = root / "data" / "dest.db"
            config.DOWNLOAD_DIR = dest_media
            dest_service = LibraryTransferService(dest_conn)
            dest_conn.execute(
                "INSERT INTO tracks (title, artist, youtube_id, local_path) VALUES (?, ?, ?, ?)",
                ("Esistente", "Artista A", "yt1111111111", str(dest_media / "old.mp4")),
            )
            dest_conn.commit()

            stats = dest_service.import_library(bundle)
            assert stats["tracks_skipped"] == 1
            assert stats["tracks_added"] == 0
            assert dest_conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0] == 1
        finally:
            config.DB_PATH = old_db
            config.DOWNLOAD_DIR = old_download


if __name__ == "__main__":
    test_export_and_import_merge_without_duplicates()
    print("OK library transfer")
