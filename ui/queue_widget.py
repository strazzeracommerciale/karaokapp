"""Sidebar coda prenotazioni con drag-and-drop."""

import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from utils.text import format_track_display

logger = logging.getLogger(__name__)


class QueueWidget(QWidget):
    """Lista coda con riordino drag-and-drop."""

    next_singer_clicked = pyqtSignal()
    remove_requested = pyqtSignal(int)
    reorder_requested = pyqtSignal(int, int)
    play_requested = pyqtSignal(int)
    requeue_requested = pyqtSignal(int)

    def __init__(self) -> None:
        """Costruisce la sidebar coda."""
        super().__init__()
        self._items: list[dict] = []
        self._build_ui()

    def _build_ui(self) -> None:
        """Assembla layout coda."""
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        header.addWidget(self._make_label("Coda"))
        self._next_btn = QPushButton("Prossimo cantante")
        self._next_btn.clicked.connect(self.next_singer_clicked.emit)
        header.addWidget(self._next_btn)
        layout.addLayout(header)
        self._list = QListWidget()
        self._list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._list.model().rowsMoved.connect(self._on_rows_moved)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self._list)
        controls = QHBoxLayout()
        self._up_btn = QPushButton("Su")
        self._up_btn.setObjectName("secondaryButton")
        self._up_btn.clicked.connect(self._on_move_up)
        self._down_btn = QPushButton("Giù")
        self._down_btn.setObjectName("secondaryButton")
        self._down_btn.clicked.connect(self._on_move_down)
        self._remove_btn = QPushButton("Rimuovi")
        self._remove_btn.setObjectName("secondaryButton")
        self._remove_btn.clicked.connect(self._on_remove_clicked)
        controls.addWidget(self._up_btn)
        controls.addWidget(self._down_btn)
        controls.addWidget(self._remove_btn)
        layout.addLayout(controls)

    def _make_label(self, text: str):
        """Crea QLabel con testo."""
        from PyQt6.QtWidgets import QLabel

        label = QLabel(text)
        label.setStyleSheet("font-size: 16px; font-weight: bold;")
        return label

    def set_queue(self, items: list[dict]) -> None:
        """Aggiorna la lista coda mantenendo la selezione corrente."""
        current = self._list.currentItem()
        selected_id = current.data(Qt.ItemDataRole.UserRole) if current else None
        self._items = items
        self._list.blockSignals(True)
        self._list.clear()
        for item in items:
            status_icon = {
                "waiting": "⏳",
                "playing": "▶",
                "done": "✓",
                "skipped": "⏭",
            }.get(item.get("status", "waiting"), "•")
            dl_suffix = "" if item.get("ready", True) else "  ⏬ in download"
            label = (
                f"{status_icon} {item.get('singer_name', 'Anonimo')} — "
                f"{format_track_display(item.get('title', ''), item.get('artist'))}{dl_suffix}"
            )
            list_item = QListWidgetItem(label)
            list_item.setData(Qt.ItemDataRole.UserRole, item.get("queue_id"))
            self._list.addItem(list_item)
            if selected_id is not None and item.get("queue_id") == selected_id:
                self._list.setCurrentItem(list_item)
        self._list.blockSignals(False)

    def _on_remove_clicked(self) -> None:
        """Emette remove_requested per l'elemento selezionato."""
        item = self._list.currentItem()
        if item is None:
            return
        queue_id = item.data(Qt.ItemDataRole.UserRole)
        if queue_id is not None:
            self.remove_requested.emit(queue_id)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        """Richiede la riproduzione del brano selezionato in coda."""
        queue_id = item.data(Qt.ItemDataRole.UserRole)
        if queue_id is not None:
            self.play_requested.emit(queue_id)

    def _on_context_menu(self, pos) -> None:
        """Menu contestuale sull'elemento della coda (riproduci/rimetti/rimuovi)."""
        item = self._list.itemAt(pos)
        if item is None:
            return
        queue_id = item.data(Qt.ItemDataRole.UserRole)
        if queue_id is None:
            return
        status = next(
            (it.get("status") for it in self._items if it.get("queue_id") == queue_id),
            "waiting",
        )
        menu = QMenu(self)
        play_action = menu.addAction("Riproduci ora")
        requeue_action = None
        if status in ("done", "skipped"):
            requeue_action = menu.addAction("Rimetti in coda")
        menu.addSeparator()
        remove_action = menu.addAction("Rimuovi dalla coda")
        chosen = menu.exec(self._list.mapToGlobal(pos))
        if chosen is None:
            return
        if chosen is play_action:
            self.play_requested.emit(queue_id)
        elif requeue_action is not None and chosen is requeue_action:
            self.requeue_requested.emit(queue_id)
        elif chosen is remove_action:
            self.remove_requested.emit(queue_id)

    def _on_move_up(self) -> None:
        """Sposta l'elemento selezionato una posizione più in alto."""
        row = self._list.currentRow()
        if 0 < row < len(self._items):
            item = self._items[row]
            self.reorder_requested.emit(item["queue_id"], item["position"] - 1)

    def _on_move_down(self) -> None:
        """Sposta l'elemento selezionato una posizione più in basso."""
        row = self._list.currentRow()
        if 0 <= row < len(self._items) - 1:
            item = self._items[row]
            self.reorder_requested.emit(item["queue_id"], item["position"] + 1)

    def keyPressEvent(self, event) -> None:
        """Rimuove l'elemento selezionato col tasto Canc."""
        if event.key() == Qt.Key.Key_Delete:
            self._on_remove_clicked()
            return
        super().keyPressEvent(event)

    def _on_rows_moved(self, _parent, start: int, _end: int, _dest, dest_row: int) -> None:
        """Emette reorder_requested dopo drag-and-drop.

        Usa lo snapshot `self._items` (ordine pre-spostamento) per ricavare il
        queue_id, perché con InternalMove il dato UserRole dell'item può andare
        perso. Converte poi la riga di destinazione del segnale Qt nel nuovo
        indice reale: spostando verso il basso (dest_row > start) l'item finisce a
        dest_row-1, perché viene prima rimosso dalla posizione di partenza.
        """
        if not (0 <= start < len(self._items)):
            return
        queue_id = self._items[start].get("queue_id")
        if queue_id is None:
            return
        new_index = dest_row - 1 if dest_row > start else dest_row
        self.reorder_requested.emit(queue_id, new_index + 1)
