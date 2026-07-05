"""Utility di testo per estrarre un titolo brano leggibile da nomi verbosi.

I titoli dei video/file karaoke sono spesso del tipo:
    "Vasco Rossi - Albachiara (Karaoke Version) [HD]"
    "Albachiara - Vasco Rossi | Base Musicale"
    "Sing King - Someone Like You (Karaoke)"

`clean_title` rimuove il "rumore" (parentesi, parole tipo karaoke/versione/HD…) e,
se restano due segmenti separati da trattino, assume il formato "Artista - Titolo"
restituendo il secondo segmento. È un'euristica: copre il caso più comune ma non
può essere infallibile sui nomi più irregolari.
"""

import re

_NOISE_PATTERNS = [
    r"\bkaraoke\b",
    r"\bkaraok[eé]\b",
    r"\bversione\b",
    r"\bversion\b",
    r"\bbase\s*musicale\b",
    r"\bbasi\b",
    r"\binstrumental\b",
    r"\bstrumentale\b",
    r"\blyrics?\b",
    r"\btesto\b",
    r"\bofficial\b",
    r"\bvideo\b",
    r"\baudio\b",
    r"\bhd\b",
    r"\b4k\b",
    r"\bfull\b",
    r"\bcover\b",
    r"\bremaster(?:ed)?\b",
    r"\bmade\s*famous\s*by\b",
    r"\bin\s*the\s*style\s*of\b",
    r"\bno\s*vocals?\b",
    r"\bbacking\s*track\b",
    r"\bminus\s*one\b",
    r"\bplayback\b",
    r"\bsing\s*king\b",
]

_EXT_RE = re.compile(r"\.(mp4|mkv|avi|webm|mp3|m4a|flac|wav|ogg)$", re.IGNORECASE)
_BRACKETS_RE = re.compile(r"[\(\[\{][^\)\]\}]*[\)\]\}]")
_SEPARATORS_RE = re.compile(r"\s*[-–—|]\s*")
_WS_RE = re.compile(r"\s+")
_STRIP_CHARS = " \t-–—|:/"
_INVALID_FS_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _title_segments(raw: str) -> list[str]:
    """Segmenti artista/titolo ripuliti dal rumore tipico dei titoli karaoke."""
    if not raw:
        return []
    text = _EXT_RE.sub("", raw.strip())
    text = _BRACKETS_RE.sub(" ", text)
    for pattern in _NOISE_PATTERNS:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    parts = [segment.strip(_STRIP_CHARS) for segment in _SEPARATORS_RE.split(text)]
    return [_WS_RE.sub(" ", segment) for segment in parts if segment.strip(_STRIP_CHARS)]


_KNOWN_CHANNEL_PREFIXES = frozenset(
    name.lower()
    for name in (
        "Sing King",
        "Karafun",
        "Party Tyme",
        "Zoom Karaoke",
        "ProSound",
        "KaraFun",
    )
)


def parse_artist_title(
    raw: str,
    registry: object | None = None,
) -> tuple[str, str]:
    """Estrae (artista, titolo) da un titolo YouTube/file karaoke."""
    parts = _title_segments(raw)
    if len(parts) >= 2:
        first, second = parts[0], parts[-1]
        if registry is not None and hasattr(registry, "disambiguate"):
            return registry.disambiguate(first, second)
        if first.lower() in _KNOWN_CHANNEL_PREFIXES:
            return "", second
        return first, second
    if len(parts) == 1:
        return "", parts[0]
    cleaned = _WS_RE.sub(" ", raw or "").strip(_STRIP_CHARS)
    return "", cleaned


def sanitize_filename_component(text: str, max_len: int = 80) -> str:
    """Rimuove caratteri non validi su Windows e tronca la lunghezza."""
    cleaned = _INVALID_FS_CHARS_RE.sub("", text or "")
    cleaned = _WS_RE.sub(" ", cleaned).strip(" .")
    if max_len > 0:
        cleaned = cleaned[:max_len].strip(" .")
    return cleaned


def format_track_display(
    title: str,
    artist: str | None = None,
    *,
    suffix: str = "",
) -> str:
    """Etichetta UI: «Artista — Titolo» (solo titolo se artista assente)."""
    cleaned_title = (title or "").strip()
    cleaned_artist = (artist or "").strip()
    if cleaned_artist and cleaned_title:
        body = f"{cleaned_artist} — {cleaned_title}"
    elif cleaned_artist:
        body = cleaned_artist
    else:
        body = cleaned_title
    return f"{body}{suffix}"


def build_download_basename(artist: str, title: str, youtube_id: str) -> str:
    """Nome file univoco: Artista - Titolo [youtube_id] (fallback su id se titolo assente)."""
    artist_part = sanitize_filename_component(artist)
    title_part = sanitize_filename_component(title) or youtube_id
    if artist_part:
        base = f"{artist_part} - {title_part} [{youtube_id}]"
    else:
        base = f"{title_part} [{youtube_id}]"
    return sanitize_filename_component(base, max_len=200) or youtube_id


def clean_title(raw: str) -> str:
    """Restituisce una versione concisa e leggibile del titolo del brano."""
    _artist, title = parse_artist_title(raw)
    if title:
        return title
    if not raw:
        return ""
    text = _EXT_RE.sub("", raw.strip())
    text = _BRACKETS_RE.sub(" ", text)
    for pattern in _NOISE_PATTERNS:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    return _WS_RE.sub(" ", text).strip(_STRIP_CHARS) or raw.strip()
