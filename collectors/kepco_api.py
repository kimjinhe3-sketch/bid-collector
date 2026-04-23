"""한국전력공사(KEPCO) 전자입찰계약정보 API 수집기.

data.go.kr 카탈로그 ID: 15148223 (LINK 유형)
실제 API 엔드포인트:
  https://bigdata.kepco.co.kr/openapi/v1/electContract.do

⚠️ 인증: data.go.kr의 공용 serviceKey가 아니라 **bigdata.kepco.co.kr(전력데이터
개방포털)에서 별도 발급받는 apiKey**를 사용합니다. 회원가입 후 "API 키 발급" 메뉴에서
신청하세요.

주요 파라미터:
  - apiKey           : 전용 API 키
  - noticeBeginDate  : YYYYMMDD, 공고 시작일
  - noticeEndDate    : YYYYMMDD, 공고 종료일 (구간 최대 90일)
  - companyId        : COM01~COM19 계열사 구분 (optional)
  - returnType       : json | xml (기본 json)
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable

from utils.logger import get_logger
from collectors.base import http_get_json

logger = get_logger("bid_collector.kepco_api")

DEFAULT_BASE_URL = "https://bigdata.kepco.co.kr/openapi/v1/electContract.do"

# KEPCO 응답의 정확한 스키마는 문서 확인 필요 — 가능한 필드명 후보를 모두 수용.
FIELD_MAP = {
    "bid_no":          ("noticeNo", "no", "bidNo", "contractNo"),
    "title":           ("noticeName", "name", "bidName", "title"),
    "org_name":        ("companyName", "company", "companyId"),
    "contract_method": ("progressState", "contractMethod"),
    "estimated_price": ("bidLimitAmt", "contractAmt", "budgetAmt", "estPrice"),
    "open_date":       ("noticeBeginDate", "noticeDate", "openDate"),
    "close_date":      ("bidAttendReqCloseDatetime", "closeDate", "noticeEndDate"),
    "detail_url":      ("noticeUrl", "contractUrl", "url"),
}

COMPANY_LABELS = {
    "COM01": "한국전력공사",
    "COM02": "한전KDN",
    "COM03": "한전KPS",
    "COM04": "한전산업개발",
    "COM05": "한전MCS",
    # 계열사 코드는 KEPCO 문서 참조, 미지 값은 코드 그대로 노출
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


def _date_range(now: datetime | None = None, lookback_days: int = 1) -> tuple[str, str]:
    now = now or datetime.now()
    end = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(seconds=1)
    start = (end - timedelta(days=max(lookback_days - 1, 0))).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def _normalize(item: dict) -> dict | None:
    bid_no = _pick(item, FIELD_MAP["bid_no"])
    title = _pick(item, FIELD_MAP["title"])
    if not bid_no or not title:
        return None
    company_id = item.get("companyId") or ""
    org_name = COMPANY_LABELS.get(company_id) or _pick(item, FIELD_MAP["org_name"]) or "한국전력공사"
    return {
        "source": "kepco_api",
        "bid_no": f"kepco-{bid_no}",
        "title": str(title).strip(),
        "org_name": org_name,
        "contract_method": _pick(item, FIELD_MAP["contract_method"]),
        "estimated_price": _safe_int(_pick(item, FIELD_MAP["estimated_price"])),
        "open_date": _pick(item, FIELD_MAP["open_date"]),
        "close_date": _pick(item, FIELD_MAP["close_date"]),
        "bid_type": "KEPCO",
        "detail_url": _pick(item, FIELD_MAP["detail_url"]),
    }


def _extract_items(body: dict) -> list[dict]:
    """KEPCO 응답 구조 후보:
      {"data": [...]}
      {"result": [...]}
      {"list": [...]}
      최상위가 리스트
      {"response": {"body": {"items": ...}}}  (data.go.kr 스타일 폴백)
    """
    if isinstance(body, list):
        return body
    for key in ("data", "result", "list", "items"):
        v = body.get(key)
        if isinstance(v, list):
            return v
        if isinstance(v, dict) and isinstance(v.get("item"), list):
            return v["item"]
    # data.go.kr 스타일 폴백
    inner = body.get("response", {}).get("body", {})
    if isinstance(inner, dict):
        return _extract_items(inner) if inner != body else []
    return []


def collect(
    api_key: str,
    base_url: str = DEFAULT_BASE_URL,
    company_ids: list[str] | None = None,
    sleep_seconds: float = 1.5,
    lookback_days: int = 1,
    now: datetime | None = None,
    http_client: Callable = http_get_json,
) -> list[dict]:
    """Collect KEPCO 전자입찰 data for the lookback window.

    KEPCO 최대 구간은 90일이지만, 기본은 G2B와 동일한 lookback(일 1회 운영).
    company_ids가 주어지면 각 계열사별로 호출, 아니면 전체(파라미터 생략).
    """
    if not api_key:
        logger.warning("kepco_api: api key missing — skipping")
        return []

    bgn, end = _date_range(now, lookback_days)
    base_params = {
        "apiKey": api_key,
        "noticeBeginDate": bgn,
        "noticeEndDate": end,
        "returnType": "json",
    }

    all_rows: list[dict] = []
    targets = company_ids or [None]
    for cid in targets:
        params = dict(base_params)
        if cid:
            params["companyId"] = cid
        try:
            resp = http_client(base_url, params, sleep_seconds=sleep_seconds)
        except Exception:
            logger.exception("kepco_api call failed (companyId=%s)", cid)
            continue
        items = _extract_items(resp if isinstance(resp, (dict, list)) else {})
        normalized = [r for r in (_normalize(i) for i in items) if r]
        all_rows.extend(normalized)
        logger.info("kepco_api %s: fetched %d", cid or "ALL", len(normalized))

    # Deduplicate by bid_no (in case 계열사 호출이 중복으로 같은 공고 반환)
    seen = set()
    deduped = []
    for r in all_rows:
        if r["bid_no"] in seen:
            continue
        seen.add(r["bid_no"])
        deduped.append(r)
    logger.info("kepco_api total: %d (deduped from %d)", len(deduped), len(all_rows))
    return deduped
