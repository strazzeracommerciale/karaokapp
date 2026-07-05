"""Selezione e persistenza del dispositivo di uscita audio VLC."""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, QSettings, pyqtSignal

import config

if TYPE_CHECKING:
    from engines.vlc_engine import VlcEngine

logger = logging.getLogger(__name__)


def _decode_vlc_text(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def enumerate_audio_output_devices(player) -> list[tuple[str, str]]:
    """Elenca i dispositivi mmdevice disponibili per un MediaPlayer libVLC."""
    devices: list[tuple[str, str]] = []
    node = player.audio_output_device_enum()
    while node:
        entry = node.contents
        device_id = _decode_vlc_text(entry.device)
        label = _decode_vlc_text(entry.description) or device_id or "Predefinito"
        devices.append((device_id, label))
        node = entry.next
    return devices


class AudioOutputService(QObject):
    """Gestisce il device audio condiviso da tutti i player VLC (tranne filler DirectSound)."""

    device_changed = pyqtSignal(str)

    def __init__(self, probe_player, *, settings: QSettings | None = None) -> None:
        super().__init__()
        self._probe_player = probe_player
        self._settings = settings or QSettings(config.APP_NAME, config.APP_NAME)
        self._engines: list[VlcEngine] = []
        saved = self._settings.value(config.AUDIO_OUTPUT_DEVICE_SETTINGS_KEY, "")
        self._device_id = "" if saved is None else str(saved)

    def register_engine(self, engine: "VlcEngine") -> None:
        """Registra un motore VLC da aggiornare al cambio dispositivo."""
        if engine not in self._engines:
            self._engines.append(engine)
        engine.set_audio_output_device(self._device_id)

    def list_devices(self) -> list[tuple[str, str]]:
        """Restituisce (device_id, etichetta) per il menu a tendina."""
        if sys.platform != "win32":
            return [("", "Predefinito di sistema")]
        try:
            devices = enumerate_audio_output_devices(self._probe_player)
        except Exception as exc:  # noqa: BLE001 - dipende da libVLC locale
            logger.warning("Enumerazione dispositivi audio fallita: %s", exc)
            return [("", "Predefinito di sistema")]
        if not devices:
            return [("", "Predefinito di sistema")]
        return devices

    def current_device_id(self) -> str:
        """ID dispositivo selezionato (stringa vuota = predefinito Windows)."""
        return self._device_id

    def set_device_id(self, device_id: str | None) -> None:
        """Imposta e persiste il dispositivo, applicandolo a tutti i motori registrati."""
        normalized = "" if device_id is None else str(device_id)
        if normalized == self._device_id:
            return
        self._device_id = normalized
        self._settings.setValue(config.AUDIO_OUTPUT_DEVICE_SETTINGS_KEY, normalized)
        for engine in self._engines:
            engine.set_audio_output_device(normalized)
        logger.info("Uscita audio VLC impostata su: %r", normalized or "Predefinito")
        self.device_changed.emit(normalized)

    def apply_saved_device(self) -> None:
        """Riapplica il dispositivo salvato (utile dopo il wiring in main)."""
        for engine in self._engines:
            engine.set_audio_output_device(self._device_id)
