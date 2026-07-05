"""Widget ricerca DJ: query, risultati YouTube/locale e load more."""

import logging

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import config
from ui.search_widget import _is_youtube_stream_only
from utils.text import format_track_display

logger = logging.getLogger(__name__)

_TRACK_DATA_ROLE = Qt.ItemDataRole.UserRole


class DjSearchWidget(QWidget):
    """Ricerca unificata DJ con debounce e lista risultati."""

    search_requested = pyqtSignal(str, int)
    track_selected = pyqtSignal(dict)
    preview_requested = pyqtSignal(dict)
    save_to_library_requested = pyqtSignal(dict)

    def __init__(self) -> None:
        """Costruisce campo query e lista risultati."""
        super().__init__()
        self._last_query = ""
        self._yt_limit = config.YT_SEARCH_LIMIT
        self._pending_query = ""
        self._build_ui()
        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(config.SEARCH_DEBOUNCE_MS)
        self._search_debounce.timeout.connect(self._dispatch_search)

    def _build_ui(self) -> None:
        """Assembla layout ricerca DJ."""
        layout = QVBoxLayout(self)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Cerca:"))
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Brani locali DJ o YouTube…")
        self._search_input.textChanged.connect(self._on_search_text_changed)
        search_row.addWidget(self._search_input)
        layout.addLayout(search_row)

        self._results_list = QListWidget()
        self._results_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._results_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._results_list.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self._results_list)

        self._load_more_btn = QPushButton("Mostra altri risultati YouTube")
        self._load_more_btn.setObjectName("secondaryButton")
        self._load_more_btn.clicked.connect(self._on_load_more_clicked)
        self._load_more_btn.setVisible(False)
        layout.addWidget(self._load_more_btn)

        self._empty_label = QLabel("Nessun risultato.")
        self._empty_label.setVisible(False)
        layout.addWidget(self._empty_label)
        hint = QLabel("Doppio click su [YT]: anteprima · tasto destro: aggiungi o salva")
        hint.setObjectName("mutedLabel")
        layout.addWidget(hint)

    def _on_search_text_changed(self, text: str) -> None:
        """Avvia il debounce della ricerca."""
        self._pending_query = text
        self._search_debounce.start()

    def _dispatch_search(self) -> None:
        """Esegue una nuova ricerca dalla prima pagina YouTube."""
        query = self._pending_query.strip()
        self._last_query = query
        self._yt_limit = config.YT_SEARCH_LIMIT
        if not query:
            self.set_results([])
            return
        self.search_requested.emit(query, self._yt_limit)

    def _on_load_more_clicked(self) -> None:
        """Amplia la ricerca YouTube e riesegue la query corrente."""
        if not self._last_query:
            return
        self._yt_limit += config.YT_SEARCH_LIMIT
        self.set_load_more_busy()
        self.search_requested.emit(self._last_query, self._yt_limit)

    def set_results(self, results: list[dict], can_load_more: bool = False) -> None:
        """Aggiorna la lista risultati con badge origine."""
        self._results_list.clear()
        for track in results:
            origin = track.get("origin", track.get("source", "local"))
            badge = {"local": "[LOCAL]", "youtube": "[YT]"}.get(origin, "[?]")
            label = f"{badge} {format_track_display(track.get('title', ''), track.get('artist'))}"
            item = QListWidgetItem(label)
            item.setData(_TRACK_DATA_ROLE, track)
            self._results_list.addItem(item)
        self._load_more_btn.setVisible(can_load_more)
        self._load_more_btn.setEnabled(True)
        self._empty_label.setVisible(bool(self._last_query) and len(results) == 0)
        logger.debug("Risultati DJ visualizzati: %d", len(results))

    def set_load_more_busy(self) -> None:
        """Disabilita il pulsante durante il caricamento di altri risultati."""
        self._load_more_btn.setEnabled(False)

    def mark_downloading(self, youtube_id: str) -> None:
        """Aggiorna il badge di un risultato in download."""
        for index in range(self._results_list.count()):
            item = self._results_list.item(index)
            track = item.data(_TRACK_DATA_ROLE)
            if track and track.get("youtube_id") == youtube_id:
                artist = track.get("artist", "") or ""
                item.setText(f"[DL] {format_track_display(track.get('title', ''), artist)}")

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        """YouTube non scaricato: anteprima; altrimenti aggiunge al runtime."""
        track = item.data(_TRACK_DATA_ROLE)
        if not track:
            return
        if _is_youtube_stream_only(track):
            self.preview_requested.emit(track)
        else:
            self.track_selected.emit(track)

    def _on_context_menu(self, pos) -> None:
        """Menu contestuale: anteprima, runtime, salva."""
        item = self._results_list.itemAt(pos)
        if item is None:
            return
        track = item.data(_TRACK_DATA_ROLE)
        if not track:
            return
        menu = QMenu(self)
        preview_action = menu.addAction("Anteprima")
        runtime_action = menu.addAction("Aggiungi al runtime")
        save_action = None
        if _is_youtube_stream_only(track):
            save_action = menu.addAction("Salva in libreria")
        chosen = menu.exec(self._results_list.mapToGlobal(pos))
        if chosen is preview_action:
            self.preview_requested.emit(track)
        elif chosen is runtime_action:
            self.track_selected.emit(track)
        elif save_action is not None and chosen is save_action:
            self.save_to_library_requested.emit(track)
