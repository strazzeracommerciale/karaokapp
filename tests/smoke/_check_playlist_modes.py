"""Verifica playlist non-karaoke nel DB di produzione."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from db.db_core import close, get_conn

conn = get_conn()
rows = conn.execute(
    "SELECT id, name, mode FROM playlists WHERE mode != 'karaoke' OR mode IS NULL"
).fetchall()
print(f"Playlist non-karaoke: {len(rows)}")
for row in rows:
    print(dict(row))
close()
