"""Smoke test PlaylistService su DB in memoria."""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.playlist_service import PlaylistService


def _make_conn() -> sqlite3.Connection:
    """Crea un DB in memoria con lo schema applicato e un brano karaoke di prova."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    schema = (Path(__file__).resolve().parents[2] / "db" / "schema.sql").read_text(
        encoding="utf-8"
    )
    conn.executescript(schema)
    conn.execute(
        "INSERT INTO tracks (title, artist, source, local_path, track_type) "
        "VALUES ('Albachiara', 'Vasco', 'local', '/tmp/x.mp4', 'karaoke')"
    )
    conn.commit()
    return conn


def _make_conn_with_dj_track() -> sqlite3.Connection:
    """Aggiunge un brano DJ al DB di prova."""
    conn = _make_conn()
    conn.execute(
        "INSERT INTO tracks (title, artist, source, local_path, track_type) "
        "VALUES ('Club Hit', 'DJ One', 'local', '/tmp/dj.mp4', 'dj')"
    )
    conn.commit()
    return conn


def test_playlist_crud() -> None:
    """Verifica creazione, aggiunta, dedup, rimozione ed eliminazione."""
    conn = _make_conn()
    service = PlaylistService(conn)
    track_id = conn.execute("SELECT id FROM tracks LIMIT 1").fetchone()["id"]

    pid = service.create("Serata anni 80")
    assert pid is not None
    assert any(p["id"] == pid for p in service.list_playlists())

    assert service.add_track(pid, track_id) is True
    assert service.add_track(pid, track_id) is False  # dedup

    tracks = service.get_tracks(pid)
    assert len(tracks) == 1
    assert tracks[0]["title"] == "Albachiara"

    service.remove_track(pid, track_id)
    assert service.get_tracks(pid) == []

    service.delete(pid)
    assert service.list_playlists() == []


def test_dj_playlist_mode_filter_and_validation() -> None:
    """Playlist DJ accettano solo brani DJ; filtro list_playlists(mode='dj')."""
    conn = _make_conn_with_dj_track()
    service = PlaylistService(conn)
    karaoke_id = conn.execute(
        "SELECT id FROM tracks WHERE track_type = 'karaoke'"
    ).fetchone()["id"]
    dj_id = conn.execute("SELECT id FROM tracks WHERE track_type = 'dj'").fetchone()["id"]

    dj_pid = service.create("Serata DJ", mode="dj")
    karaoke_pid = service.create("Serata karaoke", mode="karaoke")

    assert service.add_track(dj_pid, dj_id) is True
    assert service.add_track(dj_pid, karaoke_id) is False
    assert service.add_track(karaoke_pid, karaoke_id) is True
    assert service.add_track(karaoke_pid, dj_id) is False

    dj_playlists = service.list_playlists(mode="dj")
    assert len(dj_playlists) == 1
    assert dj_playlists[0]["name"] == "Serata DJ"
    assert dj_playlists[0]["mode"] == "dj"


def test_save_runtime_as_playlist_pattern() -> None:
    """Simula il salvataggio runtime → playlist DJ (pattern DjConsoleWindow)."""
    conn = _make_conn_with_dj_track()
    service = PlaylistService(conn)
    dj_tracks = conn.execute(
        "SELECT id, title, artist, local_path, source, track_type FROM tracks "
        "WHERE track_type = 'dj'"
    ).fetchall()
    runtime_queue = [dict(row) for row in dj_tracks]

    playlist_id = service.create("Runtime salvato", mode="dj")
    added = 0
    for track in runtime_queue:
        if track.get("id") is not None and service.add_track(playlist_id, track["id"]):
            added += 1

    assert added == 1
    saved = service.get_tracks(playlist_id)
    assert len(saved) == 1
    assert saved[0]["title"] == "Club Hit"
    assert saved[0]["track_type"] == "dj"


if __name__ == "__main__":
    test_playlist_crud()
    test_dj_playlist_mode_filter_and_validation()
    test_save_runtime_as_playlist_pattern()
    print("Playlist smoke test OK")
