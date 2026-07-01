"""Smoke test DjPlayerService."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.dj_player_service import DjPlayerService


def test_import_and_instantiate() -> None:
    """Import e costruzione con motore VLC mock."""
    vlc = MagicMock()
    vlc.get_duration.return_value = 0.0
    vlc.get_position.return_value = 0.0
    vlc.is_playing.return_value = False
    service = DjPlayerService(vlc)
    assert service.get_state()["is_playing"] is False
    assert service.get_state()["current_track"] is None


def test_set_volume_clamps() -> None:
    """Il volume viene clampato 0-100."""
    vlc = MagicMock()
    service = DjPlayerService(vlc)
    service.set_volume(150)
    vlc.set_volume.assert_called_with(100)


if __name__ == "__main__":
    test_import_and_instantiate()
    test_set_volume_clamps()
    print("OK")
