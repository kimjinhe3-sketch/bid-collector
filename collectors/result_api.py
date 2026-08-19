# -*- coding: utf-8 -*-
"""나라장터 개찰결과(낙찰정보) 수집기 — AI 투찰 추천 P0 데이터 파이프라인.

API: 공공데이터개방표준서비스 낙찰정보 (기존 G2B_SERVICE_KEY 로 사용 가능, 2026-08-19 확인)
  https://apis.data.go.kr/1230000/ao/PubDataOpnStdService/getDataSetOpnStdScsbidInfo
  필수: bsnsDivCd(1물품/2외자/3공사/5용역), opengBgnDt/opengEndDt(같은 날), type=json
  응답: 개찰 참가업체별 1행 — 기초금액(bssAmt)·예정가격(rsrvtnPrce)·낙찰하한율(sucsfLwstlmtRt)
        ·투찰금액/률(bidprcAmt/Rt)·순위(opengRank)·낙찰여부(sucsfYn)·최종낙찰(fnlSucsf*)

저장: 공고 단위로 집계해 bid_results 1행 (참가업체별 전체 저장은 용량 낭비 —
      사정율 학습에는 공고당 기초/예정/하한율/1순위/참가수면 충분).
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timedelta

from utils.logger import get_logger
from collectors.base import http_get_json

logger = get_logger("bid_collector.result_api")

BASE_URL = "https://apis.data.go.kr/1230000/ao/PubDataOpnStdService/getDataSetOpnStdScsbidInfo"
BSNS_DIVS = {"1": "물품", "3": "공사", "5": "용역"}
PAGE_SIZE = 999
MAX_PAGES_PER_DAY = 300  # 안전 상한 (참가행 기준 하루 최대 ~30만행 방어)


def _safe_float(v):
    if v in (None, "", "-"):
        return None
    try:
        return float(str(v).replace(",", ""))
    except (ValueError, TypeError):
        return None


def _safe_int(v):
    f = _safe_float(v)
    return int(f) if f is not None else None


def _extract_items(data: dict) -> tuple[int, list[dict]]:
    body = data.get("response", {}).get("body", {})
    total = int(body.get("totalCount") or 0)
    items = body.get("items") or []
    if isinstance(items, dict):
        items = items.get("item") or []
    if isinstance(items, dict):
        items = [items]
    return total, items


def fetch_day(service_key: str, day: date, bsns_div: str,
              sleep_seconds: float = 0.2, http_client=http_get_json) -> list[dict]:
    """하루치 개찰 참가행 전체 (페이지네이션)."""
    d = day.strftime("%Y%m%d")
    params = {
        "serviceKey": service_key, "pageNo": 1, "numOfRows": PAGE_SIZE,
        "bsnsDivCd": bsns_div, "opengBgnDt": f"{d}0000", "opengEndDt": f"{d}2359",
        "type": "json",
    }
    rows: list[dict] = []
    try:
        first = http_client(BASE_URL, {**params, "pageNo": 1}, sleep_seconds=sleep_seconds)
    except Exception:
        logger.exception("result_api first page failed: %s div=%s", d, bsns_div)
        return rows
    if "nkoneps.com.response.ResponseError" in first:
        h = first["nkoneps.com.response.ResponseError"]["header"]
        logger.warning("result_api %s div=%s API 오류: %s %s", d, bsns_div,
                       h.get("resultCode"), h.get("resultMsg"))
        return rows
    total, items = _extract_items(first)
    rows.extend(items)
    pages = min(math.ceil(total / PAGE_SIZE), MAX_PAGES_PER_DAY)
    for page in range(2, pages + 1):
        try:
            data = http_client(BASE_URL, {**params, "pageNo": page}, sleep_seconds=sleep_seconds)
            _, items = _extract_items(data)
            rows.extend(items)
        except Exception:
            logger.exception("result_api page failed: %s div=%s p=%d", d, bsns_div, page)
    logger.info("result_api %s div=%s(%s): %d rows (total=%d)", d, bsns_div,
                BSNS_DIVS.get(bsns_div, "?"), len(rows), total)
    return rows


def aggregate(raw_rows: list[dict], bsns_div: str) -> list[dict]:
    """참가행 → 공고 단위 1행 집계."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in raw_rows:
        no = r.get("bidNtceNo")
        if not no:
            continue
        groups[(no, r.get("bidNtceOrd") or "000")].append(r)

    out = []
    for (no, ord_no), rows in groups.items():
        head = rows[0]
        base_amt = _safe_int(head.get("bssAmt"))
        plan_price = _safe_int(head.get("rsrvtnPrce"))
        sajeong = round(plan_price / base_amt * 100, 4) if base_amt and plan_price else None
        # 낙찰자: 최종낙찰 정보가 채워진 행 > sucsfYn=Y > 개찰 1순위
        winner = None
        for r in rows:
            if _safe_float(r.get("fnlSucsfAmt")):
                winner = r
                break
        if winner is None:
            winner = next((r for r in rows if r.get("sucsfYn") == "Y"), None)
        if winner is None:
            winner = next((r for r in rows if str(r.get("opengRank")) == "1"), head)
        win_amt = _safe_int(winner.get("fnlSucsfAmt")) or _safe_int(winner.get("bidprcAmt"))
        win_rate = _safe_float(winner.get("fnlSucsfRt")) or _safe_float(winner.get("bidprcRt"))
        bizrnos = {r.get("bidprcCorpBizrno") for r in rows if r.get("bidprcCorpBizrno")}
        out.append({
            "bid_no": f"{no}-{ord_no}" if ord_no else str(no),
            "title": (head.get("bidNtceNm") or "").strip(),
            "org_name": head.get("ntceInsttNm") or head.get("dmndInsttNm"),
            "bsns_div": BSNS_DIVS.get(bsns_div, bsns_div),
            "decision_method": head.get("bidwinrDcsnMthdNm"),
            "presmpt_price": _safe_int(head.get("presmptPrce")),
            "base_price": base_amt,
            "planned_price": plan_price,
            "sajeong_rate": sajeong,
            "win_lower_rate": _safe_float(head.get("sucsfLwstlmtRt")),
            "win_bid_amount": win_amt,
            "win_bid_rate": win_rate,
            "bidder_count": len(bizrnos) or len(rows),
            "open_result_date": head.get("opengDate"),
            "winner_name": winner.get("fnlSucsfCorpNm") or winner.get("bidprcCorpNm"),
        })
    return out


def collect_range(service_key: str, start: date, end: date,
                  sleep_seconds: float = 0.2) -> list[dict]:
    """[start, end] 기간의 개찰결과 (물품/공사/용역) 를 공고 단위로 집계해 반환."""
    all_out: list[dict] = []
    day = start
    while day <= end:
        for div in BSNS_DIVS:
            raw = fetch_day(service_key, day, div, sleep_seconds=sleep_seconds)
            if raw:
                all_out.extend(aggregate(raw, div))
        day += timedelta(days=1)
    logger.info("result_api collect_range %s~%s: %d 공고", start, end, len(all_out))
    return all_out
