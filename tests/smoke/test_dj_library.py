"""Smoke test import e catalogo libreria DJ."""

import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.library_service import LibraryService


def _make_conn() -> sqlite3.Connection:
    """Crea un DB in memoria con lo schema applicato."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    schema = (Path(__file__).resolve().parents[2] / "db" / "schema.sql").read_text(
        encoding="utf-8"
    )
    conn.executescript(schema)
    conn.commit()
    return conn


def test_import_dj_registers_original_path() -> None:
    """Import DJ salva il path originale senza copiare il file."""
    conn = _make_conn()
    service = LibraryService(conn)
    with tempfile.TemporaryDirectory() as tmp_dir:
        source = Path(tmp_dir) / "Vasco Rossi - Albachiara.mp3"
        source.write_bytes(b"audio")

        imported = service.import_files([source], track_type="dj")
        assert len(imported) == 1
        assert imported[0]["title"] == "Albachiara"
        assert imported[0]["artist"] == "Vasco Rossi"
        assert imported[0]["local_path"] == str(source.resolve())
        assert imported[0]["track_type"] == "dj"
        assert source.exists()

        dj_tracks = service.list_tracks(track_type="dj")
        karaoke_tracks = service.list_tracks(track_type="karaoke")
        assert len(dj_tracks) == 1
        assert len(karaoke_tracks) == 0


def test_import_dj_dedup_and_cross_type() -> None:
    """Stesso path può esistere come karaoke e DJ; il duplicato stesso tipo è ignorato."""
    conn = _make_conn()
    service = LibraryService(conn)
    with tempfile.TemporaryDirectory() as tmp_dir:
        source = Path(tmp_dir) / "Shared - Track.mp3"
        source.write_bytes(b"audio")

        first = service.import_files([source], track_type="dj")
        second = service.import_files([source], track_type="dj")
        karaoke = service.import_files([source], track_type="karaoke")

        assert len(first) == 1
        assert len(second) == 0
        assert len(karaoke) == 1
        assert service.list_tracks(track_type="dj")[0]["id"] != karaoke[0]["id"]


def test_scan_dj_media_dir_registers_new_files() -> None:
    """Scan registra solo i file non ancora presenti in catalogo."""
    conn = _make_conn()
    service = LibraryService(conn)
    with tempfile.TemporaryDirectory() as tmp_dir:
        media_dir = Path(tmp_dir)
        first_file = media_dir / "One.mp3"
        second_file = media_dir / "nested" / "Two.mp3"
        second_file.parent.mkdir(parents=True)
        first_file.write_bytes(b"a")
        second_file.write_bytes(b"b")

        imported = service.scan_media_dir(track_type="dj", media_dir=media_dir)
        assert len(imported) == 2

        rescanned = service.scan_media_dir(track_type="dj", media_dir=media_dir)
        assert len(rescanned) == 0
        assert len(service.list_tracks(track_type="dj")) == 2


if __name__ == "__main__":
    test_import_dj_registers_original_path()
    test_import_dj_dedup_and_cross_type()
    test_scan_dj_media_dir_registers_new_files()
    print("OK")
