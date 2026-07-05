"""Aggiornamento batch di artista/titolo (e opzionale rinomina file) su archivio esistente."""

import logging
import re
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from engines.ytdlp_engine import YtdlpEngine
from services.metadata_refresh_models import TrackRefreshOutcome
from utils.text import build_download_basename
from utils.track_metadata import resolve_artist_title

logger = logging.getLogger(__name__)

TrackType = Literal["karaoke", "dj"]

_YT_ID_IN_STEM = re.compile(r"\[([a-zA-Z0-9_-]{11})\]$")
_YT_ID_ONLY_STEM = re.compile(r"^[a-zA-Z0-9_-]{11}$")


def youtube_id_from_path(path: Path) -> str | None:
    """Estrae l'id YouTube dal nome file (vecchio `id.mp4` o nuovo `… [id].ext`)."""
    stem = path.stem.strip()
    match = _YT_ID_IN_STEM.search(stem)
    if match:
        return match.group(1)
    if _YT_ID_ONLY_STEM.match(stem):
        return stem
    return None


class MetadataRefreshService:
    """Ricalcola metadati libreria e, opzionalmente, rinomina i file locali."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        ytdlp: YtdlpEngine | None = None,
        artist_registry: object | None = None,
    ) -> None:
        self._conn = conn
        self._ytdlp = ytdlp or YtdlpEngine()
        self._artist_registry = artist_registry

    def refresh_all(
        self,
        *,
        rename_files: bool = False,
        parse_only: bool = False,
        dry_run: bool = False,
        track_type: TrackType | None = None,
        skip_confirmed: bool = True,
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> dict:
        """Aggiorna titolo/artista nel DB; opzionalmente rinomina i file su disco."""
        query = (
            "SELECT id, title, artist, youtube_id, local_path, track_type "
            "FROM tracks WHERE local_path IS NOT NULL AND local_path != ''"
        )
        params: list = []
        if track_type is not None:
            query += " AND track_type = ?"
            params.append(track_type)
        if skip_confirmed:
            query += " AND COALESCE(metadata_confirmed, 0) = 0"
        rows = self._conn.execute(query, tuple(params)).fetchall()

        stats = {
            "total": len(rows),
            "metadata_updated": 0,
            "files_renamed": 0,
            "unchanged": 0,
            "skipped": 0,
            "errors": 0,
        }
        outcomes: list[TrackRefreshOutcome] = []

        for index, row in enumerate(rows, start=1):
            if on_progress is not None:
                label = row["title"] or Path(row["local_path"]).stem
                on_progress(index, len(rows), label)
            try:
                outcome = self._refresh_one(
                    row,
                    rename_files=rename_files,
                    parse_only=parse_only,
                    dry_run=dry_run,
                )
                outcomes.append(outcome)
                if outcome.status == "updated":
                    stats["metadata_updated"] += 1
                elif outcome.status == "renamed":
                    stats["files_renamed"] += 1
                elif outcome.status == "unchanged":
                    stats["unchanged"] += 1
                elif outcome.status == "skipped":
                    stats["skipped"] += 1
                elif outcome.status == "error":
                    stats["errors"] += 1
            except Exception as exc:
                stats["errors"] += 1
                outcomes.append(
                    TrackRefreshOutcome(
                        track_id=row["id"],
                        status="error",
                        old_title=row["title"] or "",
                        old_artist=row["artist"],
                        new_title=row["title"] or "",
                        new_artist=row["artist"],
                        old_path=row["local_path"] or "",
                        message=str(exc),
                    )
                )
                logger.exception(
                    "Errore refresh track_id=%s: %s",
                    row["id"],
                    exc,
                )

        stats["outcomes"] = outcomes
        return stats

    def _refresh_one(
        self,
        row: sqlite3.Row,
        *,
        rename_files: bool,
        parse_only: bool,
        dry_run: bool,
    ) -> TrackRefreshOutcome:
        old_title = row["title"] or ""
        old_artist = row["artist"]
        old_path = row["local_path"] or ""

        path = Path(old_path)
        if not path.is_file():
            logger.warning("File assente, saltato: track_id=%s %s", row["id"], path)
            return TrackRefreshOutcome(
                track_id=row["id"],
                status="skipped",
                old_title=old_title,
                old_artist=old_artist,
                new_title=old_title,
                new_artist=old_artist,
                old_path=old_path,
                message="File assente",
            )

        youtube_id = row["youtube_id"] or youtube_id_from_path(path)
        metadata: dict | None = None
        if not parse_only and youtube_id:
            try:
                metadata = self._ytdlp.extract_metadata(youtube_id)
            except Exception as exc:
                logger.warning(
                    "Metadati YouTube non disponibili per %s: %s",
                    youtube_id,
                    exc,
                )

        raw_title = old_title or path.stem
        if metadata and metadata.get("title"):
            raw_title = metadata["title"]

        artist, title = resolve_artist_title(
            raw_title, metadata, registry=self._artist_registry
        )
        if not title:
            logger.warning("Titolo vuoto dopo parsing: track_id=%s", row["id"])
            return TrackRefreshOutcome(
                track_id=row["id"],
                status="skipped",
                old_title=old_title,
                old_artist=old_artist,
                new_title=old_title,
                new_artist=old_artist,
                old_path=old_path,
                message="Titolo vuoto dopo parsing",
            )

        db_artist = old_artist or None
        db_title = old_title or ""
        metadata_changed = (db_title != title) or (db_artist != artist)
        needs_yt_id_update = youtube_id and row["youtube_id"] != youtube_id

        new_path = path
        file_needs_rename = False
        if rename_files and youtube_id:
            basename = build_download_basename(artist, title, youtube_id)
            candidate = path.parent / f"{basename}{path.suffix.lower()}"
            if candidate.resolve() != path.resolve():
                file_needs_rename = True
                new_path = candidate

        if not metadata_changed and not file_needs_rename and not needs_yt_id_update:
            return TrackRefreshOutcome(
                track_id=row["id"],
                status="unchanged",
                old_title=old_title,
                old_artist=old_artist,
                new_title=title,
                new_artist=artist,
                old_path=old_path,
                new_path=str(path),
            )

        if dry_run:
            logger.info(
                "[dry-run] track_id=%s → %r / %r%s",
                row["id"],
                artist,
                title,
                f" | file → {new_path.name}" if file_needs_rename else "",
            )
            dry_status = "renamed" if file_needs_rename else "updated"
            return TrackRefreshOutcome(
                track_id=row["id"],
                status=dry_status,
                old_title=old_title,
                old_artist=old_artist,
                new_title=title,
                new_artist=artist,
                old_path=old_path,
                new_path=str(new_path),
                message="simulazione",
            )

        if file_needs_rename:
            if new_path.exists():
                logger.error(
                    "Rinomina impossibile, destinazione esistente: %s",
                    new_path,
                )
                return TrackRefreshOutcome(
                    track_id=row["id"],
                    status="error",
                    old_title=old_title,
                    old_artist=old_artist,
                    new_title=title,
                    new_artist=artist,
                    old_path=old_path,
                    new_path=str(new_path),
                    message="Destinazione file già esistente",
                )
            path.rename(new_path)
            logger.info("File rinominato: %s → %s", path.name, new_path.name)

        with self._conn:
            self._conn.execute(
                "UPDATE tracks SET title = ?, artist = ?, youtube_id = COALESCE(?, youtube_id), "
                "local_path = ?, metadata_confirmed = 0, metadata_confirmed_at = NULL "
                "WHERE id = ?",
                (title, artist, youtube_id, str(new_path), row["id"]),
            )

        final_status = "renamed" if file_needs_rename else "updated"
        return TrackRefreshOutcome(
            track_id=row["id"],
            status=final_status,
            old_title=old_title,
            old_artist=old_artist,
            new_title=title,
            new_artist=artist,
            old_path=old_path,
            new_path=str(new_path),
        )
