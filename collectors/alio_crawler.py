"""ALIO (공공기관 경영정보) 입찰공고 수집기.

원래 스펙: alio.go.kr/occasional/bidList.do HTML 크롤링.
실제: 페이지가 Angular.js로 렌더되어 HTML은 빈 껍데기.
→ Angular가 호출하는 XHR JSON 엔드포인트를 직접 사용:
   GET https://www.alio.go.kr/occasional/findBidList.json
       ?type=title&word=&pageNo=N&area=

응답 구조:
  {
    "status": "success",
    "data": {
      "result":   [ {rtitle, pname, bidInfoEndDt, bdate, cdNo, seq, ...}, ... ],
      "totalCnt": 1234,
      "todayCnt": 56,
      "page":     "<pagination html>"
    }
  }
"""
from __future__ import annotations

import math
import urllib.parse
from datetime import date, datetime, timedelta
from typing import Callable

from utils.logger import get_logger
from collectors.base import http_get_json

logger = get_logger("bid_collector.alio")

DEFAULT_URL = "https://www.alio.go.kr/occasional/findBidList.json"
PAGE_SIZE = 10  # 서버 고정: 페이지당 10건
# ALIO doesn't expose a shareable per-bid detail URL (the site is an
# Angular.js SPA that renders details client-side). The closest useful
# landing page is the list view with the title pre-populated as a search.
LIST_URL = "https://www.alio.go.kr/occasional/bidList.do"


def _detail_url(title: str) -> str:
    # Use up to 30 characters of the title as the search keyword so the row
    # is likely the top hit when the user lands on the page.
    keyword = (title or "")[:30]
    return f"{LIST_URL}?type=title&word={urllib.parse.quote(keyword)}"


def _normalize(item: dict) -> dict | None:
    title = item.get("rtitle")
    seq = item.get("seq")
    if not title or seq in (None, ""):
        return None
    title_s = str(title).strip()
    return {
        "source": "alio",
        "bid_no": f"alio-{seq}",
        "title": title_s,
        "org_name": item.get("pname"),
        "contract_method": None,
        "estimated_price": None,
        "open_date": item.get("bdate"),
        "close_date": item.get("bidInfoEndDt"),
        "bid_type": "공공기관",
        "detail_url": _detail_url(title_s),
    }


def _parse_bdate(s: str | None) -> date | None:
    """ALIO의 bdate는 'YYYY.MM.DD' 형식."""
    if not s:
        return None
    try:
        return datetime.strptime(s.strip(), "%Y.%m.%d").date()
    except ValueError:
        return None


def _extract_rows(body: dict) -> list[dict]:
    data = body.get("data") or {}
    if isinstance(data, dict):
        result = data.get("result")
        if isinstance(result, list):
            return result
    return []


def collect(
    base_url: str = DEFAULT_URL,
    word: str = "",
    search_type: str = "title",
    area: str = "",
    max_pages: int = 10,
    sleep_seconds: float = 1.5,
    http_client: Callable = http_get_json,
    since_date: date | None = None,
    lookback_days: int | None = None,
    now: datetime | None = None,
) -> list[dict]:
    """Collect ALIO bids from latest page backward.

    ALIO의 XHR은 게시일 필터를 지원하지 않고 최신순으로만 응답합니다.
    - ``since_date``나 ``lookback_days``를 지정하면 ``bdate`` 기준으로 더 오래된 행이
      나오는 즉시 페이지네이션을 조기 종료하고 해당 행을 결과에서 제외합니다.
    - 지정이 없으면 단순히 ``max_pages`` 까지만 수집 (기존 동작 유지).
    """
    if since_date is None and lookback_days is not None:
        today = (now or datetime.now()).date()
        since_date = today - timedelta(days=max(lookback_days - 1, 0))

    base_params = {"type": search_type, "word": word, "pageNo": 1, "area": area}

    def _filter_by_date(raw_rows: list[dict]) -> tuple[list[dict], bool]:
        """Return (rows_in_range, hit_older_than_since)."""
        kept: list[dict] = []
        stop = False
        for item in raw_rows:
            n = _normalize(item)
            if n is None:
                continue
            if since_date is not None:
                d = _parse_bdate(n.get("open_date"))
                if d is not None and d < since_date:
                    stop = True
                    continue
            kept.append(n)
        return kept, stop

    try:
        first = http_client(base_url, {**base_params, "pageNo": 1}, sleep_seconds=sleep_seconds)
    except Exception:
        logger.exception("alio first-page failed")
        return []

    if first.get("status") != "success":
        logger.error("alio unexpected status: %s", first.get("status"))
        return []

    total_cnt = int((first.get("data") or {}).get("totalCnt") or 0)
    first_rows_raw = _extract_rows(first)
    rows, stop = _filter_by_date(first_rows_raw)

    if stop or total_cnt <= PAGE_SIZE or not first_rows_raw:
        logger.info("alio: fetched %d (totalCnt=%d, since=%s)",
                    len(rows), total_cnt, since_date)
        return rows

    total_pages = min(math.ceil(total_cnt / PAGE_SIZE), max_pages)
    for page_no in range(2, total_pages + 1):
        try:
            data = http_client(base_url, {**base_params, "pageNo": page_no},
                               sleep_seconds=sleep_seconds)
        except Exception:
            logger.exception("alio page failed: pageNo=%d", page_no)
            continue
        page_rows_raw = _extract_rows(data)
        page_rows, stop = _filter_by_date(page_rows_raw)
        rows.extend(page_rows)
        if stop:
            logger.info("alio: reached bdate < %s on pageNo=%d — stopping",
                        since_date, page_no)
            break

    logger.info("alio: fetched %d (totalCnt=%d, pages<=%d, since=%s)",
                len(rows), total_cnt, total_pages, since_date)
    return rows
