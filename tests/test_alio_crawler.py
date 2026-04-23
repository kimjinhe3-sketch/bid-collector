import json
from pathlib import Path

from collectors import alio_crawler


FIXTURE = Path(__file__).parent / "fixtures" / "alio_sample.json"


def _load():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _client_returning(data):
    calls = []
    def _c(url, params, **kwargs):
        calls.append(dict(params))
        return data
    _c.calls = calls
    return _c


def test_collect_parses_real_fixture():
    sample = _load()
    client = _client_returning(sample)

    rows = alio_crawler.collect(max_pages=1, sleep_seconds=0, http_client=client)
    assert len(rows) >= 1
    r = rows[0]
    assert r["source"] == "alio"
    assert r["bid_type"] == "공공기관"
    assert r["bid_no"].startswith("alio-")
    assert r["title"]
    assert r["org_name"]
    assert r["close_date"]  # bidInfoEndDt mapped
    assert r["open_date"]   # bdate mapped
    assert r["detail_url"].startswith("https://www.alio.go.kr/occasional/bidList.do")
    assert "type=title" in r["detail_url"]
    assert "word=" in r["detail_url"]


def test_collect_stops_when_status_not_success():
    client = _client_returning({"status": "fail", "message": "something"})
    rows = alio_crawler.collect(max_pages=5, sleep_seconds=0, http_client=client)
    assert rows == []


def test_collect_respects_max_pages():
    data = {
        "status": "success",
        "data": {
            "totalCnt": 100,
            "result": [
                {"rtitle": f"t{i}", "pname": "org",
                 "bidInfoEndDt": "2026-05-01", "bdate": "2026-04-22",
                 "seq": 1000 + i}
                for i in range(10)
            ],
        },
    }
    n_calls = {"n": 0}
    def client(url, params, **kwargs):
        n_calls["n"] += 1
        return data
    rows = alio_crawler.collect(max_pages=3, sleep_seconds=0, http_client=client)
    assert n_calls["n"] == 3
    assert len(rows) == 30


def test_collect_tolerates_first_page_failure():
    def broken(url, params, **kwargs):
        raise RuntimeError("boom")
    assert alio_crawler.collect(max_pages=5, sleep_seconds=0, http_client=broken) == []


def test_collect_skips_items_missing_required_fields():
    data = {
        "status": "success",
        "data": {
            "totalCnt": 3,
            "result": [
                {"pname": "제목 없음", "seq": 1},            # missing rtitle
                {"rtitle": "seq 없음", "pname": "x"},        # missing seq
                {"rtitle": "정상", "pname": "org", "seq": 99,
                 "bidInfoEndDt": "2026-05-01", "bdate": "2026-04-22"},
            ],
        },
    }
    rows = alio_crawler.collect(max_pages=1, sleep_seconds=0, http_client=_client_returning(data))
    assert len(rows) == 1
    assert rows[0]["bid_no"] == "alio-99"


def test_collect_tolerates_per_page_failure():
    data = _load()
    calls = {"n": 0}
    def flaky(url, params, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("page 2 down")
        d = json.loads(FIXTURE.read_text(encoding="utf-8"))
        d["data"]["totalCnt"] = 30
        return d
    rows = alio_crawler.collect(max_pages=3, sleep_seconds=0, http_client=flaky)
    # Pages 1 and 3 succeed, page 2 raises
    assert calls["n"] == 3
    # Should still have rows from successful pages
    assert len(rows) >= 10


# ---- Date-range filter boundary tests ----

def _row(seq, bdate, title="sample"):
    return {"rtitle": title, "pname": "org", "seq": seq,
            "bdate": bdate, "bidInfoEndDt": "2026.05.10"}


def test_since_date_excludes_older_rows_and_stops_pagination():
    from datetime import date
    # page 1: 2 recent + 1 old → filter drops old AND stops paginating
    page1 = {
        "status": "success",
        "data": {"totalCnt": 30, "result": [
            _row(1, "2026.04.23"),
            _row(2, "2026.04.22"),
            _row(3, "2026.04.18"),   # older → triggers stop
        ]},
    }
    calls = {"n": 0}
    def client(url, params, **kwargs):
        calls["n"] += 1
        return page1
    rows = alio_crawler.collect(
        max_pages=5, sleep_seconds=0,
        since_date=date(2026, 4, 22),
        http_client=client,
    )
    # Row 3 excluded, pagination stopped (only 1 call)
    assert calls["n"] == 1
    seqs = {r["bid_no"] for r in rows}
    assert "alio-3" not in seqs
    assert "alio-1" in seqs and "alio-2" in seqs


def test_lookback_days_converts_to_since_date(monkeypatch):
    from datetime import datetime
    fixed_now = datetime(2026, 4, 23, 12, 0)
    page = {
        "status": "success",
        "data": {"totalCnt": 10, "result": [
            _row(10, "2026.04.23"),
            _row(11, "2026.04.22"),   # lookback_days=2 → include from 2026-04-22
            _row(12, "2026.04.21"),   # excluded
        ]},
    }
    def client(url, params, **kwargs):
        return page
    rows = alio_crawler.collect(
        max_pages=1, sleep_seconds=0,
        lookback_days=2, now=fixed_now,
        http_client=client,
    )
    bids = {r["bid_no"] for r in rows}
    assert bids == {"alio-10", "alio-11"}


def test_missing_or_unparseable_date_passes_through():
    """If bdate is missing/garbage, we can't filter — keep the row."""
    from datetime import date
    page = {
        "status": "success",
        "data": {"totalCnt": 10, "result": [
            {"rtitle": "no date", "pname": "o", "seq": 20, "bdate": None,
             "bidInfoEndDt": "2026.05.10"},
            {"rtitle": "bad date", "pname": "o", "seq": 21, "bdate": "not-a-date",
             "bidInfoEndDt": "2026.05.10"},
        ]},
    }
    def client(url, params, **kwargs):
        return page
    rows = alio_crawler.collect(
        max_pages=1, sleep_seconds=0,
        since_date=date(2026, 4, 22),
        http_client=client,
    )
    assert {r["bid_no"] for r in rows} == {"alio-20", "alio-21"}
