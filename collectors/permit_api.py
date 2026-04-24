"""MOLIT ArchPmsHubService — 건축HUB 건축인허가정보 서비스.

data.go.kr 15134735 (ArchPmsHubService)
Endpoint: https://apis.data.go.kr/1613000/ArchPmsHubService

Operations used here:
  - getApBasisOulnInfo : 건축인허가 기본개요 (허가/착공/사용승인)

API 특성:
  - sigunguCd, bjdongCd 둘 다 필수 (전국 스캔 불가 → 지역별 조회)
  - 요청 간 sleep 권장 (403 Forbidden = rate limit)
  - 응답은 UTF-8 JSON. 레거시 DB row는 일부 글자 깨져있을 수 있음 (MOLIT 측 데이터 이슈)
"""
from __future__ import annotations

from typing import Callable

from collectors.base import http_get_json
from utils.logger import get_logger

logger = get_logger("bid_collector.permit_api")

BASE_URL = "https://apis.data.go.kr/1613000/ArchPmsHubService"


def _parse_float(v) -> float | None:
    if v in (None, "", " "):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_int(v) -> int | None:
    if v in (None, "", " "):
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _fmt_date(s) -> str | None:
    """YYYYMMDD → YYYY-MM-DD. 빈 값은 None."""
    if not s:
        return None
    s = str(s).strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return s or None


def _normalize(it: dict, sigungu_cd: str, bjdong_cd: str) -> dict:
    """ArchPms raw item → dashboard-friendly dict."""
    def _s(key: str) -> str:
        v = it.get(key)
        return str(v).strip() if v not in (None, "") else ""

    pk = _s("mgmPmsrgstPk") or _s("rnum")
    return {
        "mgm_pk":        pk,
        "plat_plc":      _s("platPlc") or _s("newPlatPlc"),
        "new_plat_plc":  _s("newPlatPlc"),
        "bld_nm":        _s("bldNm"),
        "main_purps":    _s("mainPurpsCdNm") or _s("purpsCdNm"),
        "strct":         _s("strctCdNm"),
        "roof":          _s("roofCdNm"),
        "plat_area":     _parse_float(it.get("platArea")),
        "arch_area":     _parse_float(it.get("archArea")),
        "tot_area":      _parse_float(it.get("totArea")),
        "bc_rat":        _parse_float(it.get("bcRat")),
        "vl_rat":        _parse_float(it.get("vlRat")),
        "grnd_flr_cnt":  _parse_int(it.get("grndFlrCnt")),
        "ugrnd_flr_cnt": _parse_int(it.get("ugrndFlrCnt")),
        "heit":          _parse_float(it.get("heit")),
        "hhld_cnt":      _parse_int(it.get("hhldCnt")),
        "fmly_cnt":      _parse_int(it.get("fmlyCnt")),
        "pms_day":       _fmt_date(it.get("pmsDay")),
        "stcns_day":     _fmt_date(it.get("stcnsDay")),
        "use_apr_day":   _fmt_date(it.get("useAprDay")),
        "crtn_day":      _fmt_date(it.get("crtnDay")),
        "sigungu_cd":    sigungu_cd,
        "bjdong_cd":     bjdong_cd,
    }


def collect(
    service_key: str,
    sigungu_cd: str,
    bjdong_cd: str,
    *,
    start_date: str | None = None,   # YYYYMMDD, inclusive (startDate 파라미터)
    end_date: str | None = None,
    page_size: int = 100,
    max_pages: int = 10,
    sleep_seconds: float = 1.0,
    http_client: Callable = http_get_json,
) -> list[dict]:
    """Fetch building permit records for given (sigunguCd, bjdongCd).

    Returns a list of normalized dicts. Empty list on any error (logs it).
    """
    if not sigungu_cd or not bjdong_cd:
        logger.warning("permit_api.collect: sigungu_cd/bjdong_cd required")
        return []

    url = f"{BASE_URL}/getApBasisOulnInfo"
    out: list[dict] = []
    try:
        for page in range(1, max_pages + 1):
            params = {
                "serviceKey": service_key,
                "sigunguCd":  sigungu_cd,
                "bjdongCd":   bjdong_cd,
                "pageNo":     str(page),
                "numOfRows":  str(page_size),
                "_type":      "json",
            }
            if start_date:
                params["startDate"] = start_date
            if end_date:
                params["endDate"] = end_date

            data = http_client(url, params, sleep_seconds=sleep_seconds)
            body = (((data or {}).get("response") or {}).get("body") or {})
            items_obj = body.get("items") or {}
            if isinstance(items_obj, str) or not items_obj:
                items = []
            else:
                items = items_obj.get("item") or []
            if isinstance(items, dict):
                items = [items]
            if not items:
                break
            for it in items:
                out.append(_normalize(it, sigungu_cd, bjdong_cd))
            total = _parse_int(body.get("totalCount")) or 0
            if page * page_size >= total:
                break
    except Exception:
        logger.exception("permit_api.collect failed sigungu=%s bjdong=%s",
                         sigungu_cd, bjdong_cd)
        return out
    logger.info("permit_api.collect: sigungu=%s bjdong=%s → %d rows",
                sigungu_cd, bjdong_cd, len(out))
    return out
