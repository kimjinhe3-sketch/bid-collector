import json
from pathlib import Path

from collectors import d2b_api


FIXTURE = Path(__file__).parent / "fixtures" / "d2b_sample.json"


def _load():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _client(data):
    calls = []
    def _c(url, params, **kwargs):
        calls.append(dict(params))
        return data
    _c.calls = calls
    return _c


def test_collect_parses_and_normalizes():
    c = _client(_load())
    rows = d2b_api.collect_all(
        service_key="TEST",
        page_size=100,
        sleep_seconds=0,
        lookback_days=1,
        http_client=c,
    )
    assert len(rows) == 3
    first = rows[0]
    assert first["source"] == "d2b_api_dmstc"
    assert first["bid_type"] == "국방"
    assert first["bid_no"] == "HDL0016-2"
    assert "LPG" in first["title"]
    assert first["org_name"] == "공군제16전투비행단"
    assert first["estimated_price"] == 209_704_147
    assert first["contract_method"] == "제한경쟁"
    assert first["open_date"] == "20260423"


def test_sends_underscore_type_and_capital_service_key():
    c = _client(_load())
    d2b_api.collect_all(service_key="TEST", page_size=100,
                        sleep_seconds=0, lookback_days=1, http_client=c)
    p = c.calls[0]
    assert p["_type"] == "json"
    assert p["ServiceKey"] == "TEST"
    assert "anmtDateBegin" in p
    assert "anmtDateEnd" in p


def test_skipped_without_key():
    rows = d2b_api.collect_all(
        service_key="",
        http_client=lambda *a, **kw: (_ for _ in ()).throw(AssertionError("must not call")),
    )
    assert rows == []


def test_tolerates_first_page_failure():
    def broken(url, params, **kwargs):
        raise RuntimeError("boom")
    rows = d2b_api.collect_all(service_key="T", sleep_seconds=0, http_client=broken)
    assert rows == []


def test_paginates_when_total_exceeds_page_size():
    n = {"n": 0}
    def client(url, params, **kwargs):
        n["n"] += 1
        d = json.loads(FIXTURE.read_text(encoding="utf-8"))
        d["response"]["body"]["totalCount"] = 7
        return d
    rows = d2b_api.collect_all(
        service_key="T", page_size=3, sleep_seconds=0,
        lookback_days=1, http_client=client,
    )
    # ceil(7/3) = 3 pages
    assert n["n"] == 3
    assert len(rows) == 9


def test_skips_items_missing_required_fields():
    data = {
        "response": {"body": {
            "totalCount": 2, "numOfRows": 100, "pageNo": 1,
            "items": {"item": [
                {"pblancOdr": "1"},                            # missing pblancNo + bidNm
                {"pblancNo": "X1"},                            # missing bidNm
                {"pblancNo": "X2", "bidNm": "정상"},
            ]}
        }}
    }
    rows = d2b_api.collect_all(
        service_key="T", sleep_seconds=0,
        http_client=_client(data), lookback_days=1,
    )
    assert len(rows) == 1
    assert rows[0]["bid_no"] == "X2"
