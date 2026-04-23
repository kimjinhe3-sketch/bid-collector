from collectors import kepco_api


def _client(data):
    calls = []
    def _c(url, params, **kwargs):
        calls.append({"url": url, **params})
        return data
    _c.calls = calls
    return _c


def test_skipped_without_api_key():
    rows = kepco_api.collect(api_key="", http_client=_client({}))
    assert rows == []


def test_parses_real_kepco_schema():
    """실제 bigdata.kepco.co.kr 응답 구조 기반 테스트."""
    data = {
        "data": [
            {"purchaseType": "Product",
             "companyId": "COM04",
             "no": "G042600170",
             "name": "기력 2호기 암모니아 주입설비 Metering Pump 구매",
             "presumedPrice": 39820000,
             "noticeDate": "20260401",
             "beginDatetime": "2026-04-08 10:00:00",
             "endDatetime": "2026-04-10 10:00:00",
             "bidAttendReqCloseDatetime": "2026-04-08 10:00:00"},
            {"purchaseType": "Construction",
             "companyId": "COM01",
             "no": "C012600001",
             "name": "변전소 옥외철구 정비공사",
             "presumedPrice": 850000000},
            {"purchaseType": "Service",
             "companyId": "COM02",
             "no": "S022600001",
             "name": "설비 점검 용역"},
        ]
    }
    rows = kepco_api.collect(api_key="KEY", sleep_seconds=0,
                              http_client=_client(data))
    assert len(rows) == 3
    # Product → 물품
    assert rows[0]["bid_type"] == "물품"
    assert rows[0]["bid_no"] == "kepco-G042600170"
    assert rows[0]["estimated_price"] == 39_820_000
    assert rows[0]["open_date"] == "2026-04-08 10:00:00"
    assert rows[0]["close_date"] == "2026-04-10 10:00:00"
    assert rows[0]["org_name"] == "한전산업개발"  # COM04
    # Construction → 공사
    assert rows[1]["bid_type"] == "공사"
    assert rows[1]["org_name"] == "한국전력공사"  # COM01
    # Service → 용역
    assert rows[2]["bid_type"] == "용역"
    assert rows[2]["org_name"] == "한전KDN"       # COM02


def test_parses_result_list_response():
    data = {"result": [{"no": "1", "name": "테스트"}]}
    rows = kepco_api.collect(api_key="K", sleep_seconds=0,
                              http_client=_client(data))
    assert len(rows) == 1
    assert rows[0]["bid_no"] == "kepco-1"


def test_parses_items_dict_response():
    data = {"items": {"item": [{"noticeNo": "X1", "name": "dict.item"}]}}
    rows = kepco_api.collect(api_key="K", sleep_seconds=0,
                              http_client=_client(data))
    assert len(rows) == 1


def test_iterates_company_ids_and_dedupes():
    # Same bid returned from 2 companies
    data = {"data": [
        {"noticeNo": "SAME", "noticeName": "공통 공고"},
    ]}
    client = _client(data)
    rows = kepco_api.collect(
        api_key="K",
        company_ids=["COM01", "COM02", "COM03"],
        sleep_seconds=0, http_client=client,
    )
    # 3 calls but 1 unique row after dedupe
    assert len(client.calls) == 3
    assert len(rows) == 1


def test_sends_correct_params():
    client = _client({"data": []})
    kepco_api.collect(api_key="MYKEY", sleep_seconds=0, http_client=client)
    p = client.calls[0]
    assert p["apiKey"] == "MYKEY"
    assert p["returnType"] == "json"
    assert "noticeBeginDate" in p
    assert "noticeEndDate" in p


def test_detail_url_prefers_공고_filename_and_upgrades_to_https():
    """filename1~5 중 '공고' 포함 파일 우선, 없으면 첫 번째. HTTP→HTTPS."""
    # Case 1: 공고문 파일이 2번째 — 우선 선택되어야 함
    data = {"data": [{
        "no": "N1", "name": "test",
        "filenlink1": "http://srm.kepco.net/printDownloadAttachment.do?id=SPEC",
        "filename1": "규격서_spec.pdf",
        "filenlink2": "http://srm.kepco.net/printDownloadAttachment.do?id=NOTICE",
        "filename2": "입찰공고문.pdf",
    }]}
    rows = kepco_api.collect(api_key="K", sleep_seconds=0, http_client=_client(data))
    url = rows[0]["detail_url"]
    assert url.startswith("https://")  # HTTPS 변환
    assert url.endswith("id=NOTICE")   # 공고문 파일 선택됨

    # Case 2: "공고" 포함 파일이 없으면 fallback = filenlink1
    data2 = {"data": [{
        "no": "N2", "name": "test",
        "filenlink1": "http://srm.kepco.net/printDownloadAttachment.do?id=FIRST",
        "filename1": "규격서.pdf",
        "filenlink2": "http://srm.kepco.net/printDownloadAttachment.do?id=SECOND",
        "filename2": "별첨.pdf",
    }]}
    rows2 = kepco_api.collect(api_key="K", sleep_seconds=0, http_client=_client(data2))
    url2 = rows2[0]["detail_url"]
    assert url2.startswith("https://")
    assert url2.endswith("id=FIRST")

    # Case 3: 파일 없음 → None
    rows3 = kepco_api.collect(api_key="K", sleep_seconds=0,
                                http_client=_client({"data": [{"no": "N3", "name": "t"}]}))
    assert rows3[0]["detail_url"] is None


def test_tolerates_http_error():
    def broken(url, params, **kwargs):
        raise RuntimeError("down")
    rows = kepco_api.collect(api_key="K", sleep_seconds=0, http_client=broken)
    assert rows == []


def test_skips_rows_missing_required_fields():
    data = {"data": [
        {"name": "no-number"},        # no bid_no
        {"noticeNo": "X"},             # no title
        {"noticeNo": "OK", "noticeName": "정상"},
    ]}
    rows = kepco_api.collect(api_key="K", sleep_seconds=0,
                              http_client=_client(data))
    assert len(rows) == 1
    assert rows[0]["bid_no"] == "kepco-OK"
