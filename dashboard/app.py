"""대한민국 입찰공고 대시보드 (Streamlit).

로컬:  streamlit run dashboard/app.py
배포:  Streamlit Community Cloud — 이 파일을 entrypoint로 지정.

환경변수/시크릿은 utils.secrets.get_secret()로 통일 해석.
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# Windows corporate proxy SSL fix — no-op on Linux (Streamlit Cloud).
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Load .env when running locally (no-op on Streamlit Cloud).
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from db import database
from filters import keyword_filter
from utils.config_loader import load_config
from utils.secrets import get_secret


EOK = 100_000_000

SOURCE_LABELS = {
    "g2b_api_thng": "나라장터 물품",
    "g2b_api_servc": "나라장터 용역",
    "g2b_api_cnstwk": "나라장터 공사",
    "kapt_api": "K-apt",
    "alio": "ALIO",
    "g2b_crawl": "나라장터 크롤",
}


# ────────────────────────────────────────────────────────────────
# Styling — custom CSS incl. mobile media queries
# ────────────────────────────────────────────────────────────────

CUSTOM_CSS = """
<style>
/* Header brand bar */
.brand-bar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 18px; border-radius: 12px;
  background: linear-gradient(135deg, #1f6feb 0%, #0b4fbf 100%);
  color: #fff; margin-bottom: 18px;
  box-shadow: 0 2px 6px rgba(15, 23, 42, 0.08);
}
.brand-title {
  font-size: 1.35rem; font-weight: 700; margin: 0;
  display: flex; gap: 8px; align-items: center;
}
.brand-sub { font-size: 0.85rem; opacity: 0.9; }

/* Metric cards */
[data-testid="stMetric"] {
  background: #ffffff; border: 1px solid #e5e9ef; border-radius: 10px;
  padding: 12px 16px; transition: box-shadow 0.15s;
}
[data-testid="stMetric"]:hover { box-shadow: 0 2px 8px rgba(15,23,42,0.08); }

/* Section headers */
h2, h3 { color: #1f2328; }
.section-hint { color: #6b7280; font-size: 0.85rem; margin-top: -6px; margin-bottom: 10px; }

/* Filter caption chips */
.kw-chip {
  display: inline-block; padding: 2px 8px; margin: 2px 4px 2px 0;
  background: #eef3ff; color: #1f6feb; border-radius: 999px; font-size: 0.78rem;
}
.kw-chip.ex { background: #fef2f2; color: #b91c1c; }

/* Table title — data-editor links feel more native */
[data-testid="stDataFrame"] a { text-decoration: none; }

/* Empty state */
.empty-state {
  text-align: center; padding: 40px 20px; background: #f6f8fa;
  border-radius: 10px; color: #6b7280; border: 1px dashed #d1d5db;
}

/* ─── Mobile (≤ 768px) responsive tweaks ─── */
@media (max-width: 768px) {
  .brand-bar { flex-direction: column; align-items: flex-start; gap: 6px; padding: 12px; }
  .brand-title { font-size: 1.1rem; }
  [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
  [data-testid="stMetric"] { padding: 10px 12px; min-width: 44%; }
  [data-testid="stMetricValue"] { font-size: 1.2rem !important; }
  [data-testid="stMetricLabel"] { font-size: 0.75rem !important; }
  /* Hide the "DB 전체" secondary caption on small screens */
  .desktop-only { display: none; }
  /* Make dataframe horizontally scrollable but compact */
  [data-testid="stDataFrame"] { font-size: 0.82rem; }
  .block-container { padding-top: 1rem !important; padding-bottom: 1rem !important; }
}

/* Hide "Made with Streamlit" footer */
footer { visibility: hidden; }
#MainMenu { visibility: hidden; }
</style>
"""


# ────────────────────────────────────────────────────────────────
# Data loaders (cached)
# ────────────────────────────────────────────────────────────────

@st.cache_data(ttl=30)
def load_counts(db_path: str, since_date: str | None):
    return database.count_by_source(db_path, since_date=since_date)


@st.cache_data(ttl=30)
def load_rows(db_path: str, since_date: str | None, bid_types: tuple[str, ...],
              keyword: str | None, limit: int):
    return database.fetch_for_dashboard(
        db_path,
        since_date=since_date,
        bid_types=list(bid_types) if bid_types else None,
        keyword=keyword or None,
        limit=limit,
    )


@st.cache_data(ttl=30)
def load_trend(db_path: str, days: int):
    return database.daily_counts(db_path, days=days)


@st.cache_data(ttl=30)
def load_db_meta(db_path: str):
    if not Path(db_path).exists():
        return None
    mtime = datetime.fromtimestamp(Path(db_path).stat().st_mtime)
    return mtime


def invalidate_all_caches():
    load_counts.clear()
    load_rows.clear()
    load_trend.clear()
    load_db_meta.clear()


# ────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────

def rows_to_dataframe(rows: list[dict]) -> pd.DataFrame:
    cols = ["bid_no", "title", "org_name", "금액(억)", "close_date",
            "bid_type", "source_label", "detail_url"]
    if not rows:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(rows)
    if "estimated_price" in df.columns:
        df["금액(억)"] = (df["estimated_price"].fillna(0) / EOK).round(2)
    if "source" in df.columns:
        df["source_label"] = df["source"].map(SOURCE_LABELS).fillna(df["source"])
    return df[[c for c in cols if c in df.columns]]


def humanize_since(dt: datetime) -> str:
    delta = datetime.now() - dt
    if delta.total_seconds() < 60:
        return "방금 전"
    m = int(delta.total_seconds() / 60)
    if m < 60:
        return f"{m}분 전"
    h = m // 60
    if h < 24:
        return f"{h}시간 전"
    return f"{h // 24}일 전"


def render_kw_chips(include: list[str], exclude: list[str]) -> str:
    parts = []
    for kw in include:
        parts.append(f'<span class="kw-chip">+ {kw}</span>')
    for kw in exclude:
        parts.append(f'<span class="kw-chip ex">- {kw}</span>')
    return " ".join(parts) if parts else "<span style='color:#6b7280'>(설정된 키워드 없음)</span>"


# ────────────────────────────────────────────────────────────────
# Actions (in-dashboard collect / notify)
# ────────────────────────────────────────────────────────────────

def run_collect_action(config: dict, db_path: Path) -> tuple[bool, str]:
    """Run collection synchronously from within the dashboard."""
    from collectors import g2b_api, kapt_api, alio_crawler
    from db import database as dbmod

    sleep = float(config.get("collection", {}).get("request_sleep_seconds", 1.5))
    page_size = int(config.get("collection", {}).get("page_size", 100))
    lookback = int(config.get("collection", {}).get("lookback_days", 1))
    sources = config.get("collection", {}).get("sources") or {}

    dbmod.init_db(db_path)
    total = 0
    errors = []

    if sources.get("g2b_api"):
        key = get_secret("G2B_SERVICE_KEY")
        if not key:
            errors.append("G2B_SERVICE_KEY가 설정되지 않았습니다.")
        else:
            try:
                rows = g2b_api.collect_all(service_key=key, page_size=page_size,
                                            sleep_seconds=sleep, lookback_days=lookback)
                dbmod.upsert_bids(db_path, rows)
                total += len(rows)
            except Exception as e:
                errors.append(f"g2b_api: {e}")

    if sources.get("kapt_api"):
        key = get_secret("KAPT_SERVICE_KEY")
        if key:
            try:
                rows = kapt_api.collect(service_key=key, page_size=page_size,
                                        sleep_seconds=sleep, lookback_days=lookback)
                dbmod.upsert_bids(db_path, rows)
                total += len(rows)
            except Exception as e:
                errors.append(f"kapt_api: {e}")

    if sources.get("alio"):
        try:
            alio_cfg = (config.get("collection", {}).get("alio") or {})
            rows = alio_crawler.collect(
                word=alio_cfg.get("keyword", ""),
                max_pages=int(alio_cfg.get("max_pages", 10)),
                sleep_seconds=sleep,
                lookback_days=lookback,
            )
            dbmod.upsert_bids(db_path, rows)
            total += len(rows)
        except Exception as e:
            errors.append(f"alio: {e}")

    msg = f"수집 완료: {total:,}건"
    if errors:
        msg += "  (일부 오류: " + "; ".join(errors[:2]) + ")"
    invalidate_all_caches()
    return len(errors) == 0, msg


def run_notify_action(config: dict, db_path: Path, dry_run: bool = True) -> tuple[int, str]:
    from notifiers import email_notifier, slack_notifier
    from db import database as dbmod

    rows = dbmod.get_unnotified(db_path)
    filtered = keyword_filter.apply_filters(rows, config.get("filters") or {})
    if dry_run:
        return len(filtered), f"미리보기: {len(filtered):,}건이 알림 대상입니다. (전송은 하지 않음)"

    channels = (config.get("notifier") or {}).get("channels") or []
    sent = False
    if "email" in channels:
        sent = email_notifier.send_email(filtered, config.get("notifier") or {}) or sent
    if "slack" in channels:
        sent = slack_notifier.send_slack(filtered, config.get("notifier") or {}) or sent
    if sent:
        dbmod.mark_notified(db_path, [r["id"] for r in filtered])
        invalidate_all_caches()
    return len(filtered), ("전송 완료" if sent else "전송 실패 (설정을 확인하세요)")


# ────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(
        page_title="입찰공고 대시보드",
        page_icon="📋",
        layout="wide",
        initial_sidebar_state="auto",
    )
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    config = load_config(ROOT / "config.yaml")
    db_path = ROOT / (config.get("database", {}).get("path") or "data/bids.sqlite")

    # ── Brand bar ──────────────────────────────────────────
    db_mtime = load_db_meta(str(db_path))
    last_update = humanize_since(db_mtime) if db_mtime else "없음"
    st.markdown(
        f"""
        <div class="brand-bar">
          <div>
            <div class="brand-title">📋 대한민국 입찰공고 대시보드</div>
            <div class="brand-sub">마지막 수집: <b>{last_update}</b></div>
          </div>
          <div class="brand-sub">공공데이터포털 · ALIO · K-apt</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── First-run guard ────────────────────────────────────
    if not db_path.exists():
        st.info("아직 수집된 데이터가 없습니다. 아래 버튼을 눌러 수집을 시작하세요.")
        if st.button("🚀 지금 수집", type="primary", use_container_width=True):
            with st.status("공고 수집 중... 약 2~3분 소요됩니다.", expanded=True) as status:
                ok, msg = run_collect_action(config, db_path)
                status.update(label=msg, state=("complete" if ok else "error"))
            st.rerun()
        st.stop()

    # ── Sidebar filters ────────────────────────────────────
    with st.sidebar:
        st.markdown("### 🎛️ 필터")
        today = date.today()
        since = st.date_input("조회 시작일", value=today - timedelta(days=7))

        bid_type_options = ["물품", "용역", "공사", "민간", "K-apt", "공공기관"]
        cfg_types = config.get("filters", {}).get("bid_types") or bid_type_options[:3]
        for t in cfg_types:
            if t not in bid_type_options:
                bid_type_options.append(t)
        default_types = [t for t in cfg_types if t in bid_type_options]
        bid_types = st.multiselect("업종", bid_type_options, default=default_types)

        keyword = st.text_input("제목 검색", placeholder="예: 데이터")

        st.markdown("---")
        st.markdown("**키워드 필터 (config)**")
        st.markdown(
            render_kw_chips(
                config.get("filters", {}).get("include_keywords", []),
                config.get("filters", {}).get("exclude_keywords", []),
            ),
            unsafe_allow_html=True,
        )
        use_config_filter = st.checkbox("위 키워드 필터 적용", value=True)

        st.markdown("---")
        min_eok, max_eok = st.slider(
            "금액 범위 (억원)", 0, 9999,
            (int(config.get("filters", {}).get("min_amount_eok") or 0),
             int(config.get("filters", {}).get("max_amount_eok") or 9999)),
            step=1,
        )

        st.markdown("---")
        st.markdown("### ⚙️ 작업")
        if st.button("🚀 지금 수집", use_container_width=True, type="primary"):
            with st.status("공고 수집 중... 약 2~3분 소요됩니다.", expanded=True) as status:
                ok, msg = run_collect_action(config, db_path)
                status.update(label=msg, state=("complete" if ok else "error"))
            st.rerun()

        if st.button("📧 알림 미리보기 (dry-run)", use_container_width=True):
            count, msg = run_notify_action(config, db_path, dry_run=True)
            st.success(msg) if count else st.info(msg)

        if st.button("🔄 새로고침", use_container_width=True):
            invalidate_all_caches()
            st.rerun()

        st.caption(f"DB: `{db_path.name}` · 최종 업데이트 {last_update}")

    since_str = since.isoformat() if since else None

    # ── Section 1: metrics ─────────────────────────────────
    st.markdown("### 📊 오늘의 수집 현황")
    today_counts = load_counts(str(db_path), today.isoformat())
    total_counts = load_counts(str(db_path), None)

    if today_counts:
        items = sorted(today_counts.items())
        # Use up to 4 columns but wrap on mobile via CSS flex-wrap
        n = max(1, min(len(items), 4))
        cols = st.columns(n)
        for i, (src, count) in enumerate(items):
            with cols[i % n]:
                st.metric(SOURCE_LABELS.get(src, src), f"{count:,}건")
    else:
        st.info(f"{today} 수집 기록이 없습니다. 사이드바의 '지금 수집'을 눌러보세요.")

    st.markdown(
        f"<div class='section-hint desktop-only'>DB 전체: "
        f"<b>{sum(total_counts.values()):,}건</b> — "
        + " · ".join(f"{SOURCE_LABELS.get(k, k)} {v:,}"
                     for k, v in sorted(total_counts.items()))
        + "</div>",
        unsafe_allow_html=True,
    )

    # ── Section 2: filtered list ───────────────────────────
    st.markdown("### 📋 키워드 히트 목록")
    rows = load_rows(str(db_path), since_str, tuple(bid_types), keyword, 20_000)

    # Apply config filter on top (if checked)
    if use_config_filter:
        filter_cfg = dict(config.get("filters", {}))
        filter_cfg.pop("bid_types", None)  # sidebar already handled
        filter_cfg["min_amount_eok"] = min_eok
        filter_cfg["max_amount_eok"] = max_eok
        rows = keyword_filter.apply_filters(rows, filter_cfg)
    else:
        # still respect amount slider
        rows = keyword_filter.apply_filters(rows, {
            "min_amount_eok": min_eok, "max_amount_eok": max_eok,
        })

    df = rows_to_dataframe(rows)
    st.write(f"**검색 결과: {len(df):,}건**")

    if len(df) > 0:
        st.dataframe(
            df,
            width="stretch",
            hide_index=True,
            column_config={
                "bid_no": st.column_config.TextColumn("공고번호", width="small"),
                "title": st.column_config.TextColumn("제목", width="large"),
                "org_name": st.column_config.TextColumn("기관", width="medium"),
                "금액(억)": st.column_config.NumberColumn("금액", format="%.2f 억"),
                "close_date": st.column_config.TextColumn("마감", width="small"),
                "bid_type": st.column_config.TextColumn("업종", width="small"),
                "source_label": st.column_config.TextColumn("출처", width="small"),
                "detail_url": st.column_config.LinkColumn(
                    "🔗", display_text="보기", width="small"
                ),
            },
        )
    else:
        hint = []
        inc = config.get("filters", {}).get("include_keywords", [])
        if use_config_filter and inc:
            hint.append(f"포함 키워드({', '.join(inc)})와 겹치는 제목이 없을 수 있습니다")
        if bid_types:
            hint.append("사이드바 업종 선택을 바꿔보세요")
        if keyword:
            hint.append(f"제목 검색 '{keyword}' 제외해보세요")
        st.markdown(
            f"""<div class='empty-state'>
               조건에 해당하는 공고가 없습니다.<br>
               <small>{' · '.join(hint) if hint else '필터를 완화해보세요'}</small>
               </div>""",
            unsafe_allow_html=True,
        )

    # ── Section 3: trend ──────────────────────────────────
    st.markdown("### 📈 날짜별 수집 트렌드 (최근 30일)")
    trend = load_trend(str(db_path), 30)
    if trend and len(trend) >= 2:
        trend_df = pd.DataFrame(trend).rename(columns={"d": "날짜", "n": "건수"}).set_index("날짜")
        st.line_chart(trend_df, height=260, use_container_width=True)
    else:
        st.markdown(
            "<div class='empty-state'><b>데이터가 1일치 뿐입니다.</b><br>"
            "<small>며칠 더 수집되면 추세가 보입니다.</small></div>",
            unsafe_allow_html=True,
        )


if __name__ == "__main__":
    main()
