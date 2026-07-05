"""Pannello ricerca YouTube/locale per la finestra Preparazione."""

from __future__ import annotations

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

import config
from ui.search_widget import SearchWidget


class PrepSearchPanel(QWidget):
    """Campo ricerca + risultati per trovare brani non ancora in libreria."""

    def __init__(self) -> None:
        super().__init__()
        self._last_query = ""
        self._yt_limit = config.YT_SEARCH_LIMIT
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Cerca online e in libreria:"))
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Artista, titolo o parole chiave…")
        self._search_input.textChanged.connect(self._on_search_text_changed)
        search_row.addWidget(self._search_input, stretch=1)
        layout.addLayout(search_row)

        self._search_widget = SearchWidget(prep_mode=True)
        layout.addWidget(self._search_widget, stretch=1)

        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(config.SEARCH_DEBOUNCE_MS)
        self._pending_query = ""

    def search_widget(self) -> SearchWidget:
        """Restituisce il widget risultati per il wiring esterno."""
        return self._search_widget

    def connect_debounce(self, callback) -> None:
        """Collega il timeout debounce al dispatcher esterno."""
        self._search_debounce.timeout.connect(callback)

    def pending_query(self) -> str:
        """Query in attesa di debounce."""
        return self._pending_query.strip()

    def last_query(self) -> str:
        """Ultima query inviata al service."""
        return self._last_query

    def set_last_query(self, query: str) -> None:
        """Memorizza l'ultima query eseguita."""
        self._last_query = query

    def yt_limit(self) -> int:
        """Limite risultati YouTube corrente."""
        return self._yt_limit

    def increase_yt_limit(self) -> None:
        """Amplia la pagina risultati YouTube."""
        self._yt_limit += config.YT_SEARCH_LIMIT

    def _on_search_text_changed(self, text: str) -> None:
        self._pending_query = text
        self._search_debounce.start()
