"""Smoke test database layer."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from db.db_core import get_conn, migrate


def test_migrate() -> None:
    """Verifica migrazione schema."""
    migrate()
    conn = get_conn()
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    names = {row[0] for row in tables}
    assert "tracks" in names
    assert "queue" in names


if __name__ == "__main__":
    test_migrate()
    print("DB smoke test OK")
