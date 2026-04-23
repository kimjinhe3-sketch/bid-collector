"""나라장터(조달청) 입찰공고정보서비스 API 수집기.

공공데이터포털: BidPublicInfoService
오퍼레이션:
  - getBidPblancListInfoThng    (물품)
  - getBidPblancListInfoServc   (용역)
  - getBidPblancListInfoCnstwk  (공사)
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Callable

from utils.logger import get_logger
from collectors.base import http_get_json

logger = get_logger("bid_collector.g2b_api")

BASE_URL = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService"

OPERATIONS: dict[str, tuple[str, str]] = {
    "g2b_api_thng":   ("getBidPblancListInfoThng",   "물품"),
    "g2b_api_servc":  ("getBidPblancListInfoServc",  "용역"),
    "g2b_api_cnstwk": ("getBidPblancListInfoCnstwk", "공사"),
}


def _yesterday_range(now: datetime | None = None, lookback_days: int = 1) -> tuple[str, str]:
    now = now or datetime.now()
    end = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(seconds=1)
    start = (end - timedelta(days=lookback_days - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    fmt = "%Y%m%d%H%M"
    return start.strftime(fmt), end.strftime(fmt)


def _safe_int(v) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


def _normalize(item: dict, source: str, bid_type: str) -> dict | None:
    bid_no = item.get("bidNtceNo") or item.get("bidNtceNoCombo")
    title = item.get("bidNtceNm")
    if not bid_no or not title:
        return None
    ord_no = item.get("bidNtceOrd") or ""
    bid_no_full = f"{bid_no}-{ord_no}" if ord_no else str(bid_no)
    return {
        "source": source,
        "bid_no": bid_no_full,
        "title": title.strip(),
        "org_name": item.get("ntceInsttNm") or item.get("dminsttNm"),
        "contract_method": item.get("cntrctCnclsMthdNm"),
        "estimated_price": _safe_int(item.get("presmptPrce") or item.get("asignBdgtAmt")),
        "open_date": item.get("bidNtceDt"),
        "close_date": item.get("bidClseDt"),
        "bid_type": bid_type,
        "detail_url": item.get("bidNtceDtlUrl") or item.get("bidNtceUrl"),
    }


def fetch_operation(
    service_key: str,
    operation: str,
    bid_type: str,
    source: str,
    inqry_bgn: str,
    inqry_end: str,
    page_size: int = 100,
    sleep_seconds: float = 1.5,
    http_client: Callable = http_get_json,
) -> list[dict]:
    """Fetch all pages for a single operation. Returns normalized rows."""
    url = f"{BASE_URL}/{operation}"
    base_params = {
        "serviceKey": service_key,
        "pageNo": 1,
        "numOfRows": page_size,
        "inqryDiv": 1,
        "inqryBgnDt": inqry_bgn,
        "inqryEndDt": inqry_end,
        "type": "json",
    }

    rows: list[dict] = []
    try:
        first = http_client(url, {**base_params, "pageNo": 1}, sleep_seconds=sleep_seconds)
    except Exception:
        logger.exception("g2b_api first-page failed: op=%s", operation)
        return rows

    body = first.get("response", {}).get("body", {})
    total = int(body.get("totalCount") or 0)
    items = _extract_items(body)
    rows.extend(r for r in (_normalize(i, source, bid_type) for i in items) if r)

    if total <= page_size:
        logger.info("g2b_api %s: fetched %d/%d", operation, len(rows), total)
        return rows

    total_pages = math.ceil(total / page_size)
    for page_no in range(2, total_pages + 1):
        try:
            data = http_client(url, {**base_params, "pageNo": page_no}, sleep_seconds=sleep_seconds)
        except Exception:
            logger.exception("g2b_api page failed: op=%s pageNo=%d", operation, page_no)
            continue
        items = _extract_items(data.get("response", {}).get("body", {}))
        rows.extend(r for r in (_normalize(i, source, bid_type) for i in items) if r)

    logger.info("g2b_api %s: fetched %d/%d across %d pages",
                operation, len(rows), total, total_pages)
    return rows


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


def collect_all(
    service_key: str,
    page_size: int = 100,
    sleep_seconds: float = 1.5,
    lookback_days: int = 1,
    now: datetime | None = None,
    http_client: Callable = http_get_json,
) -> list[dict]:
    """Collect bids across all three operations for the lookback window."""
    inqry_bgn, inqry_end = _yesterday_range(now, lookback_days)
    logger.info("g2b_api collection range: %s ~ %s", inqry_bgn, inqry_end)

    all_rows: list[dict] = []
    for source, (operation, bid_type) in OPERATIONS.items():
        try:
            rows = fetch_operation(
                service_key=service_key,
                operation=operation,
                bid_type=bid_type,
                source=source,
                inqry_bgn=inqry_bgn,
                inqry_end=inqry_end,
                page_size=page_size,
                sleep_seconds=sleep_seconds,
                http_client=http_client,
            )
            all_rows.extend(rows)
        except Exception:
            logger.exception("g2b_api operation crashed: %s", operation)
    return all_rows
