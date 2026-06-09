"""Gestione playlist: scalette di brani locali riutilizzabili."""

import logging
import sqlite3
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

PlaylistMode = Literal["karaoke", "dj"]


class PlaylistService:
    """CRUD su playlist e relativi brani."""

    def __init__(self, db_conn: sqlite3.Connection) -> None:
        """Inizializza con la connessione DB condivisa."""
        self._conn = db_conn

    def create(self, name: str, mode: PlaylistMode = "karaoke") -> int:
        """Crea una nuova playlist e ne restituisce l'id."""
        with self._conn:
            cursor = self._conn.execute(
                "INSERT INTO playlists (name, mode) VALUES (?, ?)",
                (name, mode),
            )
        logger.info("Playlist creata: %s (mode=%s)", name, mode)
        return cursor.lastrowid

    def delete(self, playlist_id: int) -> None:
        """Elimina una playlist e i suoi riferimenti ai brani."""
        with self._conn:
            self._conn.execute(
                "DELETE FROM playlist_tracks WHERE playlist_id = ?", (playlist_id,)
            )
            self._conn.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))
        logger.info("Playlist eliminata: id=%s", playlist_id)

    def list_playlists(self, mode: PlaylistMode | None = None) -> list[dict]:
        """Elenca le playlist ordinate per nome, opzionalmente filtrate per mode."""
        if mode is None:
            rows = self._conn.execute(
                "SELECT id, name, mode FROM playlists ORDER BY name COLLATE NOCASE"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, name, mode FROM playlists WHERE mode = ? "
                "ORDER BY name COLLATE NOCASE",
                (mode,),
            ).fetchall()
        return [{"id": row["id"], "name": row["name"], "mode": row["mode"]} for row in rows]

    def get_tracks(self, playlist_id: int) -> list[dict]:
        """Restituisce i brani di una playlist nell'ordine salvato."""
        rows = self._conn.execute(
            """SELECT t.id, t.title, t.artist, t.local_path, t.source,
                      t.duration_sec, t.track_type, pt.position
               FROM playlist_tracks pt
               JOIN tracks t ON t.id = pt.track_id
               WHERE pt.playlist_id = ?
               ORDER BY pt.position""",
            (playlist_id,),
        ).fetchall()
        tracks: list[dict] = []
        for row in rows:
            local_path = row["local_path"]
            ready = row["source"] == "local" or bool(local_path and Path(local_path).exists())
            tracks.append(
                {
                    "id": row["id"],
                    "title": row["title"],
                    "artist": row["artist"],
                    "local_path": local_path,
                    "source": row["source"],
                    "duration_sec": row["duration_sec"],
                    "track_type": row["track_type"],
                    "position": row["position"],
                    "ready": ready,
                }
            )
        return tracks

    def add_track(self, playlist_id: int, track_id: int) -> bool:
        """Aggiunge un brano in coda alla playlist; ignora i duplicati.

        Restituisce True se aggiunto, False se già presente o se playlist.mode
        e track.track_type non coincidono.
        """
        playlist = self._conn.execute(
            "SELECT mode FROM playlists WHERE id = ?",
            (playlist_id,),
        ).fetchone()
        track = self._conn.execute(
            "SELECT track_type FROM tracks WHERE id = ?",
            (track_id,),
        ).fetchone()
        if playlist is None or track is None:
            logger.warning(
                "add_track fallito: playlist_id=%s track_id=%s non trovati",
                playlist_id,
                track_id,
            )
            return False
        if playlist["mode"] != track["track_type"]:
            logger.warning(
                "Brano %s (type=%s) non aggiungibile a playlist %s (mode=%s)",
                track_id,
                track["track_type"],
                playlist_id,
                playlist["mode"],
            )
            return False
        existing = self._conn.execute(
            "SELECT 1 FROM playlist_tracks WHERE playlist_id = ? AND track_id = ?",
            (playlist_id, track_id),
        ).fetchone()
        if existing:
            return False
        max_pos = self._conn.execute(
            "SELECT COALESCE(MAX(position), 0) FROM playlist_tracks WHERE playlist_id = ?",
            (playlist_id,),
        ).fetchone()[0]
        with self._conn:
            self._conn.execute(
                "INSERT INTO playlist_tracks (playlist_id, track_id, position) VALUES (?, ?, ?)",
                (playlist_id, track_id, max_pos + 1),
            )
        return True

    def reorder_tracks(self, playlist_id: int, track_id: int, new_position: int) -> None:
        """Sposta un brano alla nuova posizione all'interno della playlist."""
        row = self._conn.execute(
            "SELECT position FROM playlist_tracks WHERE playlist_id = ? AND track_id = ?",
            (playlist_id, track_id),
        ).fetchone()
        if row is None:
            return
        old_position = row[0]
        with self._conn:
            if new_position < old_position:
                self._conn.execute(
                    """UPDATE playlist_tracks SET position = position + 1
                       WHERE playlist_id = ? AND position >= ? AND position < ?""",
                    (playlist_id, new_position, old_position),
                )
            elif new_position > old_position:
                self._conn.execute(
                    """UPDATE playlist_tracks SET position = position - 1
                       WHERE playlist_id = ? AND position > ? AND position <= ?""",
                    (playlist_id, old_position, new_position),
                )
            self._conn.execute(
                """UPDATE playlist_tracks SET position = ?
                   WHERE playlist_id = ? AND track_id = ?""",
                (new_position, playlist_id, track_id),
            )
        self._reindex_positions(playlist_id)
        logger.debug(
            "Playlist %s: track %s spostato da pos %s a %s",
            playlist_id,
            track_id,
            old_position,
            new_position,
        )

    def remove_track(self, playlist_id: int, track_id: int) -> None:
        """Rimuove un brano dalla playlist."""
        with self._conn:
            self._conn.execute(
                "DELETE FROM playlist_tracks WHERE playlist_id = ? AND track_id = ?",
                (playlist_id, track_id),
            )
        self._reindex_positions(playlist_id)

    def _reindex_positions(self, playlist_id: int) -> None:
        """Ricalcola le posizioni 1..N dopo rimozione o riordino."""
        rows = self._conn.execute(
            "SELECT track_id FROM playlist_tracks WHERE playlist_id = ? ORDER BY position",
            (playlist_id,),
        ).fetchall()
        with self._conn:
            for index, row in enumerate(rows, start=1):
                self._conn.execute(
                    """UPDATE playlist_tracks SET position = ?
                       WHERE playlist_id = ? AND track_id = ?""",
                    (index, playlist_id, row["track_id"]),
                )
