"""Entry point KaraokeManager — bootstrap Qt e wiring moduli."""

import argparse
import logging
import sys
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication

import config
from db import db_core
from engines.display_manager import DisplayManager
from engines.search_engine import SearchEngine
from services.app_mode_service import AppModeService
from services.dj_playback_flow import DjPlaybackFlow
from services.dj_runtime_service import DjRuntimeService
from services.external_display_coordinator import ExternalDisplayCoordinator
from services.library_service import LibraryService
from services.playlist_service import PlaylistService
from services.queue_service import QueueService
from services.search_service import SearchService
from ui.dj_console_window import DjConsoleWindow
from ui.hdmi_window import HdmiWindow
from ui.main_window import MainWindow

logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    """Parsa flag CLI supportati."""
    parser = argparse.ArgumentParser(description="KaraokeManager")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Avvia UI senza VLC né yt-dlp",
    )
    parser.add_argument(
        "--screen",
        type=int,
        default=None,
        help="Forza output HDMI sullo schermo N",
    )
    parser.add_argument(
        "--db",
        type=str,
        default=None,
        help="Percorso custom database SQLite",
    )
    parser.add_argument(
        "--auto-close-ms",
        type=int,
        default=0,
        help="Chiude automaticamente dopo N ms (per smoke test)",
    )
    return parser.parse_args()


def _setup_logging() -> None:
    """Configura logging su stream e file."""
    config.LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(config.LOG_PATH, encoding="utf-8"),
        ],
    )


def _create_session(conn) -> int:
    """Crea una nuova sessione karaoke e ritorna l'id."""
    with conn:
        cursor = conn.execute(
            "INSERT INTO sessions (name, mode) VALUES (?, ?)",
            ("Sessione corrente", "karaoke"),
        )
        return cursor.lastrowid


def _toggle_dj_console(dj_console_window: DjConsoleWindow) -> None:
    """Mostra o nasconde la consolle DJ (toggle show/hide)."""
    if dj_console_window.isVisible():
        dj_console_window.hide()
        return
    dj_console_window.show()
    dj_console_window.raise_()
    dj_console_window.activateWindow()


def _cleanup() -> None:
    """Shutdown pulito: connessione DB."""
    db_core.close()
    logger.info("Shutdown completato")


def main() -> int:
    """Avvia l'applicazione KaraokeManager."""
    args = _parse_args()
    if args.db:
        config.DB_PATH = Path(args.db)
    _setup_logging()
    logger.info("Avvio %s (dry_run=%s)", config.APP_NAME, args.dry_run)

    app = QApplication(sys.argv)

    app.aboutToQuit.connect(_cleanup)

    db_core.migrate()
    conn = db_core.get_conn()
    session_id = _create_session(conn)
    logger.info("Sessione creata: id=%s", session_id)

    queue_service = QueueService(conn, session_id)
    library_service = LibraryService(conn)
    playlist_service = PlaylistService(conn)
    display_manager = DisplayManager()
    app_mode_service = AppModeService()
    dj_runtime_service = DjRuntimeService()
    dj_playback_flow = DjPlaybackFlow(dj_runtime_service, app_mode_service)

    player_service: object | None = None
    search_service: SearchService | None = None
    dj_search_service: SearchService | None = None
    download_service: object | None = None

    main_window = MainWindow(
        app_mode_service,
        player_service=None,
        search_service=None,
        queue_service=queue_service,
        download_service=None,
        library_service=library_service,
        playlist_service=playlist_service,
        dry_run=args.dry_run,
    )
    main_window.resize(1200, 800)

    hdmi_window = HdmiWindow()
    external_coordinator = ExternalDisplayCoordinator(
        display_manager,
        hdmi_window,
        queue_service,
        main_window.set_external_available,
        main_window.set_external_checked,
        player_service=None,
        forced_screen_index=args.screen,
    )

    if not args.dry_run:
        from engines.vlc_engine import VlcEngine
        from engines.ytdlp_engine import YtdlpEngine
        from services.download_service import DownloadService
        from services.filler_service import FillerService
        from services.player_service import PlayerService

        vlc_engine = VlcEngine()
        vlc_engine.set_output_widget(main_window.video_output_widget())
        vlc_engine_secondary = vlc_engine.clone()
        ytdlp_engine = YtdlpEngine()
        search_engine = SearchEngine(conn)
        search_engine_dj = SearchEngine(conn, track_type="dj")
        download_service = DownloadService(ytdlp_engine, conn)
        search_service = SearchService(search_engine, download_service)
        dj_search_service = SearchService(
            search_engine_dj,
            download_service,
            track_type="dj",
        )
        player_service = PlayerService(
            vlc_engine,
            ytdlp_engine,
            vlc_engine_secondary,
        )
        filler_engine = VlcEngine(*config.FILLER_VLC_ARGS)
        filler_service = FillerService(filler_engine)
        main_window.wire_services(player_service, search_service, download_service)
        main_window.set_filler_service(filler_service)
        dj_playback_flow.set_player(player_service)
        dj_playback_flow.set_filler(filler_service)
        external_coordinator.set_player(player_service)
    else:
        search_engine = SearchEngine(conn, enable_youtube=False)
        search_engine_dj = SearchEngine(conn, track_type="dj", enable_youtube=False)
        download_service = _DryRunDownloadService()
        search_service = SearchService(search_engine, download_service)
        dj_search_service = SearchService(
            search_engine_dj,
            download_service,
            track_type="dj",
        )
        main_window.wire_services(None, search_service, None)

    dj_console_window = DjConsoleWindow(
        app_mode_service,
        dj_runtime_service,
        dj_playback_flow,
        library_service,
        playlist_service,
        dj_search_service,
        download_service,
        player_service=player_service,
    )
    main_window.wire_mode_services(dj_playback_flow)
    main_window.dj_console_toggle_requested.connect(
        lambda: _toggle_dj_console(dj_console_window)
    )
    dj_console_window.dj_filler_track_requested.connect(main_window.apply_dj_filler_track)
    if player_service is not None:
        dj_console_window.set_player(player_service)

    main_window.show()

    queue_service.queue_updated.connect(main_window.queue_widget().set_queue)
    external_coordinator.connect_signals(app, main_window.external_toggle_requested)
    external_coordinator.initialize()

    if args.auto_close_ms > 0:
        QTimer.singleShot(args.auto_close_ms, app.quit)

    logger.info("Interfaccia avviata")
    return app.exec()


class _DryRunDownloadService(QObject):
    """Stub download service per modalità dry-run."""

    download_progress = pyqtSignal(str, int)
    download_complete = pyqtSignal(str, dict)

    def enqueue(
        self,
        youtube_id: str,
        title: str,
        trigger: str = "manual",
        track_type: str = "karaoke",
    ) -> None:
        """No-op in dry-run."""

    def get_queue_status(self) -> list[dict]:
        """Restituisce coda vuota."""
        return []


if __name__ == "__main__":
    sys.exit(main())
