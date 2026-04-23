"""Test main module dry-run and notify behavior without real network."""
import logging

import main
from db import database


def _rows():
    base = {
        "source": "g2b_api_thng",
        "contract_method": "제한경쟁",
        "org_name": "기관",
        "estimated_price": 500_000_000,
        "open_date": "2026-04-22 10:00",
        "close_date": "2026-05-02 10:00",
        "bid_type": "용역",
        "detail_url": "https://example.com/x",
    }
    return [
        {**base, "bid_no": "A1", "title": "AI 플랫폼 구축"},
        {**base, "bid_no": "A2", "title": "데이터 분석 용역"},
        {**base, "bid_no": "A3", "title": "청소 용역"},  # excluded
    ]


def _config(tmp_path):
    return {
        "database": {"path": str(tmp_path / "t.sqlite")},
        "filters": {
            "include_keywords": ["AI", "데이터"],
            "exclude_keywords": ["청소"],
            "bid_types": ["용역"],
            "min_amount_eok": 0,
            "max_amount_eok": 9999,
        },
        "notifier": {"channels": ["email", "slack"],
                     "email": {}, "slack": {}},
    }


def _setup_db(tmp_path):
    db_path = tmp_path / "t.sqlite"
    database.init_db(db_path)
    database.upsert_bids(db_path, _rows())
    return db_path


def test_run_notify_dry_run_skips_send_and_mark(tmp_path, caplog, monkeypatch):
    db_path = _setup_db(tmp_path)
    cfg = _config(tmp_path)

    # Guard: any attempt to actually send should fail loudly
    def no_send(*args, **kwargs):
        raise AssertionError("dry-run should not call send_email")

    def no_slack(*args, **kwargs):
        raise AssertionError("dry-run should not call send_slack")

    monkeypatch.setattr("notifiers.email_notifier.send_email", no_send)
    monkeypatch.setattr("notifiers.slack_notifier.send_slack", no_slack)
    monkeypatch.setattr("main.email_notifier.send_email", no_send)
    monkeypatch.setattr("main.slack_notifier.send_slack", no_slack)

    with caplog.at_level(logging.INFO):
        sent = main.run_notify(cfg, dry_run=True)

    assert sent == 2  # AI + 데이터, 청소 제외
    # is_notified should still be 0 for all rows (dry-run does not mark)
    assert len(database.get_unnotified(db_path)) == 3
    assert any("DRY-RUN" in rec.message for rec in caplog.records)


def test_run_notify_real_send_marks_notified(tmp_path, monkeypatch):
    db_path = _setup_db(tmp_path)
    cfg = _config(tmp_path)
    calls = {"email": 0, "slack": 0}

    def fake_email(rows, ncfg, **kwargs):
        calls["email"] += 1
        return True

    def fake_slack(rows, ncfg, **kwargs):
        calls["slack"] += 1
        return True

    monkeypatch.setattr("main.email_notifier.send_email", fake_email)
    monkeypatch.setattr("main.slack_notifier.send_slack", fake_slack)

    sent = main.run_notify(cfg, dry_run=False)
    assert sent == 2
    assert calls == {"email": 1, "slack": 1}
    # After successful send, the 2 matching rows should be marked
    remaining = database.get_unnotified(db_path)
    assert len(remaining) == 1
    assert remaining[0]["bid_no"] == "A3"


def test_run_notify_send_failure_does_not_mark(tmp_path, monkeypatch):
    db_path = _setup_db(tmp_path)
    cfg = _config(tmp_path)

    monkeypatch.setattr("main.email_notifier.send_email",
                        lambda rows, ncfg, **kw: False)
    monkeypatch.setattr("main.slack_notifier.send_slack",
                        lambda rows, ncfg, **kw: False)

    main.run_notify(cfg, dry_run=False)
    # All rows still unnotified because both channels failed
    assert len(database.get_unnotified(db_path)) == 3


def test_cli_help_exits_zero(capsys):
    import pytest
    with pytest.raises(SystemExit) as exc:
        main.main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "--dry-run" in out
    assert "--run-once" in out
