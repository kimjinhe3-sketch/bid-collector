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
    assert "금액(억)" in df.columns
    assert "title" in df.columns


def test_rows_to_dataframe_computes_eok_column():
    rows = [
        {**_row(1), "estimated_price": 850_000_000},
        {**_row(2), "estimated_price": 24_150_000},
        {**_row(3), "estimated_price": None},
    ]
    df = dashboard.rows_to_dataframe(rows)
    assert list(df["금액(억)"]) == [8.5, 0.24, 0.0]


def test_rows_to_dataframe_maps_source_label():
    rows = [_row(1, source="g2b_api_servc"), _row(2, source="kapt_api")]
    df = dashboard.rows_to_dataframe(rows)
    assert "나라장터 용역" in list(df["source_label"])
    assert "K-apt" in list(df["source_label"])


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
        "kapt_api", "alio", "g2b_crawl",
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
