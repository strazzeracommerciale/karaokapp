"""Dialog revisione esiti aggiornamento metadati batch."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from services.metadata_refresh_models import TrackRefreshOutcome
from ui.track_metadata_dialog import TrackMetadataDialog


class MetadataRefreshReviewDialog(QDialog):
    """Mostra gli esiti del refresh e consente conferma o modifica manuale."""

    def __init__(
        self,
        outcomes: list[TrackRefreshOutcome],
        *,
        confirm_callback: Callable[[list[int]], int],
        edit_callback: Callable[[int, str, str | None], bool],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._outcomes = list(outcomes)
        self._confirm_callback = confirm_callback
        self._edit_callback = edit_callback
        self.setWindowTitle("Revisione metadati")
        self.resize(1020, 520)
        self._build_ui()
        self._populate_table()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Verifica nome file, artista e titolo assegnati nel database. "
                "Conferma i corretti o modifica prima di confermare. "
                "I brani confermati verranno saltati nei prossimi aggiornamenti automatici."
            )
        )
        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["Nome file", "Artista assegnato", "Titolo brano", "Esito", "Confermato", "Azioni"]
        )
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table, stretch=1)

        actions = QHBoxLayout()
        self._confirm_selected_btn = QPushButton("Conferma selezionati")
        self._confirm_selected_btn.clicked.connect(self._confirm_selected)
        actions.addWidget(self._confirm_selected_btn)
        self._confirm_all_btn = QPushButton("Conferma tutti")
        self._confirm_all_btn.setObjectName("secondaryButton")
        self._confirm_all_btn.clicked.connect(self._confirm_all)
        actions.addWidget(self._confirm_all_btn)
        actions.addStretch()
        layout.addLayout(actions)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _populate_table(self) -> None:
        self._table.setRowCount(len(self._outcomes))
        for row_index, outcome in enumerate(self._outcomes):
            file_path = outcome.new_path or outcome.old_path
            file_name = Path(file_path).name if file_path else ""
            artist = outcome.new_artist or ""
            title = outcome.new_title or ""
            self._table.setItem(row_index, 0, QTableWidgetItem(file_name))
            self._table.setItem(row_index, 1, QTableWidgetItem(artist))
            self._table.setItem(row_index, 2, QTableWidgetItem(title))
            self._table.setItem(row_index, 3, QTableWidgetItem(outcome.display_summary()))
            confirmed_item = QTableWidgetItem("")
            confirmed_item.setData(Qt.ItemDataRole.UserRole, outcome.track_id)
            self._table.setItem(row_index, 4, confirmed_item)
            self._table.setCellWidget(row_index, 5, self._make_row_actions(outcome, row_index))

    def _make_row_actions(self, outcome: TrackRefreshOutcome, row_index: int) -> QPushButton:
        button = QPushButton("Modifica…")
        button.setObjectName("secondaryButton")
        button.clicked.connect(lambda _checked=False, o=outcome, r=row_index: self._edit_row(o, r))
        return button

    def _selected_track_ids(self) -> list[int]:
        ids: list[int] = []
        for model_index in self._table.selectionModel().selectedRows():
            track_id = self._outcomes[model_index.row()].track_id
            if track_id not in ids:
                ids.append(track_id)
        return ids

    def _mark_confirmed_rows(self, track_ids: list[int]) -> None:
        confirmed = set(track_ids)
        for row_index, outcome in enumerate(self._outcomes):
            if outcome.track_id in confirmed:
                self._table.item(row_index, 4).setText("✓")

    def _confirm_selected(self) -> None:
        track_ids = self._selected_track_ids()
        if not track_ids:
            QMessageBox.information(self, "Conferma metadati", "Seleziona almeno un brano.")
            return
        count = self._confirm_callback(track_ids)
        self._mark_confirmed_rows(track_ids)
        QMessageBox.information(self, "Conferma metadati", f"Confermati {count} brani.")

    def _confirm_all(self) -> None:
        track_ids = [outcome.track_id for outcome in self._outcomes if outcome.status != "error"]
        if not track_ids:
            return
        count = self._confirm_callback(track_ids)
        self._mark_confirmed_rows(track_ids)
        QMessageBox.information(self, "Conferma metadati", f"Confermati {count} brani.")

    def _edit_row(self, outcome: TrackRefreshOutcome, row_index: int) -> None:
        dialog = TrackMetadataDialog(
            outcome.new_title,
            outcome.new_artist,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        title = dialog.title_value()
        if not title:
            QMessageBox.warning(self, "Modifica brano", "Il titolo non può essere vuoto.")
            return
        artist = dialog.artist_value()
        if self._edit_callback(outcome.track_id, title, artist):
            outcome.new_title = title
            outcome.new_artist = artist
            self._table.item(row_index, 1).setText(artist or "")
            self._table.item(row_index, 2).setText(title)
            self._confirm_callback([outcome.track_id])
            self._mark_confirmed_rows([outcome.track_id])
