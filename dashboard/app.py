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
    "d2b_api_dmstc": "방위사업청",
    "kwater_api": "K-water",
    "kwater_api_cntrwk": "K-water 공사",
    "kwater_api_gds":    "K-water 물품",
    "kwater_api_servc":  "K-water 용역",
    "kwater_api_dmscpt": "K-water 내자",
    "kepco_api":         "KEPCO",
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
              keyword: str | None, limit: int,
              org_name: str | None = None,
              sources: tuple[str, ...] = ()):
    return database.fetch_for_dashboard(
        db_path,
        since_date=since_date,
        bid_types=list(bid_types) if bid_types else None,
        keyword=keyword or None,
        org_name=org_name or None,
        sources=list(sources) if sources else None,
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

def _fix_alio_url(url: str | None, title: str | None) -> str | None:
    """ALIO bidView.do URLs are 404 (legacy). Rewrite to the search-URL form
    at READ time so this works even if the DB migration didn't run."""
    if not url:
        return url
    if "alio.go.kr" in url and "bidView.do" in url:
        import urllib.parse
        kw = (title or "")[:30]
        return (
            "https://www.alio.go.kr/occasional/bidList.do"
            f"?type=title&word={urllib.parse.quote(kw)}"
        )
    return url


def _fmt_amount(price) -> str:
    """None/0/NaN → '링크 참조', 1억 이상 → 'N.NN 억', 그 미만 → 'N,NNN원'."""
    import math
    try:
        p = float(price) if price is not None else None
    except (TypeError, ValueError):
        p = None
    if p is None or (isinstance(p, float) and math.isnan(p)) or p <= 0:
        return "링크 참조"
    if p >= EOK:
        return f"{p / EOK:.2f} 억"
    return f"{int(p):,}원"


def rows_to_dataframe(rows: list[dict]) -> pd.DataFrame:
    cols = ["bid_no", "title", "org_name", "금액", "close_date",
            "bid_type", "source_label", "detail_url"]
    if not rows:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(rows)
    if "estimated_price" in df.columns:
        df["금액"] = df["estimated_price"].apply(_fmt_amount)
    if "source" in df.columns:
        df["source_label"] = df["source"].map(SOURCE_LABELS).fillna(df["source"])
    # Rewrite stale ALIO URLs on the fly (safety net in case DB migration didn't run).
    if "detail_url" in df.columns and "title" in df.columns:
        df["detail_url"] = [
            _fix_alio_url(u, t) for u, t in zip(df["detail_url"], df["title"])
        ]
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

def run_collect_action(config: dict, db_path: Path) -> tuple[bool, str, list[str]]:
    """Run collection synchronously from within the dashboard.

    Returns (ok, summary, per_source_log) so the UI can surface warnings
    even when the overall run succeeds (e.g. one source failed).
    """
    from collectors import (g2b_api, kapt_api, alio_crawler,
                            d2b_api, kwater_api, kepco_api)
    from db import database as dbmod

    sleep = float(config.get("collection", {}).get("request_sleep_seconds", 1.5))
    page_size = int(config.get("collection", {}).get("page_size", 100))
    lookback = int(config.get("collection", {}).get("lookback_days", 1))
    sources = config.get("collection", {}).get("sources") or {}

    dbmod.init_db(db_path)
    total = 0
    errors = []
    log_lines = []

    if sources.get("g2b_api"):
        key = get_secret("G2B_SERVICE_KEY")
        if not key:
            msg = "❌ 나라장터(G2B): G2B_SERVICE_KEY 미설정 — 클라우드 Secrets 탭에 추가하세요."
            errors.append(msg); log_lines.append(msg)
        else:
            try:
                rows = g2b_api.collect_all(service_key=key, page_size=page_size,
                                            sleep_seconds=sleep, lookback_days=lookback)
                dbmod.upsert_bids(db_path, rows)
                total += len(rows)
                log_lines.append(f"✅ 나라장터(G2B): {len(rows):,}건")
            except Exception as e:
                msg = f"❌ 나라장터(G2B) 오류: {type(e).__name__}: {e}"
                errors.append(msg); log_lines.append(msg)

    if sources.get("kapt_api"):
        key = get_secret("KAPT_SERVICE_KEY")
        if not key:
            log_lines.append("⏩ K-apt: 키 없음 — skip")
        else:
            try:
                rows = kapt_api.collect(service_key=key, page_size=page_size,
                                        sleep_seconds=sleep, lookback_days=lookback)
                dbmod.upsert_bids(db_path, rows)
                total += len(rows)
                log_lines.append(f"✅ K-apt: {len(rows):,}건")
            except Exception as e:
                msg = f"❌ K-apt 오류: {type(e).__name__}: {e}"
                errors.append(msg); log_lines.append(msg)

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
            log_lines.append(f"✅ ALIO: {len(rows):,}건")
        except Exception as e:
            msg = f"❌ ALIO 오류: {type(e).__name__}: {e}"
            errors.append(msg); log_lines.append(msg)

    if sources.get("d2b_api"):
        key = get_secret("G2B_SERVICE_KEY") or get_secret("D2B_SERVICE_KEY")
        if not key:
            log_lines.append("⏩ 국방전자조달(d2b): 키 없음 — skip")
        else:
            try:
                rows = d2b_api.collect_all(
                    service_key=key, page_size=page_size,
                    sleep_seconds=sleep, lookback_days=lookback,
                )
                dbmod.upsert_bids(db_path, rows)
                total += len(rows)
                log_lines.append(f"✅ 국방전자조달(d2b): {len(rows):,}건")
            except Exception as e:
                msg = f"❌ 국방전자조달(d2b) 오류: {type(e).__name__}: {e}"
                errors.append(msg); log_lines.append(msg)

    if sources.get("kwater_api"):
        key = get_secret("G2B_SERVICE_KEY") or get_secret("KWATER_SERVICE_KEY")
        kw_cfg = (config.get("collection", {}).get("kwater") or {})
        if not key or not kw_cfg.get("base_url"):
            log_lines.append("⏩ K-water: 키 또는 base_url 미설정 — skip")
        else:
            try:
                rows = kwater_api.collect(
                    service_key=key,
                    base_url=kw_cfg["base_url"],
                    type_param=kw_cfg.get("type_param", "_type"),
                    page_size=page_size,
                    sleep_seconds=sleep,
                    lookback_days=lookback,
                )
                dbmod.upsert_bids(db_path, rows)
                total += len(rows)
                log_lines.append(f"✅ K-water: {len(rows):,}건")
            except Exception as e:
                msg = f"❌ K-water 오류: {type(e).__name__}: {e}"
                errors.append(msg); log_lines.append(msg)

    if sources.get("kepco_api"):
        kepco_key = get_secret("KEPCO_API_KEY")
        kepco_cfg = (config.get("collection", {}).get("kepco") or {})
        if not kepco_key:
            log_lines.append("⏩ KEPCO: KEPCO_API_KEY 없음 — skip (bigdata.kepco.co.kr에서 별도 발급)")
        else:
            try:
                rows = kepco_api.collect(
                    api_key=kepco_key,
                    base_url=kepco_cfg.get("base_url") or kepco_api.DEFAULT_BASE_URL,
                    company_ids=kepco_cfg.get("company_ids") or None,
                    sleep_seconds=sleep,
                    lookback_days=lookback,
                )
                dbmod.upsert_bids(db_path, rows)
                total += len(rows)
                log_lines.append(f"✅ KEPCO: {len(rows):,}건")
            except Exception as e:
                msg = f"❌ KEPCO 오류: {type(e).__name__}: {e}"
                errors.append(msg); log_lines.append(msg)

    summary = f"수집 완료: {total:,}건"
    if errors:
        summary += f" · 오류 {len(errors)}건"
    invalidate_all_caches()
    return len(errors) == 0, summary, log_lines


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

    # Run startup migrations (idempotent).
    if db_path.exists():
        try:
            database.init_db(db_path)
            invalidate_all_caches()
        except Exception:
            pass

    # ── Secret availability check (warn once per session) ──
    if not get_secret("G2B_SERVICE_KEY"):
        st.warning(
            "⚠️ **나라장터(G2B) API 키가 설정되지 않았습니다.** "
            "Streamlit Cloud 앱 설정 > Secrets 탭에 `G2B_SERVICE_KEY = \"...\"` 추가하세요. "
            "현재는 ALIO 데이터만 수집됩니다."
        )

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
                ok, summary, log_lines = run_collect_action(config, db_path)
                for line in log_lines:
                    st.write(line)
                status.update(label=summary, state=("complete" if ok else "error"))
            if not ok:
                st.error("일부 소스 수집 실패. 위 로그를 확인하세요.")
            st.rerun()
        st.stop()

    # ── Session state defaults (일괄 초기화) ──
    today = date.today()
    cfg_filters = config.get("filters", {})
    cfg_include = cfg_filters.get("include_keywords", [])
    cfg_exclude = cfg_filters.get("exclude_keywords", [])
    bid_type_options = ["물품", "용역", "공사", "민간", "K-apt", "공공기관"]
    cfg_types = cfg_filters.get("bid_types") or bid_type_options[:3]
    for t in cfg_types:
        if t not in bid_type_options:
            bid_type_options.append(t)
    default_types = [t for t in cfg_types if t in bid_type_options]

    _defaults = {
        "f_since": today - timedelta(days=7),
        "f_bid_types": default_types,
        "f_keyword": "",
        "f_org_query": "",
        "f_include_text": ", ".join(cfg_include),
        "f_exclude_text": ", ".join(cfg_exclude),
        "f_use_kw": True,
        "f_min_eok": int(cfg_filters.get("min_amount_eok") or 0),
        "f_max_eok": int(cfg_filters.get("max_amount_eok") or 9999),
        "f_row_limit": 20_000,
        "source_filter": [],
    }
    for _k, _v in _defaults.items():
        st.session_state.setdefault(_k, _v)

    # ── Section 1: 클릭 가능한 metric 카드 (소스 필터 토글) ──
    st.markdown("### 📊 오늘의 수집 현황 &nbsp;<small style='color:#6b7280'>— 카드를 클릭하면 해당 소스만 필터됨</small>",
                unsafe_allow_html=True)
    today_counts = load_counts(str(db_path), today.isoformat())
    total_counts = load_counts(str(db_path), None)
    current_sources = st.session_state["source_filter"]

    if today_counts:
        items = sorted(today_counts.items())
        n = max(1, min(len(items), 4))
        cols = st.columns(n)
        for i, (src, count) in enumerate(items):
            label = SOURCE_LABELS.get(src, src)
            active = src in current_sources
            with cols[i % n]:
                btn_label = f"**{label}**  \n{count:,}건" + (" ✓" if active else "")
                if st.button(btn_label, key=f"mcard_{src}",
                             width="stretch",
                             type=("primary" if active else "secondary")):
                    st.session_state["source_filter"] = [] if active else [src]
                    st.rerun()
    else:
        st.info(f"{today} 수집 기록이 없습니다. 사이드바의 '지금 수집'을 눌러보세요.")

    if current_sources:
        label_str = ", ".join(SOURCE_LABELS.get(s, s) for s in current_sources)
        colL, colR = st.columns([4, 1])
        colL.info(f"🔍 **{label_str}** 소스만 표시 중")
        if colR.button("↩️ 전체 보기", width="stretch", key="clear_src_filter"):
            st.session_state["source_filter"] = []
            st.rerun()

    st.markdown(
        f"<div class='section-hint desktop-only'>DB 전체: "
        f"<b>{sum(total_counts.values()):,}건</b> — "
        + " · ".join(f"{SOURCE_LABELS.get(k, k)} {v:,}"
                     for k, v in sorted(total_counts.items()))
        + "</div>",
        unsafe_allow_html=True,
    )

    # ── Sidebar ────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### 🎛️ 필터")

        # 기관 바로가기 (form 바깥, 즉시 적용)
        st.caption("기관 바로가기")
        quick_cols = st.columns(3)
        for i, (lbl, q) in enumerate([
            ("한수원", "한국수력원자력"),
            ("방사청", "방위사업청"),
            ("한전", "한국전력"),
        ]):
            if quick_cols[i].button(lbl, key=f"qb_{lbl}", width="stretch"):
                st.session_state["f_org_query"] = q
                invalidate_all_caches()
                st.rerun()
        if st.session_state["f_org_query"]:
            if st.button("🔄 기관 필터 초기화", width="stretch", key="org_reset"):
                st.session_state["f_org_query"] = ""
                invalidate_all_caches()
                st.rerun()

        st.markdown("---")

        # 필터 입력 폼 (제출 버튼으로만 적용)
        with st.form("filter_form", border=False):
            st.date_input("조회 시작일", value=st.session_state["f_since"],
                          key="f_since")
            st.multiselect("업종", bid_type_options,
                           default=st.session_state["f_bid_types"],
                           key="f_bid_types")
            st.text_input("공고명 검색 (제목에만 적용)",
                          value=st.session_state["f_keyword"],
                          key="f_keyword",
                          placeholder="예: 데이터")
            st.text_input("기관명 검색",
                          value=st.session_state["f_org_query"],
                          key="f_org_query",
                          placeholder="예: 한국수력원자력")

            st.markdown("**공고명 포함 키워드** (제목 기준, 하나라도 있으면 통과)")
            st.text_area("include_keywords",
                         value=st.session_state["f_include_text"],
                         key="f_include_text", height=70,
                         help="쉼표로 구분, 공고 제목에만 적용",
                         label_visibility="collapsed")
            st.markdown("**공고명 제외 키워드** (제목 기준, 하나라도 있으면 제외)")
            st.text_area("exclude_keywords",
                         value=st.session_state["f_exclude_text"],
                         key="f_exclude_text", height=60,
                         label_visibility="collapsed")

            preview_inc = [k.strip() for k in st.session_state["f_include_text"].split(",") if k.strip()]
            preview_exc = [k.strip() for k in st.session_state["f_exclude_text"].split(",") if k.strip()]
            st.markdown(render_kw_chips(preview_inc, preview_exc),
                        unsafe_allow_html=True)
            st.checkbox("위 키워드 필터 적용", value=st.session_state["f_use_kw"],
                        key="f_use_kw")

            st.slider("금액 범위 (억원)", 0, 9999,
                      (st.session_state["f_min_eok"], st.session_state["f_max_eok"]),
                      step=1, key="f_amount_slider")

            st.number_input("최대 조회 건수", min_value=100, max_value=50_000,
                            value=st.session_state["f_row_limit"], step=1000,
                            key="f_row_limit")

            submitted = st.form_submit_button("🔍 필터 적용하기",
                                               width="stretch", type="primary")

        if submitted:
            lo, hi = st.session_state["f_amount_slider"]
            st.session_state["f_min_eok"] = lo
            st.session_state["f_max_eok"] = hi
            invalidate_all_caches()
            st.rerun()

        st.markdown("---")
        st.markdown("### ⚙️ 작업")
        if st.button("🚀 지금 수집", width="stretch", type="primary"):
            with st.status("공고 수집 중... 약 2~3분 소요됩니다.", expanded=True) as status:
                ok, summary, log_lines = run_collect_action(config, db_path)
                for line in log_lines:
                    st.write(line)
                status.update(label=summary, state=("complete" if ok else "error"))
            if not ok:
                st.error("일부 소스 수집 실패. 위 로그를 확인하세요.")
            st.rerun()
        if st.button("📧 알림 미리보기 (dry-run)", width="stretch"):
            count, msg = run_notify_action(config, db_path, dry_run=True)
            st.success(msg) if count else st.info(msg)
        if st.button("🔄 캐시 새로고침", width="stretch"):
            invalidate_all_caches()
            st.rerun()

        st.caption(f"DB: `{db_path.name}` · 최종 업데이트 {last_update}")

    # ── Section 2: 필터 적용된 목록 (세션 값 기반) ──
    st.markdown("### 📋 공고 목록")

    since_v = st.session_state["f_since"]
    since_str = since_v.isoformat() if since_v else None
    bid_types_v = st.session_state["f_bid_types"]
    keyword_v = st.session_state["f_keyword"]
    org_v = st.session_state["f_org_query"]
    live_include = [k.strip() for k in st.session_state["f_include_text"].split(",") if k.strip()]
    live_exclude = [k.strip() for k in st.session_state["f_exclude_text"].split(",") if k.strip()]
    use_kw = st.session_state["f_use_kw"]
    min_eok = st.session_state["f_min_eok"]
    max_eok = st.session_state["f_max_eok"]
    row_limit = int(st.session_state.get("f_row_limit", 20_000))

    rows = load_rows(
        str(db_path), since_str, tuple(bid_types_v), keyword_v,
        row_limit, org_name=org_v,
        sources=tuple(current_sources) if current_sources else (),
    )

    if use_kw:
        filter_cfg = {
            "include_keywords": live_include,
            "exclude_keywords": live_exclude,
            "min_amount_eok": min_eok,
            "max_amount_eok": max_eok,
            "case_sensitive": bool(cfg_filters.get("case_sensitive", False)),
        }
    else:
        filter_cfg = {"min_amount_eok": min_eok, "max_amount_eok": max_eok}
    rows = keyword_filter.apply_filters(rows, filter_cfg)

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
                "금액": st.column_config.TextColumn("금액", width="small"),
                "close_date": st.column_config.TextColumn("마감", width="small"),
                "bid_type": st.column_config.TextColumn("업종", width="small"),
                "source_label": st.column_config.TextColumn("출처", width="small"),
                "detail_url": st.column_config.LinkColumn(
                    "상세보기", display_text="🔗 열기", width="small"
                ),
            },
        )
    else:
        hint = []
        if use_kw and live_include:
            hint.append(f"포함 키워드({', '.join(live_include)})와 겹치는 제목이 없을 수 있습니다")
        if bid_types_v:
            hint.append("업종 선택을 바꿔보세요")
        if keyword_v:
            hint.append(f"공고명 검색 '{keyword_v}' 제외해보세요")
        if org_v:
            hint.append(f"기관명 검색 '{org_v}' 제외해보세요")
        if current_sources:
            hint.append("위 소스 필터를 해제해보세요 (↩️ 전체 보기)")
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
