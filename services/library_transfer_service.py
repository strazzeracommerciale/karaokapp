"""Esportazione e importazione libreria karaoke (DB + file media) su percorso esterno."""

from __future__ import annotations

import json
import logging
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import config

logger = logging.getLogger(__name__)

_BUNDLE_DIR_NAME = "KaraokeManager_libreria"
_MANIFEST_NAME = "manifest.json"


class LibraryTransferService:
    """Copia o integra libreria karaoke senza sovrascrivere il catalogo locale."""

    def __init__(self, conn: sqlite3.Connection, artist_registry: object | None = None) -> None:
        self._conn = conn
        self._artist_registry = artist_registry

    def export_library(self, destination: Path) -> dict[str, int | str]:
        """Esporta DB karaoke e file media in ``destination/KaraokeManager_libreria``."""
        dest_root = Path(destination).expanduser().resolve()
        bundle_root = dest_root / _BUNDLE_DIR_NAME
        if bundle_root.exists():
            raise FileExistsError(f"Cartella già presente: {bundle_root}")

        data_dir = bundle_root / "data"
        media_dir = bundle_root / "media" / "downloads"
        data_dir.mkdir(parents=True)
        media_dir.mkdir(parents=True)

        if not config.DB_PATH.is_file():
            raise FileNotFoundError(f"Database non trovato: {config.DB_PATH}")

        shutil.copy2(config.DB_PATH, data_dir / "karaoke.db")
        files_copied = 0
        if config.DOWNLOAD_DIR.is_dir():
            for item in config.DOWNLOAD_DIR.iterdir():
                if item.is_file():
                    shutil.copy2(item, media_dir / item.name)
                    files_copied += 1

        track_count = self._conn.execute(
            "SELECT COUNT(*) FROM tracks WHERE track_type = 'karaoke' "
            "AND local_path IS NOT NULL AND local_path != ''"
        ).fetchone()[0]

        manifest = {
            "format": "karaoke_manager_library_bundle",
            "exported_at": datetime.now(UTC).isoformat(),
            "app_version": config.APP_VERSION,
            "source_root": str(config.BASE_DIR.resolve()),
            "track_count": track_count,
            "media_files": files_copied,
        }
        (bundle_root / _MANIFEST_NAME).write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Esportazione libreria completata: %s", bundle_root)
        return {
            "bundle_path": str(bundle_root),
            "tracks": track_count,
            "files": files_copied,
        }

    def import_library(self, source: Path) -> dict[str, int]:
        """Integra un bundle esportato nel catalogo corrente senza duplicati."""
        bundle_root = self._resolve_bundle_root(source)
        bundle_db = bundle_root / "data" / "karaoke.db"
        if not bundle_db.is_file():
            raise FileNotFoundError(f"Database bundle non trovato: {bundle_db}")

        bundle_conn = sqlite3.connect(f"file:{bundle_db}?mode=ro", uri=True)
        bundle_conn.row_factory = sqlite3.Row
        try:
            stats = self._merge_from_bundle(bundle_conn, bundle_root)
        finally:
            bundle_conn.close()
        logger.info("Importazione libreria completata: %s", stats)
        return stats

    def _resolve_bundle_root(self, source: Path) -> Path:
        path = Path(source).expanduser().resolve()
        if (path / _MANIFEST_NAME).is_file() or (path / "data" / "karaoke.db").is_file():
            return path
        nested = path / _BUNDLE_DIR_NAME
        if nested.is_dir():
            return nested.resolve()
        raise FileNotFoundError(
            f"Percorso non valido: seleziona la cartella «{_BUNDLE_DIR_NAME}» esportata."
        )

    def _merge_from_bundle(self, bundle_conn: sqlite3.Connection, bundle_root: Path) -> dict[str, int]:
        stats = {
            "tracks_added": 0,
            "tracks_skipped": 0,
            "files_copied": 0,
            "playlists_created": 0,
            "playlist_tracks_added": 0,
            "artists_added": 0,
            "errors": 0,
        }
        config.DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

        dest_youtube_ids = {
            row[0]
            for row in self._conn.execute(
                "SELECT youtube_id FROM tracks WHERE youtube_id IS NOT NULL AND youtube_id != ''"
            ).fetchall()
        }
        id_map: dict[int, int] = {}

        rows = bundle_conn.execute(
            "SELECT id, title, artist, youtube_id, local_path, source, duration_sec, "
            "start_offset_sec, metadata_confirmed, metadata_confirmed_at "
            "FROM tracks WHERE track_type = 'karaoke' "
            "AND local_path IS NOT NULL AND local_path != ''"
        ).fetchall()

        for row in rows:
            try:
                outcome = self._import_track_row(row, bundle_root, dest_youtube_ids, id_map, stats)
                stats[outcome] += 1
            except Exception:
                stats["errors"] += 1
                logger.exception("Errore import track_id bundle=%s", row["id"])

        self._import_playlists(bundle_conn, id_map, stats)
        self._import_known_artists(bundle_conn, stats)
        return stats

    def _import_track_row(
        self,
        row: sqlite3.Row,
        bundle_root: Path,
        dest_youtube_ids: set[str],
        id_map: dict[int, int],
        stats: dict[str, int],
    ) -> str:
        youtube_id = row["youtube_id"]
        if youtube_id and youtube_id in dest_youtube_ids:
            return "tracks_skipped"

        source_file = self._resolve_bundle_media_path(row["local_path"], bundle_root)
        if source_file is None or not source_file.is_file():
            logger.warning("File bundle assente, saltato: %s", row["local_path"])
            return "tracks_skipped"

        dest_file = self._unique_dest_path(config.DOWNLOAD_DIR, source_file.name)
        if not dest_file.exists():
            shutil.copy2(source_file, dest_file)
            stats["files_copied"] += 1

        with self._conn:
            cursor = self._conn.execute(
                """INSERT INTO tracks
                   (title, artist, youtube_id, local_path, source, track_type,
                    duration_sec, start_offset_sec, metadata_confirmed, metadata_confirmed_at)
                   VALUES (?, ?, ?, ?, ?, 'karaoke', ?, ?, ?, ?)""",
                (
                    row["title"],
                    row["artist"],
                    youtube_id,
                    str(dest_file),
                    row["source"] or "local",
                    row["duration_sec"],
                    row["start_offset_sec"] or 0,
                    row["metadata_confirmed"] or 0,
                    row["metadata_confirmed_at"],
                ),
            )
            new_id = cursor.lastrowid

        if youtube_id:
            dest_youtube_ids.add(youtube_id)
        id_map[int(row["id"])] = int(new_id)
        return "tracks_added"

    @staticmethod
    def _resolve_bundle_media_path(local_path: str, bundle_root: Path) -> Path | None:
        raw = Path(local_path)
        candidates = [
            bundle_root / "media" / "downloads" / raw.name,
            bundle_root / raw.name,
        ]
        if "downloads" in raw.parts:
            idx = raw.parts.index("downloads")
            rel_parts = raw.parts[idx + 1 :]
            if rel_parts:
                candidates.insert(0, bundle_root / "media" / "downloads" / Path(*rel_parts))
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return None

    @staticmethod
    def _unique_dest_path(dest_dir: Path, filename: str) -> Path:
        candidate = dest_dir / filename
        if not candidate.exists():
            return candidate
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        index = 1
        while True:
            alt = dest_dir / f"{stem} ({index}){suffix}"
            if not alt.exists():
                return alt
            index += 1

    def _import_playlists(
        self,
        bundle_conn: sqlite3.Connection,
        id_map: dict[int, int],
        stats: dict[str, int],
    ) -> None:
        playlists = bundle_conn.execute(
            "SELECT id, name FROM playlists WHERE mode = 'karaoke' ORDER BY name COLLATE NOCASE"
        ).fetchall()
        dest_names = {
            row["name"]: row["id"]
            for row in self._conn.execute(
                "SELECT id, name FROM playlists WHERE mode = 'karaoke'"
            ).fetchall()
        }

        for playlist in playlists:
            name = playlist["name"]
            if name in dest_names:
                dest_playlist_id = dest_names[name]
            else:
                with self._conn:
                    cursor = self._conn.execute(
                        "INSERT INTO playlists (name, mode) VALUES (?, 'karaoke')",
                        (name,),
                    )
                    dest_playlist_id = cursor.lastrowid
                dest_names[name] = dest_playlist_id
                stats["playlists_created"] += 1

            bundle_tracks = bundle_conn.execute(
                "SELECT track_id FROM playlist_tracks WHERE playlist_id = ? ORDER BY position",
                (playlist["id"],),
            ).fetchall()

            max_pos = self._conn.execute(
                "SELECT COALESCE(MAX(position), 0) FROM playlist_tracks WHERE playlist_id = ?",
                (dest_playlist_id,),
            ).fetchone()[0]

            for bundle_track in bundle_tracks:
                new_track_id = id_map.get(bundle_track["track_id"])
                if new_track_id is None:
                    continue
                exists = self._conn.execute(
                    "SELECT 1 FROM playlist_tracks WHERE playlist_id = ? AND track_id = ?",
                    (dest_playlist_id, new_track_id),
                ).fetchone()
                if exists:
                    continue
                max_pos += 1
                with self._conn:
                    self._conn.execute(
                        "INSERT INTO playlist_tracks (playlist_id, track_id, position) "
                        "VALUES (?, ?, ?)",
                        (dest_playlist_id, new_track_id, max_pos),
                    )
                stats["playlist_tracks_added"] += 1

    def _import_known_artists(self, bundle_conn: sqlite3.Connection, stats: dict[str, int]) -> None:
        if self._artist_registry is None or not hasattr(self._artist_registry, "register"):
            return
        rows = bundle_conn.execute("SELECT name FROM known_artists").fetchall()
        for row in rows:
            if self._artist_registry.register(row["name"], source="import"):
                stats["artists_added"] += 1
