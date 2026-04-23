"""한국수자원공사(K-water) 전자조달 입찰공고 API 수집기.

공공데이터포털 ID: 15101635
실제 base URL / 오퍼레이션 이름은 공개 페이지에 노출되어 있지 않고 data.go.kr
활용신청 승인 상세페이지의 Swagger UI에서만 확인 가능합니다.

따라서 이 모듈은 base_url / operation을 config.yaml에서 주입받도록 설계했고,
설정이 비어있으면 안전하게 skip합니다. 사용자가 아래 값을 채우면 즉시 동작:

    config.yaml:
      collection:
        kwater:
          base_url: "http://apis.data.go.kr/????/????"   # swagger에서 확인
          operation: "????"                              # 예: getBidPblancList
          type_param: "_type"                            # 또는 "type"

응답 구조는 G2B BidPublicInfoService와 유사 (items.item[], bidNtceNo, bidNtceNm, ...)
로 가정합니다. 실제 응답 확인 후 FIELD_MAP 조정 필요할 수 있음.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Callable

from utils.logger import get_logger
from collectors.base import http_get_json

logger = get_logger("bid_collector.kwater_api")

DEFAULT_BASE_URL = ""      # 사용자가 config로 주입
DEFAULT_OPERATION = ""

# 관례적 필드명 (G2B 스타일 + d2b 스타일 둘 다 수용)
FIELD_MAP = {
    "bid_no":          ("bidNtceNo", "pblancNo", "bidNum"),
    "order":           ("bidNtceOrd", "pblancOdr"),
    "title":           ("bidNtceNm", "bidNm", "bidTitle", "pblancNm"),
    "org_name":        ("ntceInsttNm", "dminsttNm", "ornt"),
    "contract_method": ("cntrctCnclsMthdNm", "cntrctMth"),
    "estimated_price": ("presmptPrce", "bsicExpt", "asignBdgtAmt"),
    "open_date":       ("bidNtceDt", "pblancDate"),
    "close_date":      ("bidClseDt", "biddocPresentnClosDt", "opengDt"),
    "detail_url":      ("bidNtceDtlUrl", "pblancUrl"),
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
        "org_name": _pick(item, FIELD_MAP["org_name"]) or "한국수자원공사",
        "contract_method": _pick(item, FIELD_MAP["contract_method"]),
        "estimated_price": _safe_int(_pick(item, FIELD_MAP["estimated_price"])),
        "open_date": _pick(item, FIELD_MAP["open_date"]),
        "close_date": _pick(item, FIELD_MAP["close_date"]),
        "bid_type": "수자원",
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
    type_param: str = "_type",
    source: str = "kwater_api",
    page_size: int = 100,
    sleep_seconds: float = 1.5,
    lookback_days: int = 1,
    now: datetime | None = None,
    http_client: Callable = http_get_json,
) -> list[dict]:
    if not service_key:
        logger.warning("kwater_api: service key missing — skipping")
        return []
    if not base_url or not operation:
        logger.warning(
            "kwater_api: base_url/operation not configured — skipping. "
            "Set config.collection.kwater.{base_url,operation} from data.go.kr Swagger UI."
        )
        return []

    date_bgn, date_end = _yesterday_range(now, lookback_days)
    url = f"{base_url.rstrip('/')}/{operation}"
    base_params = {
        "serviceKey": service_key,
        "pageNo": 1,
        "numOfRows": page_size,
        "inqryDiv": 1,
        "inqryBgnDt": f"{date_bgn}0000",
        "inqryEndDt": f"{date_end}2359",
        type_param: "json",
    }

    rows: list[dict] = []
    try:
        first = http_client(url, {**base_params, "pageNo": 1}, sleep_seconds=sleep_seconds)
    except Exception:
        logger.exception("kwater_api first-page failed")
        return rows

    body = first.get("response", {}).get("body", {})
    total = int(body.get("totalCount") or 0)
    items = _extract_items(body)
    rows.extend(r for r in (_normalize(i, source) for i in items) if r)

    if total <= page_size:
        logger.info("kwater_api: fetched %d/%d", len(rows), total)
        return rows

    total_pages = math.ceil(total / page_size)
    for page_no in range(2, total_pages + 1):
        try:
            data = http_client(url, {**base_params, "pageNo": page_no}, sleep_seconds=sleep_seconds)
        except Exception:
            logger.exception("kwater_api page failed: pageNo=%d", page_no)
            continue
        items = _extract_items(data.get("response", {}).get("body", {}))
        rows.extend(r for r in (_normalize(i, source) for i in items) if r)

    logger.info("kwater_api: fetched %d/%d across %d pages",
                len(rows), total, total_pages)
    return rows
