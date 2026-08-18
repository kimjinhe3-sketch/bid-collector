# -*- coding: utf-8 -*-
"""일일 다이제스트 v2 — 그룹 세션형 이미지 메일 (2026-08-18 리디자인).

구성: 머리띠(CI) + KPI 밴드(전그룹 통합조회 링크) + 그룹 섹션 7개(상위3+신규1+마감임박1)
      + CTA. 각 블록을 Pretendard 로 렌더한 PNG 이미지로 만들어 CID 임베드 발송.

데이터: DATABASE_URL(psycopg2) 우선, 없으면 SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY (REST, 로컬 테스트용)
렌더:   playwright(chromium). 실패 시 None 반환 → 호출측이 텍스트 HTML 로 폴백 발송.

키워드 정리안(2026-08-18 확정): 그룹 7종 + 전역 제외 38종 + 통합망 전용 제외(데이터센터).
"""
from __future__ import annotations

import html as html_mod
import base64
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
CI_PNG = ROOT / "assets" / "ci_white.png"

SITE_URL = (os.environ.get("SITE_URL") or os.environ.get("CLOUDTYPE_URL")
            or "https://port-next-bidlive-korea-web-mozlrrj98331a064.sel3.cloudtype.app").rstrip("/")
SITE_BIDS = SITE_URL + "/bids"

FONT = "Pretendard,'Malgun Gothic','Apple SD Gothic Neo',sans-serif"
IMG_W = 624                   # 블록 이미지 폭 = 콘텐츠 600 + 좌우 여백 12×2 (다크모드 대비 여백 굽기)
EOK = 100_000_000
MIN_PRICE = 10 * EOK          # 리포트 대상: 10억 이상
TITLE_MAX = 28                # 사업명 말줄임
ORG_MAX = 12                  # 발주처명 말줄임

# ── 키워드 정리안 ──────────────────────────────────────────
EXCLUDE = ["교복", "급식", "의료기기", "의약품", "가구", "도시락", "여행", "축제", "행사대행", "행사 대행",
           "홍보", "공연", "숙박", "인쇄", "연구용역", "학술", "실험실습", "폐기물", "하수관로", "포장공사",
           "준설", "가로수", "차량", "보험", "셔틀", "경비", "방역", "청소", "버스", "임차", "감리",
           "배관망", "식당", "위탁", "운영", "대행", "재건축", "정비사업", "HVDC"]

GROUPS = [  # (그룹명, 포함, 제목 제외, 발주처 제외) — 구체적 → 포괄 (한 공고는 첫 매칭 그룹에만)
    ("데이터센터",    ["데이터센터", "DC", "전산센터", "전산실", "서버실"], [], []),
    ("에너지/환경",   ["태양광", "생태공장", "탄소"], ["터빈"], ["국제협력단"]),
    ("장비납품",      ["태블릿", "단말", "항온항습", "UPS", "무정전"], [], []),
    ("통합망",        ["정보통신망", "통신망", "행정망", "통합망", "교육망", "스쿨넷", "IPT",
                      "사업자 선정", "사업자선정"], ["데이터센터"], []),
    ("통신/네트워크", ["네트워크", "CCTV", "5G", "LTE", "특화망", "통신구"], [], []),
    ("MEP공사",      ["전기공사", "소방시설", "소방공사", "기계설비", "통신공사", "154kV"], [], []),
    ("그외",          ["건축", "신축", "인프라"], [], []),
]

# 메일 제목 헤드라인 제한: '그외' 그룹·해외 사업은 대표 사업명으로 뽑지 않음
HEADLINE_SKIP_GROUPS = {"그외"}
HEADLINE_SKIP_KW = ["해외", "국외", "모로코", "미국", "일본", "중국", "베트남", "인도네시아",
                    "필리핀", "캄보디아", "라오스", "몽골", "우즈베키", "카자흐", "아프리카",
                    "중남미", "유럽", "텍사스", "ODA", "KOICA"]
ORDER = [g for g, _, _, _ in GROUPS]
DISPLAY_ORDER = ["통합망", "통신/네트워크", "MEP공사", "데이터센터", "에너지/환경", "장비납품", "그외"]
BAND = [g for g in DISPLAY_ORDER if g != "그외"]


def kst_now() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=9)


# ── 데이터 로드 ────────────────────────────────────────────
COLS = "id,source,bid_no,title,org_name,region,bid_type,estimated_price,open_date,close_date,detail_url"


def fetch_rows() -> list[dict]:
    url = os.environ.get("DATABASE_URL", "")
    if url:
        return _fetch_pg(url)
    return _fetch_rest()


def _fetch_pg(url: str) -> list[dict]:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    if "sslmode=" not in url:
        url = f"{url}{'&' if '?' in url else '?'}sslmode=require"
    conn = psycopg2.connect(url, cursor_factory=RealDictCursor)
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {COLS} FROM bid_announcements")
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def _fetch_rest() -> list[dict]:
    """로컬 테스트용 — Supabase REST (SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY)."""
    import requests
    base = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    hdr = {"apikey": key, "Authorization": f"Bearer {key}"}
    rows, offset = [], 0
    while True:
        r = requests.get(f"{base}/rest/v1/bid_announcements",
                         headers={**hdr, "Range-Unit": "items", "Range": f"{offset}-{offset + 999}"},
                         params={"select": COLS, "order": "id.asc"}, timeout=30)
        r.raise_for_status()
        chunk = r.json()
        rows.extend(chunk)
        if len(chunk) < 1000:
            return rows
        offset += 1000


# ── 정규화·중복제거·그룹 매칭 ──────────────────────────────
def norm_date(s) -> str | None:
    if not s:
        return None
    t = str(s).strip()
    if re.match(r"^\d{8}", t):
        return f"{t[:4]}-{t[4:6]}-{t[6:8]}"
    m = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", t)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return None


def _base_no(bid_no: str) -> str:
    m = re.match(r"^(.*)-(\d{1,3})$", bid_no)
    return m.group(1) if m else bid_no


def _keep_latest(group: list[dict]) -> dict:
    return sorted(group, key=lambda x: (str(x.get("open_date") or ""), x["bid_no"], x["id"]), reverse=True)[0]


def _matches(title: str, kws: list[str]) -> bool:
    t = title.lower()
    return any(k.lower() in t for k in kws)


def build_digest_data(today: date | None = None) -> dict:
    today = today or kst_now().date()
    today_s = today.isoformat()
    rows = fetch_rows()

    active = []
    for r in rows:
        cd = norm_date(r.get("close_date"))
        if cd and cd >= today_s:
            r["close_norm"] = cd
            active.append(r)

    # 중복 제거: 차수(-NN) → 동일 (source,제목,기관,업종,금액) 재공고
    g1 = defaultdict(list)
    for r in active:
        g1[(r["source"], _base_no(r["bid_no"]))].append(r)
    stage1 = [_keep_latest(v) for v in g1.values()]
    g2 = defaultdict(list)
    for r in stage1:
        key = (r["source"], (r["title"] or "").strip(), r.get("org_name") or "",
               r.get("bid_type") or "", r.get("estimated_price") if r.get("estimated_price") is not None else -1)
        g2[key].append(r)
    stage2 = [_keep_latest(v) for v in g2.values()]

    # 3단계: 유사 제목 중복 — 같은 (소스·기관·마감) 에서 제목이 "단어 1개 추가/삭제" 차이면
    # 같은 사업 (예: "수중데이터센터 실증모델 [시작품] AI 인프라"). 단어가 "바뀐" 경우는
    # 별개 공고 (분리발주 전기/통신/소방, 다른 학교·지구 등) — 병합 금지.
    from collections import Counter

    def _digits(t: str) -> list[str]:
        return re.findall(r"\d+", t)

    def _tokens(t: str) -> Counter:
        return Counter(re.sub(r"[\[\]()【】,·]", " ", t).split())

    def _near_dup(a: str, b: str) -> bool:
        if _digits(a) != _digits(b):
            return False
        ta, tb = _tokens(a), _tokens(b)
        diff = sum(((ta - tb) + (tb - ta)).values())
        return diff <= 1  # 0=공백차이만, 1=단어 하나 추가/삭제

    g3 = defaultdict(list)
    for r in stage2:
        g3[(r["source"], r.get("org_name") or "", r["close_norm"])].append(r)
    deduped = []
    for group in g3.values():
        clusters: list[list[dict]] = []
        for r in sorted(group, key=lambda x: x["title"]):
            for c in clusters:
                if _near_dup(r["title"], c[0]["title"]):
                    c.append(r)
                    break
            else:
                clusters.append([r])
        deduped.extend(_keep_latest(c) for c in clusters)

    def dd_of(r):
        return (date.fromisoformat(r["close_norm"]) - today).days

    counts, result, assigned, matched_all = {}, {}, set(), []
    for gname, kws, g_exc, g_org_exc in GROUPS:
        pool = []
        for r in deduped:
            if r["id"] in assigned:
                continue
            title = r["title"] or ""
            if not _matches(title, kws):
                continue
            if _matches(title, EXCLUDE):
                continue
            if g_exc and _matches(title, g_exc):
                continue
            if g_org_exc and _matches(r.get("org_name") or "", g_org_exc):
                continue
            if (r.get("estimated_price") or 0) < MIN_PRICE:
                continue
            pool.append(r)
        for r in pool:
            assigned.add(r["id"])
        matched_all.extend((gname, r) for r in pool)
        counts[gname] = len(pool)

        by_price = sorted(pool, key=lambda x: x.get("estimated_price") or 0, reverse=True)
        top3 = by_price[:3]
        top3_ids = {r["id"] for r in top3}
        new_pool = [r for r in by_price if r["id"] not in top3_ids and norm_date(r.get("open_date")) == today_s]
        new_pick = new_pool[0] if new_pool else None
        closing_pool = [r for r in by_price if r["id"] not in top3_ids and dd_of(r) <= 1
                        and (new_pick is None or r["id"] != new_pick["id"])]
        closing_pick = closing_pool[0] if closing_pool else None

        picks = [(r, None) for r in top3]
        if new_pick is not None:
            picks.append((new_pick, "new"))
        if closing_pick is not None:
            picks.append((closing_pick, "closing"))

        result[gname] = [{
            "title": r["title"], "org": r.get("org_name") or "-",
            "price_eok": round((r.get("estimated_price") or 0) / EOK, 1),
            "close": r["close_norm"], "dday": dd_of(r),
            "bid_type": r.get("bid_type") or "", "tag": tag,
            "url": r.get("detail_url") or "",
        } for r, tag in picks]

    # matched_all = [(그룹명, row)] — 제목 헤드라인은 '그외'·해외 사업을 피해서 뽑는다
    news_all = sorted([(g, r) for g, r in matched_all if norm_date(r.get("open_date")) == today_s],
                      key=lambda x: x[1].get("estimated_price") or 0, reverse=True)
    closings_all = sorted([(g, r) for g, r in matched_all if dd_of(r) <= 1],
                          key=lambda x: x[1].get("estimated_price") or 0, reverse=True)

    def headline_ok(gname, r, strict):
        if _matches(r["title"] or "", HEADLINE_SKIP_KW):
            return False
        return not (strict and gname in HEADLINE_SKIP_GROUPS)

    def pick_top(cands):
        # 1순위: 그외·해외 제외 / 2순위: 해외만 제외 / 3순위: 아무거나
        for strict in (True, False):
            for g, r in cands:
                if headline_ok(g, r, strict):
                    return r
        return cands[0][1] if cands else None

    def brief(r):
        return {"title": r["title"], "price_eok": round((r.get("estimated_price") or 0) / EOK, 1)}

    news_top = pick_top(news_all)
    closings_top = pick_top(closings_all)

    return {
        "today": today_s,
        "counts": counts,
        "sections": result,
        "meta": {
            "new_total": len(news_all), "closing_total": len(closings_all),
            "new_top": brief(news_top) if news_top else None,
            "closing_top": brief(closings_top) if closings_top else None,
        },
    }


# ── 링크 ──────────────────────────────────────────────────
def group_link(g: str) -> str:
    kws = next((k for n, k, _, _ in GROUPS if n == g), [])
    exc = next((e for n, _, e, _ in GROUPS if n == g), [])
    url = f"{SITE_BIDS}?active=1&amin=10&inc=" + quote(",".join(kws))
    if exc:
        url += "&exc=" + quote(",".join(exc))
    return url


def all_link() -> str:
    """KPI 밴드: 전 그룹 키워드 통합 조회 (그룹 제외 미적용)."""
    seen, kws = set(), []
    for _, ks, _, _ in GROUPS:
        for k in ks:
            if k not in seen:
                seen.add(k)
                kws.append(k)
    return f"{SITE_BIDS}?active=1&amin=10&inc=" + quote(",".join(kws))


# ── 블록 HTML ─────────────────────────────────────────────
def _fmt_eok(p: float) -> str:
    return f"{p:,.0f}억" if p >= 100 else f"{p:,.1f}억"


def _trunc(s: str, n: int) -> str:
    s = s.strip()
    return s if len(s) <= n else s[:n].rstrip() + "…"


def _dday_inline(dd: int) -> str:
    if dd == 0:
        return '<span style="color:#d03b3b;">&#9632; D-DAY</span>'
    if dd <= 2:
        return f'<span style="color:#46566f;"><span style="color:#fab219;">&#9650;</span> D-{dd}</span>'
    return f'<span style="color:#46566f;">D-{dd}</span>'


TAG_PILL = {
    "new":     '<span style="background:#e8f7f1;color:#1baf7a;font-size:12px;border-radius:4px;padding:1px 6px;margin-right:6px;">신규</span>',
    "closing": '<span style="background:#fdecec;color:#d03b3b;font-size:12px;border-radius:4px;padding:1px 6px;margin-right:6px;">마감임박</span>',
}


def _rounded(inner: str, *, bg: str, border: str | None = None, radius: int = 14,
             pad: str = "0", arc: str = "6%", inset: str = "0,0,0,0",
             width: int = 600) -> str:
    """라운드 컨테이너 하이브리드 — 아웃룩(워드 엔진)은 VML roundrect 로 둥근 모서리를
    그리고, 그 외 클라이언트는 CSS border-radius 를 쓴다. (텍스트 메일용)"""
    css = f"background:{bg};border-radius:{radius}px;padding:{pad};"
    if border:
        css += f"border:1px solid {border};"
    stroke = f'strokecolor="{border}" strokeweight="1px"' if border else 'stroked="f"'
    return (
        f'<!--[if mso]>'
        f'<v:roundrect xmlns:v="urn:schemas-microsoft-com:vml" arcsize="{arc}" '
        f'fillcolor="{bg}" {stroke} style="width:{width}px;">'
        f'<v:textbox inset="{inset}" style="mso-fit-shape-to-text:true">'
        f'<![endif]-->'
        f'<!--[if !mso]><!-- -->'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:separate;">'
        f'<tr><td style="{css}">'
        f'<!--<![endif]-->'
        f'{inner}'
        f'<!--[if !mso]><!-- --></td></tr></table><!--<![endif]-->'
        f'<!--[if mso]></v:textbox></v:roundrect><![endif]-->')


def _row_html(r: dict, last: bool) -> str:
    border = "" if last else "border-bottom:1px solid #e6ecf5;"
    title_full = html_mod.escape(r["title"])
    org_full = html_mod.escape(r["org"])
    org_disp = html_mod.escape(_trunc(r["org"], ORG_MAX))
    link = html_mod.escape(r.get("url") or SITE_BIDS)
    pill = TAG_PILL.get(r.get("tag") or "", "")
    title_disp = html_mod.escape(_trunc(r["title"], TITLE_MAX - (5 if pill else 0)))
    return (f'<tr><td style="padding:7px 0;{border}font-family:{FONT};font-size:14px;'
            f'line-height:1.45;white-space:nowrap;">{pill}'
            f'<a href="{link}" title="{title_full}" style="font-weight:400;color:#0f1f38;text-decoration:none;">{title_disp}</a>'
            f'<span title="{org_full}" style="font-size:12px;color:#8592a6;"> · {org_disp}</span></td>'
            f'<td align="right" style="padding:7px 0 7px 12px;{border}white-space:nowrap;vertical-align:top;'
            f'font-family:{FONT};font-size:14px;">'
            f'<span style="font-weight:400;color:#0f1f38;">{_fmt_eok(r["price_eok"])}</span>'
            f'<span style="font-size:12px;color:#8592a6;"> · </span>'
            f'<span style="font-size:12px;">{_dday_inline(r["dday"])}</span></td></tr>')


def _section_card(g: str, data: dict, hybrid: bool = False) -> str:
    rows = data["sections"][g]
    n = data["counts"][g]
    body = "".join(_row_html(r, i == len(rows) - 1) for i, r in enumerate(rows))
    if not rows:
        body = (f'<tr><td style="padding:10px 0;font-family:{FONT};font-size:13px;color:#8592a6;">'
                f'오늘 기준 10억 이상 공고가 없습니다</td></tr>')
    header_band = (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:separate;margin-bottom:2px;">'
        f'<tr><td style="background:#e8f1fc;border-left:4px solid #2a78d6;border-radius:7px;padding:6px 12px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;"><tr>'
        f'<td style="font-family:{FONT};font-size:16px;font-weight:800;color:#1c5cab;">{html_mod.escape(g)}</td>'
        f'<td align="right" style="font-family:{FONT};font-size:12px;font-weight:700;white-space:nowrap;">'
        f'<a href="{group_link(g)}" style="color:#2a78d6;text-decoration:none;">{n}건 전체 &#8594;</a></td>'
        f'</tr></table></td></tr></table>')
    rows_table = (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">'
        f'<tr><td style="padding:0 12px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">{body}</table>'
        f'</td></tr></table>')
    if hybrid:
        return _rounded(header_band + rows_table, bg="#ffffff", border="#e3eaf4",
                        radius=14, pad="10px 16px 6px", arc="5%", inset="16px,10px,16px,6px")
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:separate;">'
            f'<tr><td style="background:#ffffff;border:1px solid #e3eaf4;border-radius:14px;'
            f'padding:10px 16px 6px;box-shadow:0 1px 2px rgba(15,31,56,.05);">'
            f'{header_band}{rows_table}'
            f'</td></tr></table>')


def _header_card(data: dict, hybrid: bool = False) -> str:
    total = sum(data["counts"].values())
    d = date.fromisoformat(data["today"])
    wd = "월화수목금토일"[d.weekday()]
    if hybrid:
        # 텍스트 메일: 이미지(로고) 사용 불가 — 워드마크를 텍스트로 대체
        logo = (f'<div style="font-family:{FONT};font-size:13px;font-weight:700;color:#ffffff;'
                f'letter-spacing:0.02em;margin-bottom:6px;">kt engineering</div>')
    else:
        ci_b64 = base64.b64encode(CI_PNG.read_bytes()).decode()
        logo = (f'<img src="data:image/png;base64,{ci_b64}" height="15" alt="kt engineering" '
                f'style="display:block;border:0;height:15px;width:auto;margin-bottom:7px;">')
    inner = (f'{logo}'
             f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;"><tr>'
             f'<td style="font-family:{FONT};font-size:19px;font-weight:700;color:#ffffff;">공공입찰 일일 리포트</td>'
             f'<td align="right" style="font-family:{FONT};font-size:12px;font-weight:500;color:#ffffff;white-space:nowrap;vertical-align:bottom;">'
             f'{data["today"]} {wd} · 10억&#8593; {total}건</td>'
             f'</tr></table>')
    if hybrid:
        return _rounded(inner, bg="#2a78d6", radius=14, pad="12px 18px 13px",
                        arc="18%", inset="18px,12px,18px,13px")
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:separate;">'
            f'<tr><td style="background:#2a78d6;background-image:linear-gradient(105deg,#1c5cab 0%,#2a78d6 58%,#3f8ce4 100%);'
            f'border-radius:14px;padding:12px 18px 13px;">'
            f'{inner}</td></tr></table>')


def _band_card(data: dict, hybrid: bool = False) -> str:
    cells = ""
    for i, g in enumerate(BAND):
        sep = "border-left:1px solid #e6ecf5;" if i else ""
        cells += (f'<td width="16%" align="center" style="padding:1px 4px;{sep}">'
                  f'<div style="font-family:{FONT};font-size:12px;font-weight:600;color:#8592a6;white-space:nowrap;">{html_mod.escape(g.replace("/", "·"))}</div>'
                  f'<div style="font-family:{FONT};font-size:17px;font-weight:700;color:#0f1f38;line-height:1.35;">{data["counts"][g]}</div>'
                  f'</td>')
    inner = (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
             f'style="border-collapse:collapse;"><tr>{cells}</tr></table>')
    if hybrid:
        return _rounded(inner, bg="#ffffff", border="#e3eaf4", radius=14,
                        pad="9px 6px", arc="22%", inset="6px,9px,6px,9px")
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:separate;">'
            f'<tr><td style="background:#ffffff;border:1px solid #e3eaf4;border-radius:14px;padding:9px 6px;'
            f'box-shadow:0 1px 2px rgba(15,31,56,.05);">'
            f'{inner}</td></tr></table>')


def _cta_card(hybrid: bool = False) -> str:
    if hybrid:
        # 아웃룩: VML 라운드 버튼 (href 직접 지원) / 그 외: CSS 버튼
        return (
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">'
            f'<tr><td align="center" style="padding:4px 0 6px;">'
            f'<!--[if mso]>'
            f'<v:roundrect xmlns:v="urn:schemas-microsoft-com:vml" href="{SITE_BIDS}" '
            f'arcsize="28%" fillcolor="#2a78d6" stroked="f" '
            f'style="height:38px;width:200px;v-text-anchor:middle;">'
            f'<center style="color:#ffffff;font-family:{FONT};font-size:13px;font-weight:700;">대시보드 전체 보기</center>'
            f'</v:roundrect>'
            f'<![endif]-->'
            f'<!--[if !mso]><!-- -->'
            f'<a href="{SITE_BIDS}" style="display:inline-block;background:#2a78d6;'
            f'background-image:linear-gradient(105deg,#1c5cab 0%,#2a78d6 58%,#3f8ce4 100%);color:#ffffff;'
            f'font-family:{FONT};font-size:13px;font-weight:700;text-decoration:none;padding:10px 34px;border-radius:10px;">'
            f'대시보드 전체 보기</a>'
            f'<!--<![endif]-->'
            f'</td></tr></table>')
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">'
            f'<tr><td align="center" style="padding:4px 0 6px;">'
            f'<a href="{SITE_BIDS}" style="display:inline-block;background:#2a78d6;'
            f'background-image:linear-gradient(105deg,#1c5cab 0%,#2a78d6 58%,#3f8ce4 100%);color:#ffffff;'
            f'font-family:{FONT};font-size:13px;font-weight:700;text-decoration:none;padding:10px 34px;border-radius:10px;">'
            f'대시보드 전체 보기</a></td></tr></table>')


def build_blocks(data: dict) -> list[dict]:
    """[{name, html, link}] — 렌더·조립 공용 블록 목록."""
    blocks = [
        {"name": "b00_header", "html": _header_card(data), "link": SITE_BIDS},
        {"name": "b01_band", "html": _band_card(data), "link": all_link()},
    ]
    for i, g in enumerate(DISPLAY_ORDER):
        blocks.append({"name": f"b1{i}_{re.sub(r'[^0-9A-Za-z가-힣]', '_', g)}",
                       "html": _section_card(g, data), "link": group_link(g)})
    blocks.append({"name": "b90_cta", "html": _cta_card(), "link": SITE_BIDS})
    return blocks


# ── 제목 (A안) ────────────────────────────────────────────
def subject_line(data: dict) -> str:
    d = date.fromisoformat(data["today"])
    dstr = f"{d.month}/{d.day}"
    meta = data["meta"]
    n_cl = meta.get("closing_total") or 0
    top_n, top_c = meta.get("new_top"), meta.get("closing_top")
    if top_n:
        head = f"{_trunc(top_n['title'], 14)} {top_n['price_eok']:,.0f}억 신규"
    elif top_c:
        head = f"{_trunc(top_c['title'], 14)} {top_c['price_eok']:,.0f}억 D-1"
    else:
        head = "관심분야 진행 현황"
    return f"입찰 {dstr} | {head} · 마감임박 {n_cl}건"


# ── 이미지 렌더 (playwright) ───────────────────────────────
def render_blocks(blocks: list[dict]) -> dict[str, bytes] | None:
    """블록별 PNG 렌더. 실패 시 None (호출측이 텍스트 폴백).

    블록 사이 간격·좌우 여백을 이미지 안에 구워 넣는다 — 메일에서 이미지를 틈 없이
    쌓으면 전체가 연속된 밝은 지면이 되어 다크모드가 사이를 검게 칠할 수 없다.
    (첫 블록은 상단 10px, 마지막 블록은 하단 18px, 나머지는 하단 10px 여백 포함)
    """
    import tempfile
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    wrap = ('<!DOCTYPE html><html><head><meta charset="utf-8"><style>'
            'body{{margin:0;background:#f3f7fc;}}'
            '#cap{{width:{w}px;box-sizing:border-box;background:#f3f7fc;'
            'padding:{pt}px 12px {pb}px;}}'
            '</style></head><body><div id="cap">{inner}</div></body></html>')
    footer_html = (
        f'<div style="font-family:{FONT};font-size:12px;color:#8592a6;line-height:1.7;'
        f'text-align:center;padding-top:2px;">'
        f'공공입찰 수집 시스템 · 평일 오전 8시 발송 · 대시보드 바로가기 &#8594;</div>')

    try:
        images: dict[str, bytes] = {}
        footer_segs: list[dict] = []
        with tempfile.TemporaryDirectory() as td, sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 680, "height": 400}, device_scale_factor=2)
            for i, b in enumerate(blocks):
                pt = 10 if i == 0 else 0
                pb = 10 if i == len(blocks) - 1 else 10
                f = Path(td) / (b["name"] + ".html")
                f.write_text(wrap.format(inner=b["html"], w=IMG_W, pt=pt, pb=pb), encoding="utf-8")
                page.goto(f.as_uri())
                page.wait_for_timeout(120)
                images[b["name"]] = page.locator("#cap").screenshot()

            # ── 푸터: 통짜 1장 (조각 분할은 아웃룩 DPI 반올림 균열 유발 → 폐기) ──
            f = Path(td) / "footer.html"
            f.write_text(wrap.format(inner=footer_html, w=IMG_W, pt=0, pb=16), encoding="utf-8")
            page.goto(f.as_uri())
            page.wait_for_timeout(120)
            images["b99_footer"] = page.locator("#cap").screenshot()
            footer_segs.append({"cid": "b99_footer", "w": IMG_W, "kind": "dash"})
            browser.close()
        return images, footer_segs
    except Exception as e:
        print(f"[digest_v2] render failed ({e}) — 텍스트 폴백", file=sys.stderr)
        return None


# ── 메일 HTML 조립 ─────────────────────────────────────────
def _footer(unsubscribe_token: str) -> str:
    unsub = f"{SITE_URL}/unsubscribe?token={quote(unsubscribe_token)}"
    return (f'<tr><td align="center" style="padding:2px 0 8px;">'
            f'<div style="font-family:{FONT};font-size:12px;color:#8592a6;line-height:1.7;">'
            f'공공입찰 수집 시스템 · 평일 오전 8시 발송 · '
            f'<a href="{SITE_BIDS}" style="color:#8592a6;">대시보드</a> · '
            f'<a href="{unsub}" style="color:#8592a6;">구독 해지</a></div></td></tr>')


def compose_image_mail(blocks: list[dict], unsubscribe_token: str,
                       footer_segs: list[dict] | None = None) -> str:
    # 간격 없이(0px) 쌓기 — 여백·배경은 이미지 안에 구워져 있음 (다크모드가 사이를 못 칠함)
    rows = "".join(
        f'<tr><td style="padding:0;"><a href="{b["link"]}" target="_blank" style="text-decoration:none;">'
        f'<img src="cid:{b["name"]}" width="{IMG_W}" alt="공공입찰 일일 리포트" '
        f'style="display:block;border:0;width:{IMG_W}px;max-width:100%;"></a></td></tr>\n'
        for b in blocks)

    unsub = f"{SITE_URL}/unsubscribe?token={quote(unsubscribe_token)}"
    if footer_segs:
        rows_f = ""
        for seg in footer_segs:
            href = SITE_BIDS if seg["kind"] == "dash" else unsub
            rows_f += (f'<tr><td style="padding:0;"><a href="{href}" target="_blank" style="text-decoration:none;">'
                       f'<img src="cid:{seg["cid"]}" width="{seg["w"]}" alt="" '
                       f'style="display:block;border:0;width:{seg["w"]}px;"></a></td></tr>')
        # 구독 해지: 지면(이미지) 아래 텍스트 링크 — 수신자별 URL
        rows_f += (f'<tr><td align="center" style="padding:8px 0 4px;">'
                   f'<a href="{unsub}" style="font-family:{FONT};font-size:12px;color:#8592a6;">구독 해지</a>'
                   f'</td></tr>')
        footer_row = rows_f
    else:
        footer_row = _footer(unsubscribe_token)

    return (f'<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"></head>'
            f'<body style="margin:0;padding:0;" bgcolor="#f3f7fc">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="#f3f7fc" style="border-collapse:collapse;">'
            f'<tr><td align="center" style="padding:0;">'
            f'<table role="presentation" width="{IMG_W}" cellpadding="0" cellspacing="0" style="width:{IMG_W}px;max-width:100%;border-collapse:collapse;">'
            f'{rows}{footer_row}'
            f'</table></td></tr></table></body></html>')


def compose_text_mail(data: dict, unsubscribe_token: str) -> str:
    """텍스트(HTML) 메일 — 사내 아웃룩용 기본 모드.

    이미지 차단 환경에서도 온전히 보이도록 이미지 0장. 둥근 모서리는 VML 하이브리드
    (_rounded) 로 아웃룩에서도 그려진다. 폰트는 Pretendard 우선(설치자) + 맑은고딕.
    """
    cards = [_header_card(data, hybrid=True), _band_card(data, hybrid=True)]
    cards += [_section_card(g, data, hybrid=True) for g in DISPLAY_ORDER]
    cards.append(_cta_card(hybrid=True))
    rows = "".join(f'<tr><td style="padding:0 0 10px;">{c}</td></tr>\n' for c in cards)
    return (f'<!DOCTYPE html>'
            f'<html lang="ko" xmlns:v="urn:schemas-microsoft-com:vml" '
            f'xmlns:o="urn:schemas-microsoft-com:office:office">'
            f'<head><meta charset="utf-8">'
            f'<!--[if mso]><xml><o:OfficeDocumentSettings>'
            f'<o:PixelsPerInch>96</o:PixelsPerInch>'
            f'</o:OfficeDocumentSettings></xml><![endif]-->'
            f'</head>'
            f'<body style="margin:0;padding:0;" bgcolor="#f3f7fc">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="#f3f7fc" style="border-collapse:collapse;">'
            f'<tr><td align="center" style="padding:10px 12px 24px;">'
            f'<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:600px;max-width:100%;border-collapse:collapse;">'
            f'{rows}{_footer(unsubscribe_token)}'
            f'</table></td></tr></table></body></html>')


if __name__ == "__main__":
    # 로컬 점검: python -m scripts.digest_v2 → 데이터 요약 + 렌더 시도 결과 출력
    data = build_digest_data()
    print("counts:", json.dumps(data["counts"], ensure_ascii=False))
    print("subject:", subject_line(data))
    blocks = build_blocks(data)
    rendered = render_blocks(blocks)
    if rendered:
        imgs, segs = rendered
        print("render: OK", [len(v) // 1024 for v in imgs.values()], "KB / footer segs:", len(segs))
    else:
        print("render: FAILED(폴백)")
