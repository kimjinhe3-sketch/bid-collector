from collectors import kwater_api


def _client(data):
    def _c(url, params, **kwargs):
        return data
    return _c


def test_skipped_without_service_key():
    rows = kwater_api.collect(service_key="", base_url="http://x", operation="op",
                              http_client=_client({}))
    assert rows == []


def test_skipped_when_url_not_configured():
    rows = kwater_api.collect(service_key="K", base_url="", operation="",
                              http_client=_client({}))
    assert rows == []


def test_parses_g2b_style_response():
    data = {
        "response": {"body": {
            "totalCount": 2, "numOfRows": 100, "pageNo": 1,
            "items": {"item": [
                {"bidNtceNo": "KW-001", "bidNtceOrd": "00",
                 "bidNtceNm": "대청댐 저수지 준설 공사",
                 "ntceInsttNm": "한국수자원공사",
                 "cntrctCnclsMthdNm": "제한경쟁",
                 "presmptPrce": "3500000000",
                 "bidNtceDt": "2026-04-22 10:00",
                 "bidClseDt": "2026-05-15 10:00"},
                {"bidNtceNo": "KW-002",
                 "bidNtceNm": "상수도 수질모니터링 용역",
                 "presmptPrce": "120000000",
                 "bidNtceDt": "2026-04-22 11:00"},
            ]}
        }}
    }
    rows = kwater_api.collect(
        service_key="K", base_url="http://api.test", operation="getBidList",
        sleep_seconds=0, lookback_days=1, http_client=_client(data),
    )
    assert len(rows) == 2
    assert rows[0]["source"] == "kwater_api"
    assert rows[0]["bid_type"] == "수자원"
    assert rows[0]["bid_no"] == "KW-001-00"
    assert "준설" in rows[0]["title"]
    assert rows[0]["estimated_price"] == 3_500_000_000


def test_accepts_d2b_style_fields_as_fallback():
    data = {
        "response": {"body": {
            "totalCount": 1, "numOfRows": 100, "pageNo": 1,
            "items": {"item": [
                {"pblancNo": "KW-ALT",
                 "bidNm": "대체 필드 테스트",
                 "bsicExpt": "999999"},
            ]}
        }}
    }
    rows = kwater_api.collect(
        service_key="K", base_url="http://x", operation="op",
        sleep_seconds=0, http_client=_client(data),
    )
    assert len(rows) == 1
    assert rows[0]["bid_no"] == "KW-ALT"
    assert rows[0]["estimated_price"] == 999_999
