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


def clean_title(raw: str) -> str:
    """Restituisce una versione concisa e leggibile del titolo del brano."""
    if not raw:
        return ""
    text = _EXT_RE.sub("", raw.strip())
    text = _BRACKETS_RE.sub(" ", text)
    for pattern in _NOISE_PATTERNS:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    parts = [segment.strip(_STRIP_CHARS) for segment in _SEPARATORS_RE.split(text)]
    parts = [_WS_RE.sub(" ", segment) for segment in parts if segment.strip(_STRIP_CHARS)]
    if not parts:
        return _WS_RE.sub(" ", text).strip(_STRIP_CHARS) or raw.strip()
    if len(parts) == 1:
        return parts[0]
    # Formato più diffuso nei canali karaoke: "Artista - Titolo" → prendi il titolo.
    return parts[-1]
