"""Test dashboard helper functions without launching Streamlit runtime."""
import pandas as pd

from dashboard import app as dashboard
from db import database


def _row(n, source="g2b_api_thng", price=500_000_000, bid_type="용역"):
    return {
        "source": source,
        "bid_no": f"B{n}",
        "title": f"sample {n}",
        "org_name": "기관",
        "contract_method": "제한경쟁",
        "estimated_price": price,
        "open_date": "2026-04-22 10:00",
        "close_date": "2026-05-02 10:00",
        "bid_type": bid_type,
        "detail_url": f"https://example.com/{n}",
    }


def test_rows_to_dataframe_empty():
    df = dashboard.rows_to_dataframe([])
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 0
    assert "금액(억원)" in df.columns
    assert "title" in df.columns
    assert "신규" in df.columns


def test_rows_to_dataframe_new_badge_today_only():
    from datetime import date, timedelta
    today = date.today()
    today_str = today.strftime("%Y-%m-%d")
    yesterday_str = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    rows = [
        {**_row(1), "open_date": today_str + " 10:00"},
        {**_row(2), "open_date": yesterday_str},
        {**_row(3), "open_date": None},
    ]
    df = dashboard.rows_to_dataframe(rows)
    vals = list(df["신규"])
    assert vals[0] == "N"     # 오늘 → N
    assert vals[1] == ""      # 어제 → 공란
    assert vals[2] == ""      # 파싱 실패 → 공란


def test_rows_to_dataframe_formats_amount_column():
    import math
    rows = [
        {**_row(1), "estimated_price": 850_000_000},
        {**_row(2), "estimated_price": 24_150_000},
        {**_row(3), "estimated_price": None},
        {**_row(4), "estimated_price": 0},
    ]
    df = dashboard.rows_to_dataframe(rows)
    vals = list(df["금액(억원)"])
    # 숫자형 (억 단위), 2자리 소수
    assert vals[0] == 8.50
    assert vals[1] == 0.24
    # None/0 → NaN (정렬 시 pandas 기본으로 최하단)
    assert vals[2] is None or (isinstance(vals[2], float) and math.isnan(vals[2]))
    assert vals[3] is None or (isinstance(vals[3], float) and math.isnan(vals[3]))


def test_rows_to_dataframe_maps_source_label():
    rows = [_row(1, source="g2b_api_servc"), _row(2, source="alio")]
    df = dashboard.rows_to_dataframe(rows)
    assert "나라장터 용역" in list(df["source_label"])
    assert "ALIO" in list(df["source_label"])


def test_rows_to_dataframe_upgrades_kepco_http_to_https():
    rows = [
        {**_row(1, source="kepco_api"), "title": "KEPCO 공고",
         "detail_url": "http://srm.kepco.net/printDownloadAttachment.do?id=abc"},
        {**_row(2, source="kepco_api"), "title": "KEPCO 공고 2",
         "detail_url": "https://srm.kepco.net/printDownloadAttachment.do?id=xyz"},
    ]
    df = dashboard.rows_to_dataframe(rows)
    urls = list(df["detail_url"])
    assert urls[0] == "https://srm.kepco.net/printDownloadAttachment.do?id=abc"
    assert urls[1] == "https://srm.kepco.net/printDownloadAttachment.do?id=xyz"


def test_rows_to_dataframe_rewrites_stale_alio_bidview_urls():
    rows = [
        {
            **_row(1, source="alio"),
            "title": "AI 기반 데이터 플랫폼",
            "detail_url": "https://www.alio.go.kr/occasional/bidView.do?seq=3520838",
        },
        {
            **_row(2, source="alio"),
            "title": "이미 정상",
            "detail_url": "https://www.alio.go.kr/occasional/bidList.do?type=title&word=ok",
        },
        {
            **_row(3, source="g2b_api_thng"),
            "title": "G2B 건드리지 말 것",
            "detail_url": "https://www.g2b.go.kr/foo?seq=1",
        },
    ]
    df = dashboard.rows_to_dataframe(rows)
    urls = list(df["detail_url"])
    # 레거시 ALIO URL은 search URL로 변환됨
    assert "bidView.do" not in urls[0]
    assert "bidList.do?type=title" in urls[0]
    # 이미 정상인 ALIO URL은 그대로
    assert urls[1] == "https://www.alio.go.kr/occasional/bidList.do?type=title&word=ok"
    # G2B URL은 건드리지 않음
    assert urls[2] == "https://www.g2b.go.kr/foo?seq=1"


def test_rows_to_dataframe_uses_raw_source_when_unknown():
    rows = [_row(1, source="unknown_source")]
    df = dashboard.rows_to_dataframe(rows)
    assert list(df["source_label"]) == ["unknown_source"]


def test_source_labels_cover_known_sources():
    expected = {
        "g2b_api_thng", "g2b_api_servc", "g2b_api_cnstwk",
        "g2b_api_frgcpt", "g2b_api_etc",
        "prvt_api_servc", "prvt_api_thng",
        "prvt_api_cnstwk", "prvt_api_etc",
        "alio", "g2b_crawl",
        "d2b_api_dmstc", "kwater_api",
        "kwater_api_cntrwk", "kwater_api_gds",
        "kwater_api_servc", "kwater_api_dmscpt",
        "kepco_api",
    }
    assert expected == set(dashboard.SOURCE_LABELS.keys())


def test_load_rows_uses_database_helpers(tmp_path, monkeypatch):
    """Ensure the cached loader calls database.fetch_for_dashboard with right args."""
    db = tmp_path / "t.sqlite"
    database.init_db(db)
    database.upsert_bids(db, [
        _row(1, bid_type="용역"),
        _row(2, bid_type="물품"),
        _row(3, bid_type="공사"),
    ])
    dashboard.load_rows.clear()  # clear st.cache_data between tests
    out = dashboard.load_rows(str(db), None, ("용역", "물품"), None, 100)
    assert {r["bid_type"] for r in out} == {"용역", "물품"}

    dashboard.load_rows.clear()
    out = dashboard.load_rows(str(db), None, (), "sample 2", 100)
    assert len(out) == 1
    assert out[0]["bid_no"] == "B2"
