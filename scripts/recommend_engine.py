# -*- coding: utf-8 -*-
"""P1 추천 엔진 — 진행중 나라장터 공고에 적정 투찰률·금액 산출 → bid_recommendations 캐시.

로직 (룰+통계, 설명가능):
  1. 낙찰하한율 추정: (공종, 금액대) 과거 최빈값 — 확신도(최빈 비중) 기록
  2. 예상 사정율:    세그먼트 계층 폴백 중앙값
  3. 마진:           세그먼트 마진 최빈 구간(0.005%p 빈) — 낙찰자 밀집 지점 조준
     (2026-08-26 적중권률 목표화로 p25에서 교체. 백테스트: 적중권 4.4→6.5%)
     + 마진 다이얼(B안): 기관 이력상 약경쟁(참가 중앙 ≤6개사) 예측 시
       이력 낙찰마진 중앙의 절반으로 상향 — 저가 수주 방지 (상한 +3%p)
  4. 추천 투찰률 = 하한율 + 마진 (예정가격 대비 %)
     추천 투찰금액 = 기초금액추정(추정가격×공종별 배율) × 사정율 × 투찰률

세그먼트 계층 (표본 많은 쪽 우선):
  발주기관×공종(n≥8) → 기관유형×공종(n≥8) → 공종×하한율밴드(n≥5) → 공종 전체

confidence: high(기관 세그먼트 + 하한율 확신 ≥70%) / medium(유형·밴드 세그먼트) / low(그 외)
대상: 나라장터(g2b_api_*) 진행중 공고, 공종 물품/공사/용역, 추정가격 존재.

Usage (DATABASE_URL 필요 — Actions):
    python -m scripts.recommend_engine
"""
from __future__ import annotations

import json
import os
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import setup_logger, get_logger  # noqa: E402
from scripts.analyze_patterns import org_type, amount_band  # noqa: E402

EOK = 100_000_000

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS bid_recommendations (
    id               BIGSERIAL PRIMARY KEY,
    source           TEXT NOT NULL,
    bid_no           TEXT NOT NULL,
    rec_bid_rate     NUMERIC(8,4),     -- 추천 투찰률 (예정가격 대비 %)
    rec_bid_amount   BIGINT,           -- 추천 투찰금액 (원)
    est_lower_rate   NUMERIC(8,4),     -- 추정 낙찰하한율
    expected_sajeong NUMERIC(8,4),     -- 예상 사정율
    margin           NUMERIC(8,4),     -- 적용 마진 (p25)
    confidence       TEXT,             -- high / medium / low
    sample_count     INT,              -- 참조 세그먼트 표본수
    rationale        JSONB,            -- 근거 (세그먼트 경로·분포)
    computed_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(source, bid_no)
);
-- ③ 섀도우 모델 (기관 사정율 편향 반영) — 실제 노출 안 함, 채점 비교용 (2026-08-19)
ALTER TABLE bid_recommendations ADD COLUMN IF NOT EXISTS rec_bid_amount_v2 BIGINT;
ALTER TABLE bid_recommendations ADD COLUMN IF NOT EXISTS expected_sajeong_v2 NUMERIC(8,4);
-- 실행 순서 무관 보장: 공고 실제값 컬럼 (본생성은 수집기 init_db — 여기선 멱등 백업)
ALTER TABLE bid_announcements ADD COLUMN IF NOT EXISTS win_lower_rate NUMERIC(8,4);
ALTER TABLE bid_announcements ADD COLUMN IF NOT EXISTS base_price BIGINT;
ALTER TABLE bid_announcements ADD COLUMN IF NOT EXISTS prc_rng_bgn NUMERIC(6,2);
ALTER TABLE bid_announcements ADD COLUMN IF NOT EXISTS prc_rng_end NUMERIC(6,2);
ALTER TABLE bid_announcements ADD COLUMN IF NOT EXISTS decision_method TEXT;
-- 웹 정렬용: AI 추천 신뢰도 랭크 (high=3/medium=2/low=1, 추천 없음=NULL)
ALTER TABLE bid_announcements ADD COLUMN IF NOT EXISTS rec_rank SMALLINT;
"""


def _q(vals, p):
    vals = sorted(vals)
    if not vals:
        return None
    i = (len(vals) - 1) * p
    lo, hi = int(i), min(int(i) + 1, len(vals) - 1)
    return vals[lo] + (vals[hi] - vals[lo]) * (i - lo)


def _mode(vals, binw=0.005):
    """최빈 구간(binw 반올림) 중심값 — 낙찰자들이 가장 많이 서는 마진 지점.

    적중권률(오차 ±0.005%p) 목표 확정(2026-08-26)에 따라 p25 → 최빈 조준으로 교체.
    시간분리 백테스트 3,284건: 적중권 4.4→6.5% / 낙찰률 71.6→68.9% / 기대마진 -14%.
    """
    from collections import Counter as _C
    c = _C(round(v / binw) * binw for v in vals)
    return c.most_common(1)[0][0]


def _conn():
    import psycopg2
    from psycopg2.extras import RealDictCursor
    url = os.environ["DATABASE_URL"]
    if "sslmode=" not in url:
        url = f"{url}{'&' if '?' in url else '?'}sslmode=require"
    return psycopg2.connect(url, cursor_factory=RealDictCursor)


def load_results(cur) -> list[dict]:
    cur.execute(
        "SELECT title, org_name, bsns_div, base_price, presmpt_price, sajeong_rate,"
        "       win_lower_rate, win_bid_rate, bidder_count FROM bid_results "
        "WHERE decision_method LIKE '%적격%' AND win_lower_rate IS NOT NULL "
        "  AND win_bid_rate IS NOT NULL")
    out = []
    for x in cur.fetchall():
        lw, wr = float(x["win_lower_rate"]), float(x["win_bid_rate"])
        if not (0 <= wr - lw <= 15):
            continue
        sj = float(x["sajeong_rate"]) if x["sajeong_rate"] else None
        if sj is not None and not (95 <= sj <= 105):
            continue
        out.append({**x, "_lw": lw, "_m": wr - lw, "_sj": sj,
                    "_otype": org_type(x["org_name"]), "_band": amount_band(x["base_price"])})
    return out


class SegmentBook:
    """계층 폴백 룩업 — 사정율·마진·하한율·기초/추정 배율."""

    def __init__(self, results: list[dict]):
        self.by_org = defaultdict(list)
        self.by_otype = defaultdict(list)
        self.by_band = defaultdict(list)
        self.by_div = defaultdict(list)
        self.lower_by_div_band = defaultdict(list)
        self.ratio_by_div = defaultdict(list)
        self.sj_by_org = defaultdict(list)   # ③ 섀도우: 발주기관별 사정율
        # 마진 다이얼용 경쟁 이력 — (참가업체수, 낙찰마진) (2026-08-25 B안)
        self.comp_by_ob = defaultdict(list)  # (기관, 공종, 금액밴드)
        self.comp_by_od = defaultdict(list)  # (기관, 공종)
        for x in results:
            div = x["bsns_div"]
            self.by_org[(x["org_name"], div)].append(x)
            self.by_otype[(x["_otype"], div)].append(x)
            self.by_band[(div, round(x["_lw"], 3))].append(x)
            self.by_div[div].append(x)
            self.lower_by_div_band[(div, x["_band"])].append(round(x["_lw"], 3))
            self.comp_by_ob[(x["org_name"], div, x["_band"])].append((x.get("bidder_count"), x["_m"]))
            self.comp_by_od[(x["org_name"], div)].append((x.get("bidder_count"), x["_m"]))
            if x["_sj"] is not None:
                self.sj_by_org[x["org_name"]].append(x["_sj"])
            if x["base_price"] and x["presmpt_price"]:
                r = x["base_price"] / x["presmpt_price"]
                if 0.9 <= r <= 1.3:
                    self.ratio_by_div[div].append(r)

    def est_lower(self, div: str, band: str) -> tuple[float | None, float, int]:
        vals = self.lower_by_div_band.get((div, band)) or []
        if not vals:
            vals = [round(x["_lw"], 3) for x in self.by_div.get(div, [])]
        if not vals:
            return None, 0.0, 0
        mode, cnt = Counter(vals).most_common(1)[0]
        return mode, cnt / len(vals), len(vals)

    def stats(self, org: str, otype: str, div: str, lower: float | None):
        for level, items in (("발주기관", self.by_org.get((org, div))),
                             ("기관유형", self.by_otype.get((otype, div)))):
            if items and len(items) >= 8:
                return level, items
        if lower is not None:
            items = self.by_band.get((div, round(lower, 3)))
            if items and len(items) >= 5:
                return "공종x하한율", items
        return "공종전체", self.by_div.get(div) or []

    def org_sajeong(self, org: str, seg_median: float, k: int = 8) -> float | None:
        """③ 기관 사정율 수축(shrinkage) 추정 — n<8 이면 None (섀도우 미적용).
        소표본 과적합 방지: (n*기관중앙 + k*세그중앙) / (n+k)."""
        vals = self.sj_by_org.get(org) or []
        if len(vals) < 8:
            return None
        org_med = statistics.median(vals)
        return (len(vals) * org_med + k * seg_median) / (len(vals) + k)

    def ratio(self, div: str) -> float:
        vals = self.ratio_by_div.get(div) or []
        return statistics.median(vals) if len(vals) >= 5 else 1.1  # 통상 부가세 배율

    def predict_weak_comp(self, org: str, div: str, band: str):
        """마진 다이얼(B안) 경쟁 예측 — 기관x공종x밴드(n>=2) 우선, 기관x공종(n>=3) 폴백.
        과거 참가업체수 중앙 <=6 이면 약경쟁 예측 → (이력 낙찰마진들, 참가수중앙, 표본수).
        백테스트(2026-08-25, 2512건): 정밀도 70%, 발동건 기대마진 0.55→1.21%p."""
        for hist, key, min_n in ((self.comp_by_ob, (org, div, band), 2),
                                 (self.comp_by_od, (org, div), 3)):
            past = hist.get(key) or []
            if len(past) >= min_n:
                bcs = [b for b, _ in past if b]
                if bcs and statistics.median(bcs) <= 6:
                    return [m for _, m in past], statistics.median(bcs), len(past)
                return None  # 이력 있고 경쟁 치열 → 폴백 안 내려감
        return None


BID_TYPE_MAP = {"물품": "물품", "공사": "공사", "용역": "용역"}


def load_seg_feedback(cur) -> dict[str, str]:
    """세그먼트 피드백 (score_recommendations 산출) — seg_key → flag."""
    try:
        cur.execute("SELECT seg_key, flag FROM bid_seg_feedback WHERE flag != 'ok'")
        return {r["seg_key"]: r["flag"] for r in cur.fetchall()}
    except Exception:
        return {}


def load_active_bids(cur) -> list[dict]:
    today = (datetime.now(timezone.utc) + timedelta(hours=9)).date().isoformat()
    cur.execute(
        "SELECT source, bid_no, title, org_name, bid_type, estimated_price, "
        "       win_lower_rate, base_price, decision_method "
        "FROM bid_announcements "
        "WHERE source LIKE 'g2b_api%%' AND estimated_price > 0 "
        "  AND bid_type = ANY(%s) "
        "  AND close_date IS NOT NULL AND SUBSTR(REPLACE(close_date,'/','-'),1,10) >= %s",
        (list(BID_TYPE_MAP), today))
    return [dict(r) for r in cur.fetchall()]


def recommend(bid: dict, book: SegmentBook, feedback: dict[str, str] | None = None) -> dict | None:
    div = BID_TYPE_MAP.get(bid["bid_type"])
    if not div:
        return None
    # 낙찰방식 게이트 — 우리 모델은 "하한선 위 최저가" 게임(적격심사제)에만 유효.
    # 협상·수의·최저가·규격가격동시 등은 게임 규칙이 달라 추천하지 않는다 (2026-08-21).
    dm = bid.get("decision_method")
    if dm:
        if "적격" not in dm:
            return None
    elif not bid.get("win_lower_rate"):
        # 방식 미상(구수집분)이면 공고 하한율 존재를 적격심사형 증거로 요구
        return None
    presmpt = bid["estimated_price"]
    ratio = book.ratio(div)
    # ② 기초금액: 공고 실제값 우선, 없으면 추정 폴백
    actual_base = bid.get("base_price")
    base_est = actual_base or (presmpt * ratio)
    band = amount_band(base_est)
    # ② 낙찰하한율: 공고 실제값 우선 (sucsfbidLwltRate), 없으면 최빈 추정 폴백
    actual_lower = bid.get("win_lower_rate")
    if actual_lower:
        lower, lower_conf, lower_n = float(actual_lower), 1.0, 0
    else:
        lower, lower_conf, lower_n = book.est_lower(div, band)
    if lower is None:
        return None
    otype = org_type(bid.get("org_name"))
    level, items = book.stats(bid.get("org_name") or "", otype, div, lower)
    if len(items) < 3:
        return None
    sjs = [x["_sj"] for x in items if x["_sj"] is not None]
    ms = [x["_m"] for x in items]
    exp_sj = statistics.median(sjs) if sjs else 100.0
    margin = _mode(ms)  # 적중권률 조준 — p25(안전빵)에서 최빈(낙찰자 밀집 지점)으로 (2026-08-26)

    # ── 마진 다이얼 (B안, 2026-08-25): 경쟁 약함 예측 시 저가 수주 방지 ──
    # 하한 근처(p25) 안전빵은 경쟁 치열 공고에선 정답이지만, 참가 1~3개사
    # 공고에선 낙찰자보다 3~4%p 낮게 써 수익을 버림(실측 남긴폭 중앙 3.8%p).
    # 발동 시 이력 낙찰마진 중앙의 절반 지점으로 상향 (상한 +3%p).
    dial = None
    weak = book.predict_weak_comp(bid.get("org_name") or "", div, band)
    if weak:
        hist_ms, med_bc, hist_n = weak
        margin_base = margin
        margin = round(min(max(margin, 0.5 * statistics.median(hist_ms)), margin + 3.0), 4)
        if margin > margin_base:
            dial = {"pred": "약경쟁", "med_bidders": med_bc, "hist_n": hist_n,
                    "margin_base": round(margin_base, 4)}
    rec_rate = round(lower + margin, 4)
    rec_amount = int(base_est * (exp_sj / 100) * (rec_rate / 100) // 10 * 10)

    # ③ 섀도우: 기관 사정율 편향(수축) 적용 금액 — 노출 안 함, 채점 비교 전용
    sj_v2 = book.org_sajeong(bid.get("org_name") or "", exp_sj)
    rec_amount_v2 = (int(base_est * (sj_v2 / 100) * (rec_rate / 100) // 10 * 10)
                     if sj_v2 is not None else None)

    # 신뢰도 — 하한율이 공고 실제값이면 한 단계 승격
    if level == "발주기관" and lower_conf >= 0.7:
        conf = "high"
    elif level in ("기관유형", "공종x하한율") and lower_conf >= 0.5:
        conf = "medium"
    else:
        conf = "low"
    if actual_lower and conf != "high":
        conf = "high" if level in ("발주기관", "기관유형") else "medium"

    # ── 세그먼트 피드백 반영 (실전 채점 기반 자동 보완 장치, 2026-08-21) ──
    # unreliable(|오차|중앙>3%p): 추천 보류 / under_risk·margin_low: 신뢰도 강등 + 근거 표기
    fb_flag = None
    if feedback:
        seg_key = f"{div}|{level}|{otype}"
        fb_flag = feedback.get(seg_key)
        if fb_flag == "unreliable":
            return None
        if fb_flag in ("under_risk", "margin_low"):
            conf = {"high": "medium", "medium": "low", "low": "low"}[conf]
    return {
        "source": bid["source"], "bid_no": bid["bid_no"],
        "rec_bid_rate": rec_rate, "rec_bid_amount": rec_amount,
        "rec_bid_amount_v2": rec_amount_v2,
        "expected_sajeong_v2": round(sj_v2, 4) if sj_v2 is not None else None,
        "est_lower_rate": lower, "expected_sajeong": round(exp_sj, 4),
        "margin": round(margin, 4), "confidence": conf, "sample_count": len(items),
        "rationale": json.dumps({
            "segment": level, "n": len(items),
            "lower_src": "공고" if actual_lower else "추정",
            "base_src": "공고" if actual_base else "추정",
            "lower_mode_share": round(lower_conf, 3), "lower_n": lower_n,
            "seg_feedback": fb_flag, "dial": dial,
            "base_ratio": round(ratio, 4), "band": band, "org_type": otype,
            "margin_p25_p50_p75": [round(_q(ms, p), 3) for p in (0.25, 0.5, 0.75)],
            "sajeong_iqr": [round(_q(sjs, p), 3) for p in (0.25, 0.75)] if len(sjs) >= 4 else None,
        }, ensure_ascii=False),
    }


def main() -> int:
    setup_logger(level="INFO")
    logger = get_logger("recommend_engine")
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
            results = load_results(cur)
            if len(results) < 50:
                logger.warning("학습 표본 부족(%d) — 추천 생략", len(results))
                return 0
            book = SegmentBook(results)
            bids = load_active_bids(cur)
            feedback = load_seg_feedback(cur)
            if feedback:
                print(f"[recommend_engine] 세그먼트 피드백 반영: {len(feedback)}건 {feedback}")
            logger.info("학습 %d건 / 대상 공고 %d건", len(results), len(bids))

            recs = [r for r in (recommend(b, book, feedback) for b in bids) if r]
            cols = ("source", "bid_no", "rec_bid_rate", "rec_bid_amount",
                    "rec_bid_amount_v2", "expected_sajeong_v2", "est_lower_rate",
                    "expected_sajeong", "margin", "confidence", "sample_count", "rationale")
            import psycopg2.extras
            sql = (f"INSERT INTO bid_recommendations ({', '.join(cols)}) "
                   f"VALUES ({', '.join('%(' + c + ')s' for c in cols)}) "
                   f"ON CONFLICT (source, bid_no) DO UPDATE SET "
                   + ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c not in ("source", "bid_no"))
                   + ", computed_at=NOW()")
            psycopg2.extras.execute_batch(cur, sql, recs, page_size=200)
            # 웹 "AI 추천" 정렬용 랭크를 공고 테이블에 동기화
            cur.execute(
                "UPDATE bid_announcements a SET rec_rank = sub.rank "
                "FROM (SELECT bid_no, CASE confidence WHEN 'high' THEN 3 "
                "      WHEN 'medium' THEN 2 ELSE 1 END AS rank "
                "      FROM bid_recommendations) sub "
                "WHERE a.bid_no = sub.bid_no AND a.source LIKE 'g2b_api%%'")
        conn.commit()
        by_conf = Counter(r["confidence"] for r in recs)
        n_dial = sum(1 for r in recs if '"pred": "약경쟁"' in r["rationale"])
        print(f"[recommend_engine] 추천 {len(recs)}건 저장 (high {by_conf.get('high',0)} / "
              f"medium {by_conf.get('medium',0)} / low {by_conf.get('low',0)}) "
              f"| 마진 다이얼 발동 {n_dial}건")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
