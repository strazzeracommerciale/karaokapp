"""Finestra principale operatore."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QEvent, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSlider,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

import config
from services.app_mode_service import AppModeService
from services.karaoke_playback_flow import KaraokePlaybackFlow
from services.queue_service import QueueService

if TYPE_CHECKING:
    from services.dj_playback_flow import DjPlaybackFlow
    from services.download_service import DownloadService
    from services.filler_service import FillerService
    from services.library_service import LibraryService
    from services.playlist_service import PlaylistService
    from services.player_service import PlayerService
    from services.search_service import SearchService
from ui.library_widget import LibraryWidget
from ui.playlist_widget import PlaylistWidget
from ui.player_widget import PlayerWidget
from ui.queue_widget import QueueWidget
from ui.search_widget import SearchWidget
from utils.text import clean_title

logger = logging.getLogger(__name__)


class _VideoOutputWidget(QWidget):
    """Widget nero per embed nativo dell'output video VLC."""

    def __init__(self) -> None:
        """Inizializza l'area video."""
        super().__init__()
        self.setMinimumHeight(200)
        self.setStyleSheet("background-color: #000000;")
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)


class MainWindow(QMainWindow):
    """Finestra principale con search, player e coda."""

    external_toggle_requested = pyqtSignal(bool)
    dj_console_toggle_requested = pyqtSignal()

    def __init__(
        self,
        app_mode_service: AppModeService,
        player_service: "PlayerService | None",
        search_service: "SearchService | None",
        queue_service: QueueService | None,
        download_service: "DownloadService | None",
        library_service: "LibraryService | None" = None,
        playlist_service: "PlaylistService | None" = None,
        dry_run: bool = False,
    ) -> None:
        """Costruisce la UI e collega i service."""
        super().__init__()
        self._app_mode = app_mode_service
        self._player = player_service
        self._search = search_service
        self._queue = queue_service
        self._download = download_service
        self._library = library_service
        self._playlist = playlist_service
        self._filler: "FillerService | None" = None
        self._pending_filler_youtube_id: str | None = None
        self._dry_run = dry_run
        self._karaoke_flow: KaraokePlaybackFlow | None = None
        self._dj_flow: "DjPlaybackFlow | None" = None
        if queue_service is not None:
            self._karaoke_flow = KaraokePlaybackFlow(
                queue_service,
                app_mode_service,
                player_service,
                search_service,
                library_service=library_service,
            )
        self._last_query = ""
        self._yt_limit = config.YT_SEARCH_LIMIT
        self.setWindowTitle("KaraokeManager")
        self._load_stylesheet()
        self._build_ui()
        self._connect_karaoke_flow_signals()
        self._connect_widget_signals()
        self._connect_service_signals()
        self._app_mode.mode_changed.connect(self._sync_mode_pills)
        self._sync_mode_pills(self._app_mode.get_mode())
        self._refresh_library()
        self._refresh_playlists()
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def wire_services(
        self,
        player_service: "PlayerService | None",
        search_service: "SearchService | None",
        download_service: "DownloadService | None",
    ) -> None:
        """Collega service aggiunti dopo la costruzione (es. post dry-run)."""
        self._player = player_service
        self._search = search_service
        self._download = download_service
        if self._karaoke_flow is not None:
            self._karaoke_flow.set_player(player_service)
            self._karaoke_flow.set_search(search_service)
        self._connect_service_signals()

    def wire_mode_services(self, dj_playback_flow: "DjPlaybackFlow") -> None:
        """Collega il flow playback DJ (guard interno su AppModeService)."""
        self._dj_flow = dj_playback_flow
        self.set_dj_flow(dj_playback_flow)

    def set_dj_flow(self, dj_playback_flow: "DjPlaybackFlow") -> None:
        """Collega il flow DJ al karaoke per l'ownership condivisa del player."""
        if self._karaoke_flow is not None:
            self._karaoke_flow.set_dj_flow(dj_playback_flow)
        self._connect_service_signals()

    def set_filler_service(self, filler_service: "FillerService | None") -> None:
        """Collega il service di sottofondo e sincronizza i controlli."""
        self._filler = filler_service
        if self._karaoke_flow is not None:
            self._karaoke_flow.set_filler(filler_service)
        if filler_service is not None:
            filler_service.set_volume(self._filler_volume.value())

    def queue_widget(self) -> QueueWidget:
        """Restituisce il widget coda per il wiring esterno."""
        return self._queue_widget

    def _load_stylesheet(self) -> None:
        """Carica QSS da assets."""
        qss_path = Path(__file__).resolve().parent.parent / "assets" / "style.qss"
        if qss_path.exists():
            self.setStyleSheet(qss_path.read_text(encoding="utf-8"))

    def _build_ui(self) -> None:
        """Assembla layout principale con pannelli ridimensionabili."""
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.addLayout(self._build_top_bar())

        self._video_output = _VideoOutputWidget()

        controls_panel = QWidget()
        controls = QVBoxLayout(controls_panel)
        controls.setContentsMargins(0, 0, 0, 0)
        singer_row = QHBoxLayout()
        singer_row.addWidget(QLabel("Cantante:"))
        self._singer_input = QLineEdit()
        self._singer_input.setPlaceholderText("Nome di chi canta")
        singer_row.addWidget(self._singer_input)
        controls.addLayout(singer_row)
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Cerca:"))
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Cerca brani locali o YouTube...")
        self._search_input.textChanged.connect(self._on_search_text_changed)
        search_row.addWidget(self._search_input)
        controls.addLayout(search_row)
        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(config.SEARCH_DEBOUNCE_MS)
        self._search_debounce.timeout.connect(self._dispatch_search)
        self._pending_query = ""
        self._tabs = QTabWidget()
        self._search_widget = SearchWidget()
        self._library_widget = LibraryWidget()
        self._playlist_widget = PlaylistWidget()
        self._tabs.addTab(self._search_widget, "Ricerca")
        self._tabs.addTab(self._library_widget, "Libreria")
        self._tabs.addTab(self._playlist_widget, "Playlist")
        controls.addWidget(self._tabs)
        self._player_widget = PlayerWidget()
        controls.addWidget(self._player_widget)

        self._left_splitter = QSplitter(Qt.Orientation.Vertical)
        self._left_splitter.setHandleWidth(10)
        self._left_splitter.addWidget(self._video_output)
        self._left_splitter.addWidget(controls_panel)
        self._left_splitter.setStretchFactor(0, 3)
        self._left_splitter.setStretchFactor(1, 2)

        self._queue_widget = QueueWidget()

        self._main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._main_splitter.setHandleWidth(10)
        self._main_splitter.addWidget(self._left_splitter)
        self._main_splitter.addWidget(self._queue_widget)
        self._main_splitter.setStretchFactor(0, 3)
        self._main_splitter.setStretchFactor(1, 1)
        root.addWidget(self._main_splitter)

        self._preview_maximized = False
        self._saved_left_sizes: list[int] | None = None
        self._saved_main_sizes: list[int] | None = None

    def _build_top_bar(self) -> QHBoxLayout:
        """Barra superiore: modalità, consolle DJ, monitor esterno e sottofondo."""
        bar = QHBoxLayout()
        self._mode_karaoke_btn = QPushButton("Karaoke")
        self._mode_karaoke_btn.setObjectName("modeToggle")
        self._mode_karaoke_btn.setCheckable(True)
        self._mode_karaoke_btn.setChecked(True)
        self._mode_karaoke_btn.clicked.connect(self._on_mode_karaoke_clicked)
        bar.addWidget(self._mode_karaoke_btn)
        self._mode_dj_btn = QPushButton("DJ")
        self._mode_dj_btn.setObjectName("modeToggle")
        self._mode_dj_btn.setCheckable(True)
        self._mode_dj_btn.clicked.connect(self._on_mode_dj_clicked)
        bar.addWidget(self._mode_dj_btn)
        self._dj_console_btn = QPushButton("Consolle DJ")
        self._dj_console_btn.setObjectName("secondaryButton")
        self._dj_console_btn.clicked.connect(self._on_dj_console_toggle)
        bar.addWidget(self._dj_console_btn)
        bar.addSpacing(12)
        self._external_available = False
        self._external_btn = QPushButton("Monitor esterno: OFF")
        self._external_btn.setCheckable(True)
        self._external_btn.setEnabled(False)
        self._external_btn.setToolTip("Nessun secondo schermo rilevato")
        self._external_btn.toggled.connect(self._on_external_toggled)
        bar.addWidget(self._external_btn)
        bar.addStretch()
        bar.addWidget(QLabel("Sottofondo:"))
        self._filler_choose_btn = QPushButton("Scegli brano…")
        self._filler_choose_btn.setObjectName("secondaryButton")
        self._filler_choose_btn.clicked.connect(self._on_filler_choose)
        bar.addWidget(self._filler_choose_btn)
        self._filler_name = QLabel("(nessuno)")
        self._filler_name.setStyleSheet("color: #9a9aa6;")
        bar.addWidget(self._filler_name)
        self._filler_enabled = QCheckBox("Attivo nelle pause")
        self._filler_enabled.toggled.connect(self._on_filler_enabled)
        bar.addWidget(self._filler_enabled)
        bar.addWidget(QLabel("Vol"))
        self._filler_volume = QSlider(Qt.Orientation.Horizontal)
        self._filler_volume.setRange(0, 100)
        self._filler_volume.setValue(30)
        self._filler_volume.setMaximumWidth(120)
        self._filler_volume.valueChanged.connect(self._on_filler_volume)
        bar.addWidget(self._filler_volume)
        return bar

    def _connect_karaoke_flow_signals(self) -> None:
        """Collega i segnali del flow karaoke agli aggiornamenti UI (idempotente)."""
        flow = self._karaoke_flow
        if flow is None:
            return
        for signal, slot in (
            (flow.player_reset_requested, self._player_widget.reset),
            (flow.track_info_updated, self._player_widget.set_track_info),
            (flow.start_save_enabled_changed, self._player_widget.set_start_save_enabled),
            (flow.track_failed, self._on_flow_track_failed),
        ):
            try:
                signal.disconnect(slot)
            except TypeError:
                pass
            signal.connect(slot)

    def _connect_widget_signals(self) -> None:
        """Collega segnali interni widget → handler."""
        self._search_widget.track_selected.connect(self._on_track_selected)
        self._search_widget.load_more_requested.connect(self._on_load_more)
        self._search_widget.set_as_filler_requested.connect(self._on_set_as_filler)
        self._library_widget.track_selected.connect(self._on_track_selected)
        self._library_widget.refresh_requested.connect(self._on_library_refresh)
        self._library_widget.add_to_playlist_requested.connect(self._on_add_to_playlist)
        self._library_widget.set_as_filler_requested.connect(self._on_set_as_filler)
        self._playlist_widget.track_selected.connect(self._on_track_selected)
        self._playlist_widget.create_requested.connect(self._on_playlist_create)
        self._playlist_widget.delete_requested.connect(self._on_playlist_delete)
        self._playlist_widget.playlist_changed.connect(self._on_playlist_load_tracks)
        self._playlist_widget.enqueue_all_requested.connect(self._on_playlist_enqueue_all)
        self._playlist_widget.remove_track_requested.connect(self._on_playlist_remove_track)
        self._tabs.currentChanged.connect(self._on_tab_changed)
        self._player_widget.play_pause_clicked.connect(self._on_play_pause)
        self._player_widget.stop_clicked.connect(self._on_stop)
        self._player_widget.skip_clicked.connect(self._on_skip)
        self._player_widget.seek_requested.connect(self._on_seek)
        self._player_widget.volume_changed.connect(self._on_volume)
        self._player_widget.set_start_here_clicked.connect(self._on_set_start_here)
        self._queue_widget.next_singer_clicked.connect(self._on_next_singer)
        self._queue_widget.reorder_requested.connect(self._on_reorder)
        self._queue_widget.remove_requested.connect(self._on_remove)
        self._queue_widget.play_requested.connect(self._on_queue_play)
        self._queue_widget.requeue_requested.connect(self._on_requeue)

    def _connect_service_signals(self) -> None:
        """Collega segnali service → widget e flow (idempotente)."""
        if self._search is not None:
            try:
                self._search.results_ready.disconnect(self._on_results_ready)
            except TypeError:
                pass
            self._search.results_ready.connect(self._on_results_ready)
        if self._queue is not None:
            self._queue_widget.set_queue(self._queue.get_queue())
        if self._player is not None:
            if self._karaoke_flow is not None:
                flow = self._karaoke_flow
                try:
                    self._player.track_started.disconnect(flow.on_track_started)
                    self._player.track_ended.disconnect(flow.on_track_ended)
                    self._player.track_failed.disconnect(flow.on_track_failed)
                    self._player.position_updated.disconnect(self._player_widget.update_position)
                except TypeError:
                    pass
                self._player.track_started.connect(flow.on_track_started)
                self._player.track_ended.connect(flow.on_track_ended)
                self._player.track_failed.connect(flow.on_track_failed)
                self._player.position_updated.connect(self._player_widget.update_position)
                self._player.set_volume(self._player_widget.volume())
            if self._dj_flow is not None:
                dj_flow = self._dj_flow
                try:
                    self._player.track_started.disconnect(dj_flow.on_track_started)
                    self._player.track_ended.disconnect(dj_flow.on_track_ended)
                    self._player.track_failed.disconnect(dj_flow.on_track_failed)
                except TypeError:
                    pass
                self._player.track_started.connect(dj_flow.on_track_started)
                self._player.track_ended.connect(dj_flow.on_track_ended)
                self._player.track_failed.connect(dj_flow.on_track_failed)
        if self._download is not None:
            try:
                self._download.download_progress.disconnect(self._on_download_progress)
                self._download.download_complete.disconnect(self._on_download_complete)
            except TypeError:
                pass
            self._download.download_progress.connect(self._on_download_progress)
            self._download.download_complete.connect(self._on_download_complete)

    def video_output_widget(self) -> QWidget:
        """Restituisce il widget per embed VLC."""
        return self._video_output

    def _on_search_text_changed(self, text: str) -> None:
        """Avvia il debounce della ricerca/filtro."""
        self._pending_query = text
        self._search_debounce.start()

    def _dispatch_search(self) -> None:
        """Instrada la query: ricerca unificata o filtro libreria a seconda della scheda."""
        query = self._pending_query.strip()
        if self._tabs.currentWidget() is self._library_widget:
            self._library_widget.filter(query)
        else:
            self._on_search(query)

    def _on_search(self, query: str) -> None:
        """Avvia ricerca tramite service, ripartendo dalla prima pagina YouTube."""
        self._last_query = query
        self._yt_limit = config.YT_SEARCH_LIMIT
        if not query:
            self._search_widget.set_results([])
        elif self._search is not None:
            self._search.search(query, self._yt_limit)
        else:
            self._search_widget.set_results([])

    def _on_load_more(self) -> None:
        """Amplia la ricerca YouTube di una pagina e riesegue la query."""
        if self._search is None or not self._last_query:
            return
        self._yt_limit += config.YT_SEARCH_LIMIT
        self._search_widget.set_load_more_busy()
        self._search.search(self._last_query, self._yt_limit)

    def _on_results_ready(self, results: list[dict]) -> None:
        """Mostra i risultati e abilita 'mostra altri' se YouTube può offrirne di più."""
        yt_count = sum(1 for track in results if track.get("source") == "youtube")
        can_load_more = bool(self._last_query) and yt_count >= self._yt_limit
        self._search_widget.set_results(results, can_load_more)

    def _on_track_selected(self, track: dict) -> None:
        """Aggiunge in coda il brano selezionato col nome del cantante."""
        name = self._singer_input.text().strip() or "Ospite"
        if self._queue is not None:
            self._queue.add(track, singer_name=name)
        if track.get("source") == "youtube" and self._search is not None:
            self._search.trigger_download_for_track(track)

    def _on_library_refresh(self, sort: str = "") -> None:
        """Aggiorna la lista della libreria locale."""
        if self._library is None:
            return
        criterion = sort or self._library_widget.current_sort()
        self._library_widget.set_tracks(self._library.list_tracks(criterion))

    def _refresh_library(self) -> None:
        """Popola la libreria all'avvio se il service è disponibile."""
        self._on_library_refresh()

    def _on_tab_changed(self, index: int) -> None:
        """Applica placeholder e ricerca/filtro coerenti con la scheda attiva."""
        query = self._search_input.text().strip()
        if self._tabs.widget(index) is self._library_widget:
            self._search_input.setPlaceholderText("Filtra la libreria...")
            self._on_library_refresh()
            self._library_widget.filter(query)
        elif self._tabs.widget(index) is self._playlist_widget:
            self._refresh_playlists()
        else:
            self._search_input.setPlaceholderText("Cerca brani locali o YouTube...")
            self._on_search(query)

    def _refresh_playlists(self) -> None:
        """Ricarica l'elenco delle playlist karaoke mantenendo la selezione."""
        if self._playlist is None:
            return
        self._playlist_widget.set_playlists(self._playlist.list_playlists(mode="karaoke"))

    def _on_playlist_load_tracks(self, playlist_id: int) -> None:
        """Carica i brani della playlist selezionata."""
        if self._playlist is not None:
            self._playlist_widget.set_tracks(self._playlist.get_tracks(playlist_id))

    def _on_playlist_create(self, name: str) -> None:
        """Crea una nuova playlist e la seleziona."""
        if self._playlist is None:
            return
        self._playlist.create(name)
        self._refresh_playlists()

    def _on_playlist_delete(self, playlist_id: int) -> None:
        """Elimina una playlist."""
        if self._playlist is None:
            return
        self._playlist.delete(playlist_id)
        self._refresh_playlists()

    def _on_playlist_enqueue_all(self, playlist_id: int) -> None:
        """Accoda tutti i brani della playlist col cantante corrente."""
        if self._playlist is None or self._queue is None:
            return
        name = self._singer_input.text().strip() or "Ospite"
        for track in self._playlist.get_tracks(playlist_id):
            self._queue.add(track, singer_name=name)

    def _on_playlist_remove_track(self, playlist_id: int, track_id: int) -> None:
        """Rimuove un brano dalla playlist e ricarica la lista."""
        if self._playlist is None:
            return
        self._playlist.remove_track(playlist_id, track_id)
        self._on_playlist_load_tracks(playlist_id)

    def _on_add_to_playlist(self, track: dict) -> None:
        """Mostra un menu per aggiungere il brano a una playlist (o crearne una)."""
        if self._playlist is None or not track.get("id"):
            return
        menu = QMenu(self)
        for playlist in self._playlist.list_playlists(mode="karaoke"):
            action = menu.addAction(playlist["name"])
            action.setData(playlist["id"])
        menu.addSeparator()
        new_action = menu.addAction("Nuova playlist…")
        new_action.setData(-1)
        chosen = menu.exec(QCursor.pos())
        if chosen is None:
            return
        playlist_id = chosen.data()
        if playlist_id == -1:
            name, ok = QInputDialog.getText(self, "Nuova playlist", "Nome della playlist:")
            if not ok or not name.strip():
                return
            playlist_id = self._playlist.create(name.strip())
        added = self._playlist.add_track(playlist_id, track["id"])
        self._refresh_playlists()
        if self._playlist_widget.current_playlist_id() == playlist_id:
            self._on_playlist_load_tracks(playlist_id)
        if not added:
            logger.info("Brano già presente nella playlist: %s", track.get("title"))

    def _on_mode_karaoke_clicked(self) -> None:
        """Attiva la modalità karaoke."""
        self._app_mode.set_mode("karaoke")

    def _on_mode_dj_clicked(self) -> None:
        """Attiva la modalità DJ."""
        self._app_mode.set_mode("dj")

    def _on_dj_console_toggle(self) -> None:
        """Richiede a main.py il toggle show/hide della consolle DJ."""
        self.dj_console_toggle_requested.emit()

    def _sync_mode_pills(self, mode: str) -> None:
        """Aggiorna le pill modalità nella titlebar."""
        karaoke_active = mode == "karaoke"
        self._mode_karaoke_btn.setChecked(karaoke_active)
        self._mode_dj_btn.setChecked(not karaoke_active)
        self._mode_karaoke_btn.setObjectName("modeToggleActive" if karaoke_active else "modeToggle")
        self._mode_dj_btn.setObjectName("modeToggleActive" if not karaoke_active else "modeToggle")
        self._mode_karaoke_btn.style().unpolish(self._mode_karaoke_btn)
        self._mode_karaoke_btn.style().polish(self._mode_karaoke_btn)
        self._mode_dj_btn.style().unpolish(self._mode_dj_btn)
        self._mode_dj_btn.style().polish(self._mode_dj_btn)

    def _on_play_pause(self) -> None:
        """Delega play/pausa a entrambi i flow (guard interno su modalità)."""
        if self._dj_flow is not None:
            self._dj_flow.play_pause()
        if self._karaoke_flow is not None:
            self._karaoke_flow.play_pause()

    def _on_stop(self) -> None:
        """Delega stop a entrambi i flow (guard interno su modalità)."""
        if self._dj_flow is not None:
            self._dj_flow.stop()
        if self._karaoke_flow is not None:
            self._karaoke_flow.stop()

    def _on_skip(self) -> None:
        """Delega skip a entrambi i flow (guard interno su modalità)."""
        if self._dj_flow is not None:
            self._dj_flow.skip()
        if self._karaoke_flow is None:
            return
        if (
            self._app_mode.get_mode() == "karaoke"
            and self._dj_flow is not None
            and self._dj_flow.is_playback_active()
        ):
            QMessageBox.warning(
                self,
                "Skip",
                "Il player è occupato dalla consolle DJ.",
            )
            return
        self._karaoke_flow.skip()

    def _on_seek(self, seconds: float) -> None:
        """Seek nel brano corrente."""
        if self._player is not None:
            self._player.seek(seconds)

    def _on_volume(self, value: int) -> None:
        """Aggiorna il volume di riproduzione."""
        if self._player is not None:
            self._player.set_volume(value)

    def set_external_available(self, available: bool) -> None:
        """Abilita il pulsante solo se è presente un secondo schermo."""
        self._external_available = available
        self._external_btn.setEnabled(available)
        self._external_btn.setToolTip(
            "" if available else "Nessun secondo schermo rilevato"
        )
        if not available and self._external_btn.isChecked():
            self._external_btn.setChecked(False)

    def set_external_checked(self, checked: bool) -> None:
        """Allinea lo stato del pulsante senza riemettere richieste ridondanti."""
        if self._external_btn.isChecked() != checked:
            self._external_btn.blockSignals(True)
            self._external_btn.setChecked(checked)
            self._external_btn.blockSignals(False)
            self._external_btn.setText(f"Monitor esterno: {'ON' if checked else 'OFF'}")

    def _on_external_toggled(self, checked: bool) -> None:
        """Accende/spegne il monitor esterno e aggiorna l'etichetta del pulsante."""
        if checked and not self._external_available:
            self.set_external_checked(False)
            return
        self._external_btn.setText(f"Monitor esterno: {'ON' if checked else 'OFF'}")
        self.external_toggle_requested.emit(checked)

    def _on_filler_choose(self) -> None:
        """Sceglie il file del brano di sottofondo."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Scegli il brano di sottofondo",
            "",
            "Audio/Video (*.mp3 *.m4a *.wav *.flac *.ogg *.aac *.mp4 *.mkv *.webm *.avi)",
        )
        if not path:
            return
        self._apply_filler_track(path, Path(path).name)

    def _apply_filler_track(self, path: str, label: str) -> None:
        """Imposta il file del sottofondo, attiva la funzione e lo avvia se in pausa."""
        self._filler_name.setText(label)
        if self._filler is None:
            return
        self._filler.set_track(path)
        if not self._filler_enabled.isChecked():
            self._filler_enabled.setChecked(True)
        elif not self._is_track_playing():
            self._filler.start()

    def _on_set_as_filler(self, track: dict) -> None:
        """Imposta come sottofondo un brano da ricerca/libreria (scaricandolo se serve)."""
        if self._filler is None:
            QMessageBox.information(
                self, "Sottofondo", "Il sottofondo non è disponibile in questa modalità."
            )
            return
        local_path = track.get("local_path") or ""
        if local_path and Path(local_path).exists():
            self._apply_filler_track(local_path, clean_title(track.get("title", "")))
            return
        youtube_id = track.get("youtube_id")
        if youtube_id and self._download is not None:
            self._pending_filler_youtube_id = youtube_id
            self._filler_name.setText(f"⏳ {clean_title(track.get('title', ''))}")
            self._download.enqueue(youtube_id, track.get("title", ""), trigger="filler")
            QMessageBox.information(
                self,
                "Sottofondo",
                "Scaricamento del brano di sottofondo avviato: sarà impostato al termine.",
            )
        else:
            QMessageBox.warning(
                self, "Sottofondo", "Brano non disponibile come sottofondo."
            )

    def _on_filler_enabled(self, checked: bool) -> None:
        """Abilita/disabilita il sottofondo nelle pause."""
        if self._filler is None:
            return
        self._filler.set_enabled(checked)
        if checked and not self._is_track_playing():
            self._filler.start()

    def _on_filler_volume(self, value: int) -> None:
        """Aggiorna il volume del sottofondo."""
        if self._filler is not None:
            self._filler.set_volume(value)

    def _is_track_playing(self) -> bool:
        """True se è in corso la riproduzione di un brano."""
        if self._karaoke_flow is None:
            return False
        return self._karaoke_flow.is_track_playing()

    def closeEvent(self, event) -> None:
        """Chiudere la finestra principale termina l'intera applicazione."""
        QApplication.instance().quit()
        super().closeEvent(event)

    def eventFilter(self, obj, event) -> bool:
        """Scorciatoie globali stile YouTube indipendenti dal focus."""
        if event.type() == QEvent.Type.KeyPress:
            if QApplication.activeModalWidget() is not None:
                return super().eventFilter(obj, event)
            focus = QApplication.focusWidget()
            if isinstance(focus, QLineEdit):
                return super().eventFilter(obj, event)
            key = event.key()
            if key == Qt.Key.Key_Space:
                self._on_play_pause()
                return True
            if key == Qt.Key.Key_Right:
                self._seek_relative(5)
                return True
            if key == Qt.Key.Key_Left:
                self._seek_relative(-5)
                return True
            if key == Qt.Key.Key_Up:
                self._nudge_volume(5)
                return True
            if key == Qt.Key.Key_Down:
                self._nudge_volume(-5)
                return True
            if key == Qt.Key.Key_F11:
                self._toggle_preview()
                return True
        return super().eventFilter(obj, event)

    def _seek_relative(self, delta_sec: float) -> None:
        """Sposta la posizione di riproduzione di delta_sec secondi."""
        if self._player is None:
            return
        state = self._player.get_state()
        duration = state.get("duration", 0.0)
        position = state.get("position", 0.0)
        target = position + delta_sec
        if duration > 0:
            target = max(0.0, min(target, duration - 1))
        else:
            target = max(0.0, target)
        self._player.seek(target)

    def _nudge_volume(self, delta: int) -> None:
        """Aumenta o diminuisce il volume agendo sullo slider del player."""
        new_value = max(0, min(100, self._player_widget.volume() + delta))
        self._player_widget.set_volume_value(new_value)

    def _toggle_preview(self) -> None:
        """Alterna tra anteprima massimizzata e dimensioni precedenti dei frame."""
        if not self._preview_maximized:
            self._saved_left_sizes = self._left_splitter.sizes()
            self._saved_main_sizes = self._main_splitter.sizes()
            left_total = sum(self._saved_left_sizes)
            main_total = sum(self._saved_main_sizes)
            self._left_splitter.setSizes([left_total, 0])
            self._main_splitter.setSizes([main_total, 0])
            self._preview_maximized = True
        else:
            if self._saved_left_sizes is not None:
                self._left_splitter.setSizes(self._saved_left_sizes)
            if self._saved_main_sizes is not None:
                self._main_splitter.setSizes(self._saved_main_sizes)
            self._preview_maximized = False

    def _on_queue_play(self, queue_id: int) -> None:
        """Riproduce un brano arbitrario richiamato dalla coda."""
        if self._karaoke_flow is not None:
            self._karaoke_flow.queue_play(queue_id)

    def _on_next_singer(self) -> None:
        """Annuncia il prossimo cantante senza avviare il brano."""
        if self._karaoke_flow is not None:
            self._karaoke_flow.advance_next()

    def _on_reorder(self, queue_id: int, new_position: int) -> None:
        """Riordina elementi coda."""
        if self._queue is not None:
            self._queue.reorder(queue_id, new_position)

    def _on_remove(self, queue_id: int) -> None:
        """Rimuove un elemento dalla coda."""
        if self._queue is not None:
            self._queue.remove(queue_id)

    def _on_requeue(self, queue_id: int) -> None:
        """Rimette in coda un brano già eseguito (torna 'waiting', va in fondo)."""
        if self._queue is not None:
            self._queue.requeue(queue_id)

    def _on_set_start_here(self) -> None:
        """Salva la posizione corrente come punto di inizio del brano locale."""
        if self._karaoke_flow is None:
            return
        position = self._karaoke_flow.save_start_offset_here()
        if position is None:
            return
        track = self._karaoke_flow.current_playing_track()
        if track is None:
            return
        minutes, seconds = divmod(int(position), 60)
        QMessageBox.information(
            self,
            "Punto di inizio salvato",
            f"«{clean_title(track.get('title', ''))}» partirà da {minutes}:{seconds:02d}.",
        )

    def _on_flow_track_failed(self, track: dict, reason: str) -> None:
        """Mostra un avviso quando un brano non è riproducibile."""
        title = clean_title(track.get("title", "")) or track.get("title", "brano")
        QMessageBox.warning(
            self,
            "Riproduzione non riuscita",
            f"Impossibile riprodurre «{title}».\n\n{reason}",
        )

    def _on_download_progress(self, youtube_id: str, _percent: int) -> None:
        """Aggiorna badge download nei risultati."""
        self._search_widget.mark_downloading(youtube_id)

    def _on_download_complete(self, youtube_id: str, track_dict: dict) -> None:
        """Aggiorna coda e libreria quando un download termina."""
        if self._queue is not None:
            self._queue_widget.set_queue(self._queue.get_queue())
        self._on_library_refresh()
        if youtube_id == self._pending_filler_youtube_id:
            self._pending_filler_youtube_id = None
            local_path = track_dict.get("local_path") or ""
            if local_path:
                self._apply_filler_track(local_path, clean_title(track_dict.get("title", "")))
