"""Widget libreria locale: sfoglia i brani già scaricati."""

import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
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

logger = logging.getLogger(__name__)


class LibraryWidget(QWidget):
    """Lista sfogliabile dei brani locali con ordinamento e contatori."""

    track_selected = pyqtSignal(dict)
    refresh_requested = pyqtSignal(str)
    add_to_playlist_requested = pyqtSignal(dict)
    delete_requested = pyqtSignal(dict)
    set_as_filler_requested = pyqtSignal(dict)

    def __init__(self) -> None:
        """Costruisce la UI della libreria."""
        super().__init__()
        self._all_tracks: list[dict] = []
        self._filter = ""
        self._build_ui()

    def _build_ui(self) -> None:
        """Assembla layout libreria."""
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("Ordina:"))
        self._sort = QComboBox()
        self._sort.addItem("Recenti", "recent")
        self._sort.addItem("Più riprodotti", "played")
        self._sort.addItem("A-Z", "title")
        self._sort.currentIndexChanged.connect(self._emit_refresh)
        top.addWidget(self._sort)
        self._refresh_btn = QPushButton("Aggiorna")
        self._refresh_btn.setObjectName("secondaryButton")
        self._refresh_btn.clicked.connect(self._emit_refresh)
        top.addWidget(self._refresh_btn)
        top.addStretch()
        layout.addLayout(top)
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filtra:"))
        self._filter_input = QLineEdit()
        self._filter_input.setPlaceholderText("Titolo o artista…")
        self._filter_input.textChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self._filter_input)
        layout.addLayout(filter_row)
        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self._list)
        self._empty_label = QLabel("Nessun brano in libreria")
        layout.addWidget(self._empty_label)
        self._add_playlist_btn = QPushButton("Aggiungi a playlist")
        self._add_playlist_btn.setObjectName("secondaryButton")
        self._add_playlist_btn.clicked.connect(self._on_add_to_playlist)
        layout.addWidget(self._add_playlist_btn)

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
        normalized = (text or "").strip()
        self._filter = normalized.lower()
        if self._filter_input.text() != normalized:
            self._filter_input.blockSignals(True)
            self._filter_input.setText(normalized)
            self._filter_input.blockSignals(False)
        self._render()

    def clear_filter(self) -> None:
        """Rimuove il filtro e mostra l'intera libreria."""
        self.filter("")

    def active_filter(self) -> str:
        """Restituisce il testo del filtro attivo."""
        return self._filter

    def _on_filter_changed(self, text: str) -> None:
        """Aggiorna la lista mentre l'operatore digita nel campo filtro."""
        self._filter = text.strip().lower()
        self._render()

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
            item.setData(256, track)
            self._list.addItem(item)
            shown += 1
        self._empty_label.setVisible(shown == 0)
        if shown == 0:
            if self._filter:
                self._empty_label.setText("Nessun brano corrisponde al filtro")
            else:
                self._empty_label.setText("Nessun brano in libreria")
        logger.debug("Libreria visualizzata: %d brani (filtro='%s')", shown, self._filter)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        """Emette track_selected con il brano scelto."""
        track = item.data(256)
        if track:
            self.track_selected.emit(track)

    def _on_add_to_playlist(self) -> None:
        """Richiede l'aggiunta del brano selezionato a una playlist."""
        item = self._list.currentItem()
        if item is None:
            return
        track = item.data(256)
        if track:
            self.add_to_playlist_requested.emit(track)

    def _on_context_menu(self, pos) -> None:
        """Menu contestuale: sottofondo ed eliminazione."""
        item = self._list.itemAt(pos)
        if item is None:
            return
        track = item.data(256)
        if not track:
            return
        menu = QMenu(self)
        filler_action = menu.addAction("Imposta come sottofondo")
        delete_action = menu.addAction("Elimina dalla libreria")
        chosen = menu.exec(self._list.mapToGlobal(pos))
        if chosen is filler_action:
            self.set_as_filler_requested.emit(track)
        elif chosen is delete_action:
            self.delete_requested.emit(track)
