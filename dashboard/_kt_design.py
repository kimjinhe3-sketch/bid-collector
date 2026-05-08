"""KT Engineering Design System — Streamlit 적용 (BIDLIVE Korea 대시보드).

리뉴얼 v3 — Editorial First.

이전 버전이 "Streamlit 위에 KT 토큰 페인트" 였던 문제를 해결하기 위해
정보 위계와 시각 위계를 처음부터 재설계.

원칙:
  1. 박스/카드/그림자/보더 최소화. 활자 위계로 영역 분리.
  2. Hero = 신문 1면 헤드라인. 거대한 수치 하나 + 짧은 부제 + 작은 메타.
  3. 색은 시맨틱 의무가 있을 때만 (위험·정보·필터·새로운·기본 액션). 데코 색 금지.
  4. 사이드바는 도구 패널. 섹션 사이 큰 divider 제거, 라벨로만 구분.
  5. 표는 페이지의 주역. 그 위 toolbar 는 가볍게.
"""

KT_CSS = """
<style>
@import url("https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&display=swap");

/* ─── KT Flow self-host ─── */
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
  --kt-red:       #FE2E36;
  --kt-red-hover: #E0252D;
  --kt-red-soft:  #FFEAEB;
  --kt-purple:    #AA50FF;
  --kt-purple-soft:#F3E8FF;
  --kt-blue:      #00A5FF;
  --kt-teal:      #00BEAC;
  --kt-amber:     #F59E0B;

  /* Mono — 8단계 */
  --c-ink:    #0F0F12;   /* 본문/제목 */
  --c-coal:   #2A2A2D;   /* 강한 secondary */
  --c-graphite:#4C4C4E;
  --c-stone:  #6E6E72;
  --c-silver: #A2A4A3;
  --c-mist:   #DCDCE0;
  --c-fog:    #EFEFF1;
  --c-cloud:  #F7F7F9;
  --c-paper:  #FFFFFF;

  --r-sm: 6px;
  --r-md: 8px;
  --r-lg: 12px;
  --r-pill: 999px;

  /* Legacy aliases */
  --bg: #FFFFFF; --bg-soft: #F7F7F9;
  --fg: #0F0F12; --fg-muted: #A2A4A3;
  --border: #DCDCE0; --border-strong: #A2A4A3;
  --accent: #FE2E36; --accent-hover: #E0252D; --accent-soft: #FFEAEB;
  --accent-number: #0F0F12;
  --link: #00A5FF;
  --tag-include-bg: rgba(0,165,255,0.10);
  --tag-include-text: #00A5FF;
  --tag-include-border: rgba(0,165,255,0.28);
  --tag-exclude-bg: #EFEFF1;
  --tag-exclude-text: #4C4C4E;
  --tag-exclude-border: #DCDCE0;
  --radius-sm: 6px; --radius: 8px; --radius-lg: 12px;
}

/* ═══════════════════════════════════════════════════════════════
   Reset / typography baseline
   ═══════════════════════════════════════════════════════════════ */
html, body, .stApp { background: var(--c-paper) !important; color: var(--c-ink); }

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
  letter-spacing: -0.005em;
}

/* Material Icons preserved (Streamlit 햄버거 등) */
.material-icons, .material-symbols-outlined, .material-symbols-rounded,
span[class*="material-icons"], span[class*="material-symbols"],
[data-testid="stIconMaterial"], [data-testid*="Icon"] > span {
  font-family: "Material Symbols Outlined", "Material Symbols Rounded",
               "Material Icons" !important;
  font-feature-settings: "liga" !important;
  font-variation-settings: "FILL" 0, "wght" 400, "GRAD" 0, "opsz" 24 !important;
  font-weight: normal !important; font-style: normal !important;
  line-height: 1 !important; letter-spacing: normal !important;
  text-transform: none !important; display: inline-block !important;
  white-space: nowrap !important; direction: ltr !important;
}

h1, h2, h3, h4 {
  font-family: "KT Flow", "Noto Sans KR", sans-serif !important;
  color: var(--c-ink) !important;
  letter-spacing: -0.018em !important;
}
p, .stMarkdown { color: var(--c-graphite); font-size: 0.9375rem; }
[data-testid="stCaptionContainer"] {
  color: var(--c-stone) !important; font-size: 0.8125rem !important;
}

/* 메인 컨테이너 — 여백 (DESIGN_SYSTEM 5-4) */
.block-container {
  padding-top: 1.5rem !important;
  padding-left: 2.5rem !important;
  padding-right: 2.5rem !important;
  max-width: 1480px;
}
@media (max-width: 768px) {
  .block-container {
    padding-left: 1rem !important;
    padding-right: 1rem !important;
    padding-top: 1rem !important;
  }
}

/* ═══════════════════════════════════════════════════════════════
   Page header — 컴팩트 한 줄. 신문 발행정보처럼.
   ═══════════════════════════════════════════════════════════════ */
.kt-pageheader {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.5rem 0 1.25rem 0;
  border-bottom: 1px solid var(--c-fog);
  margin-bottom: 2.25rem;
}
.kt-pageheader-title {
  font-family: "KT Flow", "Noto Sans KR", sans-serif;
  font-weight: 700;
  font-size: 1.0625rem;     /* 17px */
  color: var(--c-ink);
  letter-spacing: -0.012em;
  margin: 0;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.kt-pageheader-title::before {
  /* 작은 KT RED 마커 (brand statement) */
  content: "";
  width: 4px; height: 16px;
  background: var(--kt-red);
  border-radius: 1px;
  display: inline-block;
}
.kt-pageheader-status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-family: "KT Flow", "Noto Sans KR", sans-serif;
  font-size: 0.8125rem;
  color: var(--c-stone);
  font-weight: 500;
}
.kt-pageheader-status .kt-dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: var(--kt-teal);
  box-shadow: 0 0 0 0 rgba(0, 190, 172, 0.45);
  animation: ktPulse 2.4s cubic-bezier(0.66, 0, 0, 1) infinite;
}
@keyframes ktPulse {
  to { box-shadow: 0 0 0 8px rgba(0, 190, 172, 0); }
}
.kt-pageheader-status strong {
  color: var(--c-ink);
  font-variant-numeric: tabular-nums;
  font-weight: 700;
}

/* ═══════════════════════════════════════════════════════════════
   Hero stat block — "신문 헤드라인" 식. 거대한 숫자 하나가 주역.
   ═══════════════════════════════════════════════════════════════ */
.kt-stat {
  padding: 0 0 2.5rem 0;
  margin: 0 0 1.75rem 0;
  border-bottom: 1px solid var(--c-fog);
}
.kt-stat-eyebrow {
  font-family: "KT Flow", "Noto Sans KR", sans-serif;
  font-size: 0.6875rem;     /* 11px */
  font-weight: 700;
  color: var(--c-stone);
  letter-spacing: 0.18em;
  text-transform: uppercase;
  margin-bottom: 0.5rem;
}
.kt-stat-row {
  display: flex;
  align-items: flex-end;
  gap: 2rem;
  flex-wrap: wrap;
}
.kt-stat-number {
  display: flex;
  align-items: baseline;
  line-height: 0.95;
}
.kt-stat-num-value {
  font-family: "KT Flow", "Noto Sans KR", sans-serif;
  font-weight: 900;
  font-size: 5.5rem;        /* 88px — 진짜 헤드라인 */
  color: var(--c-ink);
  letter-spacing: -0.045em;
  font-variant-numeric: tabular-nums;
}
.kt-stat-num-unit {
  font-family: "KT Flow", "Noto Sans KR", sans-serif;
  font-weight: 700;
  font-size: 1.5rem;
  color: var(--c-stone);
  margin-left: 0.5rem;
}
.kt-stat-caption {
  font-family: "Noto Sans KR", sans-serif;
  font-size: 0.9375rem;
  color: var(--c-graphite);
  font-weight: 500;
  padding-bottom: 0.6rem;
}
.kt-stat-caption strong { color: var(--c-ink); font-weight: 700; }
.kt-stat-zero .kt-stat-num-value { color: var(--c-silver); }

/* Breakdown row — chip 형태로 그룹별 분포 */
.kt-stat-breakdown {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 0.75rem;
  align-items: center;
  margin-top: 1rem;
  font-family: "Noto Sans KR", sans-serif;
}
.kt-stat-bd-item {
  display: inline-flex;
  align-items: baseline;
  gap: 0.4rem;
  padding: 0.35rem 0.7rem 0.35rem 0.7rem;
  background: var(--c-cloud);
  border-radius: var(--r-md);
  font-size: 0.8125rem;
  color: var(--c-graphite);
  font-weight: 500;
}
.kt-stat-bd-item strong {
  font-family: "KT Flow", "Noto Sans KR", sans-serif;
  font-weight: 700;
  color: var(--c-ink);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.01em;
}
.kt-stat-bd-divider {
  width: 1px; height: 14px;
  background: var(--c-mist);
  margin: 0 0.25rem;
}
.kt-stat-bd-meta {
  font-size: 0.8125rem;
  color: var(--c-silver);
  font-weight: 500;
}
.kt-stat-bd-meta strong { color: var(--c-graphite); font-weight: 700; font-variant-numeric: tabular-nums; }

@media (max-width: 768px) {
  .kt-stat-num-value { font-size: 3.5rem; }
  .kt-stat-num-unit  { font-size: 1.125rem; }
  .kt-stat-row { gap: 1rem; }
}

/* ═══════════════════════════════════════════════════════════════
   Toolbar (segmented control + count + xlsx) — 표 위
   ═══════════════════════════════════════════════════════════════ */
.kt-toolbar {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.25rem 0 0.75rem 0;
  flex-wrap: wrap;
}
.kt-toolbar-meta {
  margin-left: auto;
  font-family: "Noto Sans KR", sans-serif;
  font-size: 0.8125rem;
  color: var(--c-stone);
}
.kt-toolbar-meta strong {
  color: var(--c-ink);
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

/* st.segmented_control 스타일 — 깔끔한 segmented selector */
[data-testid="stSegmentedControl"] {
  background: var(--c-fog) !important;
  padding: 3px !important;
  border-radius: var(--r-md) !important;
  border: none !important;
}
[data-testid="stSegmentedControl"] button {
  background: transparent !important;
  border: none !important;
  color: var(--c-graphite) !important;
  font-family: "KT Flow", "Noto Sans KR", sans-serif !important;
  font-weight: 600 !important;
  font-size: 0.8125rem !important;
  padding: 0.35rem 0.85rem !important;
  border-radius: var(--r-sm) !important;
  transition: all 0.15s ease !important;
}
[data-testid="stSegmentedControl"] button:hover {
  color: var(--c-ink) !important;
  background: rgba(255,255,255,0.5) !important;
}
[data-testid="stSegmentedControl"] button[aria-pressed="true"],
[data-testid="stSegmentedControl"] button[aria-checked="true"] {
  background: var(--c-paper) !important;
  color: var(--c-ink) !important;
  box-shadow: 0 1px 3px rgba(15,15,18,0.08), 0 0 0 1px var(--c-mist) inset !important;
}

/* ═══════════════════════════════════════════════════════════════
   Buttons — KT RED primary, 회색 outline secondary
   ═══════════════════════════════════════════════════════════════ */
.stButton > button {
  border-radius: var(--r-md) !important;
  border: 1px solid var(--c-mist) !important;
  background: var(--c-paper) !important;
  color: var(--c-ink) !important;
  font-family: "KT Flow", "Noto Sans KR", sans-serif !important;
  font-weight: 600 !important;
  font-size: 0.875rem !important;
  padding: 0.5rem 1rem !important;
  transition: all 0.15s ease !important;
  box-shadow: none !important;
}
.stButton > button:hover {
  border-color: var(--c-ink) !important;
  background: var(--c-cloud) !important;
}
.stButton > button:focus-visible {
  outline: 2px solid var(--kt-red) !important;
  outline-offset: 2px !important;
}
.stButton > button[kind="primary"],
.stButton > button[kind="primary"] *,
.stButton > button[kind="primary"] p,
.stButton > button[kind="primary"] span,
.stButton > button[kind="primary"] div {
  background: var(--kt-red) !important;
  border: 1px solid var(--kt-red) !important;
  color: #FFFFFF !important;
  -webkit-text-fill-color: #FFFFFF !important;
}
.stButton > button[kind="primary"] svg { fill: #FFFFFF !important; }
.stButton > button[kind="primary"]:hover,
.stButton > button[kind="primary"]:hover * {
  background: var(--kt-red-hover) !important;
  border-color: var(--kt-red-hover) !important;
}

/* xlsx 다운로드 — ghost */
[data-testid="stDownloadButton"] button {
  background: transparent !important;
  color: var(--c-stone) !important;
  border: 1px solid var(--c-mist) !important;
  padding: 4px 12px !important;
  font-family: "KT Flow", "Noto Sans KR", sans-serif !important;
  font-size: 0.75rem !important;
  font-weight: 600 !important;
  letter-spacing: 0.01em !important;
  min-height: 30px !important; height: 30px !important;
  border-radius: var(--r-sm) !important;
  box-shadow: none !important;
}
[data-testid="stDownloadButton"] button:hover {
  background: var(--c-ink) !important;
  color: #FFFFFF !important;
  border-color: var(--c-ink) !important;
}

/* ═══════════════════════════════════════════════════════════════
   Inputs / multiselect / slider
   ═══════════════════════════════════════════════════════════════ */
.stTextInput input, .stTextArea textarea,
.stDateInput input, .stNumberInput input,
.stSelectbox > div > div, .stMultiSelect > div > div {
  border-radius: var(--r-md) !important;
  border: 1px solid var(--c-mist) !important;
  background: var(--c-paper) !important;
  font-family: "Noto Sans KR", sans-serif !important;
  font-size: 0.875rem !important;
  color: var(--c-ink) !important;
}
.stTextInput input:focus, .stTextArea textarea:focus,
.stDateInput input:focus, .stNumberInput input:focus {
  border-color: var(--kt-red) !important;
  box-shadow: 0 0 0 3px var(--kt-red-soft) !important;
  outline: none !important;
}
/* Multiselect 태그 — KT BLUE (정보·필터) */
.stMultiSelect [data-baseweb="tag"], [data-baseweb="tag"] {
  background-color: rgba(0, 165, 255, 0.10) !important;
  color: var(--kt-blue) !important;
  border: 1px solid rgba(0, 165, 255, 0.28) !important;
  border-radius: var(--r-pill) !important;
  font-family: "Noto Sans KR", sans-serif !important;
  font-weight: 500 !important;
}
.stMultiSelect [data-baseweb="tag"] span, [data-baseweb="tag"] span {
  color: var(--kt-blue) !important;
  -webkit-text-fill-color: var(--kt-blue) !important;
}
.stMultiSelect [data-baseweb="tag"] svg, [data-baseweb="tag"] svg {
  fill: var(--kt-blue) !important; color: var(--kt-blue) !important;
}
.stSlider [role="slider"] {
  background: var(--kt-red) !important;
  border-color: var(--kt-red) !important;
}

/* kw-chip preview */
.kw-chip {
  display: inline-block;
  padding: 3px 10px;
  margin: 3px 4px 3px 0;
  background: rgba(0, 165, 255, 0.10);
  color: var(--kt-blue);
  border: 1px solid rgba(0, 165, 255, 0.28);
  border-radius: var(--r-pill);
  font-family: "Noto Sans KR", sans-serif;
  font-size: 0.75rem;
  font-weight: 500;
  line-height: 1.5;
}
.kw-chip.ex {
  background: var(--c-fog);
  color: var(--c-graphite);
  border-color: var(--c-mist);
}

/* ═══════════════════════════════════════════════════════════════
   Sidebar — KT BLACK 도구 패널.
   섹션 사이 hr divider 제거. 라벨 톤다운, 위계는 폰트 크기로.
   ═══════════════════════════════════════════════════════════════ */
[data-testid="stSidebar"] {
  background: #0A0A0C !important;       /* 순흑 #000 보다 살짝 부드러운 톤 */
  border-right: none !important;
  width: 16rem !important;
  min-width: 16rem !important;
}
[data-testid="stSidebar"] > div { background: #0A0A0C !important; }
[data-testid="stSidebar"] .block-container {
  padding: 1rem 1.1rem 2rem 1.1rem !important;
}

[data-testid="stSidebar"] *,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {
  color: rgba(255, 255, 255, 0.88) !important;
  -webkit-text-fill-color: rgba(255, 255, 255, 0.88) !important;
}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
[data-testid="stSidebar"] .stCaption,
[data-testid="stSidebar"] ::placeholder {
  color: rgba(255, 255, 255, 0.42) !important;
  -webkit-text-fill-color: rgba(255, 255, 255, 0.42) !important;
  font-size: 0.75rem !important;
}

/* hr divider 제거 — 섹션은 라벨로만 구분 */
[data-testid="stSidebar"] hr {
  border: none !important;
  height: 1px !important;
  background: transparent !important;
  margin: 0.75rem 0 !important;
}

/* h3 (섹션 라벨) — 작고 눈에 안 띄게, 하지만 스캔은 가능하게 */
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
  color: rgba(255,255,255,0.45) !important;
  font-family: "KT Flow", "Noto Sans KR", sans-serif !important;
  font-size: 0.6875rem !important;
  font-weight: 700 !important;
  text-transform: uppercase;
  letter-spacing: 0.18em;
  margin: 1.25rem 0 0.6rem 0 !important;
}

/* widget 라벨 — 흰색이지만 작고 가벼움 */
[data-testid="stSidebar"] [data-testid="stWidgetLabel"],
[data-testid="stSidebar"] label {
  color: rgba(255,255,255,0.72) !important;
  font-family: "Noto Sans KR", sans-serif !important;
  font-size: 0.8125rem !important;
  font-weight: 500 !important;
}

/* glass inputs */
[data-testid="stSidebar"] input,
[data-testid="stSidebar"] textarea,
[data-testid="stSidebar"] [data-baseweb="input"] > div,
[data-testid="stSidebar"] [data-baseweb="select"] > div {
  background: rgba(255, 255, 255, 0.05) !important;
  border: 1px solid rgba(255, 255, 255, 0.12) !important;
  color: #FFFFFF !important;
  -webkit-text-fill-color: #FFFFFF !important;
  border-radius: var(--r-md) !important;
  font-size: 0.875rem !important;
}
[data-testid="stSidebar"] input:focus,
[data-testid="stSidebar"] textarea:focus {
  border-color: var(--kt-red) !important;
  background: rgba(255, 255, 255, 0.09) !important;
  box-shadow: 0 0 0 2px rgba(254, 46, 54, 0.30) !important;
}

/* sidebar buttons — secondary glass, primary KT RED */
[data-testid="stSidebar"] .stButton > button {
  background: rgba(255, 255, 255, 0.06) !important;
  border: 1px solid rgba(255, 255, 255, 0.14) !important;
  color: #FFFFFF !important;
  font-weight: 600 !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
  background: rgba(255, 255, 255, 0.12) !important;
  border-color: rgba(255, 255, 255, 0.28) !important;
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

/* sidebar multiselect tag — KT BLUE on dark */
[data-testid="stSidebar"] [data-baseweb="tag"] {
  background-color: rgba(0, 165, 255, 0.16) !important;
  color: #5FCBFF !important;
  border: 1px solid rgba(0, 165, 255, 0.36) !important;
}
[data-testid="stSidebar"] [data-baseweb="tag"] span {
  color: #5FCBFF !important; -webkit-text-fill-color: #5FCBFF !important;
}
[data-testid="stSidebar"] [data-baseweb="tag"] svg {
  fill: #5FCBFF !important; color: #5FCBFF !important;
}

[data-testid="stSidebar"] .stSlider [role="slider"] { background: var(--kt-red) !important; }
[data-testid="stSidebar"] .stSlider [data-baseweb="slider"] > div > div { background: var(--kt-red) !important; }

[data-testid="stSidebar"] [data-baseweb="checkbox"] [aria-checked="true"] > div {
  background: var(--kt-red) !important;
  border-color: var(--kt-red) !important;
}

[data-testid="stSidebar"] .kw-chip {
  background: rgba(0, 165, 255, 0.14);
  color: #5FCBFF;
  border-color: rgba(0, 165, 255, 0.32);
}
[data-testid="stSidebar"] .kw-chip.ex {
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.65);
  border-color: rgba(255, 255, 255, 0.16);
}

[data-testid="stSidebar"] [data-testid="stExpander"] {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: var(--r-md);
}

/* sidebar 브랜드 영역 — 컴팩트 */
.kt-sidebar-brand {
  padding: 0.25rem 0 0.25rem 0;
  margin: 0;
  display: flex;
  align-items: center;
}
.kt-sidebar-brand img { height: 20px; width: auto; opacity: 0.92; }
.kt-sidebar-product {
  font-family: "KT Flow", "Noto Sans KR", sans-serif;
  font-size: 0.625rem;
  font-weight: 700;
  letter-spacing: 0.22em;
  color: rgba(255, 255, 255, 0.32);
  padding: 0.25rem 0 1rem 0;
  margin: 0 0 0.5rem 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

/* sidebar 햄버거 가시성 */
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapsedControl"],
[data-testid="stSidebarCollapseButton"],
[data-testid="stExpandSidebarButton"],
[data-testid="baseButton-headerNoPadding"] {
  visibility: visible !important; display: inline-flex !important;
  opacity: 1 !important; pointer-events: auto !important;
  min-width: 32px !important; min-height: 32px !important;
  align-items: center !important; justify-content: center !important;
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
    background: var(--c-paper) !important;
    border: 1px solid var(--kt-red) !important;
    border-radius: var(--r-sm) !important;
    box-shadow: 0 2px 6px rgba(254, 46, 54, 0.20) !important;
  }
  [data-testid="stExpandSidebarButton"] svg,
  [data-testid="stExpandSidebarButton"] [data-testid="stIconMaterial"] {
    color: var(--kt-red) !important;
  }
  [data-testid="stHeader"] { z-index: 999 !important; }
}

/* ═══════════════════════════════════════════════════════════════
   Table toolbar — 표 위 가벼운 한 줄. 카운트 + xlsx 다운.
   ═══════════════════════════════════════════════════════════════ */
.st-key-bidtable_titlebar {
  background: transparent !important;
  border: none !important;
  padding: 0.5rem 0.25rem !important;
  margin: 0 0 0.25rem 0 !important;
  min-height: 36px;
}
.st-key-bidtable_titlebar [data-testid="stElementContainer"] {
  margin: 0 !important; padding: 0 !important;
}
.st-key-bidtable_titlebar .tbl-title {
  font-family: "Noto Sans KR", sans-serif;
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--c-stone);
  line-height: 1.3;
}
.st-key-bidtable_titlebar .tbl-title b {
  color: var(--c-ink);
  font-family: "KT Flow", "Noto Sans KR", sans-serif;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
[data-testid="stDataFrame"] {
  border-radius: var(--r-lg);
  overflow: hidden;
  border: 1px solid var(--c-mist);
  background: var(--c-paper);
}
[data-testid="stDataFrame"] a {
  text-decoration: none;
  color: var(--kt-blue) !important;
  font-weight: 600;
}
[data-testid="stDataFrame"] a:hover { text-decoration: underline; }
[data-testid="stDataFrame"] [role="cell"][data-testid*="Number"],
[data-testid="stDataFrame"] [data-col-index] [style*="text-align: right"] {
  color: var(--c-ink) !important;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
[data-testid="stStatus"] { border-radius: var(--r-md) !important; }
[data-testid="stAlert"] [role="alert"] {
  border-radius: var(--r-md) !important;
  font-family: "Noto Sans KR", sans-serif !important;
}

/* ═══════════════════════════════════════════════════════════════
   Hide Streamlit chrome
   ═══════════════════════════════════════════════════════════════ */
footer { visibility: hidden; }
#MainMenu { visibility: hidden; }
[data-testid="stToolbarActions"] { display: none !important; }
[data-testid="stDecoration"] { display: none; }
[data-testid="stAppDeployButton"] { display: none; }

[data-testid="stMetricValue"] {
  font-family: "KT Flow", "Noto Sans KR", sans-serif !important;
  font-weight: 900 !important;
  color: var(--c-ink) !important;
  font-variant-numeric: tabular-nums;
}
[data-testid="stMetricLabel"] {
  font-family: "Noto Sans KR", sans-serif !important;
  color: var(--c-stone) !important;
  font-weight: 500 !important;
}

/* ═══════════════════════════════════════════════════════════════
   Mobile
   ═══════════════════════════════════════════════════════════════ */
@media (max-width: 768px) {
  html, body, .stApp { font-size: 14px !important; }
  .kt-pageheader { flex-direction: column; align-items: flex-start; gap: 0.5rem; }
  [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
  [data-testid="stDataFrame"] { font-size: 0.78rem; }
  [data-testid="stDataFrame"] th,
  [data-testid="stDataFrame"] td { padding: 4px 6px !important; }
  .stButton button { font-size: 0.85rem !important; padding: 0.45rem 0.85rem !important; }
  .kw-chip { font-size: 0.72rem !important; padding: 1px 8px !important; }

  [data-testid="stDataFrame"] {
    height: calc(100vh - 360px) !important;
    min-height: 420px !important;
    max-height: calc(100vh - 220px) !important;
  }
  [data-testid="stDataFrame"] > div,
  [data-testid="stDataFrame"] > div > div { height: 100% !important; }
}
@media (max-width: 480px) {
  html, body, .stApp { font-size: 13px !important; }
  [data-testid="stDataFrame"] { font-size: 0.72rem; }
}
</style>
"""
