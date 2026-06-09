"""Smoke test AppModeService."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PyQt6.QtCore import QObject

from services.app_mode_service import AppModeService


class _ModeListener(QObject):
    """Raccoglie gli eventi mode_changed per il test."""

    def __init__(self) -> None:
        """Inizializza la lista degli eventi."""
        super().__init__()
        self.modes: list[str] = []

    def on_mode_changed(self, mode: str) -> None:
        """Registra una modalità emessa."""
        self.modes.append(mode)


def test_app_mode_initial_state() -> None:
    """Verifica stato iniziale e modalità custom al bootstrap."""
    default_service = AppModeService()
    assert default_service.get_mode() == "karaoke"
    assert default_service.is_karaoke() is True
    assert default_service.is_dj() is False

    dj_service = AppModeService(initial_mode="dj")
    assert dj_service.get_mode() == "dj"
    assert dj_service.is_dj() is True


def test_app_mode_switch_preserves_state() -> None:
    """Verifica get/set, no-op su valore invariato e segnale al cambio."""
    service = AppModeService()
    listener = _ModeListener()
    service.mode_changed.connect(listener.on_mode_changed)

    assert service.get_mode() == "karaoke"

    service.set_mode("karaoke")
    assert listener.modes == []

    service.set_mode("dj")
    assert service.get_mode() == "dj"
    assert service.is_dj() is True
    assert listener.modes == ["dj"]

    service.set_mode("invalid")  # type: ignore[arg-type]
    assert service.get_mode() == "dj"
    assert listener.modes == ["dj"]

    service.set_mode("karaoke")
    assert service.get_mode() == "karaoke"
    assert service.is_karaoke() is True
    assert listener.modes == ["dj", "karaoke"]


if __name__ == "__main__":
    test_app_mode_initial_state()
    test_app_mode_switch_preserves_state()
    print("OK")
