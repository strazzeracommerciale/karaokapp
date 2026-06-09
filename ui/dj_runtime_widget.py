"""Widget runtime DJ: coda della serata, shuffle/loop e salvataggio playlist."""

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from services.dj_runtime_service import DjRuntimeService

logger = logging.getLogger(__name__)

_TRACK_DATA_ROLE = Qt.ItemDataRole.UserRole


class DjRuntimeWidget(QWidget):
    """Lista runtime in memoria con controlli shuffle, loop e rimozione."""

    save_as_playlist_requested = pyqtSignal()

    def __init__(self, dj_runtime_service: "DjRuntimeService") -> None:
        """Costruisce la UI runtime collegata al service condiviso."""
        super().__init__()
        self._runtime = dj_runtime_service
        self._build_ui()
        self._connect_signals()
        self._sync_controls()
        self._refresh_list()

    def _build_ui(self) -> None:
        """Assembla lista runtime e controlli."""
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Runtime playlist"))
        self._list = QListWidget()
        layout.addWidget(self._list)

        flags_row = QHBoxLayout()
        self._shuffle_check = QCheckBox("Shuffle")
        self._shuffle_check.toggled.connect(self._on_shuffle_toggled)
        self._loop_check = QCheckBox("Loop")
        self._loop_check.toggled.connect(self._on_loop_toggled)
        flags_row.addWidget(self._shuffle_check)
        flags_row.addWidget(self._loop_check)
        flags_row.addStretch()
        layout.addLayout(flags_row)

        actions_row = QHBoxLayout()
        self._remove_btn = QPushButton("Rimuovi")
        self._remove_btn.setObjectName("secondaryButton")
        self._remove_btn.clicked.connect(self._on_remove_clicked)
        actions_row.addWidget(self._remove_btn)
        self._save_btn = QPushButton("Salva come playlist")
        self._save_btn.clicked.connect(self.save_as_playlist_requested.emit)
        actions_row.addWidget(self._save_btn)
        actions_row.addStretch()
        layout.addLayout(actions_row)

        self._empty_label = QLabel("Nessun brano in runtime — aggiungi dalla libreria, ricerca o playlist.")
        layout.addWidget(self._empty_label)

    def _connect_signals(self) -> None:
        """Collega aggiornamenti dal DjRuntimeService."""
        self._runtime.runtime_updated.connect(self._sync_controls)
        self._runtime.runtime_updated.connect(self._refresh_list)

    def _sync_controls(self) -> None:
        """Allinea checkbox shuffle/loop allo stato del runtime."""
        self._shuffle_check.blockSignals(True)
        self._loop_check.blockSignals(True)
        self._shuffle_check.setChecked(self._runtime.is_shuffle_enabled())
        self._loop_check.setChecked(self._runtime.is_loop_enabled())
        self._shuffle_check.blockSignals(False)
        self._loop_check.blockSignals(False)

    def _refresh_list(self) -> None:
        """Aggiorna la lista runtime ed evidenzia il brano corrente."""
        self._list.clear()
        current_index = self._runtime.get_current_index()
        for track in self._runtime.get_runtime_queue():
            title = track.get("title", "Senza titolo")
            artist = track.get("artist", "")
            label = f"{title} — {artist}" if artist else title
            item = QListWidgetItem(label)
            item.setData(_TRACK_DATA_ROLE, track)
            self._list.addItem(item)
        if 0 <= current_index < self._list.count():
            self._list.setCurrentRow(current_index)
        has_tracks = self._list.count() > 0
        self._empty_label.setVisible(not has_tracks)
        self._remove_btn.setEnabled(has_tracks)
        self._save_btn.setEnabled(has_tracks)

    def _on_shuffle_toggled(self, checked: bool) -> None:
        """Attiva/disattiva shuffle sul runtime (Fisher-Yates al toggle)."""
        self._runtime.set_shuffle(checked)

    def _on_loop_toggled(self, checked: bool) -> None:
        """Attiva/disattiva loop sul runtime."""
        self._runtime.set_loop(checked)

    def _on_remove_clicked(self) -> None:
        """Rimuove il brano selezionato dalla coda runtime."""
        row = self._list.currentRow()
        if row < 0:
            return
        self._runtime.remove_at(row)
