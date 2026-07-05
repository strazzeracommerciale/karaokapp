"""Finestra Preparazione: libreria, ricerca, scalette e strumenti batch."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QSettings, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QInputDialog,
    QMenu,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from collections.abc import Callable

import config
from engines.metadata_refresh_engine import (
    MetadataRefreshEngine,
    MetadataRefreshOptions,
    deserialize_outcomes,
)
from services.library_transfer_service import LibraryTransferService
from ui.library_widget import LibraryWidget
from ui.metadata_refresh_review_dialog import MetadataRefreshReviewDialog
from ui.prep_playback_window import PrepPlaybackWindow
from ui.prep_playlist_widget import PrepPlaylistWidget
from ui.prep_search_panel import PrepSearchPanel
from ui.track_metadata_dialog import TrackMetadataDialog
from utils.text import clean_title, format_track_display

if TYPE_CHECKING:
    from services.download_service import DownloadService
    from services.dj_player_service import DjPlayerService
    from services.library_service import LibraryService
    from services.playlist_service import PlaylistService
    from services.search_service import SearchService

logger = logging.getLogger(__name__)


class PrepWindow(QWidget):
    """Gestione archivio e scalette prima/dopo la serata."""

    library_changed = pyqtSignal()

    def __init__(
        self,
        library_service: "LibraryService",
        playlist_service: "PlaylistService",
        metadata_refresh_engine: MetadataRefreshEngine | None = None,
        search_service: "SearchService | None" = None,
        download_service: "DownloadService | None" = None,
        transfer_service: LibraryTransferService | None = None,
        player_service: "DjPlayerService | None" = None,
    ) -> None:
        super().__init__(flags=Qt.WindowType.Window)
        self._library = library_service
        self._playlist = playlist_service
        self._metadata_engine = metadata_refresh_engine
        self._search = search_service
        self._download = download_service
        self._transfer = transfer_service
        self._player = player_service
        self._bind_vlc_output: Callable | None = None
        self._current_playing_track: dict | None = None
        self._settings = QSettings(config.APP_NAME, config.APP_NAME)
        self._last_query = ""
        self._yt_limit = config.YT_SEARCH_LIMIT
        self.setWindowTitle("Preparazione — KaraokeManager")
        self.resize(config.PREP_WINDOW_DEFAULT_WIDTH, config.PREP_WINDOW_DEFAULT_HEIGHT)
        self._build_ui()
        self._playback_window = PrepPlaybackWindow()
        self._playback_window.closed_by_user.connect(self._on_stop)
        self._connect_signals()
        self._refresh_library()
        self._refresh_playlists()
        self._sync_metadata_controls()
        if player_service is not None:
            self.set_player(player_service)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.addLayout(self._build_tools_row())

        self._tabs = QTabWidget()
        self._library_widget = LibraryWidget(prep_mode=True)
        self._search_panel = PrepSearchPanel()
        self._playlist_widget = PrepPlaylistWidget()
        self._tabs.addTab(self._library_widget, "Libreria")
        self._tabs.addTab(self._search_panel, "Ricerca")
        self._tabs.addTab(self._playlist_widget, "Playlist")
        root.addWidget(self._tabs, stretch=1)

        self._status_label = QLabel("")
        self._status_label.setObjectName("mutedLabel")
        root.addWidget(self._status_label)

    def playback_window(self) -> PrepPlaybackWindow:
        """Finestra di ascolto separata (embed VLC)."""
        return self._playback_window

    def configure_playback(self, bind_output: Callable) -> None:
        """Registra il bind VLC da invocare quando la finestra di ascolto è visibile."""
        self._bind_vlc_output = bind_output
        self._playback_window.set_vlc_output_rebind(bind_output)

    def _build_tools_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel("Strumenti"))
        self._metadata_refresh_btn = QPushButton("Aggiorna metadati e rinomina…")
        self._metadata_refresh_btn.setObjectName("secondaryButton")
        self._metadata_refresh_btn.clicked.connect(self._on_metadata_refresh_clicked)
        row.addWidget(self._metadata_refresh_btn)
        self._export_btn = QPushButton("Esporta libreria…")
        self._export_btn.setObjectName("secondaryButton")
        self._export_btn.clicked.connect(self._on_export_library)
        row.addWidget(self._export_btn)
        self._import_btn = QPushButton("Importa libreria…")
        self._import_btn.setObjectName("secondaryButton")
        self._import_btn.clicked.connect(self._on_import_library)
        row.addWidget(self._import_btn)
        row.addStretch()
        return row

    def set_player(self, player_service: "DjPlayerService") -> None:
        """Collega il player isolato e i controlli nella finestra di ascolto."""
        self._player = player_service
        self._connect_player_signals()

    def _connect_player_signals(self) -> None:
        if self._player is None:
            return
        player = self._player
        controls = self._playback_window.player_widget()
        for signal, slot in (
            (player.track_started, self._on_track_started),
            (player.track_failed, self._on_track_failed),
            (player.track_ended, self._on_playback_ended),
            (player.position_updated, controls.update_position),
        ):
            try:
                signal.disconnect(slot)
            except TypeError:
                pass
            signal.connect(slot)
        player.set_volume(controls.volume())
        controls.play_pause_clicked.connect(self._on_play_pause)
        controls.stop_clicked.connect(self._on_stop)
        controls.seek_requested.connect(self._on_seek)
        controls.volume_changed.connect(self._on_volume)
        controls.set_start_here_clicked.connect(self._on_set_start_here)

    def _connect_signals(self) -> None:
        self._library_widget.refresh_requested.connect(self._on_library_refresh)
        self._library_widget.add_to_playlist_requested.connect(self._on_add_to_playlist)
        self._library_widget.delete_requested.connect(self._on_library_delete_requested)
        self._library_widget.edit_metadata_requested.connect(self._on_library_edit_metadata)
        self._library_widget.track_selected.connect(self._play_track)

        search_widget = self._search_panel.search_widget()
        self._search_panel.connect_debounce(self._dispatch_search)
        search_widget.track_selected.connect(self._play_track)
        search_widget.save_to_library_requested.connect(self._on_save_to_library)
        search_widget.add_to_playlist_requested.connect(self._on_add_to_playlist)
        search_widget.load_more_requested.connect(self._on_load_more)

        self._playlist_widget.create_requested.connect(self._on_playlist_create)
        self._playlist_widget.delete_requested.connect(self._on_playlist_delete)
        self._playlist_widget.playlist_changed.connect(self._on_playlist_load_tracks)
        self._playlist_widget.remove_track_requested.connect(self._on_playlist_remove_track)
        self._playlist_widget.add_track_requested.connect(self._on_playlist_add_track)
        self._playlist_widget.play_track_requested.connect(self._play_track)

        if self._metadata_engine is not None:
            self._metadata_engine.started.connect(self._on_metadata_refresh_started)
            self._metadata_engine.progress.connect(self._on_metadata_refresh_progress)
            self._metadata_engine.finished.connect(self._on_metadata_refresh_finished)
            self._metadata_engine.error.connect(self._on_metadata_refresh_error)
            self._metadata_engine.busy_changed.connect(self._sync_metadata_controls)

        if self._search is not None:
            self._search.results_ready.connect(self._on_results_ready)
        if self._download is not None:
            self._download.download_progress.connect(self._on_download_progress)
            self._download.download_complete.connect(self._on_download_complete)

    def _play_track(self, track: dict) -> None:
        """Riproduce un brano aprendo la finestra di ascolto dedicata."""
        if self._player is None:
            QMessageBox.information(
                self,
                "Ascolto",
                "Riproduzione non disponibile in questa modalità.",
            )
            return
        self._playback_window.show_for_track(track)
        app = QApplication.instance()
        if app is not None:
            app.processEvents()
        if self._bind_vlc_output is not None:
            self._bind_vlc_output(self._playback_window.video_output_widget())
            if app is not None:
                app.processEvents()
        # Un ciclo eventi dopo show+bind: su Windows l'HWND deve essere stabile prima del play.
        QTimer.singleShot(0, lambda: self._start_prep_playback(track))

    def _start_prep_playback(self, track: dict) -> None:
        """Avvia la riproduzione dopo che la finestra di ascolto è pronta."""
        if self._player is None:
            return
        self._player.play_track(track)
        for delay_ms in (50, 200, 500):
            QTimer.singleShot(delay_ms, self._sync_prep_audio)

    def _sync_prep_audio(self) -> None:
        """Riapplica volume e unmute dopo l'avvio."""
        if self._player is None:
            return
        volume = self._playback_window.player_widget().volume()
        self._player.set_volume(volume)

    def _on_track_started(self, track: dict) -> None:
        """Mantiene visibile la finestra di ascolto durante la riproduzione."""
        self._current_playing_track = track
        self._playback_window.show_for_track(track)
        local_path = track.get("local_path") or ""
        self._playback_window.player_widget().set_start_save_enabled(bool(local_path))
        self._sync_prep_audio()

    def _on_set_start_here(self) -> None:
        """Salva la posizione corrente come punto di inizio del brano locale."""
        track = self._current_playing_track
        if track is None or track.get("id") is None or self._player is None:
            return
        local_path = track.get("local_path") or ""
        if not local_path:
            return
        position = float(self._player.get_state().get("position", 0.0))
        self._library.set_start_offset(track["id"], position)
        track["start_offset_sec"] = position
        minutes, seconds = divmod(int(position), 60)
        QMessageBox.information(
            self,
            "Punto di inizio salvato",
            f"«{clean_title(track.get('title', ''))}» partirà da {minutes}:{seconds:02d}.",
        )

    def _on_playback_ended(self) -> None:
        """Chiude la finestra di ascolto a fine brano."""
        self._current_playing_track = None
        self._playback_window.close_playback()

    def _on_track_failed(self, track: dict, reason: str) -> None:
        self._current_playing_track = None
        self._playback_window.close_playback()
        QMessageBox.warning(
            self,
            "Riproduzione non riuscita",
            f"Impossibile riprodurre «{format_track_display(track.get('title', ''), track.get('artist'))}».\n\n{reason}",
        )

    def _on_play_pause(self) -> None:
        if self._player is not None:
            self._player.pause_resume()

    def _on_stop(self) -> None:
        if self._player is not None:
            self._player.stop()
        self._current_playing_track = None
        self._playback_window.close_playback()

    def _on_seek(self, seconds: float) -> None:
        if self._player is not None:
            self._player.seek(seconds)

    def _on_volume(self, value: int) -> None:
        if self._player is not None:
            self._player.set_volume(value)

    def _dispatch_search(self) -> None:
        query = self._search_panel.pending_query()
        self._last_query = query
        self._yt_limit = config.YT_SEARCH_LIMIT
        self._search_panel.set_last_query(query)
        if not query:
            self._search_panel.search_widget().set_results([])
        elif self._search is not None:
            self._search.search(query, self._yt_limit)
        else:
            self._search_panel.search_widget().set_results([])

    def _on_results_ready(self, results: list[dict]) -> None:
        yt_count = sum(1 for track in results if track.get("source") == "youtube")
        can_load_more = bool(self._last_query) and yt_count >= self._yt_limit
        self._search_panel.search_widget().set_results(results, can_load_more)

    def _on_load_more(self) -> None:
        if self._search is None or not self._last_query:
            return
        self._yt_limit += config.YT_SEARCH_LIMIT
        self._search_panel.search_widget().set_load_more_busy()
        self._search.search(self._last_query, self._yt_limit)

    def _on_save_to_library(self, track: dict) -> None:
        if self._search is not None and track.get("source") == "youtube":
            self._search.trigger_download_for_track(track)

    def _on_download_progress(self, youtube_id: str, _percent: int) -> None:
        self._search_panel.search_widget().mark_downloading(youtube_id)

    def _on_download_complete(self, _youtube_id: str, _track_dict: dict) -> None:
        self._refresh_library()
        self._refresh_playlists()
        self.library_changed.emit()
        if self._last_query:
            self._dispatch_search()

    def _on_export_library(self) -> None:
        if self._transfer is None:
            QMessageBox.information(self, "Esporta libreria", "Funzione non disponibile.")
            return
        dest = QFileDialog.getExistingDirectory(
            self,
            "Esporta libreria — seleziona cartella destinazione (es. chiavetta USB)",
            "",
        )
        if not dest:
            return
        try:
            result = self._transfer.export_library(Path(dest))
        except Exception as exc:
            logger.exception("Esportazione libreria fallita")
            QMessageBox.critical(self, "Esporta libreria", f"Esportazione non riuscita:\n\n{exc}")
            return
        QMessageBox.information(
            self,
            "Esporta libreria",
            "Esportazione completata.\n\n"
            f"Cartella: {result['bundle_path']}\n"
            f"Brani in catalogo: {result['tracks']}\n"
            f"File media copiati: {result['files']}",
        )

    def _on_import_library(self) -> None:
        if self._transfer is None:
            QMessageBox.information(self, "Importa libreria", "Funzione non disponibile.")
            return
        source = QFileDialog.getExistingDirectory(
            self,
            "Importa libreria — seleziona cartella «KaraokeManager_libreria» esportata",
            "",
        )
        if not source:
            return
        reply = QMessageBox.question(
            self,
            "Importa libreria",
            "Integrare i brani e le scalette dal bundle selezionato?\n\n"
            "I duplicati (stesso id YouTube) verranno saltati. "
            "Il catalogo esistente non verrà sovrascritto.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            stats = self._transfer.import_library(Path(source))
        except Exception as exc:
            logger.exception("Importazione libreria fallita")
            QMessageBox.critical(self, "Importa libreria", f"Importazione non riuscita:\n\n{exc}")
            return
        self._refresh_library()
        self._refresh_playlists()
        self.library_changed.emit()
        QMessageBox.information(
            self,
            "Importa libreria",
            "Importazione completata.\n\n"
            f"Brani aggiunti: {stats['tracks_added']}\n"
            f"Brani saltati (duplicati): {stats['tracks_skipped']}\n"
            f"File copiati: {stats['files_copied']}\n"
            f"Scalette create: {stats['playlists_created']}\n"
            f"Brani aggiunti alle scalette: {stats['playlist_tracks_added']}",
        )

    def _sync_metadata_controls(self) -> None:
        engine = self._metadata_engine
        available = engine is not None
        busy = engine.is_busy() if available else False
        self._metadata_refresh_btn.setEnabled(available and not busy)

    def _on_metadata_refresh_clicked(self) -> None:
        if self._metadata_engine is None:
            QMessageBox.information(
                self,
                "Aggiornamento metadati",
                "Funzione non disponibile in questa modalità.",
            )
            return
        if self._metadata_engine.is_busy():
            return
        reply = QMessageBox.question(
            self,
            "Aggiorna metadati e rinomina",
            "Elaborare i brani karaoke non ancora confermati?\n\n"
            "Al termine potrai rivedere artista, titolo e nome file prima di confermare.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        options = MetadataRefreshOptions(
            rename_files=True,
            parse_only=False,
            dry_run=False,
            track_type="karaoke",
            skip_confirmed=True,
        )
        if not self._metadata_engine.start(options):
            QMessageBox.information(self, "Aggiornamento metadati", "Un aggiornamento è già in corso.")

    def _on_metadata_refresh_started(self) -> None:
        self._status_label.setText("Aggiornamento metadati in corso…")

    def _on_metadata_refresh_progress(self, current: int, total: int, label: str) -> None:
        self._status_label.setText(f"Metadati: {current}/{total} — {label}")

    def _on_metadata_refresh_finished(self, stats: dict) -> None:
        self._refresh_library()
        self._refresh_playlists()
        self.library_changed.emit()
        self._status_label.setText(
            "Metadati completati: "
            f"{stats.get('metadata_updated', 0)} aggiornati, "
            f"{stats.get('files_renamed', 0)} rinominati, "
            f"{stats.get('unchanged', 0)} invariati, "
            f"{stats.get('skipped', 0)} saltati, "
            f"{stats.get('errors', 0)} errori."
        )
        outcomes = deserialize_outcomes(stats.get("outcomes") or [])
        if outcomes:
            dialog = MetadataRefreshReviewDialog(
                outcomes,
                confirm_callback=self._library.confirm_metadata,
                edit_callback=self._library.update_track_metadata,
                parent=self,
            )
            dialog.exec()
            self._refresh_library()
            self._refresh_playlists()
            self.library_changed.emit()
        if stats.get("errors"):
            QMessageBox.warning(
                self,
                "Aggiornamento metadati",
                f"Completato con {stats['errors']} errori. Controlla il log per i dettagli.",
            )

    def _on_metadata_refresh_error(self, message: str) -> None:
        self._status_label.setText("Errore aggiornamento metadati.")
        QMessageBox.critical(self, "Aggiornamento metadati", f"Operazione interrotta:\n\n{message}")

    def _on_library_refresh(self, sort: str = "") -> None:
        criterion = sort or self._library_widget.current_sort()
        tracks = self._library.list_tracks(criterion)
        self._library_widget.set_tracks(tracks)
        self._playlist_widget.set_library_tracks(tracks)

    def _refresh_library(self) -> None:
        self._on_library_refresh()

    def _refresh_playlists(self) -> None:
        self._playlist_widget.set_playlists(self._playlist.list_playlists(mode="karaoke"))

    def _on_playlist_load_tracks(self, playlist_id: int) -> None:
        tracks = self._playlist.get_tracks(playlist_id)
        self._playlist_widget.set_playlist_tracks(tracks)
        self._playlist_widget.set_library_tracks(self._library.list_tracks())

    def _on_playlist_create(self, name: str) -> None:
        self._playlist.create(name)
        self._refresh_playlists()
        self.library_changed.emit()

    def _on_playlist_delete(self, playlist_id: int) -> None:
        self._playlist.delete(playlist_id)
        self._refresh_playlists()
        self.library_changed.emit()

    def _on_playlist_remove_track(self, playlist_id: int, track_id: int) -> None:
        self._playlist.remove_track(playlist_id, track_id)
        self._on_playlist_load_tracks(playlist_id)
        self.library_changed.emit()

    def _on_playlist_add_track(self, playlist_id: int, track_id: int) -> None:
        added = self._playlist.add_track(playlist_id, track_id)
        self._on_playlist_load_tracks(playlist_id)
        if not added:
            self._status_label.setText("Brano già presente in scaletta.")
        self.library_changed.emit()

    def _on_add_to_playlist(self, track: dict) -> None:
        if not track.get("id"):
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
        self._playlist.add_track(playlist_id, track["id"])
        self._refresh_playlists()
        current_id = self._playlist_widget.current_playlist_id()
        if current_id == playlist_id:
            self._on_playlist_load_tracks(playlist_id)
        self.library_changed.emit()

    def _on_library_delete_requested(self, track: dict) -> None:
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
            self._on_library_refresh()
            self._refresh_playlists()
            self.library_changed.emit()

    def _on_library_edit_metadata(self, track: dict) -> None:
        track_id = track.get("id")
        if track_id is None:
            return
        dialog = TrackMetadataDialog(
            track.get("title", ""),
            track.get("artist"),
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        title = dialog.title_value()
        if not title:
            QMessageBox.warning(self, "Modifica brano", "Il titolo non può essere vuoto.")
            return
        if self._library.update_track_metadata(track_id, title, dialog.artist_value()):
            self._on_library_refresh()
            playlist_id = self._playlist_widget.current_playlist_id()
            if playlist_id is not None:
                self._on_playlist_load_tracks(playlist_id)
            self.library_changed.emit()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        geometry = self._settings.value(config.PREP_WINDOW_SETTINGS_GEOMETRY_KEY)
        if geometry:
            self.restoreGeometry(geometry)
        self._refresh_library()
        self._refresh_playlists()

    def closeEvent(self, event) -> None:
        self._settings.setValue(config.PREP_WINDOW_SETTINGS_GEOMETRY_KEY, self.saveGeometry())
        if self._player is not None:
            self._player.stop()
        self._playback_window.close_playback()
        super().closeEvent(event)

    def hideEvent(self, event) -> None:
        self._settings.setValue(config.PREP_WINDOW_SETTINGS_GEOMETRY_KEY, self.saveGeometry())
        if self._player is not None:
            self._player.stop()
        self._playback_window.close_playback()
        super().hideEvent(event)
