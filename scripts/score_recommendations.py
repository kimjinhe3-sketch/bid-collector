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
-- 실행 순서 무관 보장: 참조하는 bid_recommendations v2 컬럼도 여기서 멱등 생성
ALTER TABLE bid_recommendations ADD COLUMN IF NOT EXISTS rec_bid_amount_v2 BIGINT;
ALTER TABLE bid_recommendations ADD COLUMN IF NOT EXISTS expected_sajeong_v2 NUMERIC(8,4);
-- 리뷰보드 표시·필터용: 사업명/발주처/관심그룹 (2026-08-21)
ALTER TABLE bid_rec_scores ADD COLUMN IF NOT EXISTS title TEXT;
ALTER TABLE bid_rec_scores ADD COLUMN IF NOT EXISTS org_name TEXT;
ALTER TABLE bid_rec_scores ADD COLUMN IF NOT EXISTS grp TEXT;  -- 관심그룹명 / '-'=비매칭
-- 세그먼트 피드백 장치 (2026-08-21): 어떤 분류체계의 추천이었는지 기록
ALTER TABLE bid_rec_scores ADD COLUMN IF NOT EXISTS seg_level TEXT;   -- 발주기관/기관유형/공종x하한율/공종전체
ALTER TABLE bid_rec_scores ADD COLUMN IF NOT EXISTS org_type TEXT;
ALTER TABLE bid_rec_scores ADD COLUMN IF NOT EXISTS div TEXT;         -- 공종
-- 리뷰보드 금액 차이 표시용 (2026-08-26): 추천 투찰금액 vs 실제 낙찰금액
ALTER TABLE bid_rec_scores ADD COLUMN IF NOT EXISTS rec_bid_amount BIGINT;
ALTER TABLE bid_rec_scores ADD COLUMN IF NOT EXISTS win_bid_amount BIGINT;
-- 문제 세그먼트 자동 감지 결과 → 추천 엔진이 읽어 강등/보류
CREATE TABLE IF NOT EXISTS bid_seg_feedback (
    seg_key     TEXT PRIMARY KEY,     -- 공종|세그레벨|기관유형
    n           INT,
    under_pct   NUMERIC(5,1),
    beaten_pct  NUMERIC(5,1),
    med_absdiff NUMERIC(8,4),
    med_diff    NUMERIC(8,4),
    flag        TEXT,                 -- unreliable / under_risk / margin_low / ok
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);
"""

# 채점: 개찰결과 중 적격심사 + 추천 캐시가 존재하고 아직 채점 안 된 건
SCORE_SQL = """
INSERT INTO bid_rec_scores
  (bid_no, title, org_name, seg_level, org_type, div,
   rec_bid_rate, est_lower_rate, confidence,
   actual_win_rate, actual_lower, actual_sajeong,
   eff_rate, outcome, eff_rate_v2, outcome_v2,
   diff, lower_hit, open_result_date, rec_bid_amount, win_bid_amount)
SELECT r.bid_no, r.title, r.org_name,
       c.rationale->>'segment', c.rationale->>'org_type', r.bsns_div,
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
       r.open_result_date, c.rec_bid_amount, r.win_bid_amount
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
       ROUND(AVG(CASE WHEN outcome_v2 = 'win' THEN 100.0 WHEN outcome_v2 IS NOT NULL THEN 0 END), 1) AS win_v2_pct
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
            # 사업명 소급 (컬럼 추가 이전 채점분)
            cur.execute(
                "UPDATE bid_rec_scores s SET title = r.title, org_name = r.org_name "
                "FROM bid_results r WHERE r.bid_no = s.bid_no AND s.title IS NULL")
            # 금액 소급 (2026-08-26 컬럼 추가 이전 채점분)
            cur.execute(
                "UPDATE bid_rec_scores s SET rec_bid_amount = c.rec_bid_amount, "
                "       win_bid_amount = r.win_bid_amount "
                "FROM bid_recommendations c, bid_results r "
                "WHERE c.bid_no = s.bid_no AND r.bid_no = s.bid_no "
                "  AND s.rec_bid_amount IS NULL")
            # 관심그룹 분류 — digest_v2 의 그룹 정의 그대로 (포함·제외·발주처 제외)
            from scripts.digest_v2 import GROUPS as _G, _matches as _m

            def _grp(title, org):
                for gname, kws, g_exc, g_org_exc in _G:
                    t = title or ""
                    if not _m(t, kws):
                        continue
                    if g_exc and _m(t, g_exc):
                        continue
                    if g_org_exc and _m(org or "", g_org_exc):
                        continue
                    return gname
                return "-"

            cur.execute("SELECT id, title, org_name FROM bid_rec_scores WHERE grp IS NULL")
            pend = cur.fetchall()
            if pend:
                import psycopg2.extras as _ex
                _ex.execute_batch(
                    cur, "UPDATE bid_rec_scores SET grp = %s WHERE id = %s",
                    [(_grp(r["title"], r["org_name"]), r["id"]) for r in pend], page_size=200)
                print(f"[score] 그룹 분류 {len(pend)}건")
            # 세그먼트 소급 (컬럼 추가 이전 채점분)
            cur.execute(
                "UPDATE bid_rec_scores s SET seg_level = c.rationale->>'segment', "
                "  org_type = c.rationale->>'org_type' "
                "FROM bid_recommendations c WHERE c.bid_no = s.bid_no AND s.seg_level IS NULL")
            cur.execute(
                "UPDATE bid_rec_scores s SET div = r.bsns_div "
                "FROM bid_results r WHERE r.bid_no = s.bid_no AND s.div IS NULL")
            # ── 세그먼트 피드백: 최근 30일 성적으로 문제 분류체계 자동 감지 ──
            # 판정(표본 n>=10): 미달>50% → under_risk / 밀림>60% & 양수오차중앙>0.5 → margin_low
            #                 / |오차|중앙>3%p → unreliable(추천 보류) / 그 외 ok
            cur.execute("""
                INSERT INTO bid_seg_feedback
                  (seg_key, n, under_pct, beaten_pct, med_absdiff, med_diff, flag, updated_at)
                SELECT seg_key, n, under_pct, beaten_pct, med_absdiff, med_diff,
                       CASE WHEN med_absdiff > 3 THEN 'unreliable'
                            WHEN under_pct > 50 THEN 'under_risk'
                            WHEN beaten_pct > 60 AND med_diff > 0.5 THEN 'margin_low'
                            ELSE 'ok' END,
                       NOW()
                FROM (
                  SELECT COALESCE(div,'?') || '|' || COALESCE(seg_level,'?') || '|' || COALESCE(org_type,'?') AS seg_key,
                         COUNT(*) AS n,
                         ROUND(AVG(CASE WHEN outcome='under' THEN 100.0 ELSE 0 END),1) AS under_pct,
                         ROUND(AVG(CASE WHEN outcome='beaten' THEN 100.0 ELSE 0 END),1) AS beaten_pct,
                         PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ABS(diff)) AS med_absdiff,
                         PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY diff) AS med_diff
                  FROM bid_rec_scores
                  WHERE open_result_date >= to_char(NOW() - INTERVAL '30 days', 'YYYY-MM-DD')
                  GROUP BY 1
                ) t
                WHERE n >= 10
                ON CONFLICT (seg_key) DO UPDATE SET
                  n=EXCLUDED.n, under_pct=EXCLUDED.under_pct, beaten_pct=EXCLUDED.beaten_pct,
                  med_absdiff=EXCLUDED.med_absdiff, med_diff=EXCLUDED.med_diff,
                  flag=EXCLUDED.flag, updated_at=NOW()
            """)
            cur.execute("SELECT seg_key, n, flag, med_absdiff FROM bid_seg_feedback WHERE flag != 'ok' ORDER BY n DESC")
            bad = cur.fetchall()
            for b in bad:
                print(f"[score] ⚠ 문제 세그먼트: {b['seg_key']} n={b['n']} flag={b['flag']} |오차|중앙={b['med_absdiff']}")
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
