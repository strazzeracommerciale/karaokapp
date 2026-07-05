"""Normalizzazione nomi per confronto fuzzy (case, accenti, spazi)."""

import re
import unicodedata

_WS_RE = re.compile(r"\s+")
_NON_WORD_RE = re.compile(r"[^\w\s&']", re.UNICODE)


def normalize_name(text: str) -> str:
    """Restituisce una chiave comparabile: minuscolo, senza accenti, spazi uniformi."""
    if not text:
        return ""
    lowered = text.strip().casefold()
    decomposed = unicodedata.normalize("NFD", lowered)
    without_marks = "".join(
        char for char in decomposed if unicodedata.category(char) != "Mn"
    )
    cleaned = _NON_WORD_RE.sub(" ", without_marks)
    return _WS_RE.sub(" ", cleaned).strip()
