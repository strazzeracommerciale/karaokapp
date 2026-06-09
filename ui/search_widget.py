"""Widget risultati di ricerca (input gestito da MainWindow)."""

import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


class SearchWidget(QWidget):
    """Lista dei risultati di ricerca con doppio click per accodare."""

    track_selected = pyqtSignal(dict)
    load_more_requested = pyqtSignal()
    set_as_filler_requested = pyqtSignal(dict)

    def __init__(self) -> None:
        """Costruisce la lista risultati."""
        super().__init__()
        self._build_ui()

    def _build_ui(self) -> None:
        """Assembla layout e connessioni."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._results_list = QListWidget()
        self._results_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._results_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._results_list.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self._results_list)
        self._load_more_btn = QPushButton("Mostra altri risultati YouTube")
        self._load_more_btn.setObjectName("secondaryButton")
        self._load_more_btn.clicked.connect(self.load_more_requested.emit)
        self._load_more_btn.setVisible(False)
        layout.addWidget(self._load_more_btn)

    def _on_item_double_clicked(self, item) -> None:
        """Emette track_selected con i dati del risultato."""
        track = item.data(256)
        if track:
            self.track_selected.emit(track)

    def _on_context_menu(self, pos) -> None:
        """Menu contestuale: imposta il risultato come brano di sottofondo."""
        item = self._results_list.itemAt(pos)
        if item is None:
            return
        track = item.data(256)
        if not track:
            return
        menu = QMenu(self)
        action = menu.addAction("Imposta come sottofondo")
        if menu.exec(self._results_list.mapToGlobal(pos)) is action:
            self.set_as_filler_requested.emit(track)

    def set_results(self, results: list[dict], can_load_more: bool = False) -> None:
        """Aggiorna la lista risultati con badge origine."""
        self._results_list.clear()
        for track in results:
            origin = track.get("origin", track.get("source", "local"))
            badge = {"local": "[LOCAL]", "youtube": "[YT]"}.get(origin, "[?]")
            label = f"{badge} {track.get('title', '')} — {track.get('artist', '')}"
            item = QListWidgetItem(label)
            item.setData(256, track)
            self._results_list.addItem(item)
        self._load_more_btn.setVisible(can_load_more)
        self._load_more_btn.setEnabled(True)
        logger.debug("Risultati visualizzati: %d", len(results))

    def set_load_more_busy(self) -> None:
        """Disabilita il pulsante durante il caricamento di altri risultati."""
        self._load_more_btn.setEnabled(False)

    def mark_downloading(self, youtube_id: str) -> None:
        """Aggiorna il badge di un risultato in download."""
        for index in range(self._results_list.count()):
            item = self._results_list.item(index)
            track = item.data(256)
            if track and track.get("youtube_id") == youtube_id:
                item.setText(f"[DL] {track.get('title', '')} — {track.get('artist', '')}")
