"""
DB 의 close_date / open_date 를 표준 포맷 (YYYY-MM-DD HH:MM[:SS]) 으로 통일.

발견된 비표준 포맷:
  - lh_api  : "2026/05/04 10:00"     (슬래시)
  - d2b_api : "202605111100" / "20260429" (대시 없음, 8 또는 12 자리)
  - kepco_api 일부 레거시 : "20220919000000" (14 자리)

문제:
  - bid_source_counts view 의 today 카운트가 잘못 (open_date 슬래시·디지트 매치 실패)
  - bid_announcements.close_date.gte.today 필터가 lex 비교에서 슬래시 / 디지트 모두 통과
    ("/" > "-", "0" > "-") → 마감 공고가 활성 리스트에 남음

수정:
  - LH    : "/" → "-"
  - D2B   : 8자리 → "YYYY-MM-DD" / 12자리 → "YYYY-MM-DD HH:MM"
  - KEPCO : 14자리 → "YYYY-MM-DD HH:MM:SS"

이후:
  - bid_source_counts view 재생성 (KST today 비교 + slice(1,10))

Usage (GH Actions workflow_dispatch 또는 로컬에서 DATABASE_URL 환경변수 세팅 후):
    python -m scripts.normalize_dates
"""
from __future__ import annotations

import os
import sys

import psycopg2
from psycopg2.extras import RealDictCursor


SQL_NORMALIZE = """
-- LH: 2026/05/04 10:00 → 2026-05-04 10:00
UPDATE bid_announcements
SET close_date = REPLACE(close_date, '/', '-'),
    open_date  = REPLACE(open_date,  '/', '-')
WHERE source = 'lh_api'
  AND (close_date LIKE '%/%' OR open_date LIKE '%/%');

-- D2B 12자리 close_date: 202605111100 → 2026-05-11 11:00
UPDATE bid_announcements
SET close_date = SUBSTR(close_date, 1, 4) || '-' || SUBSTR(close_date, 5, 2) || '-' ||
                 SUBSTR(close_date, 7, 2) || ' ' || SUBSTR(close_date, 9, 2) || ':' ||
                 SUBSTR(close_date, 11, 2)
WHERE source = 'd2b_api_dmstc'
  AND close_date ~ '^[0-9]{12}$';

-- D2B 8자리 close_date: 20260511 → 2026-05-11
UPDATE bid_announcements
SET close_date = SUBSTR(close_date, 1, 4) || '-' || SUBSTR(close_date, 5, 2) || '-' ||
                 SUBSTR(close_date, 7, 2)
WHERE source = 'd2b_api_dmstc'
  AND close_date ~ '^[0-9]{8}$';

-- D2B 12자리 open_date
UPDATE bid_announcements
SET open_date = SUBSTR(open_date, 1, 4) || '-' || SUBSTR(open_date, 5, 2) || '-' ||
                SUBSTR(open_date, 7, 2) || ' ' || SUBSTR(open_date, 9, 2) || ':' ||
                SUBSTR(open_date, 11, 2)
WHERE source = 'd2b_api_dmstc'
  AND open_date ~ '^[0-9]{12}$';

-- D2B 8자리 open_date
UPDATE bid_announcements
SET open_date = SUBSTR(open_date, 1, 4) || '-' || SUBSTR(open_date, 5, 2) || '-' ||
                SUBSTR(open_date, 7, 2)
WHERE source = 'd2b_api_dmstc'
  AND open_date ~ '^[0-9]{8}$';

-- KEPCO 레거시 14자리: 20220919000000 → 2022-09-19 00:00:00
UPDATE bid_announcements
SET close_date = SUBSTR(close_date, 1, 4) || '-' || SUBSTR(close_date, 5, 2) || '-' ||
                 SUBSTR(close_date, 7, 2) || ' ' || SUBSTR(close_date, 9, 2) || ':' ||
                 SUBSTR(close_date, 11, 2) || ':' || SUBSTR(close_date, 13, 2)
WHERE source = 'kepco_api'
  AND close_date ~ '^[0-9]{14}$';

UPDATE bid_announcements
SET open_date = SUBSTR(open_date, 1, 4) || '-' || SUBSTR(open_date, 5, 2) || '-' ||
                SUBSTR(open_date, 7, 2) || ' ' || SUBSTR(open_date, 9, 2) || ':' ||
                SUBSTR(open_date, 11, 2) || ':' || SUBSTR(open_date, 13, 2)
WHERE source = 'kepco_api'
  AND open_date ~ '^[0-9]{14}$';

-- LH detail_url 백필 — eBid 검색 페이지 with s_bidNum prefill (1-click 으로 결과 도달)
UPDATE bid_announcements
SET detail_url = 'https://ebid.lh.or.kr/ebid.et.tp.cmd.BidMasterListCmd.dev?s_bidNum=' || bid_no
WHERE source = 'lh_api'
  AND (detail_url IS NULL OR detail_url = '');
"""

SQL_REBUILD_VIEW = """
DROP VIEW IF EXISTS bid_source_counts;

CREATE VIEW bid_source_counts AS
SELECT
  source,
  COUNT(*)::bigint AS total,
  COUNT(*) FILTER (
    WHERE SUBSTR(open_date, 1, 10) = to_char(
      (NOW() AT TIME ZONE 'Asia/Seoul')::date, 'YYYY-MM-DD'
    )
  )::bigint AS today
FROM bid_announcements
GROUP BY source;

-- anon 읽기 허용 (RLS 영향 회피)
GRANT SELECT ON bid_source_counts TO anon, authenticated;
"""


def main() -> int:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("[normalize_dates] DATABASE_URL not set", file=sys.stderr)
        return 1
    if "sslmode=" not in url:
        url = f"{url}{'&' if '?' in url else '?'}sslmode=require"

    conn = psycopg2.connect(url, cursor_factory=RealDictCursor)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            # 1) sample 진단
            cur.execute("""
                SELECT source, COUNT(*) AS n FROM bid_announcements
                WHERE close_date LIKE '%/%' OR close_date ~ '^[0-9]{8,}$'
                   OR open_date LIKE '%/%' OR open_date ~ '^[0-9]{8,}$'
                GROUP BY source ORDER BY source
            """)
            before = cur.fetchall()
            print("[BEFORE] non-standard rows:")
            for r in before:
                print(f"  {r['source']}: {r['n']}")

            # 2) 정규화 실행
            cur.execute(SQL_NORMALIZE)
            print(f"[normalize] rows updated (cumulative): {cur.rowcount}")

            # 3) view 재생성
            cur.execute(SQL_REBUILD_VIEW)
            print("[view] bid_source_counts rebuilt")

            # 4) sample 진단 후
            cur.execute("""
                SELECT source, COUNT(*) AS n FROM bid_announcements
                WHERE close_date LIKE '%/%' OR close_date ~ '^[0-9]{8,}$'
                   OR open_date LIKE '%/%' OR open_date ~ '^[0-9]{8,}$'
                GROUP BY source ORDER BY source
            """)
            after = cur.fetchall()
            print("[AFTER] non-standard rows:")
            for r in after:
                print(f"  {r['source']}: {r['n']}")
        conn.commit()
        print("[normalize_dates] OK — committed")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
