# -*- coding: utf-8 -*-
"""개찰결과 수집 실행기 — bid_results 테이블 생성(멱등) + 기간 수집 + upsert.

기존 서비스와 완전 분리: 신규 테이블에만 쓰고 bid_announcements 는 건드리지 않는다.

Usage (DATABASE_URL 필요 — GitHub Actions 에서 실행):
    python -m scripts.collect_results --days 3            # 최근 3일 (기본, 재수집으로 확정치 갱신)
    python -m scripts.collect_results --start 2026-07-01 --end 2026-07-31   # 백필
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import setup_logger, get_logger  # noqa: E402
from collectors import result_api  # noqa: E402

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS bid_results (
    id               BIGSERIAL PRIMARY KEY,
    bid_no           TEXT NOT NULL UNIQUE,      -- 공고번호-차수 (bid_announcements 매칭 키)
    title            TEXT,
    org_name         TEXT,
    bsns_div         TEXT,                      -- 물품/공사/용역
    decision_method  TEXT,                      -- 적격심사제 등
    presmpt_price    BIGINT,                    -- 추정가격
    base_price       BIGINT,                    -- 기초금액
    planned_price    BIGINT,                    -- 예정가격 (개찰 확정)
    sajeong_rate     NUMERIC(8,4),              -- 사정율 = 예정/기초 (%)
    win_lower_rate   NUMERIC(8,4),              -- 낙찰하한율 (%)
    win_bid_amount   BIGINT,                    -- 낙찰(1순위) 투찰금액
    win_bid_rate     NUMERIC(8,4),              -- 낙찰 투찰률 (%)
    bidder_count     INT,                       -- 참가업체수 (경쟁강도)
    open_result_date TEXT,                      -- 개찰일 YYYY-MM-DD
    winner_name      TEXT,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_results_open ON bid_results(open_result_date);
CREATE INDEX IF NOT EXISTS idx_results_div  ON bid_results(bsns_div);
"""

COLS = ("bid_no", "title", "org_name", "bsns_div", "decision_method", "presmpt_price",
        "base_price", "planned_price", "sajeong_rate", "win_lower_rate",
        "win_bid_amount", "win_bid_rate", "bidder_count", "open_result_date", "winner_name")


def upsert_results(rows: list[dict]) -> int:
    import psycopg2
    import psycopg2.extras
    url = os.environ["DATABASE_URL"]
    if "sslmode=" not in url:
        url = f"{url}{'&' if '?' in url else '?'}sslmode=require"
    placeholders = ", ".join(f"%({c})s" for c in COLS)
    update = ", ".join(f"{c}=EXCLUDED.{c}" for c in COLS if c != "bid_no")
    sql = (f"INSERT INTO bid_results ({', '.join(COLS)}) VALUES ({placeholders}) "
           f"ON CONFLICT (bid_no) DO UPDATE SET {update}")
    payloads = [{c: r.get(c) for c in COLS} for r in rows if r.get("bid_no")]
    conn = psycopg2.connect(url)
    try:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
            if payloads:
                psycopg2.extras.execute_batch(cur, sql, payloads, page_size=200)
        conn.commit()
        return len(payloads)
    finally:
        conn.close()


def main() -> int:
    setup_logger(level="INFO")
    logger = get_logger("collect_results")

    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3, help="최근 N일 (기본 3 — 확정치 재수집)")
    ap.add_argument("--start", help="백필 시작일 YYYY-MM-DD")
    ap.add_argument("--end", help="백필 종료일 YYYY-MM-DD")
    args = ap.parse_args()

    key = os.environ.get("G2B_SERVICE_KEY")
    if not key:
        logger.error("G2B_SERVICE_KEY 미설정")
        return 1
    if not os.environ.get("DATABASE_URL"):
        logger.error("DATABASE_URL 미설정")
        return 1

    if args.start and args.end:
        start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    else:
        end = date.today()
        start = end - timedelta(days=max(args.days - 1, 0))

    rows = result_api.collect_range(key, start, end)
    n = upsert_results(rows)
    logger.info("bid_results upsert 완료: %d 공고 (%s ~ %s)", n, start, end)
    print(f"[collect_results] upserted={n} range={start}~{end}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
