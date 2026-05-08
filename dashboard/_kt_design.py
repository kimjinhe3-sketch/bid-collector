"""KT Engineering Design System — Streamlit 적용 (BIDLIVE Korea 대시보드).

DESIGN_SYSTEM.md / kt_UX.md 의 정책을 Streamlit 환경에 맞게 통째 재구성.
원칙:
  1. 모노톤 우선 — 90% 흑/회/백, KT RED 는 primary action + 위험에만.
  2. 위계는 색이 아니라 크기·두께·간격으로.
  3. 핵심 수치는 KT Flow Black 으로 강하게, 본문은 Noto Sans KR 로 또박또박.
  4. 사이드바는 KT BLACK (스펙 5-1) — 단, 콘텐츠는 가볍게 유지하여 메인 영역과 균형.
  5. 카드 chrome — subtle 1px border + 12px radius. shadow 는 hover 시에만.
"""

KT_CSS = """
<style>
/* @import 는 항상 다른 룰 앞에 — 한글 본문 fallback */
@import url("https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&display=swap");

/* ═══════════════════════════════════════════════════════════════
   KT Flow 4종 self-host (static/fonts via enableStaticServing).
   - Thin    : 100~300
   - Medium  : 400~500
   - Bold    : 600~700
   - Black   : 800~900
   ═══════════════════════════════════════════════════════════════ */
@font-face {
  font-family: "KT Flow"; font-style: normal; font-display: swap;
  src: url("/app/static/fonts/KTFlow-Thin.ttf") format("truetype");
  font-weight: 100 300;
}
@font-face {
  font-family: "KT Flow"; font-style: normal; font-display: swap;
  src: url("/app/static/fonts/KTFlow-Medium.ttf") format("truetype");
  font-weight: 400 500;
}
@font-face {
  font-family: "KT Flow"; font-style: normal; font-display: swap;
  src: url("/app/static/fonts/KTFlow-Bold.ttf") format("truetype");
  font-weight: 600 700;
}
@font-face {
  font-family: "KT Flow"; font-style: normal; font-display: swap;
  src: url("/app/static/fonts/KTFlow-Black.ttf") format("truetype");
  font-weight: 800 900;
}

:root {
  /* Brand */
  --kt-red:        #FE2E36;
  --kt-red-hover:  #E0252D;       /* hover 90% */
  --kt-red-soft:   #FFEAEB;
  --kt-purple:     #AA50FF;
  --kt-purple-soft:#F3E8FF;
  --kt-blue:       #00A5FF;
  --kt-teal:       #00BEAC;
  --kt-amber:      #F59E0B;
  --kt-amber-soft: #FFF4DA;

  /* Mono */
  --kt-black:      #000000;
  --kt-ink:        #14141A;       /* 본문 진한 톤 (#000 보다 살짝 부드러움) */
  --kt-graphite:   #4C4C4E;       /* dark-gray */
  --kt-stone:      #6E6E72;       /* mid-gray */
  --kt-silver:     #A2A4A3;       /* light-gray */
  --kt-mist:       #E5E5E7;       /* border */
  --kt-fog:        #F1F1F3;       /* divider/소프트 */
  --kt-paper:      #F8F8FA;       /* 카드 보조 배경 */
  --kt-white:      #FFFFFF;

  /* Sizing */
  --r-sm: 8px;
  --r-md: 10px;
  --r-lg: 12px;
  --r-pill: 999px;

  /* Spacing scale */
  --s-1: 4px;
  --s-2: 8px;
  --s-3: 12px;
  --s-4: 16px;
  --s-5: 20px;
  --s-6: 24px;
  --s-8: 32px;
  --s-10: 40px;

  /* Type scale (KT Flow Black 30 → 본문 14) */
  --t-display: 1.875rem;   /* 30 */
  --t-h1:      1.5rem;     /* 24 */
  --t-h2:      1.25rem;    /* 20 */
  --t-h3:      1.125rem;   /* 18 */
  --t-body:    0.9375rem;  /* 15 */
  --t-sm:      0.875rem;   /* 14 */
  --t-xs:      0.75rem;    /* 12 */
  --t-xxs:     0.6875rem;  /* 11 (eyebrow) */

  /* Legacy aliases — 기존 코드 (.kw-chip, var(--accent), var(--bg) 등) 호환 */
  --bg: #FFFFFF;
  --bg-soft: #F8F8FA;
  --fg: #14141A;
  --fg-muted: #A2A4A3;
  --border: #E5E5E7;
  --border-strong: #A2A4A3;
  --accent: #FE2E36;
  --accent-hover: #E0252D;
  --accent-soft: #FFEAEB;
  --accent-number: #14141A;
  --link: #00A5FF;
  --tag-include-bg:     #FFEAEB;
  --tag-include-text:   #FE2E36;
  --tag-include-border: #FFC9CC;
  --tag-exclude-bg:     #F1F1F3;
  --tag-exclude-text:   #4C4C4E;
  --tag-exclude-border: #E5E5E7;
  --radius-sm: 8px;
  --radius: 10px;
  --radius-lg: 12px;
}

/* ═══════════════════════════════════════════════════════════════
   1. Global reset / typography
   ═══════════════════════════════════════════════════════════════ */
html, body, .stApp {
  background: var(--kt-white) !important;
  color: var(--kt-ink);
}
/* 메인 컨테이너 — 여백 정돈 (DESIGN_SYSTEM 5-4: 데스크톱 32px) */
.block-container:not([data-testid="stSidebar"] .block-container) {
  padding-top: var(--s-3) !important;
  padding-left: var(--s-8) !important;
  padding-right: var(--s-8) !important;
  max-width: 1400px;
}
@media (max-width: 768px) {
  .block-container {
    padding-left: var(--s-3) !important;
    padding-right: var(--s-3) !important;
  }
}
body, .stApp,
[data-testid="stMarkdownContainer"],
.stTextInput input, .stTextArea textarea,
.stDateInput input, .stNumberInput input,
.stButton > button, .stDownloadButton > button,
[data-testid="stCheckbox"] label, label, p, span, li {
  font-family: "KT Flow", "Noto Sans KR", -apple-system, BlinkMacSystemFont,
               "Apple SD Gothic Neo", "Segoe UI", sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  letter-spacing: -0.003em;
}

/* Material Icons preserved (헤더 햄버거 등 ligature 유지) */
.material-icons, .material-symbols-outlined, .material-symbols-rounded,
span[class*="material-icons"], span[class*="material-symbols"],
[data-testid="stIconMaterial"], [data-testid*="Icon"] > span {
  font-family: "Material Symbols Outlined", "Material Symbols Rounded",
               "Material Icons" !important;
  font-feature-settings: "liga" !important;
  font-variation-settings: "FILL" 0, "wght" 400, "GRAD" 0, "opsz" 24 !important;
  font-weight: normal !important;
  font-style: normal !important;
  line-height: 1 !important;
  letter-spacing: normal !important;
  text-transform: none !important;
  display: inline-block !important;
  white-space: nowrap !important;
  direction: ltr !important;
}

h1, h2, h3, h4 {
  font-family: "KT Flow", "Noto Sans KR", sans-serif !important;
  color: var(--kt-ink) !important;
  letter-spacing: -0.015em !important;
}
h1 { font-size: var(--t-h1) !important; font-weight: 700 !important; }
h2 { font-size: var(--t-h2) !important; font-weight: 700 !important; }
h3 {
  font-size: var(--t-h3) !important;
  font-weight: 700 !important;
  margin: var(--s-5) 0 var(--s-2) 0 !important;
}

p, .stMarkdown { color: var(--kt-graphite); font-size: var(--t-body); }
.section-hint, [data-testid="stCaptionContainer"] {
  color: var(--kt-stone) !important;
  font-size: var(--t-xs) !important;
}

/* ═══════════════════════════════════════════════════════════════
   2. Hero masthead — 페이지 상단 마스트헤드
   ═══════════════════════════════════════════════════════════════ */
.kt-hero {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--s-4);
  padding: var(--s-6) 0 var(--s-5) 0;
  margin-bottom: var(--s-6);
  border-bottom: 1px solid var(--kt-mist);
  position: relative;
}
.kt-hero::after {
  /* KT RED accent bar — 마스트헤드 하단 액센트 (4px) */
  content: "";
  position: absolute;
  left: 0; bottom: -1px;
  width: 56px; height: 3px;
  background: var(--kt-red);
  border-radius: 2px;
}
.kt-hero-eyebrow {
  font-size: var(--t-xxs);
  font-weight: 700;
  color: var(--kt-red);
  letter-spacing: 0.16em;
  text-transform: uppercase;
  margin-bottom: 6px;
}
.kt-hero-title {
  font-family: "KT Flow", "Noto Sans KR", sans-serif;
  font-weight: 700;
  font-size: 1.75rem;       /* 28px */
  color: var(--kt-ink);
  line-height: 1.2;
  letter-spacing: -0.02em;
  margin: 0;
}
.kt-hero-meta {
  text-align: right;
  white-space: nowrap;
}
.kt-hero-meta-label {
  font-size: var(--t-xxs);
  color: var(--kt-silver);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  font-weight: 600;
  margin-bottom: 2px;
}
.kt-hero-meta-value {
  font-family: "KT Flow", "Noto Sans KR", sans-serif;
  font-weight: 600;
  font-size: var(--t-sm);
  color: var(--kt-graphite);
}
@media (max-width: 640px) {
  .kt-hero { flex-direction: column; align-items: flex-start; gap: var(--s-2); padding: var(--s-4) 0 var(--s-3) 0; }
  .kt-hero-title { font-size: 1.4rem; }
  .kt-hero-meta { text-align: left; }
}

/* ═══════════════════════════════════════════════════════════════
   3. KPI strip — 핵심 수치 4-카드
   ═══════════════════════════════════════════════════════════════ */
.kt-kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--s-3);
  margin-bottom: var(--s-6);
}
@media (max-width: 900px) { .kt-kpi-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 480px) { .kt-kpi-grid { grid-template-columns: 1fr; } }

.kt-kpi-card {
  position: relative;
  padding: var(--s-5) var(--s-5) var(--s-4) var(--s-5);
  background: var(--kt-white);
  border: 1px solid var(--kt-mist);
  border-radius: var(--r-lg);
  transition: all 0.18s ease;
  overflow: hidden;
  min-height: 108px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}
.kt-kpi-card:hover {
  border-color: var(--kt-graphite);
  transform: translateY(-1px);
}
.kt-kpi-card::before {
  /* 좌측 3px accent — 카드별 시맨틱 색 */
  content: "";
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 3px;
  background: var(--kt-mist);
}
.kt-kpi-card.kt-accent-primary::before { background: var(--kt-red); }
.kt-kpi-card.kt-accent-info::before    { background: var(--kt-blue); }
.kt-kpi-card.kt-accent-success::before { background: var(--kt-teal); }
.kt-kpi-card.kt-accent-vip::before     { background: var(--kt-purple); }

.kt-kpi-label {
  font-family: "KT Flow", "Noto Sans KR", sans-serif;
  font-size: var(--t-xs);
  font-weight: 600;
  color: var(--kt-stone);
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.kt-kpi-value {
  font-family: "KT Flow", "Noto Sans KR", sans-serif;
  font-weight: 900;
  font-size: 2.125rem;           /* 34px = display */
  color: var(--kt-ink);
  line-height: 1.05;
  letter-spacing: -0.025em;
  margin: var(--s-2) 0 var(--s-1) 0;
  font-variant-numeric: tabular-nums;
}
.kt-kpi-value-suffix {
  font-size: 0.95rem;
  font-weight: 700;
  color: var(--kt-stone);
  margin-left: 4px;
}
.kt-kpi-meta {
  font-size: var(--t-xs);
  color: var(--kt-silver);
  font-weight: 500;
}
.kt-kpi-meta-strong { color: var(--kt-graphite); font-weight: 600; }

/* ═══════════════════════════════════════════════════════════════
   4. Source pill toggle (세그먼트형)
   .st-key-source_pills 컨테이너 안의 st.button 들을 pill 모양으로.
   ═══════════════════════════════════════════════════════════════ */
.st-key-source_pills {
  display: flex !important;
  align-items: center !important;
  flex-wrap: wrap !important;
  gap: var(--s-2) !important;
  margin: 0 0 var(--s-4) 0 !important;
  padding: 0 !important;
  background: transparent !important;
  border: none !important;
}
.st-key-source_pills [data-testid="stElementContainer"] { margin: 0 !important; padding: 0 !important; }
.st-key-source_pills .stButton > button {
  height: 36px !important;
  min-height: 36px !important;
  padding: 0 var(--s-4) !important;
  border-radius: var(--r-pill) !important;
  font-family: "KT Flow", "Noto Sans KR", sans-serif !important;
  font-size: var(--t-sm) !important;
  font-weight: 600 !important;
  letter-spacing: -0.005em !important;
  transition: all 0.15s ease !important;
}
/* Inactive pill — 화이트 outline */
.st-key-source_pills .stButton > button[kind="secondary"] {
  background: var(--kt-white) !important;
  color: var(--kt-graphite) !important;
  border: 1px solid var(--kt-mist) !important;
}
.st-key-source_pills .stButton > button[kind="secondary"]:hover {
  border-color: var(--kt-ink) !important;
  color: var(--kt-ink) !important;
  background: var(--kt-fog) !important;
}
/* Active pill — KT BLACK fill */
.st-key-source_pills .stButton > button[kind="primary"],
.st-key-source_pills .stButton > button[kind="primary"] * {
  background: var(--kt-ink) !important;
  color: var(--kt-white) !important;
  -webkit-text-fill-color: var(--kt-white) !important;
  border: 1px solid var(--kt-ink) !important;
}
.st-key-source_pills .stButton > button[kind="primary"]:hover,
.st-key-source_pills .stButton > button[kind="primary"]:hover * {
  background: var(--kt-graphite) !important;
  border-color: var(--kt-graphite) !important;
}

/* "전체/해제" subtle 텍스트 버튼처럼 — kt-action-pill 마커 */
.st-key-source_pills .kt-action-spacer { flex: 1 1 0 !important; }

/* ═══════════════════════════════════════════════════════════════
   5. Buttons — primary KT RED, secondary outline
   ═══════════════════════════════════════════════════════════════ */
.stButton > button {
  border-radius: var(--r-sm) !important;
  border: 1px solid var(--kt-mist) !important;
  background: var(--kt-white) !important;
  color: var(--kt-ink) !important;
  font-family: "KT Flow", "Noto Sans KR", sans-serif !important;
  font-weight: 600 !important;
  font-size: var(--t-sm) !important;
  padding: 0.5rem 1rem !important;
  transition: all 0.15s ease !important;
  box-shadow: none !important;
}
.stButton > button:hover {
  border-color: var(--kt-ink) !important;
  background: var(--kt-fog) !important;
}
.stButton > button:focus-visible {
  outline: 2px solid var(--kt-red) !important;
  outline-offset: 2px !important;
}
/* Primary — KT RED */
.stButton > button[kind="primary"],
.stButton > button[kind="primary"] *,
.stButton > button[kind="primary"] p,
.stButton > button[kind="primary"] span,
.stButton > button[kind="primary"] div {
  background: var(--kt-red) !important;
  border: 1px solid var(--kt-red) !important;
  color: var(--kt-white) !important;
  -webkit-text-fill-color: var(--kt-white) !important;
}
.stButton > button[kind="primary"] svg { fill: var(--kt-white) !important; }
.stButton > button[kind="primary"]:hover,
.stButton > button[kind="primary"]:hover * {
  background: var(--kt-red-hover) !important;
  border-color: var(--kt-red-hover) !important;
}

/* ═══════════════════════════════════════════════════════════════
   6. Inputs / multiselect / slider
   ═══════════════════════════════════════════════════════════════ */
.stTextInput input, .stTextArea textarea,
.stDateInput input, .stNumberInput input,
.stSelectbox > div > div, .stMultiSelect > div > div {
  border-radius: var(--r-sm) !important;
  border: 1px solid var(--kt-mist) !important;
  background: var(--kt-white) !important;
  font-family: "Noto Sans KR", sans-serif !important;
  font-size: var(--t-sm) !important;
  color: var(--kt-ink) !important;
}
.stTextInput input:focus, .stTextArea textarea:focus,
.stDateInput input:focus, .stNumberInput input:focus {
  border-color: var(--kt-red) !important;
  box-shadow: 0 0 0 3px var(--kt-red-soft) !important;
  outline: none !important;
}
/* Multiselect 선택 태그 — pill */
.stMultiSelect [data-baseweb="tag"], [data-baseweb="tag"] {
  background-color: var(--kt-red-soft) !important;
  color: var(--kt-red) !important;
  border: 1px solid #FFC9CC !important;
  border-radius: var(--r-pill) !important;
  font-family: "Noto Sans KR", sans-serif !important;
  font-weight: 500 !important;
}
.stMultiSelect [data-baseweb="tag"] span, [data-baseweb="tag"] span {
  color: var(--kt-red) !important;
  -webkit-text-fill-color: var(--kt-red) !important;
}
.stMultiSelect [data-baseweb="tag"] svg, [data-baseweb="tag"] svg {
  fill: var(--kt-red) !important; color: var(--kt-red) !important;
}
.stSlider [role="slider"] {
  background: var(--kt-red) !important;
  border-color: var(--kt-red) !important;
}

/* kw-chip (필터 미리보기 칩) */
.kw-chip {
  display: inline-block;
  padding: 3px 10px;
  margin: 3px 4px 3px 0;
  background: var(--kt-red-soft);
  color: var(--kt-red);
  border: 1px solid #FFC9CC;
  border-radius: var(--r-pill);
  font-family: "Noto Sans KR", sans-serif;
  font-size: var(--t-xs);
  font-weight: 500;
  line-height: 1.5;
}
.kw-chip.ex {
  background: var(--kt-fog);
  color: var(--kt-graphite);
  border-color: var(--kt-mist);
}

/* ═══════════════════════════════════════════════════════════════
   7. Sidebar — KT BLACK (DESIGN_SYSTEM 5-1)
   240px / 흰 텍스트 / 가벼운 위계 / 컴팩트 타이포
   ═══════════════════════════════════════════════════════════════ */
[data-testid="stSidebar"] {
  background: var(--kt-black) !important;
  border-right: none !important;
  width: 16rem !important;       /* 256px - 살짝 여유 */
  min-width: 16rem !important;
}
[data-testid="stSidebar"] > div { background: var(--kt-black) !important; }

/* 사이드바 모든 텍스트 — 흰색 */
[data-testid="stSidebar"] *,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {
  color: rgba(255, 255, 255, 0.92) !important;
  -webkit-text-fill-color: rgba(255, 255, 255, 0.92) !important;
}
/* 캡션·placeholder 는 한 단계 톤다운 */
[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
[data-testid="stSidebar"] .stCaption,
[data-testid="stSidebar"] ::placeholder {
  color: rgba(255, 255, 255, 0.5) !important;
  -webkit-text-fill-color: rgba(255, 255, 255, 0.5) !important;
}

[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
  color: #FFFFFF !important;
  font-family: "KT Flow", "Noto Sans KR", sans-serif !important;
  font-size: 0.7rem !important;
  font-weight: 700 !important;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  margin: var(--s-5) 0 var(--s-2) 0 !important;
  opacity: 0.6;
}

/* divider (사이드바 안 hr) */
[data-testid="stSidebar"] hr {
  border: none !important;
  border-top: 1px solid rgba(255, 255, 255, 0.1) !important;
  margin: var(--s-4) 0 !important;
}

/* 사이드바 입력 — glass */
[data-testid="stSidebar"] input,
[data-testid="stSidebar"] textarea,
[data-testid="stSidebar"] [data-baseweb="input"] > div,
[data-testid="stSidebar"] [data-baseweb="select"] > div {
  background: rgba(255, 255, 255, 0.06) !important;
  border: 1px solid rgba(255, 255, 255, 0.14) !important;
  color: #FFFFFF !important;
  -webkit-text-fill-color: #FFFFFF !important;
  border-radius: var(--r-sm) !important;
}
[data-testid="stSidebar"] input:focus,
[data-testid="stSidebar"] textarea:focus {
  border-color: var(--kt-red) !important;
  background: rgba(255, 255, 255, 0.10) !important;
  box-shadow: 0 0 0 2px rgba(254, 46, 54, 0.35) !important;
}

/* 사이드바 버튼 — secondary 는 dark glass, primary 는 KT RED */
[data-testid="stSidebar"] .stButton > button {
  background: rgba(255, 255, 255, 0.08) !important;
  border: 1px solid rgba(255, 255, 255, 0.16) !important;
  color: #FFFFFF !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
  background: rgba(255, 255, 255, 0.14) !important;
  border-color: rgba(255, 255, 255, 0.32) !important;
}
[data-testid="stSidebar"] .stButton > button[kind="primary"] {
  background: var(--kt-red) !important;
  border-color: var(--kt-red) !important;
  color: #FFFFFF !important;
}
[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {
  background: var(--kt-red-hover) !important;
  border-color: var(--kt-red-hover) !important;
}

/* 사이드바 multiselect 선택 태그 — 어두운 배경 위 가독성 위해 KT RED 채움 */
[data-testid="stSidebar"] [data-baseweb="tag"] {
  background-color: rgba(254, 46, 54, 0.18) !important;
  color: #FF8A8E !important;
  border: 1px solid rgba(254, 46, 54, 0.35) !important;
}
[data-testid="stSidebar"] [data-baseweb="tag"] span {
  color: #FF8A8E !important; -webkit-text-fill-color: #FF8A8E !important;
}
[data-testid="stSidebar"] [data-baseweb="tag"] svg {
  fill: #FF8A8E !important; color: #FF8A8E !important;
}

/* 사이드바 슬라이더 */
[data-testid="stSidebar"] .stSlider [role="slider"] { background: var(--kt-red) !important; }
[data-testid="stSidebar"] .stSlider [data-baseweb="slider"] > div > div {
  background: var(--kt-red) !important;
}

/* 사이드바 체크박스 */
[data-testid="stSidebar"] [data-baseweb="checkbox"] [aria-checked="true"] > div {
  background: var(--kt-red) !important;
  border-color: var(--kt-red) !important;
}

/* 사이드바 KT engineering 로고 (다크 버전) + product label */
.kt-sidebar-brand {
  padding: var(--s-4) 0 var(--s-2) 0;
  margin: 0;
  display: flex;
  align-items: center;
}
.kt-sidebar-brand img { height: 22px; width: auto; display: block; opacity: 0.95; }
.kt-sidebar-product {
  font-family: "KT Flow", "Noto Sans KR", sans-serif;
  font-size: var(--t-xxs);
  font-weight: 700;
  letter-spacing: 0.18em;
  color: rgba(255, 255, 255, 0.45);
  padding: 0 0 var(--s-3) 0;
  margin: 0 0 var(--s-3) 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}
@media (max-width: 640px) { .kt-sidebar-brand img { height: 20px; } }

/* 사이드바 kw-chip (필터 미리보기) — 어두운 배경 위 톤 조정 */
[data-testid="stSidebar"] .kw-chip {
  background: rgba(254, 46, 54, 0.16);
  color: #FF8A8E;
  border-color: rgba(254, 46, 54, 0.32);
}
[data-testid="stSidebar"] .kw-chip.ex {
  background: rgba(255, 255, 255, 0.08);
  color: rgba(255, 255, 255, 0.7);
  border-color: rgba(255, 255, 255, 0.18);
}

/* 사이드바 expander */
[data-testid="stSidebar"] [data-testid="stExpander"] {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.10);
  border-radius: var(--r-sm);
}

/* 사이드바 햄버거/접기 버튼 가시성 */
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapsedControl"],
[data-testid="stSidebarCollapseButton"],
[data-testid="stExpandSidebarButton"],
[data-testid="baseButton-headerNoPadding"] {
  visibility: visible !important;
  display: inline-flex !important;
  opacity: 1 !important;
  pointer-events: auto !important;
  min-width: 32px !important;
  min-height: 32px !important;
  align-items: center !important;
  justify-content: center !important;
}

@media (max-width: 900px) {
  [data-testid="stSidebar"] { width: 14rem !important; min-width: 14rem !important; }
}
@media (max-width: 640px) {
  [data-testid="stSidebar"][aria-expanded="true"] {
    width: 84vw !important; min-width: 0 !important; max-width: 84vw !important;
  }
  [data-testid="collapsedControl"],
  [data-testid="stSidebarCollapsedControl"],
  [data-testid="stExpandSidebarButton"] {
    background: var(--kt-white) !important;
    border: 1px solid var(--kt-red) !important;
    border-radius: var(--r-sm) !important;
    box-shadow: 0 2px 6px rgba(254, 46, 54, 0.20) !important;
  }
  [data-testid="stExpandSidebarButton"] svg,
  [data-testid="stExpandSidebarButton"] [data-testid="stIconMaterial"] {
    color: var(--kt-red) !important;
  }
  [data-testid="stHeader"] { z-index: 999 !important; }
  [data-testid="stSidebar"] .block-container { padding: 0.6rem !important; }
}

/* ═══════════════════════════════════════════════════════════════
   8. Table card chrome
   - .st-key-bidtable_titlebar = 표 위 toolbar
   - 그 다음 stDataFrame 을 카드처럼 wrap
   ═══════════════════════════════════════════════════════════════ */
.st-key-bidtable_titlebar {
  background: var(--kt-white) !important;
  border: 1px solid var(--kt-mist) !important;
  border-bottom: none !important;
  border-radius: var(--r-lg) var(--r-lg) 0 0 !important;
  padding: var(--s-3) var(--s-4) !important;
  margin: 0 !important;
  min-height: 48px;
}
.st-key-bidtable_titlebar [data-testid="stElementContainer"] {
  margin: 0 !important; padding: 0 !important;
}
.st-key-bidtable_titlebar .tbl-title {
  font-family: "KT Flow", "Noto Sans KR", sans-serif;
  font-size: var(--t-body);
  font-weight: 600;
  color: var(--kt-ink);
  line-height: 1.3;
}
.st-key-bidtable_titlebar .tbl-title b {
  color: var(--kt-red); font-weight: 700;
  font-variant-numeric: tabular-nums;
}

/* 타이틀바 다음 dataframe 을 표시상 한 카드로 연결 */
.st-key-bidtable_titlebar + [data-testid="stElementContainer"] { margin-top: 0 !important; }
.st-key-bidtable_titlebar + [data-testid="stElementContainer"] [data-testid="stDataFrame"] {
  border-radius: 0 0 var(--r-lg) var(--r-lg) !important;
  border-top: 1px solid var(--kt-fog) !important;
}

[data-testid="stDataFrame"] {
  border-radius: var(--r-lg);
  overflow: hidden;
  border: 1px solid var(--kt-mist);
  background: var(--kt-white);
}
[data-testid="stDataFrame"] a {
  text-decoration: none;
  color: var(--kt-blue) !important;
  font-weight: 600;
}
[data-testid="stDataFrame"] a:hover { text-decoration: underline; }
[data-testid="stDataFrame"] [role="cell"][data-testid*="Number"],
[data-testid="stDataFrame"] [data-col-index] [style*="text-align: right"] {
  color: var(--kt-ink) !important;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
[data-testid="stStatus"] { border-radius: var(--r-md) !important; }
[data-testid="stAlert"] [role="alert"] {
  border-radius: var(--r-sm) !important;
  font-family: "Noto Sans KR", sans-serif !important;
}

/* xlsx 다운로드 — toolbar 우측 ghost 버튼 */
.st-key-bidtable_titlebar [data-testid="stDownloadButton"] button,
[data-testid="stDownloadButton"] button {
  background: transparent !important;
  color: var(--kt-stone) !important;
  border: 1px solid var(--kt-mist) !important;
  padding: 4px 12px !important;
  font-family: "KT Flow", "Noto Sans KR", sans-serif !important;
  font-size: var(--t-xs) !important;
  font-weight: 600 !important;
  letter-spacing: 0.01em !important;
  min-height: 30px !important;
  height: 30px !important;
  border-radius: var(--r-sm) !important;
  box-shadow: none !important;
  transition: all 0.15s ease;
}
.st-key-bidtable_titlebar [data-testid="stDownloadButton"] button:hover,
[data-testid="stDownloadButton"] button:hover {
  background: var(--kt-ink) !important;
  color: var(--kt-white) !important;
  border-color: var(--kt-ink) !important;
}

/* ═══════════════════════════════════════════════════════════════
   9. Hide Streamlit chrome (사이드바 toggle 은 유지)
   ═══════════════════════════════════════════════════════════════ */
footer { visibility: hidden; }
#MainMenu { visibility: hidden; }
[data-testid="stToolbarActions"] { display: none !important; }
[data-testid="stDecoration"] { display: none; }
[data-testid="stAppDeployButton"] { display: none; }

/* metric (Streamlit 기본 metric — 잔존 시 KT 톤) */
[data-testid="stMetricValue"] {
  font-family: "KT Flow", "Noto Sans KR", sans-serif !important;
  font-weight: 900 !important;
  color: var(--kt-ink) !important;
  font-variant-numeric: tabular-nums;
}
[data-testid="stMetricLabel"] {
  font-family: "Noto Sans KR", sans-serif !important;
  color: var(--kt-stone) !important;
  font-weight: 500 !important;
}

/* ═══════════════════════════════════════════════════════════════
   10. Mobile (≤ 768px)
   ═══════════════════════════════════════════════════════════════ */
@media (max-width: 768px) {
  html, body, .stApp { font-size: 14px !important; }
  .block-container {
    padding: 0.7rem 0.6rem !important;
    max-width: 100vw !important;
  }
  h1 { font-size: 1.25rem !important; }
  h2 { font-size: 1.1rem !important; }
  h3 { font-size: 1rem !important; }
  [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
  [data-testid="stDataFrame"] { font-size: 0.78rem; }
  [data-testid="stDataFrame"] th,
  [data-testid="stDataFrame"] td { padding: 4px 6px !important; }
  .stButton button { font-size: 0.85rem !important; padding: 0.45rem 0.85rem !important; }
  .kw-chip { font-size: 0.72rem !important; padding: 1px 8px !important; }
  .kt-kpi-value { font-size: 1.65rem !important; }
  .kt-kpi-card { min-height: 92px; padding: var(--s-4); }

  /* 표 전체 viewport 채우기 */
  [data-testid="stDataFrame"] {
    height: calc(100vh - 320px) !important;
    min-height: 420px !important;
    max-height: calc(100vh - 220px) !important;
  }
  [data-testid="stDataFrame"] > div,
  [data-testid="stDataFrame"] > div > div {
    height: 100% !important;
  }
}
@media (max-width: 480px) {
  html, body, .stApp { font-size: 13px !important; }
  .kt-kpi-value { font-size: 1.5rem !important; }
  [data-testid="stDataFrame"] { font-size: 0.72rem; }
}
</style>
"""
