"""Widget playlist: crea/seleziona scalette e accoda i brani."""

import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from utils.text import format_track_display

logger = logging.getLogger(__name__)


class PlaylistWidget(QWidget):
    """Gestione playlist: selezione, creazione, accodamento brani."""

    create_requested = pyqtSignal(str)
    delete_requested = pyqtSignal(int)
    playlist_changed = pyqtSignal(int)
    track_selected = pyqtSignal(dict)
    enqueue_all_requested = pyqtSignal(int)
    remove_track_requested = pyqtSignal(int, int)

    def __init__(self) -> None:
        """Costruisce la UI della playlist."""
        super().__init__()
        self._tracks: list[dict] = []
        self._build_ui()

    def _build_ui(self) -> None:
        """Assembla layout playlist."""
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self._combo = QComboBox()
        self._combo.currentIndexChanged.connect(self._on_combo_changed)
        top.addWidget(self._combo, stretch=1)
        self._new_btn = QPushButton("Nuova")
        self._new_btn.clicked.connect(self._on_new_clicked)
        top.addWidget(self._new_btn)
        self._delete_btn = QPushButton("Elimina")
        self._delete_btn.setObjectName("secondaryButton")
        self._delete_btn.clicked.connect(self._on_delete_clicked)
        top.addWidget(self._delete_btn)
        layout.addLayout(top)
        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self._list)
        self._empty_label = QLabel("Playlist vuota")
        layout.addWidget(self._empty_label)
        controls = QHBoxLayout()
        self._enqueue_all_btn = QPushButton("Accoda tutta")
        self._enqueue_all_btn.clicked.connect(self._on_enqueue_all_clicked)
        self._remove_btn = QPushButton("Rimuovi dalla playlist")
        self._remove_btn.setObjectName("secondaryButton")
        self._remove_btn.clicked.connect(self._on_remove_clicked)
        controls.addWidget(self._enqueue_all_btn)
        controls.addWidget(self._remove_btn)
        layout.addLayout(controls)

    def set_playlists(self, playlists: list[dict]) -> None:
        """Popola la combo mantenendo la selezione corrente se possibile."""
        previous = self.current_playlist_id()
        self._combo.blockSignals(True)
        self._combo.clear()
        for playlist in playlists:
            self._combo.addItem(playlist["name"], playlist["id"])
        target_index = 0
        if previous is not None:
            found = self._combo.findData(previous)
            if found >= 0:
                target_index = found
        self._combo.setCurrentIndex(target_index if self._combo.count() else -1)
        self._combo.blockSignals(False)
        self._emit_current_playlist()

    def current_playlist_id(self) -> int | None:
        """Restituisce l'id della playlist selezionata, o None."""
        data = self._combo.currentData()
        return int(data) if data is not None else None

    def set_tracks(self, tracks: list[dict]) -> None:
        """Popola la lista brani della playlist selezionata."""
        self._tracks = tracks
        self._list.clear()
        for track in tracks:
            ready = "" if track.get("ready", True) else "  (file mancante)"
            item = QListWidgetItem(
                format_track_display(track.get("title", ""), track.get("artist"), suffix=ready)
            )
            item.setData(Qt.ItemDataRole.UserRole, track)
            self._list.addItem(item)
        self._empty_label.setVisible(len(tracks) == 0)

    def _emit_current_playlist(self) -> None:
        """Notifica la playlist correntemente selezionata."""
        playlist_id = self.current_playlist_id()
        if playlist_id is not None:
            self.playlist_changed.emit(playlist_id)
        else:
            self.set_tracks([])

    def _on_combo_changed(self, _index: int) -> None:
        """Gestisce il cambio di playlist selezionata."""
        self._emit_current_playlist()

    def _on_new_clicked(self) -> None:
        """Chiede il nome e richiede la creazione di una nuova playlist."""
        name, ok = QInputDialog.getText(self, "Nuova playlist", "Nome della playlist:")
        if ok and name.strip():
            self.create_requested.emit(name.strip())

    def _on_delete_clicked(self) -> None:
        """Richiede l'eliminazione della playlist selezionata."""
        playlist_id = self.current_playlist_id()
        if playlist_id is not None:
            self.delete_requested.emit(playlist_id)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        """Accoda il brano scelto con doppio click."""
        track = item.data(Qt.ItemDataRole.UserRole)
        if track:
            self.track_selected.emit(track)

    def _on_enqueue_all_clicked(self) -> None:
        """Richiede l'accodamento di tutta la playlist."""
        playlist_id = self.current_playlist_id()
        if playlist_id is not None:
            self.enqueue_all_requested.emit(playlist_id)

    def _on_remove_clicked(self) -> None:
        """Rimuove dalla playlist il brano selezionato."""
        playlist_id = self.current_playlist_id()
        item = self._list.currentItem()
        if playlist_id is None or item is None:
            return
        track = item.data(Qt.ItemDataRole.UserRole)
        if track and track.get("id") is not None:
            self.remove_track_requested.emit(playlist_id, track["id"])
