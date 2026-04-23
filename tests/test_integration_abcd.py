"""A-B-C-D end-to-end: exercise every collector (g2b_api, kapt_api, alio,
g2b_crawler deprecated) into DB, then run filter + notifier + dashboard helpers.
All network is mocked.
"""
import json
from pathlib import Path

from collectors import g2b_api, kapt_api, alio_crawler, g2b_crawler
from db import database
from filters import keyword_filter
from notifiers import email_notifier, slack_notifier
from dashboard import app as dashboard
import main


FIX = Path(__file__).parent / "fixtures"
G2B_FIX = json.loads((FIX / "g2b_sample.json").read_text(encoding="utf-8"))
KAPT_FIX = json.loads((FIX / "kapt_sample.json").read_text(encoding="utf-8"))
ALIO_FIX = json.loads((FIX / "alio_sample.json").read_text(encoding="utf-8"))


def _g2b_client(url, params, **kwargs):
    return G2B_FIX


def _kapt_client(url, params, **kwargs):
    return KAPT_FIX


def _alio_client(url, params, **kwargs):
    return ALIO_FIX


def test_abcd_full_pipeline(tmp_path, monkeypatch):
    db_path = tmp_path / "abcd.sqlite"
    database.init_db(db_path)

    # --- A: collect from g2b + kapt + alio (g2b_crawler deprecated)
    g2b_rows = g2b_api.collect_all(service_key="TEST", page_size=100,
                                    sleep_seconds=0, lookback_days=1,
                                    http_client=_g2b_client)
    kapt_rows = kapt_api.collect(service_key="TEST", page_size=100,
                                  sleep_seconds=0, lookback_days=1,
                                  http_client=_kapt_client)
    alio_rows = alio_crawler.collect(max_pages=1, sleep_seconds=0,
                                      http_client=_alio_client)
    crawl_rows = g2b_crawler.collect()  # deprecated → []

    assert len(g2b_rows) == 12 * 3       # 3 operations × 12 fixture items
    assert len(kapt_rows) == 3
    assert len(alio_rows) == 10
    assert crawl_rows == []

    all_rows = g2b_rows + kapt_rows + alio_rows
    processed, skipped = database.upsert_bids(db_path, all_rows)
    assert processed == len(all_rows)
    assert skipped == 0

    # --- B: filter applies correctly, bid_types now includes K-apt/공공기관
    filter_cfg = {
        "include_keywords": ["AI", "데이터", "클라우드", "승강기", "용역"],
        "exclude_keywords": ["청소", "경비"],
        "min_amount_eok": 0,
        "max_amount_eok": 9999,
        "bid_types": ["물품", "용역", "공사", "K-apt", "공공기관"],
        "case_sensitive": False,
    }
    unnotified = database.get_unnotified(db_path)
    assert len(unnotified) == len(all_rows)

    matched = keyword_filter.apply_filters(unnotified, filter_cfg)
    sources = {r["source"] for r in matched}
    assert "kapt_api" in sources       # 승강기/용역 hits
    assert "alio" in sources or "g2b_api_servc" in sources

    # --- B: notifier payloads build from multi-source rows
    html = email_notifier.build_html(matched)
    assert "K-apt" in html or "공공기관" in html
    blocks = slack_notifier.build_blocks(matched)
    assert blocks[0]["type"] == "header"

    ids = [r["id"] for r in matched]
    database.mark_notified(db_path, ids)

    # --- C: dashboard helpers query the same DB
    counts = database.count_by_source(db_path)
    assert counts["g2b_api_thng"] == 12
    assert counts["g2b_api_servc"] == 12
    assert counts["g2b_api_cnstwk"] == 12
    assert counts["kapt_api"] == 3
    assert counts["alio"] == 10

    df = dashboard.rows_to_dataframe(unnotified[:20])
    assert "금액(억)" in df.columns
    assert "source_label" in df.columns
    labels = set(df["source_label"].unique())
    assert {"나라장터 물품", "나라장터 용역", "나라장터 공사"} & labels

    dashboard.load_counts.clear()
    dashboard.load_rows.clear()
    counts_live = dashboard.load_counts(str(db_path), None)
    assert sum(counts_live.values()) == len(all_rows)

    # --- Idempotency: re-collect and re-upsert preserves total & is_notified
    database.upsert_bids(db_path, all_rows)
    assert sum(database.count_by_source(db_path).values()) == len(all_rows)
    remaining_unnotified = database.get_unnotified(db_path)
    assert len(remaining_unnotified) == len(all_rows) - len(matched)


def test_main_run_collect_skips_sources_with_missing_keys(tmp_path, monkeypatch, caplog):
    import logging

    cfg = {
        "collection": {
            "sources": {"g2b_api": True, "kapt_api": True,
                        "alio": True, "g2b_crawler": True},
            "request_sleep_seconds": 0,
            "page_size": 100,
            "lookback_days": 1,
        },
        "database": {"path": str(tmp_path / "t.sqlite")},
    }

    monkeypatch.delenv("G2B_SERVICE_KEY", raising=False)
    monkeypatch.delenv("KAPT_SERVICE_KEY", raising=False)

    # Monkey-patch the two network calls we'd expect to reach (alio + g2b_crawler)
    alio_called = {"n": 0}
    def fake_alio_collect(**kwargs):
        alio_called["n"] += 1
        return []

    monkeypatch.setattr("main.alio_crawler.collect", fake_alio_collect)

    with caplog.at_level(logging.WARNING):
        total = main.run_collect(cfg)

    assert total == 0
    assert alio_called["n"] == 1   # alio should still run (no key needed)
    msgs = " ".join(rec.message for rec in caplog.records)
    assert "G2B_SERVICE_KEY" in msgs
    assert "KAPT_SERVICE_KEY" in msgs
    assert "deprecated" in msgs


def test_main_passes_kapt_overrides_from_config(tmp_path, monkeypatch):
    """main.run_collect should forward config.collection.kapt.{base_url,operation}."""
    cfg = {
        "collection": {
            "sources": {"kapt_api": True},
            "request_sleep_seconds": 0,
            "page_size": 100,
            "lookback_days": 1,
            "kapt": {"base_url": "https://example.test/api", "operation": "customOp"},
        },
        "database": {"path": str(tmp_path / "t.sqlite")},
    }
    monkeypatch.setenv("KAPT_SERVICE_KEY", "K")

    captured = {}
    def fake_kapt(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr("main.kapt_api.collect", fake_kapt)
    main.run_collect(cfg)
    assert captured["base_url"] == "https://example.test/api"
    assert captured["operation"] == "customOp"


def test_main_passes_alio_lookback_days_to_collector(tmp_path, monkeypatch):
    cfg = {
        "collection": {
            "sources": {"alio": True},
            "request_sleep_seconds": 0,
            "page_size": 100,
            "lookback_days": 3,
            "alio": {"keyword": "AI", "max_pages": 5},
        },
        "database": {"path": str(tmp_path / "t.sqlite")},
    }
    captured = {}
    def fake_alio(**kwargs):
        captured.update(kwargs)
        return []
    monkeypatch.setattr("main.alio_crawler.collect", fake_alio)
    main.run_collect(cfg)
    assert captured["lookback_days"] == 3
    assert captured["word"] == "AI"
    assert captured["max_pages"] == 5


def test_main_run_collect_invokes_all_active_collectors(tmp_path, monkeypatch):
    cfg = {
        "collection": {
            "sources": {"g2b_api": True, "kapt_api": True,
                        "alio": True, "g2b_crawler": False},
            "request_sleep_seconds": 0,
            "page_size": 100,
            "lookback_days": 1,
            "alio": {"keyword": "", "max_pages": 2},
        },
        "database": {"path": str(tmp_path / "t.sqlite")},
    }
    monkeypatch.setenv("G2B_SERVICE_KEY", "k1")
    monkeypatch.setenv("KAPT_SERVICE_KEY", "k2")

    calls = {"g2b": 0, "kapt": 0, "alio": 0}

    def fake_g2b(**kwargs):
        calls["g2b"] += 1
        return [{"source": "g2b_api_thng", "bid_no": "X1",
                 "title": "x", "bid_type": "물품", "org_name": "o",
                 "estimated_price": 100_000_000,
                 "open_date": "2026-04-22", "close_date": "2026-05-01",
                 "detail_url": None, "contract_method": None}]

    def fake_kapt(**kwargs):
        calls["kapt"] += 1
        return [{"source": "kapt_api", "bid_no": "K1",
                 "title": "k", "bid_type": "K-apt", "org_name": "ka",
                 "estimated_price": 50_000_000,
                 "open_date": "2026-04-22", "close_date": "2026-05-01",
                 "detail_url": None, "contract_method": None}]

    def fake_alio(**kwargs):
        calls["alio"] += 1
        return [{"source": "alio", "bid_no": "alio-1",
                 "title": "a", "bid_type": "공공기관", "org_name": "ao",
                 "estimated_price": None,
                 "open_date": "2026-04-22", "close_date": "2026-05-01",
                 "detail_url": "https://alio", "contract_method": None}]

    monkeypatch.setattr("main.g2b_api.collect_all", fake_g2b)
    monkeypatch.setattr("main.kapt_api.collect", fake_kapt)
    monkeypatch.setattr("main.alio_crawler.collect", fake_alio)

    total = main.run_collect(cfg)
    assert total == 3
    assert calls == {"g2b": 1, "kapt": 1, "alio": 1}

    # DB now has one row per source
    counts = database.count_by_source(cfg["database"]["path"])
    assert counts == {"g2b_api_thng": 1, "kapt_api": 1, "alio": 1}
