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

# 메트릭 카드용 상위 그룹: 3개 버킷으로 집계
SOURCE_GROUPS = {
    "나라장터": [
        "g2b_api_thng", "g2b_api_servc", "g2b_api_cnstwk",
        "g2b_api_frgcpt", "g2b_api_etc",
    ],
    "누리장터": [
        "prvt_api_servc", "prvt_api_thng",
        "prvt_api_cnstwk", "prvt_api_etc",
    ],
    "기타": [
        "d2b_api_dmstc", "kepco_api", "alio", "kapt_api",
        "kwater_api", "kwater_api_cntrwk", "kwater_api_gds",
        "kwater_api_servc", "kwater_api_dmscpt", "g2b_crawl",
    ],
}

SOURCE_LABELS = {
    "g2b_api_thng": "나라장터 물품",
    "g2b_api_servc": "나라장터 용역",
    "g2b_api_cnstwk": "나라장터 공사",
    "g2b_api_frgcpt": "나라장터 외자",
    "g2b_api_etc":    "나라장터 기타",
    "prvt_api_servc":  "누리장터 용역",
    "prvt_api_thng":   "누리장터 물품",
    "prvt_api_cnstwk": "누리장터 공사",
    "prvt_api_etc":    "누리장터 기타",
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

def _fix_alio_url(url, title) -> str | None:
    """ALIO bidView.do URLs are 404 (legacy). Rewrite to the search-URL form
    at READ time so this works even if the DB migration didn't run.

    pandas가 빈 값을 NaN으로 바꾸므로 str 타입 가드 필수.
    """
    if not isinstance(url, str) or not url:
        return url if isinstance(url, str) else None
    if "alio.go.kr" in url and "bidView.do" in url:
        import urllib.parse
        kw = (title if isinstance(title, str) else "")[:30]
        return (
            "https://www.alio.go.kr/occasional/bidList.do"
            f"?type=title&word={urllib.parse.quote(kw)}"
        )
    return url


def _fmt_amount(price) -> str:
    """None/0/NaN → '링크 참조', 그 외 → 'N.NN 억원' (항상 억원 단위)."""
    import math
    try:
        p = float(price) if price is not None else None
    except (TypeError, ValueError):
        p = None
    if p is None or (isinstance(p, float) and math.isnan(p)) or p <= 0:
        return "링크 참조"
    return f"{p / EOK:.2f} 억원"


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

def run_collect_action(config: dict, db_path: Path,
                        log_callback=None) -> tuple[bool, str, list[str]]:
    """Run collection synchronously from within the dashboard.

    log_callback(msg: str)가 주어지면 각 스테이지 시작/종료 시 즉시 호출해
    UI에 실시간으로 진행 상황을 표시할 수 있습니다.
    Returns (ok, summary, per_source_log).
    """
    import time as _time
    from collectors import (g2b_api, kapt_api, alio_crawler,
                            d2b_api, kwater_api, kepco_api, prvt_api)
    from db import database as dbmod

    sleep = float(config.get("collection", {}).get("request_sleep_seconds", 0.8))
    page_size = int(config.get("collection", {}).get("page_size", 100))
    lookback = int(config.get("collection", {}).get("lookback_days", 1))
    sources = config.get("collection", {}).get("sources") or {}

    dbmod.init_db(db_path)
    total = 0
    errors = []
    log_lines = []

    def _log(msg: str):
        log_lines.append(msg)
        if log_callback:
            try:
                log_callback(msg)
            except Exception:
                pass

    def _run_stage(name: str, fn):
        nonlocal total
        _log(f"⏳ {name} 수집 중…")
        t0 = _time.time()
        try:
            rows = fn()
            dbmod.upsert_bids(db_path, rows)
            total += len(rows)
            elapsed = _time.time() - t0
            _log(f"✅ {name}: {len(rows):,}건 ({elapsed:.0f}s)")
        except Exception as e:
            elapsed = _time.time() - t0
            msg = f"❌ {name} 오류 ({elapsed:.0f}s): {type(e).__name__}: {e}"
            errors.append(msg); _log(msg)

    if sources.get("g2b_api"):
        key = get_secret("G2B_SERVICE_KEY")
        if not key:
            msg = "❌ 나라장터(G2B): G2B_SERVICE_KEY 미설정 — Secrets에 추가하세요."
            errors.append(msg); _log(msg)
        else:
            _run_stage("나라장터(G2B)", lambda: g2b_api.collect_all(
                service_key=key, page_size=page_size,
                sleep_seconds=sleep, lookback_days=lookback,
            ))

    if sources.get("prvt_api"):
        key = get_secret("G2B_SERVICE_KEY")
        if not key:
            _log("⏩ 누리장터(민간): G2B 키 없음 — skip")
        else:
            _run_stage("누리장터(민간)", lambda: prvt_api.collect_all(
                service_key=key, page_size=page_size,
                sleep_seconds=sleep, lookback_days=lookback,
            ))

    if sources.get("kapt_api"):
        key = get_secret("KAPT_SERVICE_KEY")
        if not key:
            _log("⏩ K-apt: 키 없음 — skip")
        else:
            _run_stage("K-apt", lambda: kapt_api.collect(
                service_key=key, page_size=page_size,
                sleep_seconds=sleep, lookback_days=lookback,
            ))

    if sources.get("alio"):
        alio_cfg = (config.get("collection", {}).get("alio") or {})
        _run_stage("ALIO", lambda: alio_crawler.collect(
            word=alio_cfg.get("keyword", ""),
            max_pages=int(alio_cfg.get("max_pages", 10)),
            sleep_seconds=sleep,
            lookback_days=lookback,
        ))

    if sources.get("d2b_api"):
        key = get_secret("G2B_SERVICE_KEY") or get_secret("D2B_SERVICE_KEY")
        if not key:
            _log("⏩ 방위사업청(d2b): 키 없음 — skip")
        else:
            _run_stage("방위사업청(d2b)", lambda: d2b_api.collect_all(
                service_key=key, page_size=page_size,
                sleep_seconds=sleep, lookback_days=lookback,
            ))

    if sources.get("kwater_api"):
        key = get_secret("G2B_SERVICE_KEY") or get_secret("KWATER_SERVICE_KEY")
        kw_cfg = (config.get("collection", {}).get("kwater") or {})
        if not key or not kw_cfg.get("base_url"):
            _log("⏩ K-water: 키 또는 base_url 미설정 — skip")
        else:
            _run_stage("K-water", lambda: kwater_api.collect(
                service_key=key,
                base_url=kw_cfg["base_url"],
                type_param=kw_cfg.get("type_param", "_type"),
                page_size=page_size,
                sleep_seconds=sleep,
                lookback_days=lookback,
            ))

    if sources.get("kepco_api"):
        kepco_key = get_secret("KEPCO_API_KEY")
        kepco_cfg = (config.get("collection", {}).get("kepco") or {})
        if not kepco_key:
            _log("⏩ KEPCO: KEPCO_API_KEY 없음 — skip (bigdata.kepco.co.kr 발급 필요)")
        else:
            _run_stage("KEPCO", lambda: kepco_api.collect(
                api_key=kepco_key,
                base_url=kepco_cfg.get("base_url") or kepco_api.DEFAULT_BASE_URL,
                company_ids=kepco_cfg.get("company_ids") or None,
                sleep_seconds=sleep,
                lookback_days=lookback,
            ))

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
        page_title="국내 입찰공고 현황",
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
            <div class="brand-title">📋 국내 입찰공고 현황</div>
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
            with st.status("공고 수집 중… 약 1~2분 소요됩니다.", expanded=True) as status:
                def _stream(msg: str):
                    st.write(msg)
                ok, summary, _logs = run_collect_action(config, db_path,
                                                         log_callback=_stream)
                status.update(label=summary, state=("complete" if ok else "error"))
            if not ok:
                st.error("일부 소스 수집 실패. 위 로그를 확인하세요.")
            st.rerun()
        st.stop()

    # ── Session state defaults ──
    # Live-reactive: 모든 필터 입력은 f_*_input key로 session_state에 자동 바인드.
    # 입력 변경 → 자동 rerun → DB 재조회. 별도 "applied" 복사 불필요.
    today = date.today()
    cfg_filters = config.get("filters", {})
    cfg_include = cfg_filters.get("include_keywords", [])
    cfg_exclude = cfg_filters.get("exclude_keywords", [])
    bid_type_options = ["물품", "용역", "공사", "외자", "기타", "민간"]
    cfg_types = cfg_filters.get("bid_types") or bid_type_options[:3]
    for t in cfg_types:
        if t not in bid_type_options:
            bid_type_options.append(t)
    default_types = [t for t in cfg_types if t in bid_type_options]

    _init_min_eok = int(cfg_filters.get("min_amount_eok") or 0)
    _init_max_eok = int(cfg_filters.get("max_amount_eok") or 9999)
    _defaults = {
        "f_bid_types_input": default_types,
        "f_keyword_input": "",
        "f_org_query_input": "",
        "f_include_text_input": ", ".join(cfg_include),
        "f_exclude_text_input": ", ".join(cfg_exclude),
        "f_amount_slider_input": (_init_min_eok, _init_max_eok),
        "f_row_limit_input": 20_000,
        "source_filter": [],
    }
    for _k, _v in _defaults.items():
        st.session_state.setdefault(_k, _v)

    # ── Section 1: 4개 그룹 메트릭 카드 (전체/나라장터/누리장터/기타) ──
    st.markdown("### 📊 오늘의 수집 현황 &nbsp;<small style='color:#6b7280'>— 카드 클릭으로 그룹 필터</small>",
                unsafe_allow_html=True)
    today_counts = load_counts(str(db_path), today.isoformat())
    total_counts = load_counts(str(db_path), None)
    current_sources = st.session_state["source_filter"]

    # 현재 활성 그룹 판정 (source_filter 가 특정 그룹 전체와 일치하면 그 그룹)
    current_set = set(current_sources)
    active_group = None
    if current_set:
        for _g, _srcs in SOURCE_GROUPS.items():
            if current_set == set(_srcs):
                active_group = _g
                break

    if today_counts or total_counts:
        total_today = sum(today_counts.values())
        group_counts = {g: sum(today_counts.get(s, 0) for s in srcs)
                        for g, srcs in SOURCE_GROUPS.items()}

        items = [
            ("__ALL__",  "🌐 전체",      total_today,              active_group is None and not current_set),
            ("나라장터", "🏛️ 나라장터",  group_counts["나라장터"], active_group == "나라장터"),
            ("누리장터", "🏘️ 누리장터",  group_counts["누리장터"], active_group == "누리장터"),
            ("기타",     "📦 기타",      group_counts["기타"],     active_group == "기타"),
        ]
        cols = st.columns(4)
        for i, (key, label, count, active) in enumerate(items):
            with cols[i]:
                btn_label = f"**{label}** · {count:,}건" + (" ✓" if active else "")
                if st.button(btn_label, key=f"mcard_{key}",
                             width="stretch",
                             type=("primary" if active else "secondary")):
                    if key == "__ALL__" or active:
                        st.session_state["source_filter"] = []
                    else:
                        st.session_state["source_filter"] = SOURCE_GROUPS[key][:]
                    st.rerun()
    else:
        st.info(f"{today} 수집 기록이 없습니다. 사이드바의 '지금 수집'을 눌러보세요.")

    # 하단 요약 — 그룹별 간단 수치
    group_totals = {g: sum(total_counts.get(s, 0) for s in srcs)
                    for g, srcs in SOURCE_GROUPS.items()}
    st.markdown(
        f"<div class='section-hint desktop-only'>DB 전체: "
        f"<b>{sum(total_counts.values()):,}건</b> — "
        + " · ".join(f"{g} {v:,}" for g, v in group_totals.items())
        + "</div>",
        unsafe_allow_html=True,
    )

    # ── Sidebar (live-reactive 필터) ────────────────────────
    with st.sidebar:
        st.markdown("### 🎛️ 필터")

        # 필터 위젯: 모두 key=로 session_state 자동 바인드 → 입력 변경 시 즉시 반영
        st.multiselect("업종", bid_type_options, key="f_bid_types_input")
        st.text_input("공고명 검색 (제목에만 적용)",
                      key="f_keyword_input", placeholder="예: 데이터")
        st.text_input("기관명 검색",
                      key="f_org_query_input", placeholder="예: 한국수력원자력")

        st.markdown("**공고명 포함 키워드** (제목 기준, 하나라도 있으면 통과)")
        st.text_area("include_keywords", key="f_include_text_input", height=70,
                     help="쉼표로 구분, 공고 제목에만 적용",
                     label_visibility="collapsed")
        st.markdown("**공고명 제외 키워드** (제목 기준, 하나라도 있으면 제외)")
        st.text_area("exclude_keywords", key="f_exclude_text_input", height=60,
                     label_visibility="collapsed")

        preview_inc = [k.strip() for k in st.session_state["f_include_text_input"].split(",") if k.strip()]
        preview_exc = [k.strip() for k in st.session_state["f_exclude_text_input"].split(",") if k.strip()]
        st.markdown(render_kw_chips(preview_inc, preview_exc),
                    unsafe_allow_html=True)

        st.slider("금액 범위 (억원)", 0, 9999, key="f_amount_slider_input", step=1)
        st.number_input("최대 조회 건수", min_value=100, max_value=50_000,
                        step=1000, key="f_row_limit_input")

        st.markdown("---")
        st.markdown("### ⚙️ 작업")

        # 조회하기 (위) — 캐시 비우고 재조회 (현재 필터 즉시 재평가)
        if st.button("🔍 조회하기", width="stretch", type="primary",
                     key="refetch_btn"):
            invalidate_all_caches()
            st.rerun()

        # 수집하기 (아래) — 외부 API 호출
        if st.button("🚀 지금 수집", width="stretch", type="secondary",
                     key="collect_btn"):
            with st.status("공고 수집 중… 약 1~2분 소요됩니다.", expanded=True) as status:
                def _stream(msg: str):
                    st.write(msg)
                ok, summary, _logs = run_collect_action(config, db_path,
                                                         log_callback=_stream)
                status.update(label=summary,
                              state=("complete" if ok else "error"))
            if not ok:
                st.error("일부 소스 수집 실패. 위 로그를 확인하세요.")
            st.rerun()

        if st.button("📧 알림 미리보기 (dry-run)", width="stretch"):
            count, msg = run_notify_action(config, db_path, dry_run=True)
            st.success(msg) if count else st.info(msg)

        st.caption(f"DB: `{db_path.name}` · 최종 업데이트 {last_update}")

    # ── Section 2: 필터 적용된 목록 (live-reactive) ──
    st.markdown("### 📋 공고 목록")

    # 날짜 필터 제거 — DB 전체 조회 (수집 시점에 DB가 갱신됨)
    since_str = None
    bid_types_v = st.session_state["f_bid_types_input"]
    keyword_v = st.session_state["f_keyword_input"]
    org_v = st.session_state["f_org_query_input"]
    applied_include = [k.strip() for k in st.session_state["f_include_text_input"].split(",") if k.strip()]
    applied_exclude = [k.strip() for k in st.session_state["f_exclude_text_input"].split(",") if k.strip()]
    lo_hi = st.session_state["f_amount_slider_input"]
    min_eok, max_eok = lo_hi[0], lo_hi[1]
    row_limit = int(st.session_state["f_row_limit_input"])

    rows = load_rows(
        str(db_path), since_str, tuple(bid_types_v), keyword_v,
        row_limit, org_name=org_v,
        sources=tuple(current_sources) if current_sources else (),
    )

    filter_cfg = {
        "include_keywords": applied_include,
        "exclude_keywords": applied_exclude,
        "min_amount_eok": min_eok,
        "max_amount_eok": max_eok,
        "case_sensitive": bool(cfg_filters.get("case_sensitive", False)),
    }
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
        if applied_include:
            hint.append(f"포함 키워드({', '.join(applied_include)})와 겹치는 제목이 없을 수 있습니다")
        if bid_types_v:
            hint.append("업종 선택을 바꿔보세요")
        if keyword_v:
            hint.append(f"공고명 검색 '{keyword_v}' 제외해보세요")
        if org_v:
            hint.append(f"기관명 검색 '{org_v}' 제외해보세요")
        if current_sources:
            hint.append("'전체' 카드를 클릭해 소스 필터를 해제해보세요")
        st.markdown(
            f"""<div class='empty-state'>
               조건에 해당하는 공고가 없습니다.<br>
               <small>{' · '.join(hint) if hint else '필터를 완화해보세요'}</small>
               </div>""",
            unsafe_allow_html=True,
        )



if __name__ == "__main__":
    main()
