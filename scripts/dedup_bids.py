"""중복 입찰공고 정리 스크립트 — 같은 공고는 공고일(open_date) 최신 행만 남긴다.

배경:
  G2B 계열은 정정/재공고 시 차수만 바뀐 새 bid_no(-000, -001, ...)로 다시 내려오는데
  upsert 키가 (source, bid_no) 라 옛 차수 행이 그대로 남아 화면·메일·KPI 가 중복 집계됨.

규칙 (둘 다 "공고일 최신 행만 유지", 나머지 삭제):
  A. 차수 중복  — 같은 source + 차수(-NNN 접미사) 제거한 base 공고번호가 동일
  B. 재공고 추정 — 같은 source + 제목 + 기관 + 업종 + 금액이 전부 동일한데 공고번호가 다름
     (금액까지 같아야 중복으로 판정 — 같은 제목의 별건 분리발주 오탐 방지)

보호:
  - bid_assignees 에 영업대표가 할당된 행은 삭제하지 않음 (cleanup_old_bids 와 동일 정책)

주의:
  - 수집 lookback(14일) 안의 옛 차수는 다음 수집에서 재유입되므로, 이 스크립트는
    daily-collect 워크플로우에서 수집 직후 매번 실행되어야 함.

사용:
  DATABASE_URL 환경변수 필요 (Postgres 연결).
  python scripts/dedup_bids.py            # 삭제 실행
  python scripts/dedup_bids.py --dry-run  # 삭제 없이 대상 건수만 출력
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 정렬 규칙: 공고일(빈값은 최소 취급) → 차수 큰 순 → id 큰 순
_ORDER = "ORDER BY COALESCE(open_date, '') DESC, bid_no DESC, id DESC"

# 규칙 A: 같은 source 내에서 차수 접미사(-N ~ -NNN)를 뗀 base 공고번호가 같은 그룹
SQL_RULE_A_TARGETS = f"""
WITH parsed AS (
    SELECT id, source, bid_no,
           regexp_replace(bid_no, '-[0-9]{{1,3}}$', '') AS base_no
    FROM bid_announcements
),
ranked AS (
    SELECT id, ROW_NUMBER() OVER (
        PARTITION BY source, base_no
        {_ORDER.replace("ORDER BY", "ORDER BY").replace("open_date", "(SELECT open_date FROM bid_announcements b WHERE b.id = parsed.id)")}
    ) AS rn
    FROM parsed
)
SELECT id FROM ranked WHERE rn > 1
"""

# 위 서브쿼리 치환이 읽기 어려우니 단순화한 버전 사용 (open_date 를 parsed 에 포함)
SQL_RULE_A_TARGETS = """
WITH parsed AS (
    SELECT id, source, bid_no, COALESCE(open_date, '') AS od,
           regexp_replace(bid_no, '-[0-9]{1,3}$', '') AS base_no
    FROM bid_announcements
),
ranked AS (
    SELECT id, ROW_NUMBER() OVER (
        PARTITION BY source, base_no
        ORDER BY od DESC, bid_no DESC, id DESC
    ) AS rn
    FROM parsed
)
SELECT id FROM ranked WHERE rn > 1
"""

# 규칙 B: 차수 정리 후에도 남는, 번호만 다른 사실상 같은 공고
#   제목(trim)+기관+업종+금액 이 전부 동일해야 중복 판정 (NULL 금액끼리는 동일 취급)
SQL_RULE_B_TARGETS = """
WITH parsed AS (
    SELECT id, source, bid_no, COALESCE(open_date, '') AS od,
           btrim(title) AS t,
           COALESCE(org_name, '') AS org,
           COALESCE(bid_type, '') AS bt,
           COALESCE(estimated_price, -1) AS price
    FROM bid_announcements
),
ranked AS (
    SELECT id, ROW_NUMBER() OVER (
        PARTITION BY source, t, org, bt, price
        ORDER BY od DESC, bid_no DESC, id DESC
    ) AS rn
    FROM parsed
)
SELECT id FROM ranked WHERE rn > 1
"""

PROTECT = "SELECT DISTINCT bid_id FROM bid_assignees"


def _run_rule(cur, label: str, targets_sql: str, dry_run: bool) -> int:
    cur.execute(
        f"SELECT COUNT(*) AS n FROM ({targets_sql}) t "
        f"WHERE t.id NOT IN ({PROTECT})"
    )
    row = cur.fetchone()
    n = row["n"] if row else 0
    if dry_run:
        print(f"[{label}] 삭제 대상: {n:,} rows (dry-run — 삭제 안 함)")
        return 0
    if n == 0:
        print(f"[{label}] 삭제 대상 없음")
        return 0
    cur.execute(
        f"DELETE FROM bid_announcements "
        f"WHERE id IN ({targets_sql}) AND id NOT IN ({PROTECT})"
    )
    deleted = cur.rowcount
    print(f"[{label}] 삭제 완료: {deleted:,} rows")
    return deleted


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="삭제 없이 대상 건수만 출력")
    args = ap.parse_args()

    if not os.environ.get("DATABASE_URL", "").startswith(("postgres://", "postgresql://")):
        print("ERROR: DATABASE_URL 미설정 (Postgres URI 필요)")
        return 1

    from db import _postgres

    total = 0
    with _postgres.connect() as conn:
        with conn.cursor() as cur:
            total += _run_rule(cur, "규칙A 차수중복", SQL_RULE_A_TARGETS, args.dry_run)
            total += _run_rule(cur, "규칙B 재공고추정", SQL_RULE_B_TARGETS, args.dry_run)
            cur.execute("SELECT COUNT(*) AS n FROM bid_announcements")
            row = cur.fetchone()
            print(f"→ 총 삭제 {total:,} rows / 잔여 {row['n'] if row else '?'} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
