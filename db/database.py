from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable

from utils.logger import get_logger

logger = get_logger("bid_collector.db")

SCHEMA_PATH = Path(__file__).parent / "schema.sql"

COLUMNS = (
    "source",
    "bid_no",
    "title",
    "org_name",
    "contract_method",
    "estimated_price",
    "open_date",
    "close_date",
    "bid_type",
    "detail_url",
)


@contextmanager
def connect(db_path: str | Path):
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: str | Path) -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with connect(db_path) as conn:
        conn.executescript(schema)


def upsert_bids(db_path: str | Path, rows: Iterable[dict]) -> tuple[int, int]:
    """Upsert by (source, bid_no). Returns (inserted_or_updated, skipped)."""
    rows = list(rows)
    if not rows:
        return 0, 0

    placeholders = ", ".join(f":{c}" for c in COLUMNS)
    update_cols = [c for c in COLUMNS if c not in ("source", "bid_no")]
    update_clause = ", ".join(f"{c}=excluded.{c}" for c in update_cols)

    sql = f"""
    INSERT INTO bid_announcements ({", ".join(COLUMNS)})
    VALUES ({placeholders})
    ON CONFLICT(source, bid_no) DO UPDATE SET {update_clause}
    """

    processed = 0
    skipped = 0
    with connect(db_path) as conn:
        for r in rows:
            if not r.get("source") or not r.get("bid_no") or not r.get("title"):
                skipped += 1
                continue
            payload = {c: r.get(c) for c in COLUMNS}
            try:
                conn.execute(sql, payload)
                processed += 1
            except sqlite3.Error:
                logger.exception("upsert failed for bid_no=%s", r.get("bid_no"))
                skipped += 1
    logger.info("upsert_bids: processed=%d skipped=%d", processed, skipped)
    return processed, skipped


def get_unnotified(db_path: str | Path) -> list[dict]:
    with connect(db_path) as conn:
        cur = conn.execute(
            "SELECT * FROM bid_announcements WHERE is_notified = 0 ORDER BY open_date DESC, id DESC"
        )
        return [dict(row) for row in cur.fetchall()]


def mark_notified(db_path: str | Path, ids: Iterable[int]) -> int:
    ids = list(ids)
    if not ids:
        return 0
    placeholders = ",".join("?" for _ in ids)
    with connect(db_path) as conn:
        cur = conn.execute(
            f"UPDATE bid_announcements SET is_notified = 1 WHERE id IN ({placeholders})",
            ids,
        )
        return cur.rowcount


def count_by_source(db_path: str | Path, since_date: str | None = None) -> dict[str, int]:
    sql = "SELECT source, COUNT(*) AS n FROM bid_announcements"
    params: tuple = ()
    if since_date:
        sql += " WHERE date(created_at) >= date(?)"
        params = (since_date,)
    sql += " GROUP BY source"
    with connect(db_path) as conn:
        cur = conn.execute(sql, params)
        return {row["source"]: row["n"] for row in cur.fetchall()}


def fetch_for_dashboard(
    db_path: str | Path,
    since_date: str | None = None,
    bid_types: list[str] | None = None,
    keyword: str | None = None,
    limit: int = 1000,
) -> list[dict]:
    where = []
    params: list = []
    if since_date:
        where.append("date(created_at) >= date(?)")
        params.append(since_date)
    if bid_types:
        placeholders = ",".join("?" for _ in bid_types)
        where.append(f"bid_type IN ({placeholders})")
        params.extend(bid_types)
    if keyword:
        where.append("title LIKE ?")
        params.append(f"%{keyword}%")
    where_clause = f"WHERE {' AND '.join(where)}" if where else ""
    sql = f"SELECT * FROM bid_announcements {where_clause} ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    with connect(db_path) as conn:
        cur = conn.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]


def daily_counts(db_path: str | Path, days: int = 30) -> list[dict]:
    with connect(db_path) as conn:
        cur = conn.execute(
            """
            SELECT date(created_at) AS d, COUNT(*) AS n
            FROM bid_announcements
            WHERE date(created_at) >= date('now', ?)
            GROUP BY d ORDER BY d
            """,
            (f"-{days} days",),
        )
        return [dict(row) for row in cur.fetchall()]
