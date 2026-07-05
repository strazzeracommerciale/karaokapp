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
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from utils.library_filter import filter_tracks
from utils.text import format_track_display

logger = logging.getLogger(__name__)

_TRACK_DATA_ROLE = Qt.ItemDataRole.UserRole


class LibraryWidget(QWidget):
    """Lista sfogliabile dei brani locali con ordinamento e contatori."""

    track_selected = pyqtSignal(dict)
    refresh_requested = pyqtSignal(str)
    add_to_playlist_requested = pyqtSignal(dict)
    delete_requested = pyqtSignal(dict)
    edit_metadata_requested = pyqtSignal(dict)
    set_as_filler_requested = pyqtSignal(dict)

    def __init__(self, *, prep_mode: bool = False, live_browse_mode: bool = False) -> None:
        """Costruisce la UI della libreria."""
        super().__init__()
        self._prep_mode = prep_mode or live_browse_mode
        self._live_browse_mode = live_browse_mode
        self._all_tracks: list[dict] = []
        self._filter = ""
        self._filter_artist = ""
        self._filter_title = ""
        self._used_fallback = False
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._build_ui()

    def _build_ui(self) -> None:
        """Assembla layout libreria orientato alla navigazione rapida in serata."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Ordina:"))
        self._sort = QComboBox()
        self._sort.addItem("Recenti", "recent")
        self._sort.addItem("Più riprodotti", "played")
        self._sort.addItem("Titolo A-Z", "title")
        self._sort.addItem("Artista A-Z", "artist")
        self._sort.currentIndexChanged.connect(self._emit_refresh)
        toolbar.addWidget(self._sort)
        self._refresh_btn = QPushButton("Aggiorna")
        self._refresh_btn.setObjectName("secondaryButton")
        self._refresh_btn.clicked.connect(self._emit_refresh)
        toolbar.addWidget(self._refresh_btn)
        layout.addLayout(toolbar)

        if self._prep_mode:
            filter_row = QHBoxLayout()
            filter_row.addWidget(QLabel("Artista:"))
            self._filter_artist_input = QLineEdit()
            self._filter_artist_input.setPlaceholderText("Parziale…")
            self._filter_artist_input.textChanged.connect(self._on_prep_filter_changed)
            filter_row.addWidget(self._filter_artist_input, stretch=1)
            filter_row.addWidget(QLabel("Brano:"))
            self._filter_title_input = QLineEdit()
            self._filter_title_input.setPlaceholderText("Parziale…")
            self._filter_title_input.textChanged.connect(self._on_prep_filter_changed)
            filter_row.addWidget(self._filter_title_input, stretch=1)
            self._filter_mode_combo = None
            self._filter_input = None
            layout.addLayout(filter_row)
        else:
            filter_row = QHBoxLayout()
            filter_row.addWidget(QLabel("Filtra:"))
            self._filter_input = QLineEdit()
            self._filter_input.setPlaceholderText("Titolo o artista…")
            self._filter_input.textChanged.connect(self._on_filter_changed)
            filter_row.addWidget(self._filter_input, stretch=1)
            self._filter_mode_combo = None
            self._filter_artist_input = None
            self._filter_title_input = None
            layout.addLayout(filter_row)

        count_row = QHBoxLayout()
        self._count_label = QLabel("0 brani")
        self._count_label.setObjectName("mutedLabel")
        count_row.addWidget(self._count_label)
        count_row.addStretch()
        self._add_playlist_btn = QPushButton("Aggiungi a playlist")
        self._add_playlist_btn.setObjectName("secondaryButton")
        self._add_playlist_btn.clicked.connect(self._on_add_to_playlist)
        if not self._live_browse_mode:
            count_row.addWidget(self._add_playlist_btn)
        layout.addLayout(count_row)

        self._list = QListWidget()
        self._list.setObjectName("libraryTrackList")
        self._list.setMinimumHeight(160)
        self._list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._list.setAlternatingRowColors(True)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        if self._live_browse_mode:
            self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        else:
            self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self._list.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self._list, stretch=1)

        if self._live_browse_mode:
            hint = QLabel("Doppio click: accoda in coda e chiudi")
        elif self._prep_mode:
            hint = QLabel(
                "Doppio click: riproduci · tasto destro: modifica metadati e altre azioni"
            )
        else:
            hint = QLabel("Doppio click per accodare · tasto destro per altre azioni")
        hint.setObjectName("mutedLabel")
        layout.addWidget(hint)

        self._empty_label = QLabel("Nessun brano in libreria")
        self._empty_label.setObjectName("mutedLabel")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._empty_label)

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
        if self._prep_mode:
            if self._filter_artist_input is not None:
                self._filter_artist_input.clear()
            if self._filter_title_input is not None:
                self._filter_title_input.clear()
            self._filter_artist = ""
            self._filter_title = ""
            self._render()
        else:
            self.filter("")

    def active_filter(self) -> str:
        """Restituisce il testo del filtro attivo (compatibilità modalità serata)."""
        if self._prep_mode:
            parts = []
            if self._filter_artist_input and self._filter_artist_input.text().strip():
                parts.append(self._filter_artist_input.text().strip())
            if self._filter_title_input and self._filter_title_input.text().strip():
                parts.append(self._filter_title_input.text().strip())
            return " ".join(parts)
        return self._filter

    def _on_filter_changed(self, text: str) -> None:
        """Aggiorna la lista mentre l'operatore digita nel campo filtro."""
        self._filter = text.strip().lower()
        self._render()

    def _on_prep_filter_changed(self, *_args) -> None:
        """Aggiorna filtri preparazione artista/brano."""
        self._filter_artist = (
            self._filter_artist_input.text().strip() if self._filter_artist_input else ""
        )
        self._filter_title = (
            self._filter_title_input.text().strip() if self._filter_title_input else ""
        )
        self._render()

    def _filtered_tracks(self) -> list[dict]:
        if self._prep_mode:
            if not self._filter_artist and not self._filter_title:
                self._used_fallback = False
                return self._all_tracks
            tracks, fallback = filter_tracks(
                self._all_tracks,
                artist_query=self._filter_artist,
                title_query=self._filter_title,
            )
            self._used_fallback = fallback
            return tracks

        if not self._filter:
            return self._all_tracks
        return [
            track
            for track in self._all_tracks
            if self._filter
            in f"{track.get('title', '')} {track.get('artist') or ''}".lower()
        ]

    def _render(self) -> None:
        """Disegna la lista applicando il filtro corrente."""
        self._list.clear()
        visible_tracks = self._filtered_tracks()
        shown = 0
        for track in visible_tracks:
            count = track.get("play_count") or 0
            meta_parts = []
            if self._prep_mode and track.get("metadata_confirmed"):
                meta_parts.append("✓")
            if count:
                meta_parts.append(f"▶ {count}")
            suffix = f"   {' '.join(meta_parts)}" if meta_parts else ""
            label = format_track_display(
                track.get("title", ""),
                track.get("artist"),
                suffix=suffix,
            )
            item = QListWidgetItem(label)
            item.setData(_TRACK_DATA_ROLE, track)
            self._list.addItem(item)
            shown += 1
        total = len(self._all_tracks)
        if self._prep_mode and (self._filter_artist or self._filter_title):
            suffix = " (ricerca estesa al nome file)" if self._used_fallback else ""
            self._count_label.setText(f"{shown} di {total} brani{suffix}")
        elif not self._prep_mode and self._filter:
            self._count_label.setText(f"{shown} di {total} brani")
        else:
            self._count_label.setText(f"{total} brani")
        self._empty_label.setVisible(shown == 0)
        self._list.setVisible(shown > 0)
        if shown == 0:
            if (self._prep_mode and (self._filter_artist or self._filter_title)) or (
                not self._prep_mode and self._filter
            ):
                self._empty_label.setText("Nessun brano corrisponde al filtro")
            else:
                self._empty_label.setText("Nessun brano in libreria")
        logger.debug("Libreria visualizzata: %d brani", shown)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        """Emette track_selected con il brano scelto."""
        track = item.data(_TRACK_DATA_ROLE)
        if track:
            self.track_selected.emit(track)

    def _on_add_to_playlist(self) -> None:
        """Richiede l'aggiunta del brano selezionato a una playlist."""
        item = self._list.currentItem()
        if item is None:
            return
        track = item.data(_TRACK_DATA_ROLE)
        if track:
            self.add_to_playlist_requested.emit(track)

    def _on_context_menu(self, pos) -> None:
        """Menu contestuale: sottofondo ed eliminazione."""
        item = self._list.itemAt(pos)
        if item is None:
            return
        track = item.data(_TRACK_DATA_ROLE)
        if not track:
            return
        menu = QMenu(self)
        if self._prep_mode:
            play_action = menu.addAction("Riproduci")
        edit_action = menu.addAction("Modifica artista e titolo…")
        add_playlist_action = menu.addAction("Aggiungi a playlist…")
        filler_action = None
        if not self._prep_mode:
            filler_action = menu.addAction("Imposta come sottofondo")
        delete_action = menu.addAction("Elimina dalla libreria")
        chosen = menu.exec(self._list.mapToGlobal(pos))
        if self._prep_mode and chosen is play_action:
            self.track_selected.emit(track)
        elif chosen is edit_action:
            self.edit_metadata_requested.emit(track)
        elif chosen is add_playlist_action:
            self.add_to_playlist_requested.emit(track)
        elif filler_action is not None and chosen is filler_action:
            self.set_as_filler_requested.emit(track)
        elif chosen is delete_action:
            self.delete_requested.emit(track)

    def filter_tracks_for_display(self, tracks: list[dict]) -> list[dict]:
        """Applica i filtri correnti a un elenco brani (es. pannello playlist)."""
        previous = self._all_tracks
        self._all_tracks = tracks
        result = self._filtered_tracks()
        self._all_tracks = previous
        return result

    def current_filter_queries(self) -> tuple[str, str]:
        """Restituisce le query artista/titolo attive in modalità preparazione."""
        if self._prep_mode:
            return self._filter_artist, self._filter_title
        text = self._filter
        return text, text
