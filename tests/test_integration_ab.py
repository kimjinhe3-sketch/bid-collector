"""End-to-end pipeline test: collect (mock) -> upsert -> filter -> notifier payloads -> mark_notified.

Exercises A (g2b_api) + B (db + filter + notifier) together without real network.
"""
import json
from pathlib import Path

from collectors import g2b_api
from db import database
from filters import keyword_filter
from notifiers import email_notifier, slack_notifier


FIXTURE = Path(__file__).parent / "fixtures" / "g2b_sample.json"


def _mock_http(sample):
    def _client(url, params, **kwargs):
        return sample
    return _client


def test_full_pipeline_collect_upsert_filter_notify(tmp_path):
    sample = json.loads(FIXTURE.read_text(encoding="utf-8"))
    client = _mock_http(sample)

    # Step 1: A — collect from three mocked operations
    rows = g2b_api.collect_all(
        service_key="TEST",
        page_size=100,
        sleep_seconds=0,
        lookback_days=1,
        http_client=client,
    )
    assert len(rows) == 12 * 5  # 5 operations × 12 fixture items

    # Step 2: B — upsert into SQLite
    db = tmp_path / "integration.sqlite"
    database.init_db(db)
    processed, skipped = database.upsert_bids(db, rows)
    assert processed == 60
    assert skipped == 0

    # Step 3: idempotency — re-collecting the same data should not dupe
    rows2 = g2b_api.collect_all(service_key="TEST", page_size=100,
                                 sleep_seconds=0, lookback_days=1, http_client=client)
    database.upsert_bids(db, rows2)
    unnotified = database.get_unnotified(db)
    assert len(unnotified) == 60, "upsert must deduplicate across runs"

    # Step 4: filter — include AI/데이터/클라우드, exclude 청소/경비
    filter_cfg = {
        "include_keywords": ["AI", "데이터", "클라우드"],
        "exclude_keywords": ["청소", "경비"],
        "min_amount_eok": 0,
        "max_amount_eok": 9999,
        "bid_types": ["물품", "용역", "공사"],
    }
    matched = keyword_filter.apply_filters(unnotified, filter_cfg)

    titles = {r["title"] for r in matched}
    assert "본관 건물 청소 용역" not in titles
    assert "공사현장 경비용역" not in titles
    assert any("AI" in t for t in titles)
    assert any("클라우드" in t for t in titles)
    assert len(matched) >= 15  # AI/데이터/클라우드 hits × 3 operations

    # Step 5: notifier payload builds correctly
    html = email_notifier.build_html(matched)
    assert "AI 기반 데이터 분석 플랫폼" in html
    assert "청소" not in html or "본관 건물 청소" not in html

    blocks = slack_notifier.build_blocks(matched)
    assert blocks[0]["type"] == "header"
    assert f"{len(matched)}건" in blocks[0]["text"]["text"]

    # Step 6: mark_notified — simulate successful send
    ids = [r["id"] for r in matched]
    updated = database.mark_notified(db, ids)
    assert updated == len(matched)
    assert database.get_unnotified(db) == [
        r for r in database.get_unnotified(db) if r["id"] not in ids
    ]  # matched rows should be gone
    remaining = database.get_unnotified(db)
    assert len(remaining) == 60 - len(matched)

    # Step 7: re-upsert should NOT resurrect is_notified flag
    database.upsert_bids(db, rows)
    assert len(database.get_unnotified(db)) == 60 - len(matched)


def test_pipeline_handles_source_failure_gracefully(tmp_path):
    sample = json.loads(FIXTURE.read_text(encoding="utf-8"))
    call_count = {"n": 0}

    def flaky_client(url, params, **kwargs):
        call_count["n"] += 1
        if "Cnstwk" in url:
            raise RuntimeError("simulated outage for 공사")
        return sample

    rows = g2b_api.collect_all(
        service_key="TEST",
        page_size=100,
        sleep_seconds=0,
        lookback_days=1,
        http_client=flaky_client,
    )
    # 공사(Cnstwk)만 실패, 나머지 4개 오퍼레이션 × 12 = 48
    assert len(rows) == 48
    sources = {r["source"] for r in rows}
    assert sources == {"g2b_api_thng", "g2b_api_servc",
                       "g2b_api_frgcpt", "g2b_api_etc"}

    db = tmp_path / "partial.sqlite"
    database.init_db(db)
    processed, _ = database.upsert_bids(db, rows)
    assert processed == 48


def test_main_module_imports_cleanly():
    """Smoke: main module imports without syntax/ImportError."""
    import main  # noqa: F401
    assert hasattr(main, "run_collect")
    assert hasattr(main, "run_notify")
    assert hasattr(main, "run_once")
