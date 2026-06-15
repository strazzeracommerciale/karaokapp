"""Connessione SQLite e migrazione schema per KaraokeManager."""

import logging
import shutil
import sqlite3
from pathlib import Path

import config

logger = logging.getLogger(__name__)

_conn: sqlite3.Connection | None = None

_TRACK_TYPE_BACKUP_NAME = "karaoke_backup_pre_tracktype.db"


def get_conn() -> sqlite3.Connection:
    """Restituisce la connessione SQLite singleton del processo."""
    global _conn
    if _conn is None:
        config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA foreign_keys=ON")
        logger.debug("Connessione SQLite aperta: %s", config.DB_PATH)
    return _conn


def migrate() -> None:
    """Applica lo schema SQL creando le tabelle se non esistono."""
    schema_path = config.SCHEMA_PATH
    schema_sql = schema_path.read_text(encoding="utf-8")
    conn = get_conn()
    with conn:
        conn.executescript(schema_sql)
        _ensure_column(conn, "tracks", "start_offset_sec", "REAL DEFAULT 0")
    _migrate_track_type(conn)
    config.DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    config.DJ_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Migrazione database completata")


def _migrate_track_type(conn: sqlite3.Connection) -> None:
    """Aggiunge track_type ai DB esistenti con backup, transazione e verifica.

    Idempotente: se la colonna esiste già (schema nuovo o migrazione precedente),
    non esegue backup né ALTER.
    """
    columns = {row[1] for row in conn.execute("PRAGMA table_info(tracks)")}
    if not columns:
        logger.debug("Tabella tracks assente, migrazione track_type saltata")
        return
    if "track_type" in columns:
        logger.debug("Colonna track_type già presente, migrazione saltata")
        return

    db_path = config.DB_PATH
    if db_path.exists():
        backup_path = db_path.parent / _TRACK_TYPE_BACKUP_NAME
        try:
            shutil.copy2(db_path, backup_path)
            logger.info("Backup pre-migrazione creato: %s", backup_path)
        except OSError as exc:
            logger.critical("Backup pre-migrazione fallito: %s", exc)
            raise RuntimeError(
                f"Backup fallito, migrazione track_type interrotta: {exc}"
            ) from exc

    try:
        with conn:
            conn.execute(
                "ALTER TABLE tracks ADD COLUMN track_type TEXT NOT NULL DEFAULT 'karaoke'"
            )
            total = conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
            karaoke_count = conn.execute(
                "SELECT COUNT(*) FROM tracks WHERE track_type = 'karaoke'"
            ).fetchone()[0]
            if total != karaoke_count:
                logger.error(
                    "Verifica track_type fallita: total=%s, karaoke=%s",
                    total,
                    karaoke_count,
                )
                raise RuntimeError(
                    "Verifica post-migrazione track_type fallita: "
                    f"total={total}, karaoke={karaoke_count}"
                )
            logger.info(
                "Migrazione track_type completata: %s brani con track_type='karaoke'",
                karaoke_count,
            )
    except Exception:
        logger.exception("Migrazione track_type fallita, rollback eseguito")
        raise


def _ensure_column(
    conn: sqlite3.Connection, table: str, column: str, decl: str
) -> None:
    """Aggiunge una colonna a una tabella esistente se non è già presente.

    Necessario perché `executescript` con CREATE TABLE IF NOT EXISTS non altera
    le tabelle preesistenti. Identificatori sono costanti interne (non input
    utente), quindi l'interpolazione è sicura.
    """
    existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
        logger.info("Colonna aggiunta: %s.%s", table, column)


def close() -> None:
    """Chiude la connessione SQLite se aperta."""
    global _conn
    if _conn is not None:
        _conn.close()
        _conn = None
        logger.info("Connessione SQLite chiusa")
