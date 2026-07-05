"""Smoke test per utils.text.clean_title."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from utils.text import build_download_basename, clean_title, format_track_display, parse_artist_title


def test_artist_title_with_noise() -> None:
    """Estrae il titolo da 'Artista - Titolo (Karaoke Version) [HD]'."""
    assert clean_title("Vasco Rossi - Albachiara (Karaoke Version) [HD]") == "Albachiara"


def test_single_segment() -> None:
    """Un titolo senza separatori resta invariato (ripulito dal rumore)."""
    assert clean_title("Albachiara (Karaoke)") == "Albachiara"


def test_strips_extension() -> None:
    """Rimuove l'estensione del file."""
    assert clean_title("Imagine.mp4") == "Imagine"


def test_empty() -> None:
    """Stringa vuota → vuota."""
    assert clean_title("") == ""


def test_parse_artist_title() -> None:
    """Separa artista e titolo da un titolo YouTube karaoke."""
    from services.artist_registry_service import ArtistRegistryService
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
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
    registry = ArtistRegistryService(conn)
    registry.register("Vasco Rossi", source="seed")

    assert parse_artist_title(
        "Vasco Rossi - Albachiara (Karaoke Version) [HD]", registry=registry
    ) == (
        "Vasco Rossi",
        "Albachiara",
    )
    assert parse_artist_title(
        "Albachiara - Vasco Rossi | Base Musicale", registry=registry
    ) == (
        "Vasco Rossi",
        "Albachiara",
    )
    assert parse_artist_title("Albachiara (Karaoke)") == ("", "Albachiara")


def test_format_track_display() -> None:
    """Mostra artista prima del titolo."""
    assert format_track_display("Albachiara", "Vasco Rossi") == "Vasco Rossi — Albachiara"
    assert format_track_display("Albachiara", None) == "Albachiara"
    assert format_track_display("", "Vasco Rossi") == "Vasco Rossi"
    assert format_track_display("Titolo", "Artista", suffix=" ✓") == "Artista — Titolo ✓"


def test_build_download_basename() -> None:
    """Il nome file include artista, titolo e id YouTube per univocità."""
    name = build_download_basename("Vasco Rossi", "Albachiara", "YZSbny3Iyeg")
    assert name == "Vasco Rossi - Albachiara [YZSbny3Iyeg]"


def test_returns_str_non_empty() -> None:
    """Su input verboso restituisce una stringa non vuota."""
    result = clean_title("Adele - Someone Like You | Base Musicale Karaoke")
    assert isinstance(result, str)
    assert result.strip() != ""


if __name__ == "__main__":
    test_artist_title_with_noise()
    test_single_segment()
    test_strips_extension()
    test_empty()
    test_returns_str_non_empty()
    print("OK: clean_title smoke test superato")
    print("Esempi:")
    for sample in [
        "Vasco Rossi - Albachiara (Karaoke Version) [HD]",
        "Adele - Someone Like You | Base Musicale Karaoke",
        "Imagine.mp4",
        "Queen - Bohemian Rhapsody (Official Karaoke)",
    ]:
        print(f"  {sample!r} -> {clean_title(sample)!r}")
