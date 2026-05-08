"""기존 SQLite 데이터를 Supabase Postgres 로 한 번에 옮기는 마이그레이션 스크립트.

사용법 (로컬에서 1회 실행):

  cd bid_collector
  export DATABASE_URL="postgresql://postgres.xxx:PASSWORD@aws-0-...:5432/postgres"
  python scripts/migrate_sqlite_to_postgres.py

기본 SQLite 경로: data/bids.sqlite (config.yaml 의 database.path)
DATABASE_URL 이 있을 때만 동작. 안전: 같은 (source, bid_no) 면 UPSERT 됨
(중복 호출해도 멱등).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sqlite3
from db import _postgres


def main() -> int:
    if not os.environ.get("DATABASE_URL", "").startswith(("postgres://", "postgresql://")):
        print("ERROR: DATABASE_URL 환경변수 미설정 (Postgres URI 필요)")
        return 1

    sqlite_path = ROOT / "data" / "bids.sqlite"
    if not sqlite_path.exists():
        print(f"ERROR: SQLite DB 없음 ({sqlite_path})")
        return 1

    print(f"→ Reading {sqlite_path}")
    conn = sqlite3.connect(str(sqlite_path))
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(
        "SELECT source, bid_no, title, org_name, contract_method, "
        "estimated_price, open_date, close_date, bid_type, detail_url "
        "FROM bid_announcements"
    ).fetchall()]
    conn.close()
    print(f"  Loaded {len(rows):,} rows from SQLite")

    print("→ Initializing Postgres schema (idempotent)")
    _postgres.init_db()

    print(f"→ Upserting to Postgres ({len(rows):,} rows)")
    BATCH = 500
    total_processed = 0
    total_skipped = 0
    for i in range(0, len(rows), BATCH):
        chunk = rows[i:i+BATCH]
        p, s = _postgres.upsert_bids(None, chunk)
        total_processed += p
        total_skipped += s
        print(f"  [{i+len(chunk):,}/{len(rows):,}] processed={p} skipped={s}")

    print(f"\n✅ DONE. processed={total_processed:,} skipped={total_skipped:,}")

    # 검증: Postgres 측 카운트
    counts = _postgres.count_by_source(None)
    print("\nPostgres 적재 현황 (source 별):")
    for src, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {src:30s} {n:>8,}")
    print(f"  {'─'*40}\n  {'TOTAL':30s} {sum(counts.values()):>8,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
