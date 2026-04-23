"""K-apt (공동주택관리정보시스템) 입찰공고 API 수집기.

공공데이터포털: AptBidInfoOfferSvc (국토교통부, 한국부동산원)
주요 오퍼레이션 (공고일자 조회):
  - getBidInfoByDate  (조회구분: 입찰공고 일자)

파라미터는 각 오퍼레이션 문서에 따라 다를 수 있어 필드 매핑을 FIELD_MAP 상수로 분리.
실제 응답 스키마를 확인한 후 필요시 조정하면 됩니다.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Callable

from utils.logger import get_logger
from collectors.base import http_get_json

logger = get_logger("bid_collector.kapt_api")

DEFAULT_BASE_URL = "https://apis.data.go.kr/1613000/AptBidInfoOfferSvc"
DEFAULT_OPERATION = "getBidInfoByDate"

FIELD_MAP = {
    "bid_no":          ("bidNum", "bidNo", "bidNtceNo"),
    "title":           ("bidTitle", "bidNm", "bidNtceNm"),
    "org_name":        ("kaptName", "ntceInsttNm", "dminsttNm"),
    "contract_method": ("cntrctMthdNm", "cntrctCnclsMthdNm"),
    "estimated_price": ("bidAmt", "presmptPrce", "asignBdgtAmt"),
    "open_date":       ("bidOpenDate", "bidNtceDt"),
    "close_date":      ("bidCloseDate", "bidClseDt"),
    "detail_url":      ("bidUrl", "bidNtceDtlUrl"),
}


def _pick(item: dict, keys: tuple[str, ...]):
    for k in keys:
        v = item.get(k)
        if v not in (None, ""):
            return v
    return None


def _safe_int(v) -> int | None:
    if v in (None, ""):
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


def _yesterday_range(now: datetime | None = None, lookback_days: int = 1) -> tuple[str, str]:
    now = now or datetime.now()
    end = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(seconds=1)
    start = (end - timedelta(days=lookback_days - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def _normalize(item: dict, source: str) -> dict | None:
    bid_no = _pick(item, FIELD_MAP["bid_no"])
    title = _pick(item, FIELD_MAP["title"])
    if not bid_no or not title:
        return None
    return {
        "source": source,
        "bid_no": str(bid_no),
        "title": str(title).strip(),
        "org_name": _pick(item, FIELD_MAP["org_name"]),
        "contract_method": _pick(item, FIELD_MAP["contract_method"]),
        "estimated_price": _safe_int(_pick(item, FIELD_MAP["estimated_price"])),
        "open_date": _pick(item, FIELD_MAP["open_date"]),
        "close_date": _pick(item, FIELD_MAP["close_date"]),
        "bid_type": "K-apt",
        "detail_url": _pick(item, FIELD_MAP["detail_url"]),
    }


def _extract_items(body: dict) -> list[dict]:
    items = body.get("items")
    if items is None:
        return []
    if isinstance(items, list):
        return items
    if isinstance(items, dict):
        inner = items.get("item")
        if isinstance(inner, list):
            return inner
        if isinstance(inner, dict):
            return [inner]
    return []


def collect(
    service_key: str,
    base_url: str = DEFAULT_BASE_URL,
    operation: str = DEFAULT_OPERATION,
    source: str = "kapt_api",
    page_size: int = 100,
    sleep_seconds: float = 1.5,
    lookback_days: int = 1,
    now: datetime | None = None,
    http_client: Callable = http_get_json,
) -> list[dict]:
    if not service_key:
        logger.warning("kapt_api: service key missing — skipping")
        return []

    start, end = _yesterday_range(now, lookback_days)
    url = f"{base_url.rstrip('/')}/{operation}"
    base_params = {
        "serviceKey": service_key,
        "numOfRows": page_size,
        "pageNo": 1,
        "bidStrtDt": start,
        "bidEndDt": end,
        "type": "json",
    }

    rows: list[dict] = []
    try:
        first = http_client(url, {**base_params, "pageNo": 1}, sleep_seconds=sleep_seconds)
    except Exception:
        logger.exception("kapt_api first-page failed")
        return rows

    body = first.get("response", {}).get("body", {})
    total = int(body.get("totalCount") or 0)
    items = _extract_items(body)
    rows.extend(r for r in (_normalize(i, source) for i in items) if r)

    if total <= page_size:
        logger.info("kapt_api: fetched %d/%d", len(rows), total)
        return rows

    total_pages = math.ceil(total / page_size)
    for page_no in range(2, total_pages + 1):
        try:
            data = http_client(url, {**base_params, "pageNo": page_no}, sleep_seconds=sleep_seconds)
        except Exception:
            logger.exception("kapt_api page failed: pageNo=%d", page_no)
            continue
        items = _extract_items(data.get("response", {}).get("body", {}))
        rows.extend(r for r in (_normalize(i, source) for i in items) if r)

    logger.info("kapt_api: fetched %d/%d across %d pages", len(rows), total, total_pages)
    return rows
