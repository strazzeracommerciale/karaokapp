"""Conferma artista/titolo sul catalogo iTunes. Nessuna ipotesi se il riscontro non è netto."""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request

import re

from rapidfuzz import fuzz

from utils.name_normalize import normalize_name
from utils.text import searchable_title

logger = logging.getLogger(__name__)

_MATCH_THRESHOLD = 92
_TIMEOUT_SEC = 5
_USER_AGENT = "KaraokeManager"
_FEAT_RE = re.compile(r"\b(feat\.?|ft\.?|featuring|&)\b", re.IGNORECASE)
_RECORDING_TAG_RE = re.compile(
    r"\s*\[[^\]]*(?:live|remix|radio edit|remaster(?:ed)?)[^\]]*\]\s*",
    re.IGNORECASE,
)


def _words(text: str) -> list[str]:
    return [word for word in normalize_name(text).split() if word]


def _phrase_in(haystack: list[str], needle: list[str]) -> bool:
    if not needle or len(needle) > len(haystack):
        return False
    width = len(needle)
    for index in range(len(haystack) - width + 1):
        if haystack[index : index + width] == needle:
            return True
    return False


def _primary_artist_words(artist: str) -> list[str]:
    primary = _FEAT_RE.split(artist, maxsplit=1)[0]
    return _words(primary)


def match_title_contains_result(
    raw_title: str,
    results: list[dict],
) -> tuple[str, str] | None:
    """Accetta un brano solo se artista e titolo compaiono entrambi nel titolo originale."""
    haystack = _words(raw_title)
    accepted: list[tuple[int, str, str]] = []
    for result in results:
        catalog_artist = str(result.get("artistName") or "").strip()
        catalog_title = str(result.get("trackName") or "").strip()
        artist_words = _primary_artist_words(catalog_artist)
        title_words = _primary_artist_words(catalog_title)
        if not artist_words or not title_words:
            continue
        if len(title_words) == 1 and len(title_words[0]) < 4:
            continue
        if not _phrase_in(haystack, artist_words):
            continue
        if not _phrase_in(haystack, title_words):
            continue
        accepted.append((len(title_words), catalog_artist, catalog_title))
    if not accepted:
        return None
    identities = {
        (normalize_name(item_artist), normalize_name(item_title))
        for _score, item_artist, item_title in accepted
    }
    artists = {artist_key for artist_key, _title_key in identities}
    if len(identities) != 1 and len(artists) != 1:
        return None
    _score, best_artist, best_title = max(accepted, key=lambda item: item[0])
    return best_artist, _RECORDING_TAG_RE.sub(" ", best_title).strip()


def lookup_song_in_title(raw_title: str) -> tuple[str, str] | None:
    """Cerca il titolo originale su iTunes e tiene il brano solo se i nomi ci sono dentro."""
    query_text = searchable_title(raw_title)
    if len(query_text) < 3:
        return None
    query = urllib.parse.urlencode(
        {"term": query_text[:160], "entity": "song", "limit": 8, "country": "it"}
    )
    url = f"https://itunes.apple.com/search?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SEC) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        logger.warning("Catalogo brani non disponibile: %s", exc)
        return None
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        return None
    match = match_title_contains_result(raw_title, results)
    if match is None:
        logger.info("Catalogo senza conferma nel titolo: %s", query_text)
        return None
    logger.info("Catalogo confermato dal titolo: %s — %s", match[0], match[1])
    return match


def match_catalog_results(
    artist: str,
    title: str,
    results: list[dict],
) -> tuple[str, str] | None:
    """Accetta un solo brano del catalogo se artista e titolo coincidono entrambi."""
    artist_key = normalize_name(artist)
    title_key = normalize_name(title)
    if not artist_key or not title_key or artist_key == title_key or len(title_key) < 2:
        return None

    accepted: list[tuple[int, str, str]] = []
    for result in results:
        catalog_artist = str(result.get("artistName") or "").strip()
        catalog_title = str(result.get("trackName") or "").strip()
        if not catalog_artist or not catalog_title:
            continue
        artist_score = fuzz.token_sort_ratio(artist_key, normalize_name(catalog_artist))
        title_score = fuzz.token_sort_ratio(title_key, normalize_name(catalog_title))
        if artist_score < _MATCH_THRESHOLD or title_score < _MATCH_THRESHOLD:
            continue
        accepted.append((artist_score + title_score, catalog_artist, catalog_title))

    if not accepted:
        return None
    identities = {
        (normalize_name(item_artist), normalize_name(item_title))
        for _score, item_artist, item_title in accepted
    }
    if len(identities) != 1:
        return None
    _score, best_artist, best_title = max(accepted, key=lambda item: item[0])
    return best_artist, best_title


def lookup_confirmed_song(artist: str, title: str) -> tuple[str, str] | None:
    """Cerca su iTunes e restituisce i nomi canonici solo se il riscontro è univoco."""
    artist = (artist or "").strip()
    title = (title or "").strip()
    if not artist or not title:
        return None
    query = urllib.parse.urlencode(
        {"term": f"{artist} {title}", "entity": "song", "limit": 5, "country": "it"}
    )
    url = f"https://itunes.apple.com/search?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SEC) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        logger.warning("Catalogo brani non disponibile: %s", exc)
        return None
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        return None
    match = match_catalog_results(artist, title, results)
    if match is None:
        logger.info("Catalogo senza conferma univoca: %s — %s", artist, title)
        return None
    logger.info("Catalogo confermato: %s — %s", match[0], match[1])
    return match
