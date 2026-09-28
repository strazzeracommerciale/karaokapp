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

from utils.name_normalize import normalize_name

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
        "Karaoke Academy",
        "Karaoke Italiano",
    )
)
_SOURCE_TAIL_RE = re.compile(r"^(from|by)\b", re.IGNORECASE)
_CHANNEL_SEGMENT_KEYS = frozenset(
    {
        "zoom",
        "karafun",
        "sing king",
        "party tyme",
        "prosound",
        "karaoke academy",
        "karaoke italiano",
        "sunfly",
        "mr entertainer",
        "cantatube",
    }
)
_SEARCH_NOISE = (
    r"\bacademy\s+italia\b",
    r"\bacademy\b",
    r"\bdemo\b",
    r"\boriginal\s+key\b",
    r"\bno\s+guide\s+melody\b",
    r"\bcori\s+originali\b",
    r"\bsongs?\s+with\b",
)


def _strip_decorations(text: str) -> str:
    """Toglie emoji e spazi lasciati dai titoli dei canali karaoke."""
    cleaned = _EMOJI_RE.sub(" ", text or "")
    return _WS_RE.sub(" ", cleaned).strip(_STRIP_CHARS)


_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\u2600-\u27BF"
    "\uFE0F"
    "]+"
)


def searchable_title(raw: str) -> str:
    """Testo da cercare nel catalogo: tiene artista e titolo, toglie il rumore karaoke."""
    text = _strip_decorations(raw or "")
    text = _EXT_RE.sub("", text)
    text = re.sub(r"\[[^\]]*\]", " ", text)
    text = re.sub(r"[()]", " ", text)
    for pattern in _NOISE_PATTERNS:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    for pattern in _SEARCH_NOISE:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    for channel in _CHANNEL_SEGMENT_KEYS:
        text = re.sub(rf"\b{re.escape(channel)}\b", " ", text, flags=re.IGNORECASE)
    return _WS_RE.sub(" ", text).strip(_STRIP_CHARS)


def _useful_segments(parts: list[str]) -> list[str]:
    """Toglie code di canale («from Zoom») e lascia almeno un segmento."""
    useful: list[str] = []
    for segment in parts:
        cleaned = segment.strip()
        if not cleaned:
            continue
        if _SOURCE_TAIL_RE.match(cleaned):
            continue
        if cleaned.lower() in _KNOWN_CHANNEL_PREFIXES:
            continue
        if normalize_name(cleaned) in _CHANNEL_SEGMENT_KEYS:
            continue
        useful.append(cleaned)
    return useful or parts


def parse_artist_title(
    raw: str,
    registry: object | None = None,
) -> tuple[str, str]:
    """Estrae (artista, titolo) da un titolo YouTube/file karaoke."""
    parts = _useful_segments(_title_segments(raw))
    parenthetical_artist = ""
    if registry is not None and hasattr(registry, "match"):
        for group in re.findall(r"\(([^)]+)\)", raw or ""):
            match = registry.match(group.strip())
            if match:
                parenthetical_artist = match
                break
    if (
        len(parts) >= 3
        and registry is not None
        and hasattr(registry, "match")
    ):
        last_artist = registry.match(parts[-1])
        first_artist = registry.match(parts[0])
        if last_artist and not first_artist:
            middle = " ".join(parts[1:-1]).strip()
            if middle:
                return _strip_decorations(last_artist), _strip_decorations(middle)
    if len(parts) >= 2:
        first, second = parts[0], parts[1]
        if registry is not None and hasattr(registry, "disambiguate"):
            artist, title = registry.disambiguate(first, second)
            return _strip_decorations(artist), _strip_decorations(title)
        if first.lower() in _KNOWN_CHANNEL_PREFIXES:
            return "", _strip_decorations(second)
        return _strip_decorations(first), _strip_decorations(second)
    if len(parts) == 1:
        if registry is not None and hasattr(registry, "split_leading_artist"):
            split = registry.split_leading_artist(parts[0])
            if split is not None:
                return _strip_decorations(split[0]), _strip_decorations(split[1])
        if parenthetical_artist:
            return parenthetical_artist, _strip_decorations(parts[0])
        return "", _strip_decorations(parts[0])
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
