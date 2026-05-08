"""한국토지주택공사 (LH) 입찰공고정보 수집기.

공공데이터포털: data.go.kr 15021183 — '한국토지주택공사 입찰공고정보' (자동승인)
Endpoint: http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev

키: 별도 발급 필요 (G2B 키와 다름). 자동승인, 일 1,000 건.
응답 형식: XML.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Callable

from utils.logger import get_logger

logger = get_logger("bid_collector.lh_api")

DEFAULT_BASE_URL = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"


def _http_get_xml(url: str, params: dict, timeout: int = 30,
                   sleep_seconds: float = 0.5) -> str:
    import requests
    import time
    headers = {"User-Agent": "Mozilla/5.0 bid-collector"}
    resp = requests.get(url, params=params, headers=headers, timeout=timeout)
    resp.raise_for_status()
    text = resp.text
    time.sleep(sleep_seconds)
    return text


def _parse_xml_items(xml_text: str) -> tuple[list[dict], int]:
    """XML 응답에서 item 리스트와 totalCount 추출."""
    from xml.etree import ElementTree as ET
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        logger.exception("LH XML parse failed")
        return [], 0

    # totalCount 검색 — 위치 다양해서 findall 로
    total = 0
    for tc in root.iter("totalCount"):
        try:
            total = int(tc.text or 0)
            break
        except (ValueError, TypeError):
            pass

    # items/item 또는 직접 item 들
    items = []
    for it in root.iter("item"):
        d = {child.tag: (child.text or "").strip() for child in it}
        items.append(d)
    return items, total


def _normalize(item: dict) -> dict | None:
    bid_no = item.get("bidNum") or item.get("bidNm")
    title = item.get("bidnmKor") or item.get("bidNm")
    if not bid_no or not title:
        return None

    def _safe_int(v):
        if v in (None, "", "0"): return None
        try: return int(float(v))
        except (ValueError, TypeError): return None

    # 참여 지역 zoneRstrct1~4 → 합쳐서 하나의 문자열 (UI 가 지역 추출 시 사용)
    zones = [item.get(f"zoneRstrct{i}", "").strip() for i in range(1, 5)]
    zones = [z for z in zones if z]
    region_str = " ".join(zones) if zones else ""

    # org_name 에 LH 표시 + 지역명 prepend (UI 의 _extract_region 활용)
    org_name = "한국토지주택공사"
    if region_str:
        org_name = f"{region_str} {org_name}"

    return {
        "source": "lh_api",
        "bid_no": str(bid_no).strip(),
        "title": str(title).strip(),
        "org_name": org_name,
        "contract_method": item.get("cntrctMthdNm") or "",
        "estimated_price": _safe_int(item.get("presmtPrc")),
        "open_date": item.get("tndrdocAcptBgninDtm") or "",
        "close_date": item.get("tndrdocAcptEndDtm") or "",
        "bid_type": "공사",  # LH 는 대부분 건설/공사 — 정확 분류는 추후
        "detail_url": None,  # LH 는 자체 URL 없음 (ebid.lh.or.kr 로그인 필요)
    }


def collect(
    service_key: str,
    base_url: str = DEFAULT_BASE_URL,
    page_size: int = 100,
    sleep_seconds: float = 0.5,
    lookback_days: int = 14,
    now: datetime | None = None,
    http_client: Callable[[str, dict], str] = _http_get_xml,
) -> list[dict]:
    """Fetch LH bid notices for the lookback window."""
    if not service_key:
        logger.warning("lh_api: service_key 없음 — skip")
        return []

    now = now or datetime.now()
    end = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=lookback_days - 1)

    rows: list[dict] = []
    base_params = {
        "serviceKey": service_key,
        "numOfRows": page_size,
        "pageNo": 1,
        "tndrbidRegDtStart": start.strftime("%Y%m%d"),
        "tndrbidRegDtEnd": end.strftime("%Y%m%d"),
    }
    try:
        xml = http_client(base_url, base_params, sleep_seconds=sleep_seconds)
    except Exception:
        logger.exception("lh_api first page failed")
        return rows

    items, total = _parse_xml_items(xml)
    rows.extend(r for r in (_normalize(i) for i in items) if r)

    if total <= page_size:
        logger.info("lh_api: %d/%d", len(rows), total)
        return rows

    pages = math.ceil(total / page_size)
    for p in range(2, pages + 1):
        try:
            xml = http_client(base_url, {**base_params, "pageNo": p},
                              sleep_seconds=sleep_seconds)
        except Exception:
            logger.exception("lh_api page %d failed", p)
            continue
        items, _ = _parse_xml_items(xml)
        rows.extend(r for r in (_normalize(i) for i in items) if r)

    logger.info("lh_api: collected %d/%d across %d pages",
                len(rows), total, pages)
    return rows
