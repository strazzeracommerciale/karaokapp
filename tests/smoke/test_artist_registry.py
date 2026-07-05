"""Test registro artisti e normalizzazione nomi."""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.artist_registry_service import ArtistRegistryService
from utils.name_normalize import normalize_name
from utils.text import parse_artist_title


def test_normalize_accent_case_space() -> None:
    assert normalize_name("  Lucio  Battisti  ") == normalize_name("lucio battisti")
    assert normalize_name("Lùnapop") == normalize_name("Lunapop")
    assert normalize_name("Måneskin") == normalize_name("Maneskin")


def test_registry_disambiguate_with_fuzzy() -> None:
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
    registry.register("Edoardo Bennato", source="seed")

    assert parse_artist_title(
        "Vasco Rossi - Albachiara (Karaoke Version) [HD]", registry=registry
    ) == ("Vasco Rossi", "Albachiara")
    assert parse_artist_title(
        "Albachiara - Vasco Rossi | Base Musicale", registry=registry
    ) == ("Vasco Rossi", "Albachiara")
    assert parse_artist_title(
        "Edoardo Bennato - Il Gatto e La Volpe (Versione Karaoke)", registry=registry
    ) == ("Edoardo Bennato", "Il Gatto e La Volpe")


def test_manual_register_excludes_karaoke_channels() -> None:
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
    assert registry.register("Karaoke Academy", source="manual") is False
    assert registry.register("Tiziano Ferro", source="manual") is True
    assert registry.count() == 1
