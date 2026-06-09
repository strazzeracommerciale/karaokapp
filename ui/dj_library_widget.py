"""Widget libreria DJ: catalogo locale, import e scan cartella download."""

import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

_TRACK_DATA_ROLE = Qt.ItemDataRole.UserRole
_MEDIA_FILTER = (
    "Audio/Video (*.mp3 *.m4a *.wav *.flac *.ogg *.aac *.mp4 *.mkv *.webm *.avi *.mov *.wmv)"
)


class DjLibraryWidget(QWidget):
    """Libreria brani DJ con import manuale e scan della cartella download."""

    track_selected = pyqtSignal(dict)
    refresh_requested = pyqtSignal(str)
    import_paths_selected = pyqtSignal(list)
    scan_requested = pyqtSignal()

    def __init__(self) -> None:
        """Costruisce la UI della libreria DJ."""
        super().__init__()
        self._all_tracks: list[dict] = []
        self._filter = ""
        self._build_ui()

    def _build_ui(self) -> None:
        """Assembla layout libreria DJ."""
        layout = QVBoxLayout(self)

        import_row = QHBoxLayout()
        self._import_btn = QPushButton("Importa file…")
        self._import_btn.clicked.connect(self._on_import_clicked)
        import_row.addWidget(self._import_btn)
        self._scan_btn = QPushButton("Scan download DJ")
        self._scan_btn.setObjectName("secondaryButton")
        self._scan_btn.setToolTip("Registra i file già presenti in media/dj/downloads/")
        self._scan_btn.clicked.connect(self.scan_requested.emit)
        import_row.addWidget(self._scan_btn)
        import_row.addStretch()
        layout.addLayout(import_row)

        sort_row = QHBoxLayout()
        sort_row.addWidget(QLabel("Ordina:"))
        self._sort = QComboBox()
        self._sort.addItem("Recenti", "recent")
        self._sort.addItem("Più riprodotti", "played")
        self._sort.addItem("A-Z", "title")
        self._sort.currentIndexChanged.connect(self._emit_refresh)
        sort_row.addWidget(self._sort)
        self._refresh_btn = QPushButton("Aggiorna")
        self._refresh_btn.setObjectName("secondaryButton")
        self._refresh_btn.clicked.connect(self._emit_refresh)
        sort_row.addWidget(self._refresh_btn)
        sort_row.addStretch()
        layout.addLayout(sort_row)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filtra:"))
        self._filter_input = QLineEdit()
        self._filter_input.setPlaceholderText("Titolo o artista…")
        self._filter_input.textChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self._filter_input)
        layout.addLayout(filter_row)

        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self._list)

        self._empty_label = QLabel("Nessun brano DJ in libreria.")
        layout.addWidget(self._empty_label)
        layout.addWidget(QLabel("Doppio click su un brano per aggiungerlo al runtime."))

    def current_sort(self) -> str:
        """Restituisce il criterio di ordinamento selezionato."""
        return self._sort.currentData()

    def _emit_refresh(self) -> None:
        """Richiede l'aggiornamento della lista col criterio corrente."""
        self.refresh_requested.emit(self.current_sort())

    def set_tracks(self, tracks: list[dict]) -> None:
        """Memorizza l'elenco completo e mostra il sottoinsieme filtrato."""
        self._all_tracks = tracks
        self._render()

    def filter(self, text: str) -> None:
        """Limita la visualizzazione ai brani che contengono il testo."""
        self._filter = (text or "").strip().lower()
        self._render()

    def _on_filter_changed(self, text: str) -> None:
        """Applica il filtro testuale alla lista."""
        self.filter(text)

    def _on_import_clicked(self) -> None:
        """Apre il file picker multiplo e emette i path scelti."""
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Importa brani DJ",
            "",
            _MEDIA_FILTER,
        )
        if paths:
            self.import_paths_selected.emit(paths)

    def _render(self) -> None:
        """Disegna la lista applicando il filtro corrente."""
        self._list.clear()
        shown = 0
        for track in self._all_tracks:
            if self._filter:
                haystack = f"{track.get('title', '')} {track.get('artist') or ''}".lower()
                if self._filter not in haystack:
                    continue
            count = track.get("play_count") or 0
            meta = f"   ▶ {count}" if count else ""
            artist = track.get("artist") or ""
            artist_part = f" — {artist}" if artist else ""
            label = f"{track.get('title', '')}{artist_part}{meta}"
            item = QListWidgetItem(label)
            item.setData(_TRACK_DATA_ROLE, track)
            self._list.addItem(item)
            shown += 1
        self._empty_label.setVisible(shown == 0)
        logger.debug("Libreria DJ visualizzata: %d brani (filtro='%s')", shown, self._filter)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        """Emette track_selected per aggiungere il brano al runtime."""
        track = item.data(_TRACK_DATA_ROLE)
        if track:
            self.track_selected.emit(track)
