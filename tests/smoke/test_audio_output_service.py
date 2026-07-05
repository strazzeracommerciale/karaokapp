"""Smoke test AudioOutputService."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.audio_output_service import AudioOutputService


def test_set_device_id_updates_engines() -> None:
    """Il cambio dispositivo viene propagato ai motori registrati."""
    probe = MagicMock()
    engine = MagicMock()
    service = AudioOutputService(probe, settings=MagicMock())
    service.register_engine(engine)
    service.set_device_id("device-a")
    engine.set_audio_output_device.assert_called_with("device-a")
    service.set_device_id("device-a")
    assert engine.set_audio_output_device.call_count == 2


if __name__ == "__main__":
    test_set_device_id_updates_engines()
    print("OK")
