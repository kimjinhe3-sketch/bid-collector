"""마감 지난 입찰 공고 정리 스크립트.

정책:
- close_date < 오늘 - 7일 = 정리 대상 (1주일 grace period)
- 단, bid_assignees 에 영업대표 할당된 row 는 보존 (수주 기록용)
- close_date NULL 인 row 도 보존 (마감일 미상)

사용:
  DATABASE_URL 환경변수 필요 (Postgres 연결).
  python scripts/cleanup_old_bids.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from datetime import date, timedelta

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GRACE_DAYS = 0  # 마감 즉시 삭제 (close_date < 오늘 = 정리 대상)


def main() -> int:
    if not os.environ.get("DATABASE_URL", "").startswith(("postgres://", "postgresql://")):
        print("ERROR: DATABASE_URL 미설정 (Postgres URI 필요)")
        return 1

    from db import _postgres

    cutoff = (date.today() - timedelta(days=GRACE_DAYS)).isoformat()
    print(f"→ 정리 cutoff: close_date < {cutoff} 이고 영업대표 미할당 row")

    # close_date 형식 다양 (예: '2026-05-29 17:00', '20260529170000', '2026-05-29').
    # 안전 가드:
    #   - close_date NOT NULL + 빈 string 아님 (LH collector 가 '' 저장 가능)
    #   - replace('-','') 후 8자리 이상 (YYYYMMDD 추출 가능한 길이)
    #   - 첫 8자리가 모두 숫자
    where_clause = """
        WHERE close_date IS NOT NULL
          AND close_date != ''
          AND length(replace(close_date, '-', '')) >= 8
          AND substring(replace(close_date, '-', ''), 1, 8) ~ '^[0-9]{8}$'
          AND substring(replace(close_date, '-', ''), 1, 8) <
              to_char(%s::date, 'YYYYMMDD')
          AND id NOT IN (SELECT DISTINCT bid_id FROM bid_assignees)
    """
    sql_count = f"SELECT COUNT(*) AS n FROM bid_announcements {where_clause}"
    sql_delete = f"DELETE FROM bid_announcements {where_clause}"

    with _postgres.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql_count, (cutoff,))
            row = cur.fetchone()
            target_count = row["n"] if row else 0
            print(f"→ 삭제 예정: {target_count:,} rows")

            if target_count == 0:
                print("정리할 row 없음.")
                return 0

            cur.execute(sql_delete, (cutoff,))
            deleted = cur.rowcount
            print(f"✅ 삭제 완료: {deleted:,} rows")

            # 정리 후 카운트
            cur.execute("SELECT COUNT(*) AS n FROM bid_announcements")
            row = cur.fetchone()
            remaining = row["n"] if row else 0
            print(f"→ 잔여 row: {remaining:,}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
