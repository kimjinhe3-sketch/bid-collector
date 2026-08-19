# -*- coding: utf-8 -*-
"""P1 추천 엔진 — 진행중 나라장터 공고에 적정 투찰률·금액 산출 → bid_recommendations 캐시.

로직 (룰+통계, 설명가능):
  1. 낙찰하한율 추정: (공종, 금액대) 과거 최빈값 — 확신도(최빈 비중) 기록
  2. 예상 사정율:    세그먼트 계층 폴백 중앙값
  3. 마진:           세그먼트 마진 p25 (하한 대비 낙찰 여유의 하위 25%)
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
"""


def _q(vals, p):
    vals = sorted(vals)
    if not vals:
        return None
    i = (len(vals) - 1) * p
    lo, hi = int(i), min(int(i) + 1, len(vals) - 1)
    return vals[lo] + (vals[hi] - vals[lo]) * (i - lo)


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
        "       win_lower_rate, win_bid_rate FROM bid_results "
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
        for x in results:
            div = x["bsns_div"]
            self.by_org[(x["org_name"], div)].append(x)
            self.by_otype[(x["_otype"], div)].append(x)
            self.by_band[(div, round(x["_lw"], 3))].append(x)
            self.by_div[div].append(x)
            self.lower_by_div_band[(div, x["_band"])].append(round(x["_lw"], 3))
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

    def ratio(self, div: str) -> float:
        vals = self.ratio_by_div.get(div) or []
        return statistics.median(vals) if len(vals) >= 5 else 1.1  # 통상 부가세 배율


BID_TYPE_MAP = {"물품": "물품", "공사": "공사", "용역": "용역"}


def load_active_bids(cur) -> list[dict]:
    today = (datetime.now(timezone.utc) + timedelta(hours=9)).date().isoformat()
    cur.execute(
        "SELECT source, bid_no, title, org_name, bid_type, estimated_price "
        "FROM bid_announcements "
        "WHERE source LIKE 'g2b_api%' AND estimated_price > 0 "
        "  AND bid_type = ANY(%s) "
        "  AND close_date IS NOT NULL AND SUBSTR(REPLACE(close_date,'/','-'),1,10) >= %s",
        (list(BID_TYPE_MAP), today))
    return [dict(r) for r in cur.fetchall()]


def recommend(bid: dict, book: SegmentBook) -> dict | None:
    div = BID_TYPE_MAP.get(bid["bid_type"])
    if not div:
        return None
    presmpt = bid["estimated_price"]
    ratio = book.ratio(div)
    base_est = presmpt * ratio
    band = amount_band(base_est)
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
    margin = _q(ms, 0.25)
    rec_rate = round(lower + margin, 4)
    rec_amount = int(base_est * (exp_sj / 100) * (rec_rate / 100) // 10 * 10)
    if level == "발주기관" and lower_conf >= 0.7:
        conf = "high"
    elif level in ("기관유형", "공종x하한율") and lower_conf >= 0.5:
        conf = "medium"
    else:
        conf = "low"
    return {
        "source": bid["source"], "bid_no": bid["bid_no"],
        "rec_bid_rate": rec_rate, "rec_bid_amount": rec_amount,
        "est_lower_rate": lower, "expected_sajeong": round(exp_sj, 4),
        "margin": round(margin, 4), "confidence": conf, "sample_count": len(items),
        "rationale": json.dumps({
            "segment": level, "n": len(items),
            "lower_mode_share": round(lower_conf, 3), "lower_n": lower_n,
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
            logger.info("학습 %d건 / 대상 공고 %d건", len(results), len(bids))

            recs = [r for r in (recommend(b, book) for b in bids) if r]
            cols = ("source", "bid_no", "rec_bid_rate", "rec_bid_amount", "est_lower_rate",
                    "expected_sajeong", "margin", "confidence", "sample_count", "rationale")
            import psycopg2.extras
            sql = (f"INSERT INTO bid_recommendations ({', '.join(cols)}) "
                   f"VALUES ({', '.join('%(' + c + ')s' for c in cols)}) "
                   f"ON CONFLICT (source, bid_no) DO UPDATE SET "
                   + ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c not in ("source", "bid_no"))
                   + ", computed_at=NOW()")
            psycopg2.extras.execute_batch(cur, sql, recs, page_size=200)
        conn.commit()
        by_conf = Counter(r["confidence"] for r in recs)
        print(f"[recommend_engine] 추천 {len(recs)}건 저장 (high {by_conf.get('high',0)} / "
              f"medium {by_conf.get('medium',0)} / low {by_conf.get('low',0)})")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
