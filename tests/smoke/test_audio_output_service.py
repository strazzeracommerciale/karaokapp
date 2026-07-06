"""Smoke test AudioOutputService."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.audio_output_service import AudioOutputService


def test_set_device_id_persists_without_engine_rebind() -> None:
    """Con DirectSound il cambio dispositivo persiste ma non riapre i motori VLC."""
    probe = MagicMock()
    engine = MagicMock()
    settings = MagicMock()
    service = AudioOutputService(probe, settings=settings)
    service.register_engine(engine)
    service.set_device_id("device-a")
    settings.setValue.assert_called_once()
    engine.set_audio_output_device.assert_not_called()


if __name__ == "__main__":
    test_set_device_id_persists_without_engine_rebind()
    print("OK")
