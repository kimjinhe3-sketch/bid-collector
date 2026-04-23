"""국방전자조달(d2b) 입찰공고 API 수집기.

공공데이터포털 ID: 15002040 (국내경쟁 입찰공고 목록)
Base URL: http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/
필드명이 G2B와 다름 (pblancNo, bidNm, opengDt ...).

대표 오퍼레이션:
  - getDmstcCmpetBidPblancList  (국내경쟁 입찰)
  - getIntrcnBidPblancList      (국제 입찰)
  - getPrvateContrctPblancList  (수의계약)
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Callable

from utils.logger import get_logger
from collectors.base import http_get_json

logger = get_logger("bid_collector.d2b_api")

DEFAULT_BASE_URL = "http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService"

OPERATIONS: dict[str, tuple[str, str]] = {
    # 현재 d2b OpenAPI에서 공개되는 오퍼레이션은 국내경쟁 1개뿐 (2026-04 확인).
    # 국제/수의 별도 엔드포인트는 data.go.kr에 미등록 상태.
    "d2b_api_dmstc": ("getDmstcCmpetBidPblancList", "국방"),
}

FIELD_MAP = {
    "bid_no":          ("pblancNo", "bidNtceNo"),
    "order":           ("pblancOdr", "bidNtceOrd"),
    "title":           ("bidNm", "pblancNm", "bidNtceNm"),
    "org_name":        ("ornt", "orntNm", "dmndInsttNm", "ntceInsttNm"),
    "contract_method": ("cntrctMth", "cntrctCnclsMthdNm"),
    "estimated_price": ("bsicExpt", "presmptPrce", "asignBdgtAmt"),
    "open_date":       ("pblancDate", "bidNtceDt"),
    "close_date":      ("opengDt", "biddocPresentnClosDt", "bidClseDt"),
    "detail_url":      ("pblancUrl", "bidNtceDtlUrl"),
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
    # d2b uses YYYYMMDD date filter
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def _normalize(item: dict, source: str, bid_type: str) -> dict | None:
    bid_no_raw = _pick(item, FIELD_MAP["bid_no"])
    title = _pick(item, FIELD_MAP["title"])
    if not bid_no_raw or not title:
        return None
    order = _pick(item, FIELD_MAP["order"]) or ""
    bid_no = f"{bid_no_raw}-{order}" if order else str(bid_no_raw)
    return {
        "source": source,
        "bid_no": bid_no,
        "title": str(title).strip(),
        "org_name": _pick(item, FIELD_MAP["org_name"]),
        "contract_method": _pick(item, FIELD_MAP["contract_method"]),
        "estimated_price": _safe_int(_pick(item, FIELD_MAP["estimated_price"])),
        "open_date": _pick(item, FIELD_MAP["open_date"]),
        "close_date": _pick(item, FIELD_MAP["close_date"]),
        "bid_type": bid_type,
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


def fetch_operation(
    service_key: str,
    operation: str,
    bid_type: str,
    source: str,
    date_bgn: str,
    date_end: str,
    page_size: int = 100,
    sleep_seconds: float = 1.5,
    base_url: str = DEFAULT_BASE_URL,
    http_client: Callable = http_get_json,
) -> list[dict]:
    url = f"{base_url.rstrip('/')}/{operation}"
    base_params = {
        "ServiceKey": service_key,  # d2b uses capital-S ServiceKey
        "pageNo": 1,
        "numOfRows": page_size,
        "anmtDateBegin": date_bgn,
        "anmtDateEnd": date_end,
        "_type": "json",  # d2b requires underscore prefix, not "type=json"
    }

    rows: list[dict] = []
    try:
        first = http_client(url, {**base_params, "pageNo": 1}, sleep_seconds=sleep_seconds)
    except Exception:
        logger.exception("d2b first-page failed: op=%s", operation)
        return rows

    body = first.get("response", {}).get("body", {})
    total = int(body.get("totalCount") or 0)
    items = _extract_items(body)
    rows.extend(r for r in (_normalize(i, source, bid_type) for i in items) if r)

    if total <= page_size:
        logger.info("d2b %s: fetched %d/%d", operation, len(rows), total)
        return rows

    total_pages = math.ceil(total / page_size)
    for page_no in range(2, total_pages + 1):
        try:
            data = http_client(url, {**base_params, "pageNo": page_no}, sleep_seconds=sleep_seconds)
        except Exception:
            logger.exception("d2b page failed: op=%s pageNo=%d", operation, page_no)
            continue
        items = _extract_items(data.get("response", {}).get("body", {}))
        rows.extend(r for r in (_normalize(i, source, bid_type) for i in items) if r)

    logger.info("d2b %s: fetched %d/%d across %d pages",
                operation, len(rows), total, total_pages)
    return rows


def collect_all(
    service_key: str,
    page_size: int = 100,
    sleep_seconds: float = 1.5,
    lookback_days: int = 1,
    now: datetime | None = None,
    base_url: str = DEFAULT_BASE_URL,
    http_client: Callable = http_get_json,
) -> list[dict]:
    if not service_key:
        logger.warning("d2b: service key missing — skipping")
        return []

    date_bgn, date_end = _yesterday_range(now, lookback_days)
    logger.info("d2b collection range: %s ~ %s", date_bgn, date_end)

    all_rows: list[dict] = []
    for source, (operation, bid_type) in OPERATIONS.items():
        try:
            rows = fetch_operation(
                service_key=service_key,
                operation=operation,
                bid_type=bid_type,
                source=source,
                date_bgn=date_bgn,
                date_end=date_end,
                page_size=page_size,
                sleep_seconds=sleep_seconds,
                base_url=base_url,
                http_client=http_client,
            )
            all_rows.extend(rows)
        except Exception:
            logger.exception("d2b operation crashed: %s", operation)
    return all_rows
