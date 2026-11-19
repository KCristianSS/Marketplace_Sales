"""Cola SQLite durable para reintentar auditorías sin repetir operaciones comerciales."""
import json
import logging
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from backend.shared.config import settings

logger = logging.getLogger("uvicorn.error.audit")


@contextmanager
def _connect():
    path = Path(settings.AUDIT_SPOOL_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("""CREATE TABLE IF NOT EXISTS audit_pending (
        id TEXT PRIMARY KEY, event TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
        available_at REAL NOT NULL DEFAULT 0, lease_until REAL NOT NULL DEFAULT 0,
        last_error TEXT, created_at REAL NOT NULL)""")
    conn.commit()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def enqueue(row: dict):
    with _connect() as conn:
        conn.execute("INSERT OR IGNORE INTO audit_pending(id,event,created_at) VALUES(?,?,?)",
                     (row["id"], json.dumps(row, ensure_ascii=False), time.time()))


def _claim(event_id=None):
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        query = "SELECT * FROM audit_pending WHERE available_at<=? AND lease_until<=?"
        params = [time.time(), time.time()]
        if event_id:
            query += " AND id=?"
            params.append(event_id)
        row = conn.execute(query + " ORDER BY created_at LIMIT 1", params).fetchone()
        if row is None:
            return None
        lease = time.time() + 180
        conn.execute("UPDATE audit_pending SET lease_until=? WHERE id=?", (lease, row["id"]))
        return {**dict(row), "lease_until": lease}


def deliver(client, event_id=None) -> bool:
    if client is None:
        return False
    item = _claim(event_id)
    if item is None:
        return False
    event = json.loads(item["event"])
    try:
        client.table("audit_logs").insert(event).execute()
    except Exception as exc:
        # Una respuesta perdida después del INSERT puede reenviarse: el ID es estable.
        if str(getattr(exc, "code", "")) != "23505":
            attempts = item["attempts"] + 1
            with _connect() as conn:
                conn.execute("""UPDATE audit_pending SET attempts=?,available_at=?,lease_until=0,last_error=?
                    WHERE id=? AND lease_until=?""",
                    (attempts, time.time() + min(300, 2 ** min(attempts, 8)), type(exc).__name__, item["id"], item["lease_until"]))
            logger.warning("AUDIT_PENDIENTE id=%s intento=%s error=%s", item["id"], attempts, type(exc).__name__)
            return False
    with _connect() as conn:
        conn.execute("DELETE FROM audit_pending WHERE id=? AND lease_until=?", (item["id"], item["lease_until"]))
    logger.info("AUDIT_GUARDADO %s", json.dumps(event, ensure_ascii=False, sort_keys=True))
    return True


def flush_pending(client, limit=20):
    sent = 0
    while sent < limit and deliver(client):
        sent += 1
    return sent


def summary():
    with _connect() as conn:
        row = conn.execute("SELECT count(*) AS pendientes,coalesce(max(attempts),0) AS max_intentos FROM audit_pending").fetchone()
        return dict(row)
