"""Finestra consolle DJ separata dal pannello karaoke."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

import config
from ui.dj_library_widget import DjLibraryWidget
from ui.dj_playlist_widget import DjPlaylistWidget
from ui.dj_runtime_widget import DjRuntimeWidget
from ui.dj_search_widget import DjSearchWidget

if TYPE_CHECKING:
    from services.app_mode_service import AppModeService
    from services.dj_playback_flow import DjPlaybackFlow
    from services.dj_runtime_service import DjRuntimeService
    from services.download_service import DownloadService
    from services.library_service import LibraryService
    from services.playlist_service import PlaylistService
    from services.player_service import PlayerService
    from services.search_service import SearchService

logger = logging.getLogger(__name__)


class DjConsoleWindow(QWidget):
    """Consolle DJ autonoma: runtime, libreria, playlist e ricerca."""

    def __init__(
        self,
        app_mode_service: "AppModeService",
        dj_runtime_service: "DjRuntimeService",
        dj_playback_flow: "DjPlaybackFlow",
        library_service: "LibraryService",
        playlist_service: "PlaylistService",
        dj_search_service: "SearchService",
        download_service: "DownloadService",
        player_service: "PlayerService | None" = None,
    ) -> None:
        """Costruisce la finestra DJ e collega i service condivisi."""
        super().__init__(flags=Qt.WindowType.Window)
        self._app_mode = app_mode_service
        self._runtime = dj_runtime_service
        self._dj_flow = dj_playback_flow
        self._library = library_service
        self._playlist = playlist_service
        self._dj_search = dj_search_service
        self._download = download_service
        self._player = player_service
        self._settings = QSettings(config.APP_NAME, config.APP_NAME)
        self._last_search_query = ""
        self._last_yt_limit = config.YT_SEARCH_LIMIT
        self.setWindowTitle("Consolle DJ — KaraokeManager")
        self.resize(config.DJ_CONSOLE_DEFAULT_WIDTH, config.DJ_CONSOLE_DEFAULT_HEIGHT)
        self._load_stylesheet()
        self._build_ui()
        self._connect_signals()
        self._sync_mode_pills(self._app_mode.get_mode())
        self._update_player_controls()
        self._refresh_library()
        self._refresh_playlists()

    def _load_stylesheet(self) -> None:
        """Carica QSS da assets."""
        qss_path = Path(__file__).resolve().parent.parent / "assets" / "style.qss"
        if qss_path.exists():
            self.setStyleSheet(qss_path.read_text(encoding="utf-8"))

    def _build_ui(self) -> None:
        """Assembla header e tab Runtime / Libreria / Playlist / Ricerca."""
        root = QVBoxLayout(self)
        root.addLayout(self._build_header())

        self._tabs = QTabWidget()
        self._runtime_widget = DjRuntimeWidget(self._runtime)
        self._library_widget = DjLibraryWidget()
        self._playlist_widget = DjPlaylistWidget()
        self._search_widget = DjSearchWidget()
        self._tabs.addTab(self._runtime_widget, "Runtime")
        self._tabs.addTab(self._library_widget, "Libreria")
        self._tabs.addTab(self._playlist_widget, "Playlist")
        self._tabs.addTab(self._search_widget, "Ricerca")
        root.addWidget(self._tabs)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #9a9aa6;")
        root.addWidget(self._status_label)

    def _build_header(self) -> QHBoxLayout:
        """Barra superiore: pill modalità, mini player e chiudi."""
        bar = QHBoxLayout()
        self._mode_karaoke_btn = QPushButton("Karaoke")
        self._mode_karaoke_btn.setObjectName("modeToggle")
        self._mode_karaoke_btn.setCheckable(True)
        self._mode_karaoke_btn.clicked.connect(lambda: self._app_mode.set_mode("karaoke"))
        bar.addWidget(self._mode_karaoke_btn)

        self._mode_dj_btn = QPushButton("DJ")
        self._mode_dj_btn.setObjectName("modeToggle")
        self._mode_dj_btn.setCheckable(True)
        self._mode_dj_btn.clicked.connect(lambda: self._app_mode.set_mode("dj"))
        bar.addWidget(self._mode_dj_btn)

        bar.addSpacing(16)
        self._track_title = QLabel("Nessun brano")
        self._track_title.setStyleSheet("font-weight: 600;")
        bar.addWidget(self._track_title)
        self._track_artist = QLabel("")
        self._track_artist.setStyleSheet("color: #9a9aa6;")
        bar.addWidget(self._track_artist)

        bar.addStretch()

        self._mini_play_btn = QPushButton("Play/Pause")
        self._mini_play_btn.clicked.connect(self._dj_flow.play_pause)
        bar.addWidget(self._mini_play_btn)
        self._mini_skip_btn = QPushButton("Skip")
        self._mini_skip_btn.clicked.connect(self._dj_flow.skip)
        bar.addWidget(self._mini_skip_btn)

        self._mini_stop_btn = QPushButton("Stop")
        self._mini_stop_btn.clicked.connect(self._dj_flow.stop)
        bar.addWidget(self._mini_stop_btn)

        close_btn = QPushButton("Chiudi")
        close_btn.setObjectName("secondaryButton")
        close_btn.clicked.connect(self.hide)
        bar.addWidget(close_btn)
        return bar

    def _connect_signals(self) -> None:
        """Collega segnali UI ↔ service condivisi."""
        self._app_mode.mode_changed.connect(self._sync_mode_pills)
        self._app_mode.mode_changed.connect(self._update_player_controls)

        self._runtime_widget.save_as_playlist_requested.connect(self._on_save_runtime_as_playlist)

        self._library_widget.refresh_requested.connect(self._refresh_library)
        self._library_widget.import_paths_selected.connect(self._on_import_paths)
        self._library_widget.scan_requested.connect(self._on_scan_library)
        self._library_widget.track_selected.connect(self._add_track_to_runtime)

        self._playlist_widget.create_requested.connect(self._on_playlist_create)
        self._playlist_widget.delete_requested.connect(self._on_playlist_delete)
        self._playlist_widget.playlist_changed.connect(self._on_playlist_load_tracks)
        self._playlist_widget.load_to_runtime_requested.connect(self._on_playlist_load_runtime)
        self._playlist_widget.track_selected.connect(self._add_track_to_runtime)
        self._playlist_widget.remove_track_requested.connect(self._on_playlist_remove_track)

        self._search_widget.search_requested.connect(self._on_search_requested)
        self._search_widget.track_selected.connect(self._on_search_track_selected)
        self._dj_search.results_ready.connect(self._on_search_results)

        try:
            self._download.download_progress.disconnect(self._on_download_progress)
            self._download.download_complete.disconnect(self._on_download_complete)
        except TypeError:
            pass
        self._download.download_progress.connect(self._on_download_progress)
        self._download.download_complete.connect(self._on_download_complete)

        try:
            self._dj_flow.track_info_updated.disconnect(self._on_track_info_updated)
            self._dj_flow.status_message.disconnect(self._on_status_message)
        except TypeError:
            pass
        self._dj_flow.track_info_updated.connect(self._on_track_info_updated)
        self._dj_flow.status_message.connect(self._on_status_message)

    def set_player(self, player_service: "PlayerService | None") -> None:
        """Conserva il riferimento al player; la UI DJ usa i segnali del flow."""
        self._player = player_service

    def showEvent(self, event) -> None:
        """Ripristina geometria salvata al primo show."""
        super().showEvent(event)
        geometry = self._settings.value(config.DJ_CONSOLE_SETTINGS_GEOMETRY_KEY)
        if geometry is not None:
            self.restoreGeometry(geometry)

    def hideEvent(self, event) -> None:
        """Salva geometria quando la finestra viene nascosta."""
        self._settings.setValue(
            config.DJ_CONSOLE_SETTINGS_GEOMETRY_KEY,
            self.saveGeometry(),
        )
        super().hideEvent(event)

    def _sync_mode_pills(self, mode: str) -> None:
        """Aggiorna lo stile delle pill Karaoke/DJ."""
        karaoke_active = mode == "karaoke"
        self._mode_karaoke_btn.setChecked(karaoke_active)
        self._mode_dj_btn.setChecked(not karaoke_active)
        self._mode_karaoke_btn.setObjectName("modeToggleActive" if karaoke_active else "modeToggle")
        self._mode_dj_btn.setObjectName("modeToggleActive" if not karaoke_active else "modeToggle")
        self._mode_karaoke_btn.style().unpolish(self._mode_karaoke_btn)
        self._mode_karaoke_btn.style().polish(self._mode_karaoke_btn)
        self._mode_dj_btn.style().unpolish(self._mode_dj_btn)
        self._mode_dj_btn.style().polish(self._mode_dj_btn)

    def _update_player_controls(self, _mode: str | None = None) -> None:
        """Abilita i controlli mini player solo in modalità DJ."""
        dj_active = self._app_mode.get_mode() == "dj"
        self._mini_play_btn.setEnabled(dj_active)
        self._mini_skip_btn.setEnabled(dj_active)
        self._mini_stop_btn.setEnabled(dj_active)
        if not dj_active:
            self._track_title.setText("Nessun brano")
            self._track_artist.setText("(modalità karaoke attiva)")

    def _refresh_library(self, sort: str = "") -> None:
        """Ricarica la libreria DJ."""
        criterion = sort or self._library_widget.current_sort()
        self._library_widget.set_tracks(self._library.list_tracks(criterion, track_type="dj"))

    def _refresh_playlists(self) -> None:
        """Ricarica l'elenco playlist DJ."""
        self._playlist_widget.set_playlists(self._playlist.list_playlists(mode="dj"))

    def _add_track_to_runtime(self, track: dict) -> None:
        """Aggiunge un brano al runtime in memoria."""
        self._runtime.add_track(track)
        self._tabs.setCurrentWidget(self._runtime_widget)
        logger.info("Runtime DJ: aggiunto %s", track.get("title"))

    def _on_import_paths(self, paths: list) -> None:
        """Importa file locali come brani DJ (path originale, senza copia)."""
        imported = self._library.import_files(paths, track_type="dj")
        self._refresh_library()
        logger.info("Import DJ: %d nuovi brani", len(imported))

    def _on_scan_library(self) -> None:
        """Registra i file presenti in DJ_MEDIA_DIR non ancora in catalogo."""
        imported = self._library.scan_media_dir(track_type="dj")
        self._refresh_library()
        logger.info("Scan DJ_MEDIA_DIR: %d nuovi brani", len(imported))

    def _on_search_requested(self, query: str, yt_limit: int) -> None:
        """Avvia ricerca DJ tramite SearchService dedicato."""
        self._last_search_query = query
        self._last_yt_limit = yt_limit
        self._dj_search.search(query, yt_limit)

    def _on_search_results(self, results: list[dict]) -> None:
        """Mostra i risultati e abilita load more se applicabile."""
        yt_count = sum(1 for track in results if track.get("source") == "youtube")
        can_load_more = bool(self._last_search_query) and yt_count >= self._last_yt_limit
        self._search_widget.set_results(results, can_load_more)

    def _on_search_track_selected(self, track: dict) -> None:
        """Aggiunge al runtime e avvia download YouTube se necessario."""
        self._add_track_to_runtime(track)
        self._dj_search.trigger_download_for_track(track)

    def _on_download_progress(self, youtube_id: str, _percent: int) -> None:
        """Aggiorna badge download nei risultati ricerca DJ."""
        self._search_widget.mark_downloading(youtube_id)

    def _on_download_complete(self, youtube_id: str, track_dict: dict) -> None:
        """Aggiorna libreria DJ al termine di un download."""
        if track_dict.get("track_type") == "dj":
            self._refresh_library()
            logger.debug("Download DJ completato: %s", youtube_id)

    def _on_playlist_create(self, name: str) -> None:
        """Crea una nuova playlist DJ."""
        self._playlist.create(name, mode="dj")
        self._refresh_playlists()

    def _on_playlist_delete(self, playlist_id: int) -> None:
        """Elimina una playlist DJ."""
        self._playlist.delete(playlist_id)
        self._refresh_playlists()

    def _on_playlist_load_tracks(self, playlist_id: int) -> None:
        """Carica i brani della playlist selezionata."""
        self._playlist_widget.set_tracks(self._playlist.get_tracks(playlist_id))

    def _on_playlist_load_runtime(self, playlist_id: int) -> None:
        """Sostituisce il runtime con i brani della playlist DJ."""
        tracks = self._playlist.get_tracks(playlist_id)
        self._runtime.load_tracks(tracks)
        self._tabs.setCurrentWidget(self._runtime_widget)
        logger.info("Runtime DJ caricato da playlist id=%s (%d brani)", playlist_id, len(tracks))

    def _on_playlist_remove_track(self, playlist_id: int, track_id: int) -> None:
        """Rimuove un brano dalla playlist DJ e ricarica la lista."""
        self._playlist.remove_track(playlist_id, track_id)
        self._on_playlist_load_tracks(playlist_id)

    def _on_save_runtime_as_playlist(self) -> None:
        """Salva la coda runtime corrente come nuova playlist DJ."""
        tracks = self._runtime.get_runtime_queue()
        if not tracks:
            return
        name, ok = QInputDialog.getText(
            self,
            "Salva come playlist",
            "Nome della playlist DJ:",
        )
        if not ok or not name.strip():
            return
        playlist_id = self._playlist.create(name.strip(), mode="dj")
        added = 0
        for track in tracks:
            track_id = track.get("id")
            if track_id is not None and self._playlist.add_track(playlist_id, track_id):
                added += 1
        self._refresh_playlists()
        logger.info("Runtime salvato come playlist '%s' (%d brani)", name.strip(), added)

    def _on_track_info_updated(self, title: str, artist: object) -> None:
        """Aggiorna il mini player dai segnali del flow DJ."""
        if self._app_mode.get_mode() != "dj":
            return
        self._track_title.setText(title or "Nessun brano")
        self._track_artist.setText(str(artist) if artist else "")

    def _on_status_message(self, message: str) -> None:
        """Mostra un messaggio breve nella barra di stato DJ."""
        self._status_label.setText(message)
