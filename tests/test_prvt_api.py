from collectors import prvt_api


def _client(data):
    calls = []
    def _c(url, params, **kwargs):
        calls.append({"url": url, **params})
        return data
    _c.calls = calls
    return _c


def test_skipped_without_service_key():
    rows = prvt_api.collect_all(service_key="", http_client=_client({}))
    assert rows == []


def test_parses_real_prvt_schema():
    """Based on the actual PrvtBidNtceService response shape (Apr 2026)."""
    data = {"response": {"body": {
        "pageNo": 1, "numOfRows": 100, "totalCount": 2,
        "items": [
            {"bidNtceNo": "R26BK01482245",
             "bidNtceOrd": "00",
             "ntceNm": "둔촌2동 모아주택1구역 가로주택정비사업조합 사업관리 용역",
             "ntceInsttNm": "둔촌2동 모아주택1구역 가로주택정비사업조합",
             "cntrctMthdNm": "제한경쟁",
             "refAmt": "180000000",
             "asignBdgtAmt": "200000000",
             "bidBeginDt": "2026-04-22 10:00:00",
             "bidClseDt": "2026-04-30 14:00:00",
             "nticeDt": "2026-04-22"},
            {"bidNtceNo": "R26BK01482246",
             "ntceNm": "ABC교회 리모델링 공사",
             "ntceInsttNm": "ABC교회",
             "asignBdgtAmt": "80000000",
             "bidClseDt": "2026-05-01 10:00:00"},
        ]
    }}}
    rows = prvt_api.collect_all(service_key="TEST", sleep_seconds=0,
                                 http_client=_client(data))
    # 4 operations × 2 items = 8 rows
    assert len(rows) == 8
    first = rows[0]
    assert first["source"] in {"prvt_api_servc", "prvt_api_thng",
                                 "prvt_api_cnstwk", "prvt_api_etc"}
    assert first["bid_no"] == "R26BK01482245-00"
    assert "둔촌2동" in first["title"]
    assert first["org_name"] == "둔촌2동 모아주택1구역 가로주택정비사업조합"
    # refAmt 우선
    assert first["estimated_price"] == 180_000_000
    assert first["open_date"] == "2026-04-22 10:00:00"
    assert first["close_date"] == "2026-04-30 14:00:00"
    # 두번째 행은 refAmt 없음 → asignBdgtAmt
    second = rows[1]
    assert second["estimated_price"] == 80_000_000


def test_iterates_four_operations():
    data = {"response": {"body": {"totalCount": 1, "items": [
        {"bidNtceNo": "X1", "ntceNm": "t"},
    ]}}}
    client = _client(data)
    rows = prvt_api.collect_all(service_key="K", sleep_seconds=0,
                                 http_client=client)
    ops = {call["url"].rsplit("/", 1)[-1] for call in client.calls}
    assert ops == {
        "getPrvtBidPblancListInfoServc",
        "getPrvtBidPblancListInfoThng",
        "getPrvtBidPblancListInfoCnstwk",
        "getPrvtBidPblancListInfoEtc",
    }
    assert len(rows) == 4
    assert {r["bid_type"] for r in rows} == {"용역", "물품", "공사", "기타"}


def test_detail_url_picks_first_nonempty_ntceSpecDocUrl():
    """API 응답의 ntceSpecDocUrl1~10 중 첫 비어있지 않은 http URL 을 detail_url 로."""
    data = {"response": {"body": {"totalCount": 1, "items": [
        {"bidNtceNo": "DOC1", "ntceNm": "다운로드 있는 공고",
         "ntceSpecDocUrl1": "",
         "ntceSpecDocUrl2": "https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/downloadFile.do?bidPbancNo=DOC1&bidPbancOrd=000&fileType=&fileSeq=2&prcmBsneSeCd=22",
         "ntceSpecDocUrl3": "https://nope.example/"},
    ]}}}
    rows = prvt_api.collect_all(service_key="K", sleep_seconds=0,
                                 http_client=_client(data))
    assert len(rows) == 4  # 4 operations each see same fixture
    for r in rows:
        # 두 번째 URL 이 첫 비어있지 않은 http 값
        assert r["detail_url"].startswith(
            "https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/"
        )
        assert "bidPbancNo=DOC1" in r["detail_url"]


def test_detail_url_none_when_no_ntceSpecDoc_provided():
    """공고문 파일이 아직 등록되지 않은 공고는 detail_url=None."""
    data = {"response": {"body": {"totalCount": 1, "items": [
        {"bidNtceNo": "NODOC", "ntceNm": "파일 없는 공고"},
    ]}}}
    rows = prvt_api.collect_all(service_key="K", sleep_seconds=0,
                                 http_client=_client(data))
    for r in rows:
        assert r["detail_url"] is None


def test_skips_items_missing_required_fields():
    data = {"response": {"body": {"totalCount": 3, "items": [
        {"bidNtceNo": "", "ntceNm": "제목만"},   # no bid_no
        {"bidNtceNo": "X"},                       # no title
        {"bidNtceNo": "OK", "ntceNm": "정상"},
    ]}}}
    rows = prvt_api.collect_all(service_key="K", sleep_seconds=0,
                                 http_client=_client(data))
    # Only "OK" survives × 4 operations
    assert len(rows) == 4
    assert all(r["bid_no"] == "OK" for r in rows)


def test_paginates_when_total_exceeds_page():
    call_counter = {"n": 0}
    def client(url, params, **kwargs):
        call_counter["n"] += 1
        return {"response": {"body": {
            "totalCount": 7, "pageNo": params["pageNo"],
            "items": [{"bidNtceNo": f"p{params['pageNo']}", "ntceNm": "t"}],
        }}}
    rows = prvt_api.collect_all(service_key="K", page_size=3, sleep_seconds=0,
                                 http_client=client)
    # 7/3 = 3 pages per op × 4 ops = 12 calls
    assert call_counter["n"] == 12
    assert len(rows) == 12  # 1 row per page × 3 pages × 4 ops


def test_sends_correct_params():
    client = _client({"response": {"body": {"totalCount": 0, "items": []}}})
    prvt_api.collect_all(service_key="KEY", sleep_seconds=0, http_client=client)
    p = client.calls[0]
    assert p["serviceKey"] == "KEY"
    assert p["type"] == "json"
    assert p["inqryDiv"] == 1
    assert "inqryBgnDt" in p
    assert "inqryEndDt" in p
