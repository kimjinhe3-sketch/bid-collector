from db import database


def _row(n: int, **overrides) -> dict:
    base = {
        "source": "g2b_api_thng",
        "bid_no": f"R26BK0000000{n}",
        "title": f"sample bid {n}",
        "org_name": "기관",
        "contract_method": "제한경쟁",
        "estimated_price": 100_000_000,
        "open_date": "2026-04-22 10:00",
        "close_date": "2026-05-01 10:00",
        "bid_type": "물품",
        "detail_url": f"https://example.com/{n}",
    }
    base.update(overrides)
    return base


def test_init_and_upsert(tmp_path):
    db = tmp_path / "t.sqlite"
    database.init_db(db)
    rows = [_row(1), _row(2)]
    processed, skipped = database.upsert_bids(db, rows)
    assert processed == 2
    assert skipped == 0

    unnotified = database.get_unnotified(db)
    assert len(unnotified) == 2


def test_upsert_deduplicates_by_source_and_bid_no(tmp_path):
    db = tmp_path / "t.sqlite"
    database.init_db(db)
    database.upsert_bids(db, [_row(1)])
    database.upsert_bids(db, [_row(1, title="updated title")])
    unnotified = database.get_unnotified(db)
    assert len(unnotified) == 1
    assert unnotified[0]["title"] == "updated title"


def test_upsert_preserves_is_notified_flag(tmp_path):
    db = tmp_path / "t.sqlite"
    database.init_db(db)
    database.upsert_bids(db, [_row(1)])
    row_id = database.get_unnotified(db)[0]["id"]
    database.mark_notified(db, [row_id])
    assert database.get_unnotified(db) == []
    database.upsert_bids(db, [_row(1, title="re-fetched")])
    assert database.get_unnotified(db) == []


def test_upsert_skips_rows_missing_required_fields(tmp_path):
    db = tmp_path / "t.sqlite"
    database.init_db(db)
    bad = [
        {"source": "g2b_api_thng", "bid_no": "", "title": "x"},
        {"source": "", "bid_no": "1", "title": "y"},
        _row(1),
    ]
    processed, skipped = database.upsert_bids(db, bad)
    assert processed == 1
    assert skipped == 2


def test_mark_notified_and_count(tmp_path):
    db = tmp_path / "t.sqlite"
    database.init_db(db)
    database.upsert_bids(db, [_row(1), _row(2), _row(3, source="g2b_api_servc")])
    ids = [r["id"] for r in database.get_unnotified(db)]
    assert database.mark_notified(db, ids[:1]) == 1
    assert len(database.get_unnotified(db)) == 2
    counts = database.count_by_source(db)
    assert counts == {"g2b_api_thng": 2, "g2b_api_servc": 1}
