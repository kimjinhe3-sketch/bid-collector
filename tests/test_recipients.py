from utils import recipients as rc


def test_is_valid_email():
    assert rc.is_valid_email("hong@example.com")
    assert rc.is_valid_email("a.b.c+tag@sub.domain.co.kr")
    assert not rc.is_valid_email("")
    assert not rc.is_valid_email("no-at-sign.example.com")
    assert not rc.is_valid_email("foo@")
    assert not rc.is_valid_email("@bar.com")
    assert not rc.is_valid_email(None)


def test_add_remove_load_save_roundtrip(tmp_path):
    p = tmp_path / "r.json"
    assert rc.load(p) == []
    assert rc.add("a@x.com", p) is True
    assert rc.add("a@x.com", p) is False  # 중복
    assert rc.add("invalid", p) is False  # 형식
    assert rc.add("b@x.com", p) is True
    assert sorted(rc.load(p)) == ["a@x.com", "b@x.com"]
    assert rc.remove("a@x.com", p) is True
    assert rc.remove("a@x.com", p) is False  # 없음
    assert rc.load(p) == ["b@x.com"]


def test_load_handles_corrupt_file(tmp_path):
    p = tmp_path / "corrupt.json"
    p.write_text("{not valid json}", encoding="utf-8")
    assert rc.load(p) == []


def test_save_deduplicates_and_sorts(tmp_path):
    p = tmp_path / "s.json"
    rc.save(["z@z.com", "a@a.com", "z@z.com", "  ", "m@m.com"], p)
    assert rc.load(p) == ["a@a.com", "m@m.com", "z@z.com"]


def test_resolve_to_addrs_merges_config_and_stored(tmp_path):
    p = tmp_path / "r.json"
    rc.save(["user1@a.com", "user2@b.com"], p)
    config = {"notifier": {"email": {"to_addrs": ["cfg@c.com", "user1@a.com"]}}}
    merged = rc.resolve_to_addrs(config, p)
    # config 먼저, 중복 제거, 유효 이메일만
    assert merged == ["cfg@c.com", "user1@a.com", "user2@b.com"]


def test_resolve_to_addrs_filters_invalid(tmp_path):
    p = tmp_path / "r.json"
    rc.save(["ok@x.com", "bad-email"], p)
    config = {"notifier": {"email": {"to_addrs": ["also-bad", "good@y.com"]}}}
    assert rc.resolve_to_addrs(config, p) == ["good@y.com", "ok@x.com"]


def test_resolve_to_addrs_empty_when_no_recipients(tmp_path):
    p = tmp_path / "r.json"
    assert rc.resolve_to_addrs({}, p) == []
