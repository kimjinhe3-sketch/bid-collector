from filters import keyword_filter

CONFIG = {
    "include_keywords": ["AI", "데이터"],
    "exclude_keywords": ["청소", "경비"],
    "min_amount_eok": 1,
    "max_amount_eok": 50,
    "bid_types": ["용역", "공사"],
}


def _r(title, price=500_000_000, bid_type="용역"):
    return {"title": title, "estimated_price": price, "bid_type": bid_type}


def test_include_keyword_or_match():
    assert keyword_filter.passes(_r("AI 플랫폼 구축"), CONFIG)
    assert keyword_filter.passes(_r("데이터 분석 용역"), CONFIG)
    assert not keyword_filter.passes(_r("일반 물품 납품"), CONFIG)


def test_exclude_keyword_wins_over_include():
    assert not keyword_filter.passes(_r("AI 청소 로봇"), CONFIG)
    assert not keyword_filter.passes(_r("데이터센터 경비 용역"), CONFIG)


def test_amount_min_max():
    c = dict(CONFIG)
    assert not keyword_filter.passes(_r("AI 작은건", price=50_000_000), c)  # 0.5억 < 1억
    assert keyword_filter.passes(_r("AI 정상건", price=500_000_000), c)
    assert not keyword_filter.passes(_r("AI 대형", price=60 * 10**8), c)  # 60억 > 50억


def test_amount_none_passes_range_check():
    assert keyword_filter.passes(_r("AI 미정", price=None), CONFIG)


def test_bid_type_filter():
    c = dict(CONFIG)
    assert not keyword_filter.passes(_r("AI 플랫폼", bid_type="물품"), c)
    assert keyword_filter.passes(_r("AI 플랫폼", bid_type="공사"), c)


def test_empty_filters_pass_everything():
    empty = {}
    assert keyword_filter.passes(_r("아무거나 경비"), empty)


def test_apply_filters_collects_matches():
    rows = [
        _r("AI 데이터 구축"),
        _r("청소 용역"),
        _r("데이터 공사", bid_type="공사"),
        _r("일반 납품"),
    ]
    out = keyword_filter.apply_filters(rows, CONFIG)
    assert len(out) == 2


def test_case_insensitive_by_default():
    c = {"include_keywords": ["AI", "cloud"], "bid_types": ["용역"]}
    assert keyword_filter.passes(_r("ai 플랫폼 구축"), c)
    assert keyword_filter.passes(_r("Cloud 마이그레이션"), c)
    assert keyword_filter.passes(_r("CLOUD 인프라"), c)


def test_case_sensitive_when_enabled():
    c = {"include_keywords": ["AI"], "bid_types": ["용역"], "case_sensitive": True}
    assert keyword_filter.passes(_r("AI 플랫폼"), c)
    assert not keyword_filter.passes(_r("ai 플랫폼"), c)


def test_case_insensitive_applies_to_exclude_too():
    c = {
        "include_keywords": ["데이터"],
        "exclude_keywords": ["청소"],
        "bid_types": ["용역"],
    }
    assert not keyword_filter.passes(_r("데이터 청소 용역"), c)
    assert not keyword_filter.passes(_r("데이터 CLEANING 청소"), c)
