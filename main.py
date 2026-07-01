"""Entry point KaraokeManager — bootstrap Qt e wiring moduli."""

import argparse
import logging
import sys
import traceback
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication, QMessageBox

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
from ui.theme_service import ThemeService

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
    parser.add_argument(
        "--migrate-paths",
        metavar="OLD_ROOT",
        help="Riscrive local_path nel DB: sostituisce OLD_ROOT con la cartella dati corrente",
    )
    parser.add_argument(
        "--migrate-paths-to",
        metavar="NEW_ROOT",
        default=None,
        help="Con --migrate-paths: destinazione esplicita (es. cartella install sul portatile)",
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


def _install_crash_logger() -> None:
    """Scrive eccezioni non gestite su crash.log (utile su .app senza console)."""
    if not getattr(sys, "frozen", False):
        return
    crash_log = config.LOG_PATH.parent / "crash.log"

    def _hook(exc_type, exc, tb) -> None:
        try:
            crash_log.parent.mkdir(parents=True, exist_ok=True)
            with crash_log.open("a", encoding="utf-8") as handle:
                handle.write("\n--- crash ---\n")
                traceback.print_exception(exc_type, exc, tb, file=handle)
        except OSError:
            pass
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = _hook


def _migrate_paths(old_root: str, new_root: str | None = None) -> int:
    """Aggiorna i percorsi assoluti nel DB dopo copia dati su un altro PC."""
    old = Path(old_root).expanduser().resolve()
    new = Path(new_root).expanduser().resolve() if new_root else config.BASE_DIR.resolve()
    if not old.is_dir():
        print(f"Errore: cartella origine non trovata: {old}", file=sys.stderr)
        return 1
    conn = db_core.get_conn()
    rows = conn.execute(
        "SELECT id, local_path FROM tracks WHERE local_path IS NOT NULL AND local_path != ''"
    ).fetchall()
    updated = 0
    skipped = 0
    with conn:
        conn.execute("PRAGMA wal_checkpoint(FULL)")
        for row in rows:
            raw = row["local_path"]
            if not raw:
                skipped += 1
                continue
            try:
                rel = Path(raw).resolve().relative_to(old)
            except (ValueError, OSError):
                skipped += 1
                continue
            new_path = str(new / rel)
            conn.execute(
                "UPDATE tracks SET local_path = ? WHERE id = ?",
                (new_path, row["id"]),
            )
            updated += 1
    db_core.close()
    print("Migrazione percorsi completata.")
    print(f"  Origine:    {old}")
    print(f"  Destino:    {new}")
    print(f"  Aggiornati: {updated}")
    if skipped:
        print(f"  Saltati:    {skipped} (non sotto {old})")
    return 0


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


def _verify_standalone_bundle() -> str | None:
    """Controlla che l'installazione frozen contenga tutti i componenti necessari."""
    if not getattr(sys, "frozen", False):
        return None

    missing: list[str] = []
    vlc_dir = config.INSTALL_DIR / "vlc"
    for name in ("libvlc.dll", "libvlccore.dll"):
        if not (vlc_dir / name).is_file():
            missing.append(f"  • vlc\\{name}")
    plugins = vlc_dir / "plugins"
    if not plugins.is_dir() or not any(plugins.iterdir()):
        missing.append("  • vlc\\plugins\\ (moduli di decodifica video/audio)")
    ffmpeg = config.INSTALL_DIR / "bin" / "ffmpeg.exe"
    if not ffmpeg.is_file():
        missing.append("  • bin\\ffmpeg.exe (download da YouTube)")
    qt_platform = (
        config.BUNDLE_DIR / "PyQt6" / "Qt6" / "plugins" / "platforms" / "qwindows.dll"
    )
    if not qt_platform.is_file():
        missing.append("  • interfaccia grafica Qt (installazione incompleta)")

    if not missing:
        return None

    install = config.INSTALL_DIR
    return (
        "Installazione incompleta o danneggiata.\n\n"
        "Mancano questi file nella cartella del programma:\n"
        + "\n".join(missing)
        + f"\n\nCartella installazione:\n  {install}\n\n"
        "Reinstalla con KaraokeManager-Setup.exe (non copiare solo il file .exe).\n"
        "Se il problema persiste, disinstalla e reinstalla da zero."
    )


def main() -> int:
    """Avvia l'applicazione KaraokeManager."""
    args = _parse_args()
    if args.db:
        config.DB_PATH = Path(args.db)
    if args.migrate_paths:
        _setup_logging()
        return _migrate_paths(args.migrate_paths, args.migrate_paths_to)
    _install_crash_logger()
    _setup_logging()
    logger.info("Avvio %s v%s (dry_run=%s)", config.APP_NAME, config.APP_VERSION, args.dry_run)

    bundle_error = _verify_standalone_bundle()
    if bundle_error:
        logger.error("Bundle incompleto:\n%s", bundle_error)
        app = QApplication(sys.argv)
        QMessageBox.critical(None, "KaraokeManager — installazione incompleta", bundle_error)
        return 1

    app = QApplication(sys.argv)

    theme_service = ThemeService()
    theme_service.apply_globally()

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
    dj_playback_flow = DjPlaybackFlow(dj_runtime_service)

    player_service: object | None = None
    dj_player_service: object | None = None
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
        theme_service=theme_service,
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
        from services.dj_player_service import DjPlayerService
        from services.download_service import DownloadService
        from services.filler_service import FillerService
        from services.player_service import PlayerService

        try:
            vlc_engine = VlcEngine()
            vlc_engine_secondary = vlc_engine.clone()
            vlc_dj_engine = VlcEngine()
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
            dj_player_service = DjPlayerService(vlc_dj_engine, ytdlp_engine)
            filler_engine = VlcEngine(*config.FILLER_VLC_ARGS)
            filler_service = FillerService(filler_engine)
            main_window.wire_services(player_service, search_service, download_service)
            main_window.set_filler_service(filler_service)
            dj_playback_flow.set_player(dj_player_service)
            dj_playback_flow.set_filler(filler_service)
            external_coordinator.set_player(player_service)
        except Exception as exc:
            logger.exception("Inizializzazione VLC/player fallita")
            QMessageBox.critical(
                None,
                "KaraokeManager — errore VLC",
                "Impossibile inizializzare il motore video/audio (VLC).\n\n"
                f"Dettaglio: {exc}\n\n"
                f"Log: {config.LOG_PATH}",
            )
            return 1
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
        player_service=dj_player_service,
    )
    main_window.dj_console_toggle_requested.connect(
        lambda: _toggle_dj_console(dj_console_window)
    )
    dj_console_window.dj_filler_track_requested.connect(main_window.apply_dj_filler_track)

    main_window.show()
    app.processEvents()

    if not args.dry_run and player_service is not None:
        vlc_engine.set_output_widget(main_window.video_output_widget())
        main_window.set_vlc_output_rebind(vlc_engine.set_output_widget)
    if not args.dry_run and dj_player_service is not None:
        dj_player_service.bind_output_widget(dj_console_window.video_output_widget())
        dj_console_window.set_vlc_output_rebind(vlc_dj_engine.set_output_widget)

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
