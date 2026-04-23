from collectors import g2b_crawler


def test_stub_returns_empty_and_logs_warning(caplog):
    import logging
    with caplog.at_level(logging.WARNING):
        result = g2b_crawler.collect(taskClCds=20)
    assert result == []
    assert any("deprecated" in rec.message for rec in caplog.records)
