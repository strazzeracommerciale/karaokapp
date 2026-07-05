"""Test filtro libreria artista/titolo con fallback."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from utils.library_filter import filter_tracks


def test_strict_artist_and_title_partial() -> None:
    tracks = [
        {"title": "Angels", "artist": "Robbie Williams", "local_path": "/a/Robbie - Angels.mp4"},
        {"title": "Albachiara", "artist": "Vasco Rossi", "local_path": "/a/vasco.mp4"},
    ]
    result, fallback = filter_tracks(tracks, artist_query="robb", title_query="ang")
    assert len(result) == 1
    assert result[0]["title"] == "Angels"
    assert not fallback


def test_fallback_searches_filename() -> None:
    tracks = [
        {
            "title": "brano generico",
            "artist": "Sconosciuto",
            "local_path": "/media/Nek - Se io non avessi te [abc].mp4",
        }
    ]
    result, fallback = filter_tracks(tracks, artist_query="nek", title_query="")
    assert len(result) == 1
    assert fallback


def test_empty_filters_return_all() -> None:
    tracks = [{"title": "A", "artist": "B", "local_path": "/a.mp4"}]
    result, fallback = filter_tracks(tracks, "", "")
    assert result == tracks
    assert not fallback


if __name__ == "__main__":
    test_strict_artist_and_title_partial()
    test_fallback_searches_filename()
    test_empty_filters_return_all()
    print("OK library filter")
