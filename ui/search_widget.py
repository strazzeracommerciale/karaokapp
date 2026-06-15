"""Widget risultati di ricerca (input gestito da MainWindow)."""

import logging
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


def _has_local_file(track: dict) -> bool:
    """True se il brano ha un file locale esistente."""
    local_path = track.get("local_path") or ""
    return bool(local_path) and Path(local_path).exists()


def _is_youtube_stream_only(track: dict) -> bool:
    """True se il risultato è YouTube senza file locale scaricato."""
    return track.get("source") == "youtube" and not _has_local_file(track)


class SearchWidget(QWidget):
    """Lista dei risultati di ricerca con anteprima e accodamento."""

    track_selected = pyqtSignal(dict)
    preview_requested = pyqtSignal(dict)
    save_to_library_requested = pyqtSignal(dict)
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
        hint = QLabel("Doppio click su [YT]: anteprima · tasto destro: accoda o salva")
        hint.setObjectName("mutedLabel")
        layout.addWidget(hint)

    def _on_item_double_clicked(self, item) -> None:
        """YouTube non scaricato: anteprima; altrimenti accoda."""
        track = item.data(256)
        if not track:
            return
        if _is_youtube_stream_only(track):
            self.preview_requested.emit(track)
        else:
            self.track_selected.emit(track)

    def _on_context_menu(self, pos) -> None:
        """Menu contestuale: anteprima, accoda, salva e sottofondo."""
        item = self._results_list.itemAt(pos)
        if item is None:
            return
        track = item.data(256)
        if not track:
            return
        menu = QMenu(self)
        preview_action = menu.addAction("Anteprima")
        queue_action = menu.addAction("Accoda in coda")
        save_action = None
        if _is_youtube_stream_only(track):
            save_action = menu.addAction("Salva in libreria")
        filler_action = menu.addAction("Imposta come sottofondo")
        chosen = menu.exec(self._results_list.mapToGlobal(pos))
        if chosen is preview_action:
            self.preview_requested.emit(track)
        elif chosen is queue_action:
            self.track_selected.emit(track)
        elif save_action is not None and chosen is save_action:
            self.save_to_library_requested.emit(track)
        elif chosen is filler_action:
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
