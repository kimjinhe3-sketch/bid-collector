# -*- coding: utf-8 -*-
"""추천 채점 루프 — 개찰 완료된 공고의 추천값 vs 실제 결과 대조 → bid_rec_scores 누적.

Lesson-learned 측정 장치:
  개찰결과가 들어올 때마다, 그 공고에 대해 캐시돼 있던 추천(rec_bid_rate)을
  실제 개찰 결과(낙찰 투찰률·하한율)와 대조해 성적을 기록한다.
  - outcome: win(낙찰권) / under(하한미달) / beaten(순위밀림)
  - diff: 추천률 − 실제 낙찰률 (±0.3%p 적중 지표)
  일별 성적 추이가 쌓이면 파라미터(마진 분위수·사정율 보정) 조정 근거가 된다.

실행: 개찰결과 수집 직후 (recommend.yml 에서 추천 재계산 전에).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import setup_logger, get_logger  # noqa: E402

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS bid_rec_scores (
    id               BIGSERIAL PRIMARY KEY,
    bid_no           TEXT NOT NULL UNIQUE,
    rec_bid_rate     NUMERIC(8,4),   -- 당시 추천 투찰률
    est_lower_rate   NUMERIC(8,4),   -- 당시 추정 하한율
    confidence       TEXT,
    actual_win_rate  NUMERIC(8,4),   -- 실제 낙찰 투찰률
    actual_lower     NUMERIC(8,4),   -- 실제 낙찰하한율
    actual_sajeong   NUMERIC(8,4),
    outcome          TEXT,           -- win / under / beaten
    diff             NUMERIC(8,4),   -- 추천률 − 실제낙찰률
    lower_hit        BOOLEAN,        -- 하한율 추정 적중 여부
    open_result_date TEXT,
    scored_at        TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_rec_scores_date ON bid_rec_scores(open_result_date);
-- 금액 기준 채점 + ③ 섀도우 비교 (2026-08-19)
ALTER TABLE bid_rec_scores ADD COLUMN IF NOT EXISTS eff_rate NUMERIC(8,4);     -- 유효율 = 추천금액/실제예정가
ALTER TABLE bid_rec_scores ADD COLUMN IF NOT EXISTS eff_rate_v2 NUMERIC(8,4);
ALTER TABLE bid_rec_scores ADD COLUMN IF NOT EXISTS outcome_v2 TEXT;           -- 섀도우 모델 결과
"""

# 채점: 개찰결과 중 적격심사 + 추천 캐시가 존재하고 아직 채점 안 된 건
SCORE_SQL = """
INSERT INTO bid_rec_scores
  (bid_no, rec_bid_rate, est_lower_rate, confidence,
   actual_win_rate, actual_lower, actual_sajeong,
   eff_rate, outcome, eff_rate_v2, outcome_v2,
   diff, lower_hit, open_result_date)
SELECT r.bid_no,
       c.rec_bid_rate, c.est_lower_rate, c.confidence,
       r.win_bid_rate, r.win_lower_rate, r.sajeong_rate,
       e.eff, 
       CASE WHEN e.eff < r.win_lower_rate THEN 'under'
            WHEN e.eff < r.win_bid_rate  THEN 'win'
            ELSE 'beaten' END,
       e.eff2,
       CASE WHEN e.eff2 IS NULL THEN NULL
            WHEN e.eff2 < r.win_lower_rate THEN 'under'
            WHEN e.eff2 < r.win_bid_rate  THEN 'win'
            ELSE 'beaten' END,
       c.rec_bid_rate - r.win_bid_rate,
       ABS(c.est_lower_rate - r.win_lower_rate) < 0.001,
       r.open_result_date
FROM bid_results r
JOIN bid_recommendations c ON c.bid_no = r.bid_no
CROSS JOIN LATERAL (
  SELECT ROUND(c.rec_bid_amount::numeric    / r.planned_price * 100, 4) AS eff,
         ROUND(c.rec_bid_amount_v2::numeric / r.planned_price * 100, 4) AS eff2
) e
WHERE r.decision_method LIKE '%적격%'
  AND r.win_bid_rate IS NOT NULL AND r.win_lower_rate IS NOT NULL
  AND r.planned_price > 0 AND c.rec_bid_amount > 0
  AND (r.win_bid_rate - r.win_lower_rate) BETWEEN 0 AND 15
ON CONFLICT (bid_no) DO NOTHING
"""

SUMMARY_SQL = """
SELECT COUNT(*) AS n,
       ROUND(AVG(CASE WHEN outcome = 'win'    THEN 100.0 ELSE 0 END), 1) AS win_pct,
       ROUND(AVG(CASE WHEN outcome = 'under'  THEN 100.0 ELSE 0 END), 1) AS under_pct,
       ROUND(AVG(CASE WHEN outcome = 'beaten' THEN 100.0 ELSE 0 END), 1) AS beaten_pct,
       ROUND(AVG(CASE WHEN ABS(diff) <= 0.3   THEN 100.0 ELSE 0 END), 1) AS hit03_pct,
       ROUND(AVG(CASE WHEN lower_hit          THEN 100.0 ELSE 0 END), 1) AS lower_hit_pct,
       COUNT(outcome_v2) AS n_v2,
       ROUND(AVG(CASE WHEN outcome_v2 = 'win' THEN 100.0 END), 1) AS win_v2_pct
FROM bid_rec_scores
WHERE open_result_date >= to_char(NOW() - INTERVAL '%s days', 'YYYY-MM-DD')
"""


def main() -> int:
    setup_logger(level="INFO")
    logger = get_logger("score_recommendations")
    import psycopg2
    from psycopg2.extras import RealDictCursor
    url = os.environ["DATABASE_URL"]
    if "sslmode=" not in url:
        url = f"{url}{'&' if '?' in url else '?'}sslmode=require"
    conn = psycopg2.connect(url, cursor_factory=RealDictCursor)
    try:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
            cur.execute(SCORE_SQL)
            new = cur.rowcount
            conn.commit()
            for days, label in ((7, "최근 7일"), (30, "최근 30일")):
                cur.execute(SUMMARY_SQL % days)
                s = cur.fetchone()
                if s and s["n"]:
                    print(f"[score] {label}: n={s['n']}  낙찰권 {s['win_pct']}% / 미달 {s['under_pct']}% / "
                          f"밀림 {s['beaten_pct']}% / ±0.3적중 {s['hit03_pct']}% / 하한율적중 {s['lower_hit_pct']}%"
                          + (f" | 섀도우(v2) n={s['n_v2']} 낙찰권 {s['win_v2_pct']}%" if s.get('n_v2') else ""))
        print(f"[score] 신규 채점 {new}건")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
