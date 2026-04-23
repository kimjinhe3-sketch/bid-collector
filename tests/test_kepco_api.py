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


def test_parses_data_list_response():
    data = {
        "data": [
            {"noticeNo": "KEPCO-2026-001",
             "noticeName": "송전선로 전기 공사 입찰",
             "companyId": "COM01",
             "bidLimitAmt": "5000000000",
             "noticeBeginDate": "20260422"},
            {"noticeNo": "KEPCO-2026-002",
             "noticeName": "변전소 통신설비 구매",
             "companyId": "COM02",
             "bidLimitAmt": "800000000",
             "noticeBeginDate": "20260422"},
        ]
    }
    client = _client(data)
    rows = kepco_api.collect(api_key="KEY", sleep_seconds=0, http_client=client)
    assert len(rows) == 2
    first = rows[0]
    assert first["source"] == "kepco_api"
    assert first["bid_type"] == "KEPCO"
    assert first["bid_no"] == "kepco-KEPCO-2026-001"
    assert first["org_name"] == "한국전력공사"  # COM01 매핑
    assert first["estimated_price"] == 5_000_000_000
    assert rows[1]["org_name"] == "한전KDN"     # COM02 매핑


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
