"""Conferma artista/titolo: solo un riscontro netto del catalogo viene accettato."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.song_catalog import match_catalog_results, match_title_contains_result


def test_unique_catalog_match_is_accepted() -> None:
    match = match_catalog_results(
        "Justin Timberlake",
        "Can't Stop The Feeling",
        [
            {"artistName": "Justin Timberlake", "trackName": "Can't Stop the Feeling!"},
            {"artistName": "Justin Timberlake", "trackName": "Can't Stop the Feeling!"},
        ],
    )
    assert match == ("Justin Timberlake", "Can't Stop the Feeling!")


def test_ambiguous_or_weak_catalog_match_is_rejected() -> None:
    assert (
        match_catalog_results(
            "Gruppo Italiano",
            "Stadio",
            [{"artistName": "Stadio", "trackName": "Sorprendimi"}],
        )
        is None
    )
    assert (
        match_catalog_results(
            "Nomadi",
            "Nomadi",
            [{"artistName": "Nomadi", "trackName": "Io voglio vivere"}],
        )
        is None
    )
    assert (
        match_catalog_results(
            "Annalisa",
            "Sinceramente",
            [
                {"artistName": "Annalisa", "trackName": "Sinceramente"},
                {"artistName": "Annalisa", "trackName": "Bellissima"},
            ],
        )
        == ("Annalisa", "Sinceramente")
    )


def test_catalog_must_appear_inside_the_original_title() -> None:
    raw = "Karaoke Italiano - Io voglio vivere - Nomadi ( Testo )"
    assert match_title_contains_result(
        raw,
        [{"artistName": "Nomadi", "trackName": "Io voglio vivere"}],
    ) == ("Nomadi", "Io voglio vivere")
    assert (
        match_title_contains_result(
            raw,
            [{"artistName": "Gruppo Italiano", "trackName": "Io voglio vivere"}],
        )
        is None
    )
    assert match_title_contains_result(
        "Your Song - Elton John | Karaoke Version | KaraFun",
        [{"artistName": "Elton John", "trackName": "Your Song"}],
    ) == ("Elton John", "Your Song")


if __name__ == "__main__":
    test_unique_catalog_match_is_accepted()
    test_ambiguous_or_weak_catalog_match_is_rejected()
    test_catalog_must_appear_inside_the_original_title()
    print("OK song catalog")
