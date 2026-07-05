"""Pannello playlist per Preparazione: costruzione scaletta con libreria integrata."""

from __future__ import annotations

import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from utils.library_filter import filter_tracks
from utils.text import format_track_display

logger = logging.getLogger(__name__)

_TRACK_DATA_ROLE = Qt.ItemDataRole.UserRole


class PrepPlaylistWidget(QWidget):
    """Gestione scaletta in preparazione con aggiunta brani dalla libreria locale."""

    create_requested = pyqtSignal(str)
    delete_requested = pyqtSignal(int)
    playlist_changed = pyqtSignal(int)
    remove_track_requested = pyqtSignal(int, int)
    add_track_requested = pyqtSignal(int, int)
    edit_track_requested = pyqtSignal(dict)
    play_track_requested = pyqtSignal(dict)

    def __init__(self) -> None:
        super().__init__()
        self._playlist_tracks: list[dict] = []
        self._library_tracks: list[dict] = []
        self._filter_artist = ""
        self._filter_title = ""
        self._used_fallback = False
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        top = QHBoxLayout()
        top.addWidget(QLabel("Scaletta:"))
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

        splitter = QSplitter(Qt.Orientation.Vertical)

        playlist_panel = QWidget()
        playlist_layout = QVBoxLayout(playlist_panel)
        playlist_layout.setContentsMargins(0, 0, 0, 0)
        playlist_layout.addWidget(QLabel("Brani in scaletta"))
        self._playlist_list = QListWidget()
        self._playlist_list.itemDoubleClicked.connect(self._on_playlist_item_double_clicked)
        playlist_layout.addWidget(self._playlist_list, stretch=1)
        playlist_controls = QHBoxLayout()
        self._remove_btn = QPushButton("Rimuovi selezionato")
        self._remove_btn.setObjectName("secondaryButton")
        self._remove_btn.clicked.connect(self._on_remove_clicked)
        playlist_controls.addWidget(self._remove_btn)
        playlist_controls.addStretch()
        playlist_layout.addLayout(playlist_controls)
        self._playlist_empty = QLabel("Nessun brano in scaletta")
        self._playlist_empty.setObjectName("mutedLabel")
        playlist_layout.addWidget(self._playlist_empty)
        splitter.addWidget(playlist_panel)

        library_panel = QWidget()
        library_layout = QVBoxLayout(library_panel)
        library_layout.setContentsMargins(0, 0, 0, 0)
        library_layout.addWidget(QLabel("Aggiungi dalla libreria"))
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Artista:"))
        self._artist_input = QLineEdit()
        self._artist_input.setPlaceholderText("Parziale…")
        self._artist_input.textChanged.connect(self._on_library_filter_changed)
        filter_row.addWidget(self._artist_input, stretch=1)
        filter_row.addWidget(QLabel("Brano:"))
        self._title_input = QLineEdit()
        self._title_input.setPlaceholderText("Parziale…")
        self._title_input.textChanged.connect(self._on_library_filter_changed)
        filter_row.addWidget(self._title_input, stretch=1)
        library_layout.addLayout(filter_row)
        self._library_list = QListWidget()
        self._library_list.itemDoubleClicked.connect(self._on_add_clicked)
        library_layout.addWidget(self._library_list, stretch=1)
        library_controls = QHBoxLayout()
        self._library_count = QLabel("0 brani")
        self._library_count.setObjectName("mutedLabel")
        library_controls.addWidget(self._library_count)
        library_controls.addStretch()
        self._add_btn = QPushButton("Aggiungi alla scaletta")
        self._add_btn.clicked.connect(self._on_add_clicked)
        library_controls.addWidget(self._add_btn)
        library_layout.addLayout(library_controls)
        hint = QLabel("Doppio click sul brano per aggiungerlo · ricerca estesa al nome file se serve")
        hint.setObjectName("mutedLabel")
        library_layout.addWidget(hint)
        splitter.addWidget(library_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, stretch=1)

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

    def set_playlist_tracks(self, tracks: list[dict]) -> None:
        """Popola la lista brani della scaletta selezionata."""
        self._playlist_tracks = tracks
        self._playlist_list.clear()
        for track in tracks:
            ready = "" if track.get("ready", True) else "  (file mancante)"
            item = QListWidgetItem(
                format_track_display(track.get("title", ""), track.get("artist"), suffix=ready)
            )
            item.setData(_TRACK_DATA_ROLE, track)
            self._playlist_list.addItem(item)
        self._playlist_empty.setVisible(len(tracks) == 0)

    def set_library_tracks(self, tracks: list[dict]) -> None:
        """Imposta il catalogo locale disponibile per l'aggiunta."""
        self._library_tracks = tracks
        self._render_library_candidates()

    def _emit_current_playlist(self) -> None:
        playlist_id = self.current_playlist_id()
        if playlist_id is not None:
            self.playlist_changed.emit(playlist_id)
        else:
            self.set_playlist_tracks([])

    def _on_combo_changed(self, _index: int) -> None:
        self._emit_current_playlist()

    def _on_new_clicked(self) -> None:
        name, ok = QInputDialog.getText(self, "Nuova scaletta", "Nome della scaletta:")
        if ok and name.strip():
            self.create_requested.emit(name.strip())

    def _on_delete_clicked(self) -> None:
        playlist_id = self.current_playlist_id()
        if playlist_id is not None:
            self.delete_requested.emit(playlist_id)

    def _on_remove_clicked(self) -> None:
        playlist_id = self.current_playlist_id()
        item = self._playlist_list.currentItem()
        if playlist_id is None or item is None:
            return
        track = item.data(_TRACK_DATA_ROLE)
        if track and track.get("id") is not None:
            self.remove_track_requested.emit(playlist_id, track["id"])

    def _on_add_clicked(self) -> None:
        playlist_id = self.current_playlist_id()
        if playlist_id is None:
            return
        item = self._library_list.currentItem()
        if item is None:
            return
        track = item.data(_TRACK_DATA_ROLE)
        if track and track.get("id") is not None:
            self.add_track_requested.emit(playlist_id, track["id"])

    def _on_playlist_item_double_clicked(self, item: QListWidgetItem) -> None:
        track = item.data(_TRACK_DATA_ROLE)
        if track:
            self.play_track_requested.emit(track)

    def _on_library_filter_changed(self, *_args) -> None:
        self._filter_artist = self._artist_input.text().strip()
        self._filter_title = self._title_input.text().strip()
        self._render_library_candidates()

    def _render_library_candidates(self) -> None:
        self._library_list.clear()
        playlist_ids = {
            track.get("id") for track in self._playlist_tracks if track.get("id") is not None
        }
        if self._filter_artist or self._filter_title:
            visible, self._used_fallback = filter_tracks(
                self._library_tracks,
                artist_query=self._filter_artist,
                title_query=self._filter_title,
            )
        else:
            visible = self._library_tracks
            self._used_fallback = False

        shown = 0
        for track in visible:
            if track.get("id") in playlist_ids:
                continue
            label = format_track_display(track.get("title", ""), track.get("artist"))
            item = QListWidgetItem(label)
            item.setData(_TRACK_DATA_ROLE, track)
            self._library_list.addItem(item)
            shown += 1

        total = len(self._library_tracks)
        suffix = " (ricerca estesa al nome file)" if self._used_fallback else ""
        if self._filter_artist or self._filter_title:
            self._library_count.setText(f"{shown} candidati · {total} in libreria{suffix}")
        else:
            self._library_count.setText(f"{shown} disponibili · {total} in libreria")
