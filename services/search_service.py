"""Coordina ricerca locale/YouTube in modo asincrono."""

import logging
from typing import Literal

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from engines.search_engine import SearchEngine
from services.download_service import DownloadService

logger = logging.getLogger(__name__)

TrackType = Literal["karaoke", "dj"]


class _SearchWorker(QThread):
    """Worker thread per ricerca unificata."""

    finished_with_results = pyqtSignal(list)

    def __init__(
        self, search_engine: SearchEngine, query: str, yt_limit: int | None = None
    ) -> None:
        """Inizializza il worker con query da eseguire."""
        super().__init__()
        self._engine = search_engine
        self._query = query
        self._yt_limit = yt_limit

    def run(self) -> None:
        """Esegue search_unified e emette i risultati."""
        try:
            results = self._engine.search_unified(self._query, yt_limit=self._yt_limit)
            self.finished_with_results.emit(results)
        except Exception as exc:
            logger.error("Ricerca fallita per '%s': %s", self._query, exc)
            self.finished_with_results.emit([])


class SearchService(QObject):
    """Service di ricerca con emissione asincrona dei risultati."""

    results_ready = pyqtSignal(list)

    def __init__(
        self,
        search_engine: SearchEngine,
        download_service: DownloadService,
        track_type: TrackType = "karaoke",
    ) -> None:
        """Inizializza con engine di ricerca, download e tipo brano associato."""
        super().__init__()
        self._engine = search_engine
        self._download = download_service
        self._track_type = track_type
        self._worker: _SearchWorker | None = None

    def search(self, query: str, yt_limit: int | None = None) -> None:
        """Avvia ricerca asincrona; emette results_ready al termine."""
        if self._worker is not None and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait()
        self._worker = _SearchWorker(self._engine, query, yt_limit)
        self._worker.finished_with_results.connect(self.results_ready.emit)
        self._worker.start()

    def search_sync(self, query: str) -> list[dict]:
        """Versione sincrona per uso interno."""
        return self._engine.search_unified(query)

    def track_type(self) -> TrackType:
        """Restituisce il tipo brano associato a questa istanza di ricerca."""
        return self._track_type

    def trigger_download_for_track(self, track: dict) -> None:
        """Avvia download silenzioso per un risultato YouTube del tipo configurato."""
        youtube_id = track.get("youtube_id")
        if youtube_id and track.get("source") == "youtube" and not track.get("local_path"):
            self._download.enqueue(
                youtube_id,
                track.get("title", ""),
                trigger="auto",
                track_type=self._track_type,
            )
