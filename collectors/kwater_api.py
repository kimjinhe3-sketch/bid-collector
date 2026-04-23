"""한국수자원공사(K-water) 전자조달 입찰공고 API 수집기.

공공데이터포털 ID: 15101635
Base URL:  https://apis.data.go.kr/B500001/eBid/tndr3
오퍼레이션 (상세기능):
  - /cntrwkList   (공사)
  - /gdsList      (물품)
  - /servcList    (용역)
  - /dmscptList   (내자)
  - /rstList      (입찰결과 — 수집 대상 아님)

2026-04 기준 새로 활용신청한 서비스키로 호출 시 HTTP 500("Unexpected errors")가
몇 시간 지속될 수 있음 (키 전파 대기). 전파 완료 후 정상 응답 예상.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Callable

from utils.logger import get_logger
from collectors.base import http_get_json

logger = get_logger("bid_collector.kwater_api")

DEFAULT_BASE_URL = "https://apis.data.go.kr/B500001/eBid/tndr3"

# (path, source_key, bid_type_label)
OPERATIONS: list[tuple[str, str, str]] = [
    ("cntrwkList", "kwater_api_cntrwk", "K-water·공사"),
    ("gdsList",    "kwater_api_gds",    "K-water·물품"),
    ("servcList",  "kwater_api_servc",  "K-water·용역"),
    ("dmscptList", "kwater_api_dmscpt", "K-water·내자"),
]

# G2B 스타일과 d2b 스타일 필드명을 모두 수용 (K-water 실제 스키마 미확정)
FIELD_MAP = {
    "bid_no":          ("bidNtceNo", "tndrNo", "pblancNo", "bidNo"),
    "order":           ("bidNtceOrd", "tndrOdr", "pblancOdr"),
    "title":           ("bidNtceNm", "tndrNm", "bidNm", "pblancNm"),
    "org_name":        ("ntceInsttNm", "dminsttNm", "orntNm", "ornt"),
    "contract_method": ("cntrctCnclsMthdNm", "cntrctMth"),
    "estimated_price": ("presmptPrce", "bsicExpt", "asignBdgtAmt", "sucsfbidAmt"),
    "open_date":       ("bidNtceDt", "tndrNticDt", "pblancDate"),
    "close_date":      ("bidClseDt", "tndrClosDt", "opengDt"),
    "detail_url":      ("bidNtceDtlUrl", "tndrUrl", "pblancUrl"),
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
        "org_name": _pick(item, FIELD_MAP["org_name"]) or "한국수자원공사",
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
        # 새로운 포맷 (data 키 또는 최상위 리스트) 대응
        if isinstance(body.get("data"), list):
            return body["data"]
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


def _fetch_operation(
    service_key: str,
    path: str,
    source: str,
    bid_type: str,
    base_url: str,
    type_param: str,
    date_bgn: str,
    date_end: str,
    page_size: int = 100,
    sleep_seconds: float = 1.5,
    http_client: Callable = http_get_json,
) -> list[dict]:
    url = f"{base_url.rstrip('/')}/{path}"
    base_params = {
        "serviceKey": service_key,
        "pageNo": 1,
        "numOfRows": page_size,
        "inqryBgnDt": f"{date_bgn}0000",
        "inqryEndDt": f"{date_end}2359",
        type_param: "json",
    }

    rows: list[dict] = []
    try:
        first = http_client(url, {**base_params, "pageNo": 1}, sleep_seconds=sleep_seconds)
    except Exception:
        logger.exception("kwater_api first-page failed: path=%s", path)
        return rows

    body = first.get("response", {}).get("body", first)  # 일부 API는 response.body 래핑 없음
    total = int((body or {}).get("totalCount") or (body or {}).get("totalCnt") or 0)
    items = _extract_items(body or {})
    rows.extend(r for r in (_normalize(i, source, bid_type) for i in items) if r)

    if total <= page_size or not rows:
        logger.info("kwater_api %s: fetched %d/%d", path, len(rows), total)
        return rows

    total_pages = math.ceil(total / page_size)
    for page_no in range(2, total_pages + 1):
        try:
            data = http_client(url, {**base_params, "pageNo": page_no}, sleep_seconds=sleep_seconds)
        except Exception:
            logger.exception("kwater_api page failed: path=%s pageNo=%d", path, page_no)
            continue
        body = data.get("response", {}).get("body", data)
        items = _extract_items(body or {})
        rows.extend(r for r in (_normalize(i, source, bid_type) for i in items) if r)

    logger.info("kwater_api %s: fetched %d/%d across %d pages",
                path, len(rows), total, total_pages)
    return rows


def collect(
    service_key: str,
    base_url: str = DEFAULT_BASE_URL,
    # operation 인자는 호환성을 위해 유지하지만 실제로는 OPERATIONS 리스트 사용
    operation: str = "",
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
    if not base_url:
        logger.warning("kwater_api: base_url not set — skipping")
        return []

    date_bgn, date_end = _yesterday_range(now, lookback_days)
    logger.info("kwater_api collection range: %s ~ %s", date_bgn, date_end)

    all_rows: list[dict] = []
    for path, src, bt in OPERATIONS:
        try:
            rows = _fetch_operation(
                service_key=service_key,
                path=path,
                source=src,
                bid_type=bt,
                base_url=base_url,
                type_param=type_param,
                date_bgn=date_bgn,
                date_end=date_end,
                page_size=page_size,
                sleep_seconds=sleep_seconds,
                http_client=http_client,
            )
            all_rows.extend(rows)
        except Exception:
            logger.exception("kwater_api operation crashed: %s", path)
    return all_rows
