import json
from pathlib import Path

from collectors import kapt_api


FIXTURE = Path(__file__).parent / "fixtures" / "kapt_sample.json"


def _client_returning(data):
    calls = []
    def _c(url, params, **kwargs):
        calls.append(dict(params))
        return data
    _c.calls = calls
    return _c


def test_collect_parses_and_normalizes():
    sample = json.loads(FIXTURE.read_text(encoding="utf-8"))
    client = _client_returning(sample)
    rows = kapt_api.collect(
        service_key="TEST",
        page_size=100,
        sleep_seconds=0,
        lookback_days=1,
        http_client=client,
    )
    assert len(rows) == 3
    first = rows[0]
    assert first["source"] == "kapt_api"
    assert first["bid_type"] == "K-apt"
    assert first["bid_no"] == "KAPT-2026-0422-001"
    assert "승강기" in first["title"]
    assert first["org_name"].startswith("래미안강남")
    assert first["estimated_price"] == 450_000_000
    assert first["open_date"] == "2026-04-22"
    assert first["close_date"] == "2026-05-10"
    assert first["detail_url"].startswith("http://www.k-apt.go.kr/")


def test_collect_skipped_without_key():
    rows = kapt_api.collect(service_key="", http_client=lambda *a, **kw: (_ for _ in ()).throw(AssertionError("must not call")))
    assert rows == []


def test_collect_tolerates_first_page_failure():
    def broken(url, params, **kwargs):
        raise RuntimeError("boom")
    rows = kapt_api.collect(service_key="TEST", sleep_seconds=0, http_client=broken)
    assert rows == []


def test_collect_paginates_when_total_exceeds_page():
    sample = json.loads(FIXTURE.read_text(encoding="utf-8"))
    call_counter = {"n": 0}

    def client(url, params, **kwargs):
        call_counter["n"] += 1
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        data["response"]["body"]["totalCount"] = 7
        data["response"]["body"]["pageNo"] = params["pageNo"]
        return data

    rows = kapt_api.collect(
        service_key="TEST",
        page_size=3,
        sleep_seconds=0,
        lookback_days=1,
        http_client=client,
    )
    assert call_counter["n"] == 3  # ceil(7/3) = 3
    assert len(rows) == 9  # 3 items × 3 pages


def test_skips_items_missing_required_fields():
    data = {
        "response": {"body": {
            "totalCount": 2, "numOfRows": 100, "pageNo": 1,
            "items": {"item": [
                {"bidTitle": "제목만"},                      # missing bidNum
                {"bidNum": "K1"},                           # missing title
                {"bidNum": "K2", "bidTitle": "정상 공고"},
            ]}
        }}
    }
    client = _client_returning(data)
    rows = kapt_api.collect(service_key="TEST", sleep_seconds=0, http_client=client)
    assert len(rows) == 1
    assert rows[0]["bid_no"] == "K2"


def test_field_map_accepts_alternate_keys():
    data = {
        "response": {"body": {
            "totalCount": 1, "numOfRows": 100, "pageNo": 1,
            "items": {"item": [
                {
                    "bidNtceNo": "alt-1",
                    "bidNm": "대체 필드 테스트",
                    "ntceInsttNm": "기관",
                    "presmptPrce": "1000000",
                    "bidNtceDt": "2026-04-22",
                },
            ]}
        }}
    }
    client = _client_returning(data)
    rows = kapt_api.collect(service_key="TEST", sleep_seconds=0, http_client=client)
    assert len(rows) == 1
    assert rows[0]["bid_no"] == "alt-1"
    assert rows[0]["estimated_price"] == 1_000_000
