"""Registro artisti noti: lookup fuzzy e apprendimento da correzioni manuali."""

import logging
import sqlite3
from pathlib import Path

from rapidfuzz import fuzz

import config
from utils.name_normalize import normalize_name

logger = logging.getLogger(__name__)

_CHANNEL_BLOCKLIST = frozenset(
    normalize_name(name)
    for name in (
        "Sing King",
        "Karafun",
        "KaraFun",
        "Party Tyme",
        "Zoom Karaoke",
        "ProSound",
        "Karaoke Academy",
        "Karaoke Italiano",
        "Best Original Karaoke",
        "Sunfly Karaoke",
        "Mr Entertainer",
        "Zoom Entertainments",
    )
)


class ArtistRegistryService:
    """Catalogo artisti per disambiguare artista/titolo nel parsing metadati."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._by_normalized: dict[str, str] = {}
        self._reload_cache()

    def count(self) -> int:
        """Numero di artisti nel registro."""
        return len(self._by_normalized)

    def reload(self) -> None:
        """Ricarica la cache dal database."""
        self._reload_cache()

    def ensure_seed_loaded(self) -> int:
        """Importa il seed bundled se il registro è vuoto; ritorna i nomi aggiunti."""
        if self.count() > 0:
            return 0
        added = self.import_from_file(config.ARTIST_REGISTRY_SEED_PATH, source="seed")
        logger.info("Bootstrap registro artisti: %d nomi dal seed", added)
        return added

    def import_from_file(self, path: Path, *, source: str = "import") -> int:
        """Importa nomi da file testo (un artista per riga)."""
        if not path.is_file():
            logger.warning("File seed artisti non trovato: %s", path)
            return 0
        names = [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        return self.register_many(names, source=source)

    def register_many(self, names: list[str], *, source: str = "import") -> int:
        """Registra più artisti; ritorna quanti nuovi record sono stati inseriti."""
        added = 0
        for name in names:
            if self.register(name, source=source):
                added += 1
        return added

    def register(self, name: str, *, source: str = "manual") -> bool:
        """Aggiunge o incrementa un artista; ritorna True se era un nome nuovo."""
        cleaned = (name or "").strip()
        if not cleaned:
            return False
        key = normalize_name(cleaned)
        if not key or key in _CHANNEL_BLOCKLIST:
            return False
        if key in self._by_normalized:
            with self._conn:
                self._conn.execute(
                    "UPDATE known_artists SET use_count = use_count + 1, "
                    "updated_at = CURRENT_TIMESTAMP WHERE name_normalized = ?",
                    (key,),
                )
            return False
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO known_artists (name, name_normalized, source)
                VALUES (?, ?, ?)
                ON CONFLICT(name_normalized) DO UPDATE SET
                    use_count = use_count + 1,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (cleaned, key, source),
            )
        self._by_normalized[key] = cleaned
        return True

    def match(self, candidate: str) -> str | None:
        """Ritorna il nome canonico se `candidate` corrisponde a un artista noto."""
        cleaned = (candidate or "").strip()
        if not cleaned:
            return None
        key = normalize_name(cleaned)
        if not key or key in _CHANNEL_BLOCKLIST:
            return None
        exact = self._by_normalized.get(key)
        if exact:
            return exact
        return self._fuzzy_match(key)

    def disambiguate(self, first: str, second: str) -> tuple[str, str]:
        """Sceglie quale segmento è l'artista usando il registro."""
        first_clean = first.strip()
        second_clean = second.strip()
        if normalize_name(first_clean) in _CHANNEL_BLOCKLIST:
            return "", second_clean
        match_first = self.match(first_clean)
        match_second = self.match(second_clean)
        if match_first and not match_second:
            return match_first, second_clean
        if match_second and not match_first:
            return match_second, first_clean
        if match_first and match_second:
            return match_first, second_clean
        return first_clean, second_clean

    def bootstrap_from_tracks(self) -> int:
        """Importa artisti distinti già presenti in catalogo (esclusi canali karaoke)."""
        rows = self._conn.execute(
            "SELECT DISTINCT artist FROM tracks WHERE artist IS NOT NULL AND artist != ''"
        ).fetchall()
        names = [row["artist"] for row in rows]
        added = self.register_many(names, source="import")
        logger.info("Bootstrap da catalogo: %d artisti nuovi", added)
        return added

    def _reload_cache(self) -> None:
        rows = self._conn.execute(
            "SELECT name, name_normalized FROM known_artists"
        ).fetchall()
        self._by_normalized = {row["name_normalized"]: row["name"] for row in rows}

    def _fuzzy_match(self, normalized_key: str) -> str | None:
        if not self._by_normalized:
            return None
        best_name: str | None = None
        best_score = 0
        for key, display in self._by_normalized.items():
            score = fuzz.token_set_ratio(normalized_key, key)
            if score > best_score:
                best_score = score
                best_name = display
        if best_score >= config.ARTIST_MATCH_THRESHOLD:
            return best_name
        return None
