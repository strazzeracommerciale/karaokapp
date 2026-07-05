"""Arricchisce known_artists.txt con artisti da Karaoke Version (API affiliate Recisio).

Fonte: https://www.versione-karaoke.it/api/artist/
Documentazione: https://affiliate.recisio.com/karaoke-version/webservice.html

Usa affiliateId=77 come negli esempi pubblici Recisio. Scarica solo nomi artista
(per disambiguazione metadati locali), non brani né file audio.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = ROOT / "data" / "seeds" / "known_artists.txt"
CHECKPOINT_PATH = ROOT / "data" / "seeds" / ".kv_fetch_checkpoint.json"
KV_API_IT = "https://www.versione-karaoke.it/api/artist/"
AFFILIATE_ID = 77
PAGE_SIZE = 100
REQUEST_DELAY_SEC = 0.65
RATE_LIMIT_INITIAL_BACKOFF_SEC = 8.0
RATE_LIMIT_MAX_BACKOFF_SEC = 120.0

_SKIP_EXACT = frozenset(
    name.casefold()
    for name in (
        "Traditional",
        "Christmas Carol",
        "Various Artists",
        "Unknown",
        "Karaoke",
        "Instrumental",
        "Soundtrack",
        "Musical",
        "Children's Music",
        "Miscellaneous",
        "Duets",
        "Duett",
    )
)

_SKIP_PATTERN = re.compile(
    r"\b(karaoke|backing track|tribute|cover version|instrumental|soundtrack)\b",
    re.I,
)


def _fetch_page(offset: int) -> dict:
    """Scarica una pagina; su HTTP 429 attende e riparte sulla stessa offset."""
    query = json.dumps(
        {
            "affiliateId": AFFILIATE_ID,
            "function": "list",
            "parameters": {"limit": PAGE_SIZE, "offset": offset},
        },
        separators=(",", ":"),
    )
    url = f"{KV_API_IT}?query={urllib.parse.quote(query)}"
    backoff = RATE_LIMIT_INITIAL_BACKOFF_SEC
    while True:
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                logger.warning(
                    "HTTP 429 offset=%s — attendo %.0fs e riparto…",
                    offset,
                    backoff,
                )
                time.sleep(backoff)
                backoff = min(backoff * 1.5, RATE_LIMIT_MAX_BACKOFF_SEC)
                continue
            raise
        except urllib.error.URLError as exc:
            logger.warning(
                "Errore rete offset=%s: %s — attendo 15s e riparto…",
                offset,
                exc,
            )
            time.sleep(15)


def _save_checkpoint(
    *,
    names: list[str],
    next_offset: int,
    total: int,
) -> None:
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_PATH.write_text(
        json.dumps(
            {"names": names, "next_offset": next_offset, "total": total},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _load_checkpoint() -> tuple[list[str], int, int | None]:
    if not CHECKPOINT_PATH.is_file():
        return [], 0, None
    data = json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
    names = list(data.get("names") or [])
    offset = int(data.get("next_offset") or 0)
    total = data.get("total")
    return names, offset, int(total) if total is not None else None


def fetch_karaoke_version_artists(*, resume: bool = True) -> list[str]:
    """Scarica tutti gli artisti dal catalogo italiano Karaoke Version."""
    names: list[str] = []
    seen: set[str] = set()
    offset = 0
    total: int | None = None

    if resume:
        cached, offset, cached_total = _load_checkpoint()
        if cached:
            names = cached
            seen = {n.casefold() for n in names}
            total = cached_total
            logger.info(
                "Ripresa checkpoint: offset=%s, %d nomi in cache",
                offset,
                len(names),
            )

    while total is None or offset < total:
        data = _fetch_page(offset)
        if total is None:
            total = int(data.get("totalLength") or 0)
            logger.info("Karaoke Version IT: %d artisti totali in catalogo", total)
        batch = data.get("artists") or []
        if not batch:
            logger.warning("Batch vuoto a offset=%s, interrompo.", offset)
            break
        added = 0
        for item in batch:
            name = (item.get("name") or "").strip()
            if not name:
                continue
            key = name.casefold()
            if key in seen or key in _SKIP_EXACT:
                continue
            if _SKIP_PATTERN.search(name):
                continue
            seen.add(key)
            names.append(name)
            added += 1
        offset += PAGE_SIZE
        if offset % 1000 == 0 or offset >= total:
            logger.info(
                "Progresso KV: offset=%s/%s — %d nomi utili (+ %d in pagina)",
                offset,
                total,
                len(names),
                added,
            )
        _save_checkpoint(names=names, next_offset=offset, total=total)
        time.sleep(REQUEST_DELAY_SEC)

    if CHECKPOINT_PATH.is_file():
        CHECKPOINT_PATH.unlink()
    logger.info("Karaoke Version: %d nomi artista utili dopo filtro", len(names))
    return names


def _read_existing_seed(path: Path) -> list[str]:
    if not path.is_file():
        return []
    lines: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if text and not text.startswith("#"):
            lines.append(text)
    return lines


def merge_seed(base_names: list[str], fetched_names: list[str]) -> list[str]:
    """Unisce liste preservando ordine: prima seed esistente, poi KV."""
    merged: list[str] = []
    seen: set[str] = set()
    for name in (*base_names, *fetched_names):
        cleaned = name.strip()
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        merged.append(cleaned)
    return merged


def write_seed(path: Path, names: list[str], *, kv_count: int, base_count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = [
        "# Registro bootstrap artisti — KaraokeManager",
        "# Base curata + Karaoke Version (versione-karaoke.it API Recisio)",
        f"# Totale: {len(names)} (base ~{base_count}, da KV ~{kv_count} nuovi)",
        "# Rigenerabile: python build/enrich_artist_seed_from_kv.py",
        "",
    ]
    path.write_text("\n".join(header + names) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Arricchisce seed artisti da Karaoke Version")
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Ignora checkpoint e riscarica da zero",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if args.no_resume and CHECKPOINT_PATH.is_file():
        CHECKPOINT_PATH.unlink()

    base = _read_existing_seed(SEED_PATH)
    if not base:
        import sys

        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from generate_artist_seed import ARTISTS

        base = list(ARTISTS)
        logger.info("Seed file assente, uso tupla base generate_artist_seed (%d)", len(base))

    kv_names = fetch_karaoke_version_artists(resume=not args.no_resume)
    merged = merge_seed(base, kv_names)
    base_keys = {n.casefold() for n in base}
    kv_new = sum(1 for n in kv_names if n.casefold() not in base_keys)
    write_seed(SEED_PATH, merged, kv_count=kv_new, base_count=len(base))
    print(f"Seed aggiornato: {SEED_PATH}")
    print(f"  Base:     {len(base)}")
    print(f"  Da KV:    {len(kv_names)} scaricati ({kv_new} nuovi vs base)")
    print(f"  Totale:   {len(merged)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
