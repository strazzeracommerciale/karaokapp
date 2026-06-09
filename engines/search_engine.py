"""Ricerca fuzzy locale e YouTube unificata."""

import logging
import sqlite3
from typing import Literal

import yt_dlp
from rapidfuzz import fuzz, process

import config

logger = logging.getLogger(__name__)

TrackType = Literal["karaoke", "dj"]


class SearchEngine:
    """Motore di ricerca su catalogo locale e YouTube."""

    def __init__(
        self,
        db_conn: sqlite3.Connection,
        track_type: TrackType = "karaoke",
        enable_youtube: bool = True,
        yt_search_prefix: str | None = None,
    ) -> None:
        """Inizializza con connessione DB e contesto track_type per i filtri."""
        self._conn = db_conn
        self._track_type = track_type
        self._enable_youtube = enable_youtube
        if yt_search_prefix is not None:
            self._yt_prefix = yt_search_prefix
        elif track_type == "dj":
            self._yt_prefix = config.DJ_YT_SEARCH_PREFIX
        else:
            self._yt_prefix = config.YT_SEARCH_PREFIX

    def search_local(self, query: str, track_type: TrackType | None = None) -> list[dict]:
        """Cerca nel catalogo locale con rapidfuzz su title+artist.

        Filtra per `track_type` (default: tipo configurato all'istanza).
        """
        if not query.strip():
            return []
        effective_type = track_type or self._track_type
        rows = self._conn.execute(
            """SELECT id, title, artist, local_path, source, duration_sec, track_type
               FROM tracks WHERE track_type = ?""",
            (effective_type,),
        ).fetchall()
        candidates: list[tuple[str, dict]] = []
        for row in rows:
            label = f"{row['title']} {row['artist'] or ''}".strip()
            candidates.append(
                (
                    label,
                    {
                        "id": row["id"],
                        "title": row["title"],
                        "artist": row["artist"],
                        "local_path": row["local_path"],
                        "source": row["source"],
                        "duration_sec": row["duration_sec"],
                        "track_type": row["track_type"],
                    },
                )
            )
        if not candidates:
            return []
        labels = [candidate[0] for candidate in candidates]
        matches = process.extract(
            query,
            labels,
            scorer=fuzz.WRatio,
            score_cutoff=config.FUZZY_THRESHOLD,
        )
        results: list[dict] = []
        for _label, score, index in matches:
            item = candidates[index][1].copy()
            item["score"] = score
            results.append(item)
        logger.debug(
            "Ricerca locale '%s' (type=%s): %d risultati",
            query,
            effective_type,
            len(results),
        )
        return results

    def search_youtube(
        self,
        query: str,
        limit: int | None = None,
        prefix: str | None = None,
    ) -> list[dict]:
        """Cerca su YouTube via yt-dlp extract_info."""
        if not query.strip():
            return []
        search_limit = limit if limit is not None else config.YT_SEARCH_LIMIT
        effective_query = query.strip()
        effective_prefix = self._yt_prefix if prefix is None else prefix
        if effective_prefix and effective_prefix.lower() not in effective_query.lower():
            effective_query = f"{effective_prefix} {effective_query}"
        search_url = f"ytsearch{search_limit}:{effective_query}"
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": True,
            "ignoreerrors": True,
        }
        results: list[dict] = []
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(search_url, download=False)
            entries = info.get("entries", []) if info else []
            for entry in entries:
                if entry is None:
                    continue
                youtube_id = entry.get("id", "")
                stream_url = ""  # recuperato on-demand da ytdlp_engine.get_stream_url()
                results.append(
                    {
                        "youtube_id": youtube_id,
                        "title": entry.get("title", ""),
                        "artist": entry.get("uploader", entry.get("channel", "")),
                        "source": "youtube",
                        "duration_sec": entry.get("duration"),
                        "stream_url": stream_url,
                        "track_type": self._track_type,
                    }
                )
        except Exception as exc:
            logger.error("Ricerca YouTube fallita per '%s': %s", query, exc)
        logger.debug("Ricerca YouTube '%s': %d risultati", query, len(results))
        return results

    def search_unified(
        self,
        query: str,
        yt_limit: int | None = None,
        track_type: TrackType | None = None,
        yt_prefix: str | None = None,
    ) -> list[dict]:
        """Combina i risultati locali (in cima) con quelli YouTube.

        I locali sono sempre mostrati per primi; YouTube viene comunque
        interrogato (se abilitato) così l'operatore può scegliere anche brani
        non ancora in libreria, indipendentemente da quanti locali corrispondono.
        `yt_limit` permette di ampliare progressivamente i risultati YouTube.
        """
        effective_type = track_type or self._track_type
        effective_prefix = self._yt_prefix if yt_prefix is None else yt_prefix
        local_results = self.search_local(query, track_type=effective_type)
        for item in local_results:
            item["origin"] = "local"
        if not self._enable_youtube:
            return local_results
        youtube_results = self.search_youtube(
            query, limit=yt_limit, prefix=effective_prefix
        )
        for item in youtube_results:
            item["origin"] = "youtube"
            item["track_type"] = effective_type
        return local_results + youtube_results
