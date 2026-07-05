"""Smoke test aggiornamento metadati archivio."""

import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.metadata_refresh_service import MetadataRefreshService, youtube_id_from_path


def test_youtube_id_from_path_old_and_new_format() -> None:
    assert youtube_id_from_path(Path("YZSbny3Iyeg.mp4")) == "YZSbny3Iyeg"
    assert (
        youtube_id_from_path(Path("Vasco Rossi - Albachiara [abc12345678].mp4"))
        == "abc12345678"
    )
    assert youtube_id_from_path(Path("brano senza id.mp4")) is None


def test_refresh_updates_db_and_renames() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        media = Path(tmp) / "media"
        media.mkdir()
        old_file = media / "abc12345678.mp4"
        old_file.write_bytes(b"x")

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
        conn.execute(
            "INSERT INTO tracks (title, artist, youtube_id, local_path) VALUES (?, ?, ?, ?)",
            (
                "Robbie Williams - Angels (Karaoke Version)",
                "Sing King",
                "abc12345678",
                str(old_file),
            ),
        )
        conn.commit()

        ytdlp = MagicMock()
        ytdlp.extract_metadata.return_value = {
            "title": "Robbie Williams - Angels (Karaoke Version)",
            "artist": "Robbie Williams",
            "track": "Angels",
            "uploader": "Sing King",
        }
        conn.executescript(
            """
            CREATE TABLE known_artists (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                name_normalized TEXT NOT NULL UNIQUE,
                source TEXT NOT NULL DEFAULT 'seed',
                use_count INTEGER NOT NULL DEFAULT 1,
                added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        from services.artist_registry_service import ArtistRegistryService

        registry = ArtistRegistryService(conn)
        registry.register("Robbie Williams", source="seed")
        service = MetadataRefreshService(conn, ytdlp=ytdlp, artist_registry=registry)
        stats = service.refresh_all(rename_files=True)

        assert stats["metadata_updated"] + stats["files_renamed"] == 1
        row = conn.execute("SELECT title, artist, local_path FROM tracks").fetchone()
        assert row["title"] == "Angels"
        assert row["artist"] == "Robbie Williams"
        new_path = Path(row["local_path"])
        assert new_path.is_file()
        assert "Robbie Williams - Angels [abc12345678]" in new_path.name
        assert not old_file.exists()


def test_refresh_skips_confirmed_tracks() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        media = Path(tmp) / "media"
        media.mkdir()
        confirmed_file = media / "confirmed.mp4"
        pending_file = media / "pending.mp4"
        confirmed_file.write_bytes(b"c")
        pending_file.write_bytes(b"p")

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
            "INSERT INTO tracks (title, artist, local_path, metadata_confirmed) VALUES (?, ?, ?, ?)",
            [
                ("Confirmed", "Artist", str(confirmed_file), 1),
                ("Pending", "Artist", str(pending_file), 0),
            ],
        )
        conn.commit()

        service = MetadataRefreshService(conn, ytdlp=MagicMock(), artist_registry=None)
        stats = service.refresh_all(parse_only=True, skip_confirmed=True)
        assert stats["total"] == 1
        assert len(stats["outcomes"]) == 1
        assert stats["outcomes"][0].track_id == 2


if __name__ == "__main__":
    test_youtube_id_from_path_old_and_new_format()
    test_refresh_updates_db_and_renames()
    test_refresh_skips_confirmed_tracks()
    print("OK metadata refresh smoke")
