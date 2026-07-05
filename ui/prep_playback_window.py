"""Finestra di ascolto per la preparazione: appare solo durante la riproduzione."""

from __future__ import annotations

from PyQt6.QtCore import QSettings, Qt, pyqtSignal
from PyQt6.QtWidgets import QPushButton, QVBoxLayout, QWidget

import config
from ui.player_widget import PlayerWidget
from ui.video_output_widget import VideoOutputWidget
from utils.text import clean_title


class PrepPlaybackWindow(QWidget):
    """Player video+audio in finestra separata (non fullscreen), visibile solo in riproduzione."""

    closed_by_user = pyqtSignal()

    def __init__(self) -> None:
        super().__init__(flags=Qt.WindowType.Window)
        self._settings = QSettings(config.APP_NAME, config.APP_NAME)
        self.setWindowTitle("Ascolto — Preparazione")
        self.resize(config.PREP_PLAYBACK_DEFAULT_WIDTH, config.PREP_PLAYBACK_DEFAULT_HEIGHT)
        self._build_ui()
        self.hide()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        self._video_output = VideoOutputWidget(min_height=280)
        self._player_widget = PlayerWidget()
        self._player_widget.set_start_save_enabled(False)
        layout.addWidget(self._video_output, stretch=1)
        layout.addWidget(self._player_widget)

    def video_output_widget(self) -> VideoOutputWidget:
        """Widget destinazione embed VLC."""
        return self._video_output

    def player_widget(self) -> PlayerWidget:
        """Controlli play/stop/volume."""
        return self._player_widget

    def set_vlc_output_rebind(self, callback) -> None:
        """Riaggancia VLC al resize della finestra."""
        self._video_output.set_vlc_resize_callback(callback)

    def show_for_track(self, track: dict) -> None:
        """Mostra la finestra prima di avviare VLC (necessario per l'embed su Windows)."""
        self._player_widget.set_track_info(
            clean_title(track.get("title", "")),
            track.get("artist"),
        )
        local_path = track.get("local_path") or ""
        self._player_widget.set_start_save_enabled(bool(local_path))
        geometry = self._settings.value(config.PREP_PLAYBACK_SETTINGS_GEOMETRY_KEY)
        if geometry:
            self.restoreGeometry(geometry)
        self.show()
        self.raise_()
        self.activateWindow()

    def close_playback(self) -> None:
        """Nasconde la finestra al termine o allo stop."""
        self._player_widget.reset()
        self.hide()

    def closeEvent(self, event) -> None:
        self._settings.setValue(
            config.PREP_PLAYBACK_SETTINGS_GEOMETRY_KEY,
            self.saveGeometry(),
        )
        self.closed_by_user.emit()
        self.hide()
        event.ignore()

    def hideEvent(self, event) -> None:
        self._settings.setValue(
            config.PREP_PLAYBACK_SETTINGS_GEOMETRY_KEY,
            self.saveGeometry(),
        )
        super().hideEvent(event)
