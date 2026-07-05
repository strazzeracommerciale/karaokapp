"""Finestra di sfoglio libreria durante la serata live."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QSettings, Qt, pyqtSignal
from PyQt6.QtWidgets import QVBoxLayout, QWidget

import config
from ui.library_widget import LibraryWidget

if TYPE_CHECKING:
    from services.library_service import LibraryService


class LibraryBrowseWindow(QWidget):
    """Libreria filtrabile: doppio click accoda il brano e chiude la finestra."""

    track_chosen = pyqtSignal(dict)

    def __init__(self, library_service: "LibraryService") -> None:
        super().__init__(flags=Qt.WindowType.Window)
        self._library = library_service
        self._settings = QSettings(config.APP_NAME, config.APP_NAME)
        self.setWindowTitle("Sfoglia libreria")
        self.resize(config.LIBRARY_BROWSE_DEFAULT_WIDTH, config.LIBRARY_BROWSE_DEFAULT_HEIGHT)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        self._library_widget = LibraryWidget(live_browse_mode=True)
        layout.addWidget(self._library_widget)
        self._library_widget.refresh_requested.connect(self._on_refresh)
        self._library_widget.track_selected.connect(self._on_track_chosen)

    def open_browse(self) -> None:
        """Mostra la finestra con l'elenco libreria aggiornato."""
        geometry = self._settings.value(config.LIBRARY_BROWSE_SETTINGS_GEOMETRY_KEY)
        if geometry:
            self.restoreGeometry(geometry)
        self._on_refresh(self._library_widget.current_sort())
        self.show()
        self.raise_()
        self.activateWindow()

    def refresh_if_visible(self) -> None:
        """Aggiorna la lista se la finestra è aperta."""
        if self.isVisible():
            self._on_refresh(self._library_widget.current_sort())

    def _on_refresh(self, sort: str = "") -> None:
        criterion = sort or self._library_widget.current_sort()
        self._library_widget.set_tracks(self._library.list_tracks(criterion))

    def _on_track_chosen(self, track: dict) -> None:
        self.track_chosen.emit(track)
        self.hide()

    def closeEvent(self, event) -> None:
        self._settings.setValue(
            config.LIBRARY_BROWSE_SETTINGS_GEOMETRY_KEY,
            self.saveGeometry(),
        )
        self.hide()
        event.ignore()

    def hideEvent(self, event) -> None:
        self._settings.setValue(
            config.LIBRARY_BROWSE_SETTINGS_GEOMETRY_KEY,
            self.saveGeometry(),
        )
        super().hideEvent(event)
