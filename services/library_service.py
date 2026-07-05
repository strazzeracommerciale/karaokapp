"""Catalogo locale sfogliabile e contatori di riproduzione."""

import logging
import sqlite3
from pathlib import Path
from typing import Literal

import config

logger = logging.getLogger(__name__)

TrackType = Literal["karaoke", "dj"]

_MEDIA_EXTENSIONS = {
    ".mp3",
    ".m4a",
    ".wav",
    ".flac",
    ".ogg",
    ".aac",
    ".mp4",
    ".mkv",
    ".webm",
    ".avi",
    ".mov",
    ".wmv",
}

_SORT_CLAUSES = {
    "recent": "last_played IS NULL, last_played DESC, title COLLATE NOCASE",
    "played": "play_count DESC, title COLLATE NOCASE",
    "title": "title COLLATE NOCASE",
    "artist": "artist IS NULL, artist COLLATE NOCASE, title COLLATE NOCASE",
}


class LibraryService:
    """Espone i brani già scaricati e aggiorna i contatori d'uso."""

    def __init__(
        self,
        db_conn: sqlite3.Connection,
        artist_registry: object | None = None,
    ) -> None:
        """Inizializza con la connessione DB condivisa."""
        self._conn = db_conn
        self._artist_registry = artist_registry

    def list_tracks(self, sort: str = "recent", track_type: TrackType = "karaoke") -> list[dict]:
        """Restituisce i brani con file locale presente, ordinati come richiesto.

        Filtra per `track_type` così karaoke e DJ restano cataloghi separati.
        La clausola ORDER BY proviene da una whitelist interna (non da input utente),
        quindi è sicura nonostante l'interpolazione: ORDER BY non è parametrizzabile.
        """
        order = _SORT_CLAUSES.get(sort, _SORT_CLAUSES["recent"])
        rows = self._conn.execute(
            "SELECT id, title, artist, local_path, source, duration_sec, "
            "play_count, last_played, track_type, metadata_confirmed "
            "FROM tracks "
            "WHERE local_path IS NOT NULL AND local_path != '' AND track_type = ? "
            f"ORDER BY {order}",
            (track_type,),
        ).fetchall()
        tracks: list[dict] = []
        for row in rows:
            local_path = row["local_path"]
            if not (local_path and Path(local_path).exists()):
                continue
            tracks.append(
                {
                    "id": row["id"],
                    "title": row["title"],
                    "artist": row["artist"],
                    "local_path": local_path,
                    "source": row["source"],
                    "duration_sec": row["duration_sec"],
                    "play_count": row["play_count"] or 0,
                    "last_played": row["last_played"],
                    "track_type": row["track_type"],
                    "metadata_confirmed": bool(row["metadata_confirmed"]),
                }
            )
        logger.debug(
            "Libreria locale: %d brani (sort=%s, type=%s)",
            len(tracks),
            sort,
            track_type,
        )
        return tracks

    def import_files(
        self,
        paths: list[str | Path],
        track_type: TrackType = "dj",
    ) -> list[dict]:
        """Registra file locali nel catalogo senza copiarli su disco.

        Ogni path viene salvato così com'è (path originale assoluto). I file già
        presenti con lo stesso `local_path` e `track_type` vengono ignorati.
        """
        imported: list[dict] = []
        for raw_path in paths:
            track = self._import_single_file(raw_path, track_type)
            if track is not None:
                imported.append(track)
        logger.info(
            "Import completato: %d/%d brani (type=%s)",
            len(imported),
            len(paths),
            track_type,
        )
        return imported

    def scan_media_dir(
        self,
        track_type: TrackType = "dj",
        media_dir: Path | None = None,
    ) -> list[dict]:
        """Scansiona ricorsivamente una cartella media e registra i file mancanti.

        Per i brani DJ usa `DJ_MEDIA_DIR` (download YouTube). Non sposta né copia
        i file: registra solo i path trovati non ancora in catalogo.
        """
        directory = media_dir or (
            config.DJ_MEDIA_DIR if track_type == "dj" else config.DOWNLOAD_DIR
        )
        if not directory.exists():
            logger.warning("Cartella media non trovata: %s", directory)
            return []
        paths = [
            path
            for path in directory.rglob("*")
            if path.is_file() and path.suffix.lower() in _MEDIA_EXTENSIONS
        ]
        logger.info("Scan %s: %d file candidati (type=%s)", directory, len(paths), track_type)
        return self.import_files(paths, track_type=track_type)

    def record_play(self, track_id: int) -> None:
        """Incrementa play_count e aggiorna last_played per un brano."""
        with self._conn:
            self._conn.execute(
                "UPDATE tracks SET play_count = play_count + 1, "
                "last_played = CURRENT_TIMESTAMP WHERE id = ?",
                (track_id,),
            )
        logger.debug("Riproduzione registrata per track_id=%s", track_id)

    def set_start_offset(self, track_id: int, seconds: float) -> None:
        """Memorizza il punto di inizio (in secondi) per saltare l'intro di un file."""
        value = max(0.0, float(seconds))
        with self._conn:
            self._conn.execute(
                "UPDATE tracks SET start_offset_sec = ? WHERE id = ?",
                (value, track_id),
            )
        logger.info("Punto di inizio salvato: track_id=%s -> %.1fs", track_id, value)

    def delete_track(self, track_id: int, *, remove_file: bool = True) -> bool:
        """Rimuove un brano dal catalogo e, opzionalmente, il file locale associato."""
        row = self._conn.execute(
            "SELECT id, local_path FROM tracks WHERE id = ?",
            (track_id,),
        ).fetchone()
        if row is None:
            logger.warning("Eliminazione ignorata: track_id=%s inesistente", track_id)
            return False
        local_path = row["local_path"]
        with self._conn:
            self._conn.execute("DELETE FROM playlist_tracks WHERE track_id = ?", (track_id,))
            self._conn.execute("DELETE FROM queue WHERE track_id = ?", (track_id,))
            self._conn.execute("DELETE FROM download_log WHERE track_id = ?", (track_id,))
            self._conn.execute("DELETE FROM tracks WHERE id = ?", (track_id,))
        if remove_file and local_path:
            path = Path(local_path)
            if path.is_file():
                try:
                    path.unlink()
                    logger.info("File eliminato: %s", path)
                except OSError as exc:
                    logger.warning("Impossibile eliminare %s: %s", path, exc)
        logger.info("Brano eliminato dalla libreria: track_id=%s", track_id)
        return True

    def update_track_metadata(
        self,
        track_id: int,
        title: str,
        artist: str | None,
    ) -> bool:
        """Aggiorna titolo e artista di un brano in catalogo."""
        cleaned_title = (title or "").strip()
        if not cleaned_title:
            logger.warning("update_track_metadata: titolo vuoto per track_id=%s", track_id)
            return False
        row = self._conn.execute("SELECT id FROM tracks WHERE id = ?", (track_id,)).fetchone()
        if row is None:
            return False
        with self._conn:
            self._conn.execute(
                "UPDATE tracks SET title = ?, artist = ?, "
                "metadata_confirmed = 1, metadata_confirmed_at = CURRENT_TIMESTAMP "
                "WHERE id = ?",
                (cleaned_title, artist, track_id),
            )
        if artist and self._artist_registry is not None and hasattr(
            self._artist_registry, "register"
        ):
            self._artist_registry.register(artist, source="manual")
        logger.info("Metadati aggiornati: track_id=%s titolo=%r artista=%r", track_id, cleaned_title, artist)
        return True

    def confirm_metadata(self, track_ids: list[int]) -> int:
        """Segna i metadati dei brani indicati come confermati dall'operatore."""
        if not track_ids:
            return 0
        placeholders = ",".join("?" * len(track_ids))
        with self._conn:
            cursor = self._conn.execute(
                f"UPDATE tracks SET metadata_confirmed = 1, "
                f"metadata_confirmed_at = CURRENT_TIMESTAMP "
                f"WHERE id IN ({placeholders})",
                track_ids,
            )
        count = cursor.rowcount
        logger.info("Metadati confermati per %d brani", count)
        return count

    def get_start_offset(self, track_id: int) -> float:
        """Restituisce il punto di inizio memorizzato per un brano (0 se assente)."""
        row = self._conn.execute(
            "SELECT start_offset_sec FROM tracks WHERE id = ?",
            (track_id,),
        ).fetchone()
        if row is None or row["start_offset_sec"] is None:
            return 0.0
        return float(row["start_offset_sec"])

    def _import_single_file(
        self,
        raw_path: str | Path,
        track_type: TrackType,
    ) -> dict | None:
        """Importa un singolo file se valido e non già catalogato."""
        path = Path(raw_path).resolve()
        if not path.is_file():
            logger.warning("Import ignorato, file non trovato: %s", raw_path)
            return None
        if path.suffix.lower() not in _MEDIA_EXTENSIONS:
            logger.warning("Import ignorato, estensione non supportata: %s", path)
            return None
        local_path = str(path)
        existing = self._conn.execute(
            "SELECT id, title, artist, source, track_type FROM tracks "
            "WHERE local_path = ? AND track_type = ?",
            (local_path, track_type),
        ).fetchone()
        if existing is not None:
            logger.debug("Già in libreria: %s", path.name)
            return None
        title, artist = self._metadata_from_path(path)
        with self._conn:
            cursor = self._conn.execute(
                """INSERT INTO tracks
                   (title, artist, local_path, source, track_type)
                   VALUES (?, ?, ?, 'local', ?)""",
                (title, artist, local_path, track_type),
            )
            track_id = cursor.lastrowid
        logger.info("Importato: %s (type=%s)", title, track_type)
        return {
            "id": track_id,
            "title": title,
            "artist": artist,
            "local_path": local_path,
            "source": "local",
            "track_type": track_type,
        }

    @staticmethod
    def _metadata_from_path(path: Path) -> tuple[str, str | None]:
        """Estrae titolo e artista dal nome file (euristica 'Artista - Titolo')."""
        stem = path.stem.strip()
        if " - " in stem:
            artist, title = stem.split(" - ", 1)
            return title.strip() or stem, artist.strip() or None
        return stem or path.name, None
