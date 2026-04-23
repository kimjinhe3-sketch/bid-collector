from notifiers import email_notifier, slack_notifier


ROWS = [
    {
        "bid_no": "R26BK01473926-001",
        "title": "AI 데이터 플랫폼",
        "org_name": "한국정보화진흥원",
        "estimated_price": 850_000_000,
        "close_date": "2026-05-06 10:00",
        "bid_type": "용역",
        "detail_url": "https://example.com/1",
    },
    {
        "bid_no": "R26BK01480805-000",
        "title": "서버 컴퓨터 <태그 포함>",
        "org_name": "대학교",
        "estimated_price": 24_150_000,
        "close_date": "2026-05-02 10:00",
        "bid_type": "물품",
        "detail_url": None,
    },
]


def test_email_build_html_contains_rows_and_escapes_html():
    html = email_notifier.build_html(ROWS)
    assert "AI 데이터 플랫폼" in html
    assert "&lt;태그 포함&gt;" in html  # escaped
    assert "https://example.com/1" in html
    assert "8.5억" in html or "850,000,000" in html


def test_email_build_html_empty_rows_shows_placeholder():
    html = email_notifier.build_html([])
    assert "조건에 맞는 공고가 없습니다" in html


def test_email_send_uses_injected_factory():
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port):
            sent["host"] = host
            sent["port"] = port
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self): sent["tls"] = True
        def login(self, u, p): sent["login"] = (u, p)
        def sendmail(self, f, to, msg):
            sent["from"] = f
            sent["to"] = to
            sent["msg"] = msg

    config = {
        "email": {
            "smtp_host": "smtp.test",
            "smtp_port": 587,
            "from_addr": "bot@test",
            "to_addrs": ["me@test"],
            "use_tls": True,
        }
    }
    ok = email_notifier.send_email(
        ROWS, config,
        smtp_user="u", smtp_pass="p",
        smtp_client_factory=lambda h, p: FakeSMTP(h, p),
    )
    assert ok
    assert sent["host"] == "smtp.test"
    assert sent["tls"] is True
    assert sent["login"] == ("u", "p")
    assert sent["from"] == "bot@test"
    import email as email_pkg
    parsed = email_pkg.message_from_string(sent["msg"])
    decoded = parsed.get_payload(0).get_payload(decode=True).decode("utf-8")
    assert "AI 데이터 플랫폼" in decoded
    assert "example.com/1" in decoded


def test_email_fails_gracefully_with_missing_config():
    assert email_notifier.send_email(ROWS, {}) is False


def test_slack_build_blocks_includes_header_and_rows():
    blocks = slack_notifier.build_blocks(ROWS)
    assert blocks[0]["type"] == "header"
    assert "2건" in blocks[0]["text"]["text"]
    all_text = str(blocks)
    assert "AI 데이터 플랫폼" in all_text
    assert "example.com/1" in all_text


def test_slack_truncates_long_lists():
    many = ROWS * 15  # 30 rows
    blocks = slack_notifier.build_blocks(many)
    context_blocks = [b for b in blocks if b["type"] == "context"]
    assert context_blocks, "expected an 'and N more' context block"


def test_slack_send_uses_post_fn():
    captured = {}

    def fake_post(url, payload):
        captured["url"] = url
        captured["payload"] = payload

    config = {"slack": {"webhook_url_env": "DUMMY_WEBHOOK"}}
    ok = slack_notifier.send_slack(
        ROWS, config,
        webhook_url="https://hooks.slack.com/services/AAA/BBB/CCC",
        post_fn=fake_post,
    )
    assert ok
    assert captured["url"].startswith("https://hooks.slack.com/")
    assert "blocks" in captured["payload"]


def test_slack_fails_without_webhook(monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    assert slack_notifier.send_slack(ROWS, {"slack": {}}) is False
