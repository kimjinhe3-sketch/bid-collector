import json
from pathlib import Path

from collectors import g2b_api


FIXTURE = Path(__file__).parent / "fixtures" / "g2b_sample.json"


def _load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _mock_client(sample: dict):
    calls = []

    def _client(url, params, **kwargs):
        calls.append((url, dict(params)))
        return sample

    _client.calls = calls
    return _client


def test_fetch_operation_parses_and_normalizes():
    sample = _load_fixture()
    client = _mock_client(sample)

    rows = g2b_api.fetch_operation(
        service_key="TEST_KEY",
        operation="getBidPblancListInfoServc",
        bid_type="용역",
        source="g2b_api_servc",
        inqry_bgn="202604220000",
        inqry_end="202604222359",
        page_size=100,
        sleep_seconds=0,
        http_client=client,
    )

    assert len(rows) == 12
    first = rows[0]
    assert first["source"] == "g2b_api_servc"
    assert first["bid_type"] == "용역"
    assert first["bid_no"] == "20260422001-00"
    assert first["title"] == "AI 기반 데이터 분석 플랫폼 구축 용역"
    assert first["org_name"] == "한국정보화진흥원"
    assert first["estimated_price"] == 850_000_000
    assert first["open_date"] == "2026-04-22 10:00"
    assert first["close_date"] == "2026-05-06 10:00"
    assert first["detail_url"].startswith("https://")


def test_fetch_operation_single_page_no_extra_calls():
    sample = _load_fixture()
    client = _mock_client(sample)

    g2b_api.fetch_operation(
        service_key="TEST_KEY",
        operation="getBidPblancListInfoServc",
        bid_type="용역",
        source="g2b_api_servc",
        inqry_bgn="202604220000",
        inqry_end="202604222359",
        page_size=100,
        sleep_seconds=0,
        http_client=client,
    )
    assert len(client.calls) == 1
    _, params = client.calls[0]
    assert params["pageNo"] == 1
    assert params["numOfRows"] == 100
    assert params["serviceKey"] == "TEST_KEY"
    assert params["type"] == "json"
    assert params["inqryDiv"] == 1


def test_fetch_operation_paginates_when_total_exceeds_page_size():
    sample = _load_fixture()

    call_counter = {"n": 0}

    def client(url, params, **kwargs):
        call_counter["n"] += 1
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        data["response"]["body"]["totalCount"] = 25
        data["response"]["body"]["pageNo"] = params["pageNo"]
        return data

    rows = g2b_api.fetch_operation(
        service_key="TEST_KEY",
        operation="getBidPblancListInfoThng",
        bid_type="물품",
        source="g2b_api_thng",
        inqry_bgn="202604220000",
        inqry_end="202604222359",
        page_size=10,
        sleep_seconds=0,
        http_client=client,
    )

    assert call_counter["n"] == 3
    assert len(rows) == 12 * 3


def test_collect_all_iterates_three_operations():
    sample = _load_fixture()
    client = _mock_client(sample)

    rows = g2b_api.collect_all(
        service_key="TEST_KEY",
        page_size=100,
        sleep_seconds=0,
        lookback_days=1,
        http_client=client,
    )

    assert len(client.calls) == 3
    sources = {r["source"] for r in rows}
    assert sources == {"g2b_api_thng", "g2b_api_servc", "g2b_api_cnstwk"}
    assert len(rows) == 12 * 3


def test_fetch_operation_tolerates_exceptions():
    def broken_client(url, params, **kwargs):
        raise RuntimeError("network down")

    rows = g2b_api.fetch_operation(
        service_key="TEST_KEY",
        operation="getBidPblancListInfoServc",
        bid_type="용역",
        source="g2b_api_servc",
        inqry_bgn="202604220000",
        inqry_end="202604222359",
        page_size=100,
        sleep_seconds=0,
        http_client=broken_client,
    )
    assert rows == []


def test_safe_int_handles_garbage():
    assert g2b_api._safe_int(None) is None
    assert g2b_api._safe_int("") is None
    assert g2b_api._safe_int("abc") is None
    assert g2b_api._safe_int("123") == 123
    assert g2b_api._safe_int("123.45") == 123
    assert g2b_api._safe_int(789) == 789


def test_yesterday_range_format():
    from datetime import datetime
    start, end = g2b_api._yesterday_range(now=datetime(2026, 4, 23, 10, 30))
    assert start == "202604220000"
    assert end == "202604222359"
