"""Filtro libreria per artista/titolo con fallback su nome file."""

from __future__ import annotations

from pathlib import Path


def filter_tracks(
    tracks: list[dict],
    artist_query: str = "",
    title_query: str = "",
    *,
    allow_fallback: bool = True,
) -> tuple[list[dict], bool]:
    """Restituisce i brani che corrispondono ai filtri parziali.

    Prima cerca in artista e titolo del DB; se non trova nulla e ``allow_fallback``,
    ripete la ricerca anche nel nome file locale.
    """
    artist_q = artist_query.strip().lower()
    title_q = title_query.strip().lower()
    if not artist_q and not title_q:
        return tracks, False

    strict = [track for track in tracks if _matches_strict(track, artist_q, title_q)]
    if strict or not allow_fallback:
        return strict, False

    broad = [track for track in tracks if _matches_broad(track, artist_q, title_q)]
    return broad, True


def _matches_strict(track: dict, artist_q: str, title_q: str) -> bool:
    artist = (track.get("artist") or "").lower()
    title = (track.get("title") or "").lower()
    if artist_q and artist_q not in artist:
        return False
    if title_q and title_q not in title:
        return False
    return True


def _matches_broad(track: dict, artist_q: str, title_q: str) -> bool:
    filename = _filename_haystack(track)
    haystack = f"{track.get('title', '')} {(track.get('artist') or '')} {filename}".lower()
    terms = [query for query in (artist_q, title_q) if query]
    return all(term in haystack for term in terms)


def _filename_haystack(track: dict) -> str:
    local_path = track.get("local_path") or ""
    if not local_path:
        return ""
    return Path(local_path).stem.lower()
