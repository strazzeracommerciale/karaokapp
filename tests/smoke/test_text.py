"""Smoke test per utils.text.clean_title."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from utils.text import clean_title


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
