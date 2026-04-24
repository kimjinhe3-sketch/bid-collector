"""조달청 **누리장터** 민간입찰공고 API 수집기.

공공데이터포털 서비스: 조달청_누리장터 민간입찰공고서비스 (PrvtBidNtceService)
Base URL:  https://apis.data.go.kr/1230000/ao/PrvtBidNtceService

인증: data.go.kr 일반 serviceKey (G2B 키 재사용 가능)

오퍼레이션 (4개 입찰공고):
  - /getPrvtBidPblancListInfoServc    (용역)
  - /getPrvtBidPblancListInfoThng     (물품)
  - /getPrvtBidPblancListInfoCnstwk   (공사)
  - /getPrvtBidPblancListInfoEtc      (기타)

민간수요자(아파트 재건축 조합, 사립대학, 교회 등)가 조달청 인프라로 올리는
입찰공고 데이터. `nuri.g2b.go.kr` 사이트에 노출되는 데이터와 동일.

필드 스키마가 G2B BidPublicInfoService와 **다름**:
  - `ntceNm`          : 공고명 (G2B의 bidNtceNm과 다름)
  - `ntceInsttNm`     : 공고기관 (동일)
  - `bidNtceNo`       : 공고번호
  - `bidNtceOrd`      : 차수
  - `asignBdgtAmt`    : 배정예산
  - `refAmt`          : 참고금액
  - `bidBeginDt`      : 입찰 시작
  - `bidClseDt`       : 마감 (동일)
  - `cntrctMthdNm`    : 계약방법
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Callable

from utils.logger import get_logger
from collectors.base import http_get_json

logger = get_logger("bid_collector.prvt_api")

BASE_URL = "https://apis.data.go.kr/1230000/ao/PrvtBidNtceService"

# (operation_path, source_key, bid_type_label)
OPERATIONS: list[tuple[str, str, str]] = [
    ("getPrvtBidPblancListInfoServc",  "prvt_api_servc",  "용역"),
    ("getPrvtBidPblancListInfoThng",   "prvt_api_thng",   "물품"),
    ("getPrvtBidPblancListInfoCnstwk", "prvt_api_cnstwk", "공사"),
    ("getPrvtBidPblancListInfoEtc",    "prvt_api_etc",    "기타"),
]


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
    fmt = "%Y%m%d%H%M"
    return start.strftime(fmt), end.strftime(fmt)


def _pick_doc_url(item: dict) -> str | None:
    """API 응답의 ntceSpecDocUrl1 ~ 10 중 첫 번째 비어있지 않은 값.

    이 URL은 공고문 PDF 직접 다운로드 주소 (SSO 불필요, 실제로 다운로드 동작
    확인됨). 사용자가 클릭하면 공고문 PDF 가 바로 열림.
    예: https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/downloadFile.do?
        bidPbancNo=R26BK01482245&bidPbancOrd=000&fileType=&fileSeq=1&prcmBsneSeCd=22
    """
    for i in range(1, 11):
        v = item.get(f"ntceSpecDocUrl{i}")
        if v and isinstance(v, str) and v.strip().startswith("http"):
            return v.strip()
    return None


def _normalize(item: dict, source: str, bid_type: str) -> dict | None:
    bid_no = item.get("bidNtceNo")
    # Prvt 스키마는 ntceNm; G2B는 bidNtceNm. 둘 다 수용.
    title = _pick(item, ("ntceNm", "bidNtceNm"))
    if not bid_no or not title:
        return None
    ord_no = item.get("bidNtceOrd") or ""
    bid_no_full = f"{bid_no}-{ord_no}" if ord_no else str(bid_no)
    title_str = str(title).strip()
    # 민간 공고는 presmptPrce가 없고 asignBdgtAmt 또는 refAmt 사용
    price = _safe_int(_pick(item, ("refAmt", "asignBdgtAmt", "presmptPrce")))
    return {
        "source": source,
        "bid_no": bid_no_full,
        "title": title_str,
        "org_name": _pick(item, ("ntceInsttNm", "dminsttNm")),
        "contract_method": item.get("cntrctMthdNm"),
        "estimated_price": price,
        "open_date": _pick(item, ("bidBeginDt", "nticeDt", "bidNtceDt")),
        "close_date": item.get("bidClseDt"),
        "bid_type": bid_type,
        # 공고문 PDF 직접 다운로드 URL (공개, SSO 불필요)
        "detail_url": _pick_doc_url(item),
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


def _fetch_operation(
    service_key: str,
    operation: str,
    source: str,
    bid_type: str,
    inqry_bgn: str,
    inqry_end: str,
    page_size: int = 100,
    sleep_seconds: float = 0.8,
    http_client: Callable = http_get_json,
) -> list[dict]:
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
        logger.exception("prvt_api first-page failed: op=%s", operation)
        return rows

    body = first.get("response", {}).get("body", {})
    total = int(body.get("totalCount") or 0)
    items = _extract_items(body)
    rows.extend(r for r in (_normalize(i, source, bid_type) for i in items) if r)

    if total <= page_size:
        logger.info("prvt_api %s: fetched %d/%d", operation, len(rows), total)
        return rows

    total_pages = math.ceil(total / page_size)
    for page_no in range(2, total_pages + 1):
        try:
            data = http_client(url, {**base_params, "pageNo": page_no}, sleep_seconds=sleep_seconds)
        except Exception:
            logger.exception("prvt_api page failed: op=%s pageNo=%d", operation, page_no)
            continue
        body = data.get("response", {}).get("body", {})
        items = _extract_items(body)
        rows.extend(r for r in (_normalize(i, source, bid_type) for i in items) if r)

    logger.info("prvt_api %s: fetched %d/%d across %d pages",
                operation, len(rows), total, total_pages)
    return rows


def collect_all(
    service_key: str,
    page_size: int = 100,
    sleep_seconds: float = 0.8,
    lookback_days: int = 1,
    now: datetime | None = None,
    http_client: Callable = http_get_json,
) -> list[dict]:
    if not service_key:
        logger.warning("prvt_api: service key missing — skipping")
        return []
    inqry_bgn, inqry_end = _yesterday_range(now, lookback_days)
    logger.info("prvt_api collection range: %s ~ %s", inqry_bgn, inqry_end)

    all_rows: list[dict] = []
    for operation, source, bid_type in OPERATIONS:
        try:
            rows = _fetch_operation(
                service_key=service_key,
                operation=operation,
                source=source,
                bid_type=bid_type,
                inqry_bgn=inqry_bgn,
                inqry_end=inqry_end,
                page_size=page_size,
                sleep_seconds=sleep_seconds,
                http_client=http_client,
            )
            all_rows.extend(rows)
        except Exception:
            logger.exception("prvt_api operation crashed: %s", operation)
    return all_rows
