from collectors import kwater_api


def _client(data):
    calls = []
    def _c(url, params, **kwargs):
        calls.append({"url": url, **params})
        return data
    _c.calls = calls
    return _c


def test_skipped_without_service_key():
    rows = kwater_api.collect(service_key="", http_client=_client({}))
    assert rows == []


def test_skipped_without_base_url():
    rows = kwater_api.collect(service_key="K", base_url="",
                              http_client=_client({}))
    assert rows == []


def test_iterates_all_four_operations():
    data = {"response": {"body": {"totalCount": 1, "items": {"item": [
        {"bidNtceNo": "KW-1", "bidNtceNm": "테스트 입찰",
         "presmptPrce": "1000000000"},
    ]}}}}
    client = _client(data)
    rows = kwater_api.collect(
        service_key="K",
        base_url="https://apis.data.go.kr/B500001/eBid/tndr3",
        sleep_seconds=0, http_client=client,
    )
    # 4개 오퍼레이션 호출 × 1건 = 4
    paths = {call["url"].split("/")[-1] for call in client.calls}
    assert paths == {"cntrwkList", "gdsList", "servcList", "dmscptList"}
    assert len(rows) == 4
    sources = {r["source"] for r in rows}
    assert sources == {
        "kwater_api_cntrwk", "kwater_api_gds",
        "kwater_api_servc", "kwater_api_dmscpt",
    }
    assert all(r["bid_type"].startswith("K-water·") for r in rows)


def test_parses_g2b_style_response():
    data = {"response": {"body": {
        "totalCount": 1, "items": {"item": [
            {"bidNtceNo": "KW-001", "bidNtceOrd": "00",
             "bidNtceNm": "대청댐 저수지 준설 공사",
             "ntceInsttNm": "한국수자원공사",
             "cntrctCnclsMthdNm": "제한경쟁",
             "presmptPrce": "3500000000"},
        ]}
    }}}
    rows = kwater_api.collect(
        service_key="K",
        base_url="https://apis.data.go.kr/B500001/eBid/tndr3",
        sleep_seconds=0, http_client=_client(data),
    )
    # 4 ops × 1 row = 4
    assert len(rows) == 4
    r = rows[0]
    assert r["bid_no"] == "KW-001-00"
    assert r["estimated_price"] == 3_500_000_000
    assert "준설" in r["title"]


def test_accepts_tndr_style_field_aliases():
    data = {"response": {"body": {
        "totalCount": 1, "items": {"item": [
            {"tndrNo": "TNDR-1", "tndrNm": "수자원 공사 입찰"},
        ]}
    }}}
    rows = kwater_api.collect(
        service_key="K",
        base_url="https://apis.data.go.kr/B500001/eBid/tndr3",
        sleep_seconds=0, http_client=_client(data),
    )
    assert len(rows) == 4
    assert rows[0]["bid_no"] == "TNDR-1"
    assert rows[0]["title"] == "수자원 공사 입찰"


def test_sends_serviceKey_and_type_param_correctly():
    client = _client({"response": {"body": {"totalCount": 0, "items": []}}})
    kwater_api.collect(
        service_key="K123",
        base_url="https://apis.data.go.kr/B500001/eBid/tndr3",
        type_param="_type",
        sleep_seconds=0,
        http_client=client,
    )
    p = client.calls[0]
    assert p["serviceKey"] == "K123"
    assert p["_type"] == "json"
    assert "inqryBgnDt" in p
    assert "inqryEndDt" in p
