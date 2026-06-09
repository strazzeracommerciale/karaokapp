"""Gestione coda prenotazioni per sessione karaoke."""

import logging
import sqlite3
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)


class QueueService(QObject):
    """Service per aggiunta, riordino e avanzamento coda."""

    queue_updated = pyqtSignal(list)
    next_ready = pyqtSignal(dict)

    def __init__(self, db_conn: sqlite3.Connection, session_id: int) -> None:
        """Inizializza la coda per la sessione indicata."""
        super().__init__()
        self._conn = db_conn
        self._session_id = session_id

    def add(self, track: dict, singer_name: str) -> None:
        """Aggiunge un brano in coda, creando il track in DB se necessario."""
        if track.get("track_type") == "dj":
            logger.warning(
                "Brano DJ non accodabile in coda karaoke: %s",
                track.get("title"),
            )
            return
        track_id = track.get("id")
        if track_id is None:
            track_id = self._ensure_track(track)
        elif not self._is_karaoke_track_id(track_id):
            return
        if track_id is None:
            logger.warning(
                "Impossibile accodare in coda karaoke: %s",
                track.get("title"),
            )
            return
        max_pos = self._conn.execute(
            "SELECT COALESCE(MAX(position), 0) FROM queue WHERE session_id = ?",
            (self._session_id,),
        ).fetchone()[0]
        with self._conn:
            self._conn.execute(
                """INSERT INTO queue (session_id, track_id, singer_name, position)
                   VALUES (?, ?, ?, ?)""",
                (self._session_id, track_id, singer_name, max_pos + 1),
            )
        self._emit_queue_updated()
        logger.info("Aggiunto in coda: %s (%s)", track.get("title"), singer_name)

    def remove(self, queue_id: int) -> None:
        """Rimuove un elemento dalla coda."""
        with self._conn:
            self._conn.execute(
                "DELETE FROM queue WHERE id = ? AND session_id = ?",
                (queue_id, self._session_id),
            )
        self._reindex_positions()
        self._emit_queue_updated()

    def reorder(self, queue_id: int, new_position: int) -> None:
        """Sposta un elemento alla nuova posizione."""
        row = self._conn.execute(
            "SELECT position FROM queue WHERE id = ? AND session_id = ?",
            (queue_id, self._session_id),
        ).fetchone()
        if row is None:
            return
        old_position = row[0]
        with self._conn:
            if new_position < old_position:
                self._conn.execute(
                    """UPDATE queue SET position = position + 1
                       WHERE session_id = ? AND position >= ? AND position < ?""",
                    (self._session_id, new_position, old_position),
                )
            elif new_position > old_position:
                self._conn.execute(
                    """UPDATE queue SET position = position - 1
                       WHERE session_id = ? AND position > ? AND position <= ?""",
                    (self._session_id, old_position, new_position),
                )
            self._conn.execute(
                "UPDATE queue SET position = ? WHERE id = ?",
                (new_position, queue_id),
            )
        self._emit_queue_updated()

    def requeue(self, queue_id: int) -> None:
        """Ripristina un brano già eseguito come 'waiting' e lo sposta in fondo."""
        row = self._conn.execute(
            "SELECT id FROM queue WHERE id = ? AND session_id = ?",
            (queue_id, self._session_id),
        ).fetchone()
        if row is None:
            return
        max_pos = self._conn.execute(
            "SELECT COALESCE(MAX(position), 0) FROM queue WHERE session_id = ?",
            (self._session_id,),
        ).fetchone()[0]
        with self._conn:
            self._conn.execute(
                "UPDATE queue SET status = 'waiting', position = ? WHERE id = ?",
                (max_pos + 1, queue_id),
            )
        self._reindex_positions()
        self._emit_queue_updated()
        logger.info("Brano rimesso in coda: queue_id=%s", queue_id)

    def advance(self) -> dict | None:
        """Segna il corrente come done e restituisce il prossimo in attesa."""
        current = self.get_current()
        with self._conn:
            if current is not None:
                self._conn.execute(
                    "UPDATE queue SET status = 'done' WHERE id = ?",
                    (current["queue_id"],),
                )
            next_row = self._conn.execute(
                """SELECT q.id FROM queue q
                   JOIN tracks t ON t.id = q.track_id
                   WHERE q.session_id = ? AND q.status = 'waiting'
                     AND t.track_type = 'karaoke'
                   ORDER BY q.position LIMIT 1""",
                (self._session_id,),
            ).fetchone()
            if next_row is None:
                self._emit_queue_updated()
                return None
            self._conn.execute(
                "UPDATE queue SET status = 'playing' WHERE id = ?",
                (next_row[0],),
            )
        self._emit_queue_updated()
        queue = self.get_queue()
        playing = [item for item in queue if item["status"] == "playing"]
        if playing:
            self.next_ready.emit(playing[0])
            return playing[0]
        return None

    def play_at(self, queue_id: int) -> dict | None:
        """Imposta un elemento arbitrario come 'playing' e lo restituisce.

        L'eventuale brano in corso viene segnato 'done'. Permette di richiamare
        anche brani già eseguiti senza alterarne la posizione in coda.
        """
        target = self._conn.execute(
            """SELECT q.id, t.track_type
               FROM queue q
               JOIN tracks t ON t.id = q.track_id
               WHERE q.id = ? AND q.session_id = ?""",
            (queue_id, self._session_id),
        ).fetchone()
        if target is None:
            return None
        if target["track_type"] != "karaoke":
            logger.warning(
                "Riproduzione rifiutata: brano DJ in coda karaoke (queue_id=%s)",
                queue_id,
            )
            return None
        current = self.get_current()
        with self._conn:
            if current is not None and current["queue_id"] != queue_id:
                self._conn.execute(
                    "UPDATE queue SET status = 'done' WHERE id = ?",
                    (current["queue_id"],),
                )
            self._conn.execute(
                "UPDATE queue SET status = 'playing' WHERE id = ? AND session_id = ?",
                (queue_id, self._session_id),
            )
        self._emit_queue_updated()
        for item in self.get_queue():
            if item["queue_id"] == queue_id:
                return item
        return None

    def get_queue(self) -> list[dict]:
        """Restituisce la coda ordinata per position."""
        rows = self._conn.execute(
            """SELECT q.id AS queue_id, q.singer_name, q.position, q.status,
                      q.pitch_offset, q.tempo_ratio, t.id, t.title, t.artist,
                      t.local_path, t.youtube_id, t.source, t.duration_sec,
                      t.start_offset_sec, t.track_type
               FROM queue q
               JOIN tracks t ON t.id = q.track_id
               WHERE q.session_id = ?
               ORDER BY q.position""",
            (self._session_id,),
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def get_current(self) -> dict | None:
        """Restituisce l'elemento attualmente in riproduzione."""
        row = self._conn.execute(
            """SELECT q.id AS queue_id, q.singer_name, q.position, q.status,
                      q.pitch_offset, q.tempo_ratio, t.id, t.title, t.artist,
                      t.local_path, t.youtube_id, t.source, t.duration_sec,
                      t.start_offset_sec, t.track_type
               FROM queue q
               JOIN tracks t ON t.id = q.track_id
               WHERE q.session_id = ? AND q.status = 'playing'
               LIMIT 1""",
            (self._session_id,),
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def _is_karaoke_track_id(self, track_id: int) -> bool:
        """True se il track_id è un brano karaoke accodabile."""
        row = self._conn.execute(
            "SELECT track_type FROM tracks WHERE id = ?",
            (track_id,),
        ).fetchone()
        if row is None:
            logger.warning("Track inesistente, accodamento saltato: id=%s", track_id)
            return False
        if row["track_type"] != "karaoke":
            logger.warning(
                "Brano DJ non accodabile in coda karaoke: track_id=%s",
                track_id,
            )
            return False
        return True

    def _ensure_track(self, track: dict) -> int | None:
        """Inserisce un track YouTube nel DB se non esiste e ritorna l'id."""
        youtube_id = track.get("youtube_id")
        if youtube_id:
            existing = self._conn.execute(
                "SELECT id, track_type FROM tracks WHERE youtube_id = ?",
                (youtube_id,),
            ).fetchone()
            if existing:
                if existing["track_type"] != "karaoke":
                    logger.warning(
                        "YouTube id %s già registrato come brano DJ, non accodabile",
                        youtube_id,
                    )
                    return None
                return existing["id"]
        with self._conn:
            cursor = self._conn.execute(
                """INSERT INTO tracks
                   (title, artist, youtube_id, local_path, source, duration_sec, track_type)
                   VALUES (?, ?, ?, ?, ?, ?, 'karaoke')""",
                (
                    track.get("title", ""),
                    track.get("artist"),
                    track.get("youtube_id"),
                    track.get("local_path"),
                    track.get("source", "youtube"),
                    track.get("duration_sec"),
                ),
            )
            return cursor.lastrowid

    def _reindex_positions(self) -> None:
        """Ricalcola le posizioni dopo una rimozione."""
        rows = self._conn.execute(
            "SELECT id FROM queue WHERE session_id = ? ORDER BY position",
            (self._session_id,),
        ).fetchall()
        with self._conn:
            for index, row in enumerate(rows, start=1):
                self._conn.execute(
                    "UPDATE queue SET position = ? WHERE id = ?",
                    (index, row[0]),
                )

    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        """Converte una riga JOIN queue+tracks in dict."""
        local_path = row["local_path"]
        source = row["source"]
        ready = source == "local" or bool(local_path and Path(local_path).exists())
        keys = row.keys()
        start_offset = row["start_offset_sec"] if "start_offset_sec" in keys else 0.0
        return {
            "queue_id": row["queue_id"],
            "singer_name": row["singer_name"],
            "position": row["position"],
            "status": row["status"],
            "pitch_offset": row["pitch_offset"],
            "tempo_ratio": row["tempo_ratio"],
            "id": row["id"],
            "title": row["title"],
            "artist": row["artist"],
            "local_path": local_path,
            "youtube_id": row["youtube_id"],
            "source": source,
            "duration_sec": row["duration_sec"],
            "start_offset_sec": start_offset or 0.0,
            "track_type": row["track_type"] if "track_type" in keys else "karaoke",
            "ready": ready,
        }

    def _emit_queue_updated(self) -> None:
        """Emette il segnale queue_updated con la lista corrente."""
        self.queue_updated.emit(self.get_queue())
