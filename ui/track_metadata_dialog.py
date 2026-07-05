"""Dialog modifica manuale artista e titolo di un brano in libreria."""

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QVBoxLayout,
)


class TrackMetadataDialog(QDialog):
    """Form per correggere artista e titolo catalogati."""

    def __init__(
        self,
        title: str,
        artist: str | None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Modifica brano")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._title_input = QLineEdit(title)
        self._artist_input = QLineEdit(artist or "")
        self._artist_input.setPlaceholderText("Artista (opzionale)")
        form.addRow("Titolo:", self._title_input)
        form.addRow("Artista:", self._artist_input)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def title_value(self) -> str:
        """Titolo inserito dall'operatore."""
        return self._title_input.text().strip()

    def artist_value(self) -> str | None:
        """Artista inserito; None se campo vuoto."""
        text = self._artist_input.text().strip()
        return text or None
