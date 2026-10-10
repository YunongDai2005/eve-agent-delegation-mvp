import json
import logging
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any

from eve_demo.config import DATA_DIR

logger = logging.getLogger("eve.trace")
logger.setLevel(logging.INFO)
logger.propagate = False
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(handler)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: "[REDACTED]"
            if re.search(r"key|token|authorization|secret|password", k, re.I)
            else redact(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r"(?i)(bearer\s+|sk-)[\w.-]+", "[REDACTED]", value)
        value = re.sub(
            r"(?i)((?:api[_-]?key|token|password|secret)\s*[:=]\s*)[^\s&,;]+",
            r"\1[REDACTED]",
            value,
        )
    return value


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DATA_DIR / "tasks.sqlite", timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, data TEXT NOT NULL)")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS remote_tasks (id TEXT PRIMARY KEY, data TEXT NOT NULL)"
    )
    conn.execute("CREATE TABLE IF NOT EXISTS receipts (id TEXT PRIMARY KEY, data TEXT NOT NULL)")
    conn.execute("""CREATE TABLE IF NOT EXISTS trace (
        seq INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT, data TEXT NOT NULL)""")
    return conn


def save(table: str, key: str, data: dict) -> None:
    assert table in {"jobs", "remote_tasks", "receipts"}
    with db() as conn:
        conn.execute(f"INSERT OR REPLACE INTO {table} VALUES (?, ?)", (key, json.dumps(data)))


def read(table: str, key: str) -> dict | None:
    assert table in {"jobs", "remote_tasks", "receipts"}
    with db() as conn:
        row = conn.execute(f"SELECT data FROM {table} WHERE id=?", (key,)).fetchone()
    return json.loads(row[0]) if row else None


def pending_jobs() -> list[dict]:
    with db() as conn:
        rows = conn.execute("SELECT data FROM jobs").fetchall()
    return [item for row in rows if (item := json.loads(row[0]))["status"] in {"queued", "running"}]


def trace(request_id: str, node: str, status: str, **details: Any) -> None:
    import os

    event = redact(
        {
            "request_id": request_id,
            "node": node,
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pid": os.getpid(),
            **details,
        }
    )
    with db() as conn:
        conn.execute(
            "INSERT INTO trace(request_id,data) VALUES (?,?)", (request_id, json.dumps(event))
        )
    logger.info(json.dumps(event))


def traces(request_id: str) -> list[dict]:
    with db() as conn:
        rows = conn.execute("SELECT data FROM trace WHERE request_id=? ORDER BY seq", (request_id,))
        return [json.loads(row[0]) for row in rows]
