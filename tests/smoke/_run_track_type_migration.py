"""Smoke test one-shot migrazione track_type."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from db.db_core import close, get_conn, migrate

migrate()
conn = get_conn()
cols = [row[1] for row in conn.execute("PRAGMA table_info(tracks)").fetchall()]
assert "track_type" in cols, "COLONNA MANCANTE"
bad = conn.execute(
    "SELECT COUNT(*) FROM tracks WHERE track_type != 'karaoke'"
).fetchone()[0]
assert bad == 0, f"BRANI CON TIPO ERRATO: {bad}"
print("Migrazione OK")
close()
