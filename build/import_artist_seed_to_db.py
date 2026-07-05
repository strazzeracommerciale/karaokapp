"""Importa/aggiorna known_artists.txt nel database locale (merge, non cancella)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from db import db_core
from services.artist_registry_service import ArtistRegistryService


def main() -> int:
    db_core.migrate()
    conn = db_core.get_conn()
    registry = ArtistRegistryService(conn)
    before = registry.count()
    added = registry.import_from_file(config.ARTIST_REGISTRY_SEED_PATH, source="seed")
    registry.reload()
    print(f"Registro artisti: {before} -> {registry.count()} (+{added} nuovi)")
    db_core.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
