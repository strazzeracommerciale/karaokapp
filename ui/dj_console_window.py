"""Finestra consolle DJ separata dal pannello karaoke."""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from PyQt6.QtCore import QSettings, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

import config
from ui.dj_library_widget import DjLibraryWidget
from ui.dj_playlist_widget import DjPlaylistWidget
from ui.dj_runtime_widget import DjRuntimeWidget
from ui.dj_search_widget import DjSearchWidget
from ui.player_widget import PlayerWidget
from ui.video_output_widget import VideoOutputWidget
from utils.text import clean_title

if TYPE_CHECKING:
    from services.app_mode_service import AppModeService
    from services.dj_playback_flow import DjPlaybackFlow
    from services.dj_player_service import DjPlayerService
    from services.dj_runtime_service import DjRuntimeService
    from services.download_service import DownloadService
    from services.library_service import LibraryService
    from services.playlist_service import PlaylistService
    from services.search_service import SearchService

logger = logging.getLogger(__name__)


class DjConsoleWindow(QWidget):
    """Consolle DJ autonoma con player video dedicato."""

    dj_filler_track_requested = pyqtSignal(dict)

    def __init__(
        self,
        app_mode_service: "AppModeService",
        dj_runtime_service: "DjRuntimeService",
        dj_playback_flow: "DjPlaybackFlow",
        library_service: "LibraryService",
        playlist_service: "PlaylistService",
        dj_search_service: "SearchService",
        download_service: "DownloadService",
        player_service: "DjPlayerService | None" = None,
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
        self._build_ui()
        self._connect_signals()
        self._sync_mode_pills(self._app_mode.get_mode())
        self._refresh_library()
        self._refresh_playlists()
        if player_service is not None:
            self.set_player(player_service)

    def _build_ui(self) -> None:
        """Assembla player video, controlli e tab."""
        root = QVBoxLayout(self)
        root.addLayout(self._build_header())

        self._video_output = VideoOutputWidget(min_height=180)
        self._player_widget = PlayerWidget()
        self._player_widget.set_start_save_enabled(False)
        for button in self._player_widget.findChildren(QPushButton):
            if button.text() == "Inizia da qui":
                button.setVisible(False)

        self._tabs = QTabWidget()
        self._runtime_widget = DjRuntimeWidget(self._runtime)
        self._library_widget = DjLibraryWidget()
        self._playlist_widget = DjPlaylistWidget()
        self._search_widget = DjSearchWidget()
        self._tabs.addTab(self._runtime_widget, "Runtime")
        self._tabs.addTab(self._library_widget, "Libreria")
        self._tabs.addTab(self._playlist_widget, "Playlist")
        self._tabs.addTab(self._search_widget, "Ricerca")

        bottom_panel = QWidget()
        bottom_layout = QVBoxLayout(bottom_panel)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.addWidget(self._player_widget)
        bottom_layout.addWidget(self._tabs)

        self._main_splitter = QSplitter(Qt.Orientation.Vertical)
        self._main_splitter.addWidget(self._video_output)
        self._main_splitter.addWidget(bottom_panel)
        self._main_splitter.setStretchFactor(0, 2)
        self._main_splitter.setStretchFactor(1, 3)
        root.addWidget(self._main_splitter)

        self._status_label = QLabel("")
        self._status_label.setObjectName("mutedLabel")
        root.addWidget(self._status_label)

    def _build_header(self) -> QHBoxLayout:
        """Barra superiore: pill modalità e chiudi."""
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
        self._track_artist.setObjectName("mutedLabel")
        bar.addWidget(self._track_artist)

        bar.addStretch()

        close_btn = QPushButton("Chiudi")
        close_btn.setObjectName("secondaryButton")
        close_btn.clicked.connect(self.hide)
        bar.addWidget(close_btn)
        return bar

    def _connect_signals(self) -> None:
        """Collega segnali UI ↔ service condivisi."""
        self._app_mode.mode_changed.connect(self._sync_mode_pills)

        self._player_widget.play_pause_clicked.connect(self._dj_flow.play_pause)
        self._player_widget.stop_clicked.connect(self._dj_flow.stop)
        self._player_widget.skip_clicked.connect(self._dj_flow.skip)
        self._player_widget.seek_requested.connect(self._on_seek)
        self._player_widget.volume_changed.connect(self._on_volume)

        self._runtime_widget.save_as_playlist_requested.connect(self._on_save_runtime_as_playlist)

        self._library_widget.refresh_requested.connect(self._refresh_library)
        self._library_widget.import_paths_selected.connect(self._on_import_paths)
        self._library_widget.scan_requested.connect(self._on_scan_library)
        self._library_widget.track_selected.connect(self._add_track_to_runtime)
        self._library_widget.delete_requested.connect(self._on_library_delete_requested)
        self._library_widget.set_as_filler_requested.connect(self.dj_filler_track_requested.emit)

        self._playlist_widget.create_requested.connect(self._on_playlist_create)
        self._playlist_widget.delete_requested.connect(self._on_playlist_delete)
        self._playlist_widget.playlist_changed.connect(self._on_playlist_load_tracks)
        self._playlist_widget.load_to_runtime_requested.connect(self._on_playlist_load_runtime)
        self._playlist_widget.track_selected.connect(self._add_track_to_runtime)
        self._playlist_widget.remove_track_requested.connect(self._on_playlist_remove_track)

        self._search_widget.search_requested.connect(self._on_search_requested)
        self._search_widget.track_selected.connect(self._on_search_track_selected)
        self._search_widget.preview_requested.connect(self._on_search_preview_requested)
        self._search_widget.save_to_library_requested.connect(self._on_save_to_library)
        self._dj_search.results_ready.connect(self._on_search_results)

        self._download.download_progress.connect(self._on_download_progress)
        self._download.download_complete.connect(self._on_download_complete)

        self._dj_flow.track_info_updated.connect(self._on_track_info_updated)
        self._dj_flow.status_message.connect(self._on_status_message)
        self._dj_flow.track_failed.connect(self._on_track_failed)

    def set_player(self, player_service: "DjPlayerService | None") -> None:
        """Collega il DjPlayerService e i segnali verso flow e UI."""
        self._player = player_service
        self._connect_player_signals()

    def video_output_widget(self) -> VideoOutputWidget:
        """Restituisce il widget per embed VLC DJ."""
        return self._video_output

    def set_vlc_output_rebind(self, callback: Callable[[QWidget], None]) -> None:
        """Riaggancia l'output VLC DJ al resize del pannello anteprima."""
        self._video_output.set_vlc_resize_callback(callback)

    def _connect_player_signals(self) -> None:
        """Collega segnali DjPlayerService → flow e widget (idempotente)."""
        if self._player is None:
            return
        player = self._player
        flow = self._dj_flow
        for signal, slot in (
            (player.track_started, flow.on_track_started),
            (player.track_ended, flow.on_track_ended),
            (player.track_failed, flow.on_track_failed),
            (player.position_updated, self._player_widget.update_position),
        ):
            try:
                signal.disconnect(slot)
            except TypeError:
                pass
            signal.connect(slot)
        player.set_volume(self._player_widget.volume())

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

    def _on_seek(self, seconds: float) -> None:
        """Seek nel brano corrente del player DJ."""
        if self._player is not None:
            self._player.seek(seconds)

    def _on_volume(self, value: int) -> None:
        """Aggiorna il volume del player DJ."""
        if self._player is not None:
            self._player.set_volume(value)

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
        """Aggiunge al runtime senza avviare download automatico."""
        self._add_track_to_runtime(track)

    def _on_search_preview_requested(self, track: dict) -> None:
        """Riproduce anteprima stream/local nel player DJ."""
        if self._player is None:
            QMessageBox.information(
                self,
                "Anteprima",
                "Anteprima non disponibile in questa modalità.",
            )
            return
        self._dj_flow.preview_track(track)

    def _on_save_to_library(self, track: dict) -> None:
        """Avvia il download YouTube senza aggiungere al runtime."""
        if track.get("source") == "youtube":
            self._dj_search.trigger_download_for_track(track)

    def _on_library_delete_requested(self, track: dict) -> None:
        """Elimina un brano DJ dalla libreria dopo conferma."""
        track_id = track.get("id")
        if track_id is None:
            return
        title = track.get("title", "brano")
        reply = QMessageBox.question(
            self,
            "Elimina dalla libreria",
            f"Eliminare «{title}» dalla libreria?\n\nIl file verrà rimosso dal disco.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if self._library.delete_track(track_id):
            self._refresh_library()
            self._refresh_playlists()

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
        """Aggiorna l'header dal flow DJ."""
        self._track_title.setText(title or "Nessun brano")
        self._track_artist.setText(str(artist) if artist else "")
        if title == "Nessun brano":
            self._player_widget.reset()
        else:
            self._player_widget.set_track_info(title, artist)

    def _on_status_message(self, message: str) -> None:
        """Mostra un messaggio breve nella barra di stato DJ."""
        self._status_label.setText(message)

    def _on_track_failed(self, track: dict, reason: str) -> None:
        """Avvisa l'operatore se un brano DJ non è riproducibile."""
        title = clean_title(track.get("title", "")) or track.get("title", "brano")
        QMessageBox.warning(
            self,
            "Riproduzione DJ non riuscita",
            f"Impossibile riprodurre «{title}».\n\n{reason}",
        )
