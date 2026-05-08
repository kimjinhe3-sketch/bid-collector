"""Postgres (Supabase) 백엔드.

DATABASE_URL 환경변수가 postgresql:// 또는 postgres:// 로 시작할 때 사용.
psycopg2 드라이버 + DictCursor 로 dict 결과 반환.

스키마는 처음 init_db() 호출 시 idempotent 하게 생성. RLS 정책은 사용자가
Supabase SQL Editor 에서 한 번 적용 (README 참조).

함수 시그니처는 db._sqlite 와 동일하여 db.database 의 dispatch 가
양쪽으로 그대로 위임 가능.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse, parse_qs

import psycopg2
import psycopg2.extras
import psycopg2.pool

from utils.logger import get_logger

logger = get_logger("bid_collector.db.postgres")

COLUMNS = (
    "source", "bid_no", "title", "org_name", "contract_method",
    "estimated_price", "open_date", "close_date", "bid_type", "detail_url",
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS bid_announcements (
    id              BIGSERIAL PRIMARY KEY,
    source          TEXT      NOT NULL,
    bid_no          TEXT      NOT NULL,
    title           TEXT      NOT NULL,
    org_name        TEXT,
    contract_method TEXT,
    estimated_price BIGINT,
    open_date       TEXT,
    close_date      TEXT,
    bid_type        TEXT,
    detail_url      TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    is_notified     BOOLEAN     DEFAULT FALSE,
    UNIQUE(source, bid_no)
);
CREATE INDEX IF NOT EXISTS idx_bids_created  ON bid_announcements(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_bids_open     ON bid_announcements(open_date);
CREATE INDEX IF NOT EXISTS idx_bids_notified ON bid_announcements(is_notified);
CREATE INDEX IF NOT EXISTS idx_bids_type     ON bid_announcements(bid_type);
CREATE INDEX IF NOT EXISTS idx_bids_source   ON bid_announcements(source);
"""

# Lazy connection pool — 처음 호출 시 한 번 생성, 이후 재사용
_POOL: psycopg2.pool.SimpleConnectionPool | None = None


def _get_pool() -> psycopg2.pool.SimpleConnectionPool:
    global _POOL
    if _POOL is None:
        url = os.environ.get("DATABASE_URL", "")
        if not url:
            raise RuntimeError("DATABASE_URL not set")
        # Supabase 는 SSL 필요. URL 에 ?sslmode=require 가 없으면 추가.
        if "sslmode=" not in url:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}sslmode=require"
        _POOL = psycopg2.pool.SimpleConnectionPool(
            minconn=1, maxconn=4, dsn=url,
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
    return _POOL


@contextmanager
def connect(_db_path=None):
    """db_path 인자는 SQLite 백엔드와의 인터페이스 호환을 위해 받지만 무시."""
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def init_db(_db_path=None) -> None:
    """스키마 idempotent 생성. RLS 정책은 사용자가 Supabase 콘솔에서 별도 적용."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
    # 레거시 데이터 정리 (SQLite 와 동일한 마이그레이션)
    _migrate_clear_prvt_google_urls()
    _migrate_remove_kapt_rows()
    _migrate_stale_alio_urls()


def _migrate_clear_prvt_google_urls() -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE bid_announcements SET detail_url = NULL "
                "WHERE source LIKE 'prvt_api%' "
                "  AND detail_url LIKE '%google.com/search%'"
            )
            n = cur.rowcount
    if n:
        logger.info("[pg] cleared %d legacy Google URLs", n)


def _migrate_remove_kapt_rows() -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM bid_announcements "
                "WHERE source = 'kapt_api' OR bid_type = 'K-apt'"
            )
            n = cur.rowcount
    if n:
        logger.info("[pg] removed %d K-apt rows", n)


def _migrate_stale_alio_urls() -> None:
    import urllib.parse
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, title FROM bid_announcements "
                "WHERE source = 'alio' AND detail_url LIKE '%bidView.do%'"
            )
            rows = cur.fetchall()
            if not rows:
                return
            for r in rows:
                keyword = (r["title"] or "")[:30]
                new_url = (
                    "https://www.alio.go.kr/occasional/bidList.do?"
                    f"type=title&word={urllib.parse.quote(keyword)}"
                )
                cur.execute(
                    "UPDATE bid_announcements SET detail_url = %s WHERE id = %s",
                    (new_url, r["id"]),
                )
            logger.info("[pg] migrated %d stale ALIO URLs", len(rows))


def upsert_bids(_db_path, rows: Iterable[dict]) -> tuple[int, int]:
    rows = list(rows)
    if not rows:
        return 0, 0

    cols = list(COLUMNS)
    placeholders = ", ".join(f"%({c})s" for c in cols)
    update_cols = [c for c in cols if c not in ("source", "bid_no")]
    update_clause = ", ".join(f"{c}=EXCLUDED.{c}" for c in update_cols)
    sql = (
        f"INSERT INTO bid_announcements ({', '.join(cols)}) "
        f"VALUES ({placeholders}) "
        f"ON CONFLICT (source, bid_no) DO UPDATE SET {update_clause}"
    )

    # 유효성 검증 + payload 정리
    payloads = []
    skipped = 0
    for r in rows:
        if not r.get("source") or not r.get("bid_no") or not r.get("title"):
            skipped += 1
            continue
        payloads.append({c: r.get(c) for c in cols})

    if not payloads:
        return 0, skipped

    # Batch upsert — execute_batch 가 INSERT 을 청크로 묶어 보내서
    # round-trip 수를 페이지 크기만큼 줄임 (개별 execute 대비 5~20x 빠름).
    processed = 0
    with connect() as conn:
        with conn.cursor() as cur:
            try:
                psycopg2.extras.execute_batch(cur, sql, payloads, page_size=200)
                processed = len(payloads)
            except psycopg2.Error:
                logger.exception("batch upsert failed — falling back to per-row")
                # Fallback: 개별 처리해서 어느 row 가 깨졌는지 격리
                for p in payloads:
                    try:
                        cur.execute(sql, p)
                        processed += 1
                    except psycopg2.Error:
                        logger.exception("row upsert failed bid_no=%s", p.get("bid_no"))
                        skipped += 1

    logger.info("upsert_bids[postgres]: processed=%d skipped=%d", processed, skipped)
    return processed, skipped


def get_unnotified(_db_path=None) -> list[dict]:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM bid_announcements WHERE is_notified = FALSE "
                "ORDER BY open_date DESC NULLS LAST, id DESC"
            )
            return [dict(row) for row in cur.fetchall()]


def mark_notified(_db_path, ids: Iterable[int]) -> int:
    ids = list(ids)
    if not ids:
        return 0
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE bid_announcements SET is_notified = TRUE "
                "WHERE id = ANY(%s)",
                (ids,),
            )
            return cur.rowcount


def count_by_source(_db_path, since_date: str | None = None) -> dict[str, int]:
    sql = "SELECT source, COUNT(*) AS n FROM bid_announcements"
    params: tuple = ()
    if since_date:
        sql += " WHERE created_at::date >= %s::date"
        params = (since_date,)
    sql += " GROUP BY source"
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return {row["source"]: row["n"] for row in cur.fetchall()}


def fetch_for_dashboard(
    _db_path,
    since_date: str | None = None,
    bid_types: list[str] | None = None,
    keyword: str | None = None,
    org_name: str | None = None,
    sources: list[str] | None = None,
    limit: int = 1000,
) -> list[dict]:
    where = []
    params: list = []
    if since_date:
        where.append("created_at::date >= %s::date")
        params.append(since_date)
    if bid_types:
        where.append("bid_type = ANY(%s)")
        params.append(list(bid_types))
    if keyword:
        where.append("title ILIKE %s")
        params.append(f"%{keyword}%")
    if org_name:
        where.append("org_name ILIKE %s")
        params.append(f"%{org_name}%")
    if sources:
        where.append("source = ANY(%s)")
        params.append(list(sources))
    where_clause = f"WHERE {' AND '.join(where)}" if where else ""
    sql = (
        f"SELECT * FROM bid_announcements {where_clause} "
        f"ORDER BY created_at DESC LIMIT %s"
    )
    params.append(limit)
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]


def daily_counts(_db_path, days: int = 30) -> list[dict]:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT created_at::date AS d, COUNT(*) AS n
                FROM bid_announcements
                WHERE created_at >= NOW() - (%s || ' days')::interval
                GROUP BY d ORDER BY d
                """,
                (str(days),),
            )
            return [{"d": str(r["d"]), "n": r["n"]} for r in cur.fetchall()]
