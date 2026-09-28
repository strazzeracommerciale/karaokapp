"""Smoke test del motore mpv: rapporto dei semitoni e interfaccia pubblica."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PyQt6.QtWidgets import QApplication

from engines.mpv_engine import MpvEngine, semitone_ratio

_app = QApplication.instance() or QApplication([])


def test_semitone_ratio_matches_equal_temperament() -> None:
    """Un semitono è la dodicesima radice di 2, e zero lascia la frequenza invariata."""
    assert semitone_ratio(0) == 1.0
    assert abs(semitone_ratio(1) - 2 ** (1 / 12)) < 1e-12
    assert abs(semitone_ratio(-5) - 2 ** (-5 / 12)) < 1e-12
    assert abs(semitone_ratio(5) - 2 ** (5 / 12)) < 1e-12


def test_engine_exposes_the_player_api() -> None:
    """Il motore mpv offre gli stessi metodi usati dal player karaoke."""
    engine = MpvEngine("--karokapp-pitch")
    for name in (
        "clone",
        "load",
        "play",
        "pause",
        "stop",
        "seek",
        "set_volume",
        "set_semitones",
        "semitones",
        "is_playing",
        "shutdown",
    ):
        assert callable(getattr(engine, name))
    engine.set_semitones(6)
    assert engine.semitones() == 5
    engine.set_semitones(-9)
    assert engine.semitones() == -5
    secondary = engine.clone()
    assert secondary.semitones() == 0
    MpvEngine.shutdown_all()


if __name__ == "__main__":
    test_semitone_ratio_matches_equal_temperament()
    test_engine_exposes_the_player_api()
    print("ok")
