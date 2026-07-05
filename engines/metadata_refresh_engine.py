"""Motore UI per aggiornamento batch metadati/rinomina file (worker in background)."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import asdict, dataclass
from typing import Literal

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from engines.ytdlp_engine import YtdlpEngine
from services.metadata_refresh_models import TrackRefreshOutcome
from services.metadata_refresh_service import MetadataRefreshService

logger = logging.getLogger(__name__)

TrackType = Literal["karaoke", "dj"]


@dataclass(frozen=True)
class MetadataRefreshOptions:
    """Parametri di esecuzione refresh metadati (UX opzioni da definire in Preparazione)."""

    rename_files: bool = True
    parse_only: bool = False
    dry_run: bool = False
    track_type: TrackType | None = "karaoke"
    skip_confirmed: bool = True


class _MetadataRefreshWorker(QThread):
    """Worker thread: delega a MetadataRefreshService senza bloccare la UI."""

    progress = pyqtSignal(int, int, str)
    finished_ok = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(
        self,
        conn: sqlite3.Connection,
        options: MetadataRefreshOptions,
        ytdlp: YtdlpEngine,
        artist_registry: object | None,
    ) -> None:
        super().__init__()
        self._conn = conn
        self._options = options
        self._ytdlp = ytdlp
        self._artist_registry = artist_registry

    def run(self) -> None:
        """Esegue il refresh sull'archivio."""
        try:
            service = MetadataRefreshService(
                self._conn,
                ytdlp=self._ytdlp,
                artist_registry=self._artist_registry,
            )
            stats = service.refresh_all(
                rename_files=self._options.rename_files,
                parse_only=self._options.parse_only,
                dry_run=self._options.dry_run,
                track_type=self._options.track_type,
                skip_confirmed=self._options.skip_confirmed,
                on_progress=lambda current, total, label: self.progress.emit(
                    current, total, label
                ),
            )
            self.finished_ok.emit(_serialize_stats(stats))
        except Exception as exc:
            logger.exception("Metadata refresh fallito")
            self.failed.emit(str(exc))


class MetadataRefreshEngine(QObject):
    """Facade Qt per avviare/fermare il refresh metadati da Preparazione o altre UI.

    Richiede una connessione SQLite con ``check_same_thread=False`` (come ``db_core.get_conn()``).
    """

    started = pyqtSignal()
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    busy_changed = pyqtSignal(bool)

    def __init__(
        self,
        conn: sqlite3.Connection,
        ytdlp: YtdlpEngine | None = None,
        artist_registry: object | None = None,
    ) -> None:
        super().__init__()
        self._conn = conn
        self._ytdlp = ytdlp or YtdlpEngine()
        self._artist_registry = artist_registry
        self._worker: _MetadataRefreshWorker | None = None

    def is_busy(self) -> bool:
        """True se un refresh è in corso."""
        return self._worker is not None and self._worker.isRunning()

    def start(self, options: MetadataRefreshOptions | None = None) -> bool:
        """Avvia il refresh in background. Restituisce False se già in esecuzione."""
        if self.is_busy():
            return False
        run_options = options or MetadataRefreshOptions()
        self._worker = _MetadataRefreshWorker(
            self._conn,
            run_options,
            self._ytdlp,
            self._artist_registry,
        )
        worker = self._worker
        worker.progress.connect(self.progress.emit)
        worker.finished_ok.connect(self._on_worker_finished)
        worker.failed.connect(self._on_worker_failed)
        worker.finished.connect(self._clear_worker)
        self.busy_changed.emit(True)
        self.started.emit()
        worker.start()
        return True

    def _on_worker_finished(self, stats: dict) -> None:
        """Propaga il completamento con le statistiche aggregate."""
        self.finished.emit(stats)

    def _on_worker_failed(self, message: str) -> None:
        """Propaga un errore fatale del worker."""
        self.error.emit(message)
        self.busy_changed.emit(False)

    def _clear_worker(self) -> None:
        """Pulisce il riferimento al thread terminato."""
        self._worker = None
        self.busy_changed.emit(False)


def _serialize_stats(stats: dict) -> dict:
    """Converte gli esiti in dict serializzabili per i segnali Qt cross-thread."""
    payload = dict(stats)
    raw_outcomes = payload.get("outcomes") or []
    payload["outcomes"] = [
        asdict(item) if isinstance(item, TrackRefreshOutcome) else item for item in raw_outcomes
    ]
    return payload


def deserialize_outcomes(raw_outcomes: list) -> list[TrackRefreshOutcome]:
    """Ricostruisce gli esiti dal payload del segnale ``finished``."""
    results: list[TrackRefreshOutcome] = []
    for item in raw_outcomes:
        if isinstance(item, TrackRefreshOutcome):
            results.append(item)
        elif isinstance(item, dict):
            results.append(TrackRefreshOutcome(**item))
    return results
