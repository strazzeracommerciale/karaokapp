"""Coda download background con worker thread."""

import logging
import sqlite3
from collections import deque
from typing import Literal

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

import config
from engines.ytdlp_engine import YtdlpEngine

logger = logging.getLogger(__name__)

TrackType = Literal["karaoke", "dj"]


class _DownloadWorker(QThread):
    """Worker thread per download yt-dlp."""

    progress = pyqtSignal(str, int)
    complete = pyqtSignal(str, dict)
    error = pyqtSignal(str, str)

    def __init__(self, ytdlp_engine: YtdlpEngine, db_conn: sqlite3.Connection) -> None:
        """Inizializza il worker con engine e connessione DB."""
        super().__init__()
        self._ytdlp = ytdlp_engine
        self._conn = db_conn
        self._queue: deque[dict] = deque()
        self._active = False

    def enqueue_item(self, item: dict) -> None:
        """Aggiunge un item alla coda interna del worker."""
        self._queue.append(item)

    def run(self) -> None:
        """Processa la coda download fino a svuotamento."""
        self._active = True
        while self._queue:
            item = self._queue.popleft()
            youtube_id = item["youtube_id"]
            title = item["title"]
            trigger = item.get("trigger", "manual")
            track_type: TrackType = item.get("track_type", "karaoke")
            try:
                output_path = (
                    config.DJ_DOWNLOAD_DIR
                    if track_type == "dj"
                    else config.DOWNLOAD_DIR
                )
                output_path.mkdir(parents=True, exist_ok=True)

                def hook(d: dict) -> None:
                    if d.get("status") == "downloading":
                        total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                        downloaded = d.get("downloaded_bytes", 0)
                        percent = int(downloaded * 100 / total) if total > 0 else 0
                        self.progress.emit(youtube_id, percent)

                file_path = self._ytdlp.download(
                    youtube_id, str(output_path), progress_hook=hook
                )
                metadata = self._ytdlp.extract_metadata(youtube_id)
                track_dict = self._save_track(
                    youtube_id,
                    title,
                    metadata,
                    file_path,
                    trigger,
                    track_type,
                )
                self.complete.emit(youtube_id, track_dict)
            except Exception as exc:
                logger.error("Download fallito per %s: %s", youtube_id, exc)
                self.error.emit(youtube_id, str(exc))
        self._active = False

    def _save_track(
        self,
        youtube_id: str,
        title: str,
        metadata: dict,
        file_path: str,
        trigger: str,
        track_type: TrackType,
    ) -> dict:
        """Salva track e log download nel database."""
        with self._conn:
            existing = self._conn.execute(
                "SELECT id, track_type FROM tracks WHERE youtube_id = ?",
                (youtube_id,),
            ).fetchone()
            if existing:
                if existing["track_type"] != track_type:
                    raise ValueError(
                        f"YouTube id {youtube_id} già registrato come "
                        f"{existing['track_type']}, non come {track_type}"
                    )
                track_id = existing["id"]
                self._conn.execute(
                    "UPDATE tracks SET local_path = ?, title = ? WHERE id = ?",
                    (file_path, metadata.get("title", title), track_id),
                )
            else:
                cursor = self._conn.execute(
                    """INSERT INTO tracks
                       (title, artist, youtube_id, local_path, source, duration_sec, track_type)
                       VALUES (?, ?, ?, ?, 'youtube', ?, ?)""",
                    (
                        metadata.get("title", title),
                        metadata.get("uploader"),
                        youtube_id,
                        file_path,
                        metadata.get("duration"),
                        track_type,
                    ),
                )
                track_id = cursor.lastrowid
            self._conn.execute(
                """INSERT INTO download_log (track_id, trigger, status, downloaded_at)
                   VALUES (?, ?, 'complete', CURRENT_TIMESTAMP)""",
                (track_id, trigger),
            )
        return {
            "id": track_id,
            "title": metadata.get("title", title),
            "artist": metadata.get("uploader"),
            "youtube_id": youtube_id,
            "local_path": file_path,
            "source": "youtube",
            "duration_sec": metadata.get("duration"),
            "track_type": track_type,
        }


class DownloadService(QObject):
    """Service di download con coda e segnali di progresso."""

    download_progress = pyqtSignal(str, int)
    download_complete = pyqtSignal(str, dict)
    download_error = pyqtSignal(str, str)

    def __init__(self, ytdlp_engine: YtdlpEngine, db_conn: sqlite3.Connection) -> None:
        """Inizializza il service e il worker thread."""
        super().__init__()
        self._ytdlp = ytdlp_engine
        self._conn = db_conn
        self._pending: list[dict] = []
        self._worker: _DownloadWorker | None = None
        config.DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        config.DJ_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    def enqueue(
        self,
        youtube_id: str,
        title: str,
        trigger: str = "manual",
        track_type: TrackType = "karaoke",
    ) -> None:
        """Aggiunge un download alla coda e avvia il worker se necessario."""
        existing = self._conn.execute(
            "SELECT track_type FROM tracks WHERE youtube_id = ?",
            (youtube_id,),
        ).fetchone()
        if existing is not None and existing["track_type"] != track_type:
            logger.warning(
                "Download rifiutato: %s già registrato come %s, richiesto %s",
                youtube_id,
                existing["track_type"],
                track_type,
            )
            return
        item = {
            "youtube_id": youtube_id,
            "title": title,
            "trigger": trigger,
            "track_type": track_type,
        }
        self._pending.append({**item, "percent": 0, "status": "pending"})
        if self._worker is None or not self._worker.isRunning():
            self._start_worker()
        if self._worker is not None:
            self._worker.enqueue_item(item)
        logger.info("Download in coda: %s (type=%s)", youtube_id, track_type)

    def get_queue_status(self) -> list[dict]:
        """Restituisce lo stato della coda download."""
        return list(self._pending)

    def _start_worker(self) -> None:
        """Avvia un nuovo worker thread per i download."""
        self._worker = _DownloadWorker(self._ytdlp, self._conn)
        self._worker.progress.connect(self._on_progress)
        self._worker.complete.connect(self._on_complete)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    @pyqtSlot(str, int)
    def _on_progress(self, youtube_id: str, percent: int) -> None:
        """Aggiorna percentuale e emette segnale."""
        for item in self._pending:
            if item["youtube_id"] == youtube_id:
                item["percent"] = percent
                item["status"] = "downloading"
        self.download_progress.emit(youtube_id, percent)

    @pyqtSlot(str, dict)
    def _on_complete(self, youtube_id: str, track_dict: dict) -> None:
        """Rimuove dalla coda pending e emette complete."""
        self._pending = [p for p in self._pending if p["youtube_id"] != youtube_id]
        self.download_complete.emit(youtube_id, track_dict)

    @pyqtSlot(str, str)
    def _on_error(self, youtube_id: str, message: str) -> None:
        """Segna errore e emette segnale."""
        for item in self._pending:
            if item["youtube_id"] == youtube_id:
                item["status"] = "error"
        self.download_error.emit(youtube_id, message)
