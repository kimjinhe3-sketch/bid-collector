# -*- coding: utf-8 -*-
"""AI 투찰 추천 성과 리포트 — 관리자(jihyeong.kim) 전용, 매일 아침 발송.

다이제스트(digest_v2)와 같은 디자인 언어(파랑 그라데이션 헤더 + 카드 + Pretendard
이미지 렌더 + Outlook COM 내부발신). 내용은 북극성 지표 중심:
  ① 최신 개찰일 관심그룹 성적 (적중권·저가·오차중앙 + 베스트/워스트 사례)
  ② 최근 7 개찰일 추이
  ③ "오늘 추천에 반영된 변화" — 세그 피드백 플래그 증감, 재계산·다이얼 현황
통짜 1장 이미지(다중 조각의 DPI 균열 회피) + 텍스트 푸터.

Usage (이 PC, Outlook 로그인):
    python -m scripts.send_ai_report            # 발송
    python -m scripts.send_ai_report --dry-run  # 렌더만 (data/ai_report_preview)
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT, ".env"))

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

from scripts.digest_v2 import FONT, IMG_W, CI_PNG, SITE_URL  # noqa: E402

ADMIN = os.environ.get("ADMIN_EMAIL") or "jihyeong.kim@kt.com"
REVIEW_URL = SITE_URL + "/review"
STATE_PATH = Path(ROOT) / "data" / "ai_report_state.json"
HITZONE = 0.005   # 적중권 |오차| 한계(%p)
LOWBAND = 0.5     # 저가 제안 경계(%p)

FLAG_KO = {"unreliable": "예측 불가 — 추천 보류", "low_risk": "저가 위험 — 신뢰도 강등",
           "under_risk": "하한 미달 잦음 — 신뢰도 강등", "margin_low": "밀림 잦음 — 신뢰도 강등"}


def _rest(path: str, extra: str = "", paged: bool = False) -> list[dict]:
    import requests
    base = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    hdr = {"apikey": key, "Authorization": f"Bearer {key}"}
    rows, offset = [], 0
    while True:
        r = requests.get(f"{base}/rest/v1/{path}?{extra}",
                         headers={**hdr, "Range-Unit": "items",
                                  "Range": f"{offset}-{offset + 999}"}, timeout=30)
        r.raise_for_status()
        chunk = r.json()
        rows.extend(chunk)
        if not paged or len(chunk) < 1000:
            return rows
        offset += 1000


def collect() -> dict:
    kst = datetime.now(timezone.utc) + timedelta(hours=9)
    since = (kst - timedelta(days=12)).strftime("%Y-%m-%d")
    scores = _rest("bid_rec_scores",
                   "select=grp,title,org_name,diff,outcome,open_result_date"
                   f"&open_result_date=gte.{since}", paged=True)
    fb = _rest("bid_seg_feedback", "select=seg_key,flag,n,med_diff&order=n.desc")
    rec_top = _rest("bid_recommendations", "select=computed_at&order=computed_at.desc&limit=1")

    import requests
    base = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    hdr = {"apikey": key, "Authorization": f"Bearer {key}", "Prefer": "count=exact", "Range": "0-0"}

    def cnt(extra):
        r = requests.get(f"{base}/rest/v1/bid_recommendations?select=bid_no{extra}",
                         headers=hdr, timeout=30)
        return int(r.headers["Content-Range"].split("/")[1])

    computed_at = rec_top[0]["computed_at"][:16].replace("T", " ") if rec_top else "-"
    n_rec = cnt("")
    n_dial = cnt("&rationale->dial->>pred=eq.%EC%95%BD%EA%B2%BD%EC%9F%81")

    bydate = defaultdict(list)
    for s in scores:
        d = (s.get("open_result_date") or "")[:10]
        if d:
            bydate[d].append(s)
    dates = sorted(bydate, reverse=True)
    return {"kst": kst, "bydate": bydate, "dates": dates, "fb": fb,
            "computed_at": computed_at, "n_rec": n_rec, "n_dial": n_dial}


def _grp_rows(rows):
    return [r for r in rows if r.get("grp") and r["grp"] != "-"]


def _stats(rows):
    n = len(rows)
    if n == 0:
        return None
    ds = [float(r["diff"]) for r in rows]
    hz = sum(1 for d in ds if abs(d) <= HITZONE)
    low = sum(1 for d in ds if d < -LOWBAND)
    high = sum(1 for d in ds if d > LOWBAND)
    sd = sorted(ds)
    med = sd[n // 2] if n % 2 else (sd[n // 2 - 1] + sd[n // 2]) / 2
    best = min(rows, key=lambda r: abs(float(r["diff"])))
    worst = min(rows, key=lambda r: float(r["diff"]))
    return {"n": n, "hz": hz, "low": low, "high": high, "med": med,
            "best": best, "worst": worst}


def _trunc(s, n):
    s = s or ""
    return s if len(s) <= n else s[: n - 1] + "…"


def _card(inner: str) -> str:
    return (f'<div style="background:#ffffff;border:1px solid #e3eaf4;border-radius:14px;'
            f'padding:12px 16px;box-shadow:0 1px 2px rgba(15,31,56,.05);margin-top:10px;">{inner}</div>')


def _title(t: str) -> str:
    return (f'<div style="font-family:{FONT};font-size:12px;font-weight:700;color:#2a78d6;'
            f'letter-spacing:.04em;margin-bottom:7px;">{t}</div>')


def build_html(c: dict) -> tuple[str, str, dict]:
    kst = c["kst"]
    latest = c["dates"][0] if c["dates"] else None
    rows_l = c["bydate"].get(latest, []) if latest else []
    g = _stats(_grp_rows(rows_l))
    a = _stats(rows_l)

    # 헤더
    ci_b64 = base64.b64encode(CI_PNG.read_bytes()).decode()
    header = (
        f'<div style="background:#2a78d6;background-image:linear-gradient(105deg,#1c5cab 0%,#2a78d6 58%,#3f8ce4 100%);'
        f'border-radius:14px;padding:12px 18px 13px;">'
        f'<img src="data:image/png;base64,{ci_b64}" height="15" alt="kt engineering" '
        f'style="display:block;border:0;height:15px;width:auto;margin-bottom:7px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;"><tr>'
        f'<td style="font-family:{FONT};font-size:19px;font-weight:700;color:#ffffff;">AI 투찰 추천 성과 리포트</td>'
        f'<td align="right" style="font-family:{FONT};font-size:12px;color:#ffffff;white-space:nowrap;vertical-align:bottom;">'
        f'{kst:%Y-%m-%d} {"월화수목금토일"[kst.weekday()]} · 관리자 전용</td>'
        f'</tr></table></div>')

    # ① 최신 개찰일 성적 (관심그룹 중심)
    if g:
        big = (f'<span style="font-size:26px;font-weight:800;color:#0f1f38;">{g["hz"]}</span>'
               f'<span style="font-size:14px;font-weight:700;color:#0f1f38;">/{g["n"]}건 적중권</span>')
        detail = (f'저가 <b style="color:{"#d97706" if g["low"] else "#0f1f38"};">{g["low"]}건</b> · '
                  f'고가 {g["high"]}건 · 오차중앙 {g["med"]:+.3f}%p'
                  + (f' <span style="color:#8592a6;">(전체: 적중권 {a["hz"]}/{a["n"]})</span>' if a else ""))
        best_line = (f'가장 근접: {_trunc(g["best"].get("title"), 26)} '
                     f'<b>{float(g["best"]["diff"]):+.3f}%p</b>')
        worst = g["worst"]
        worst_line = (f'최대 저가: {_trunc(worst.get("title"), 26)} '
                      f'<b style="color:#d97706;">{float(worst["diff"]):+.3f}%p</b>'
                      if float(worst["diff"]) < -LOWBAND else "저가 제안(−0.5%p 초과) 없음 ✓")
        perf = _card(_title(f'① 관심그룹 성적 — {latest} 개찰분')
                     + f'<div style="font-family:{FONT};line-height:1.5;">{big}</div>'
                     + f'<div style="font-family:{FONT};font-size:13px;color:#3a4657;margin-top:4px;">{detail}</div>'
                     + f'<div style="font-family:{FONT};font-size:12px;color:#5b6b78;'
                     + f'margin-top:7px;line-height:1.7;">{best_line}<br>{worst_line}</div>')
    else:
        perf = _card(_title("① 관심그룹 성적") + f'<div style="font-family:{FONT};font-size:13px;color:#8592a6;">'
                     f'{latest or "최근"} 개찰분에 관심그룹 채점 건이 없습니다.</div>')

    # ② 최근 7 개찰일 추이
    tr = ""
    for d in c["dates"][:7]:
        gs = _stats(_grp_rows(c["bydate"][d]))
        if not gs:
            tr += (f'<tr><td style="font-family:{FONT};font-size:12px;color:#8592a6;padding:3px 0;">{d[5:]}</td>'
                   f'<td colspan="4" style="font-family:{FONT};font-size:12px;color:#c3ccd9;" align="right">관심그룹 채점 없음</td></tr>')
            continue
        hz_c = "#059669" if gs["hz"] else "#0f1f38"
        low_c = "#d97706" if gs["low"] else "#0f1f38"
        tr += (f'<tr>'
               f'<td style="font-family:{FONT};font-size:12px;color:#3a4657;padding:3px 0;">{d[5:]}</td>'
               f'<td align="right" style="font-family:{FONT};font-size:12px;color:#3a4657;">{gs["n"]}건</td>'
               f'<td align="right" style="font-family:{FONT};font-size:12px;font-weight:700;color:{hz_c};">적중권 {gs["hz"]}</td>'
               f'<td align="right" style="font-family:{FONT};font-size:12px;font-weight:700;color:{low_c};">저가 {gs["low"]}</td>'
               f'<td align="right" style="font-family:{FONT};font-size:12px;color:#3a4657;">{gs["med"]:+.2f}%p</td>'
               f'</tr>')
    trend = _card(_title("② 관심그룹 추이 — 최근 개찰일")
                  + f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">{tr}</table>')

    # ③ 오늘 추천에 반영된 변화 (세그 피드백 diff + 재계산 현황)
    try:
        prev = json.loads(STATE_PATH.read_text(encoding="utf-8")).get("flags", {})
    except Exception:
        prev = {}
    cur = {f["seg_key"]: f["flag"] for f in c["fb"]}
    changes = []
    for k, v in cur.items():
        if v != "ok" and prev.get(k, "ok") == "ok":
            changes.append(f'<b>신규 감지</b> {k} → {FLAG_KO.get(v, v)}')
        elif v == "ok" and prev.get(k, "ok") != "ok":
            changes.append(f'<b>해제</b> {k} — 성적 회복으로 정상 추천 복귀')
    active = [f for f in c["fb"] if f["flag"] != "ok"]
    ch_html = ""
    if changes:
        ch_html += "<br>".join(changes) + "<br>"
    ch_html += (f'유지 중인 자동 조치 <b>{len(active)}건</b>: '
                + ", ".join(f'{f["seg_key"].split("|")[0]}·{f["seg_key"].split("|")[2]}({FLAG_KO.get(f["flag"], f["flag"]).split(" — ")[0]})'
                            for f in active[:4])
                + ("…" if len(active) > 4 else ""))
    ch_html += (f'<br><span style="color:#8592a6;">추천 재계산 {c["computed_at"]} · '
                f'발행 {c["n_rec"]:,}건 · 약경쟁 마진 상향 {c["n_dial"]}건</span>')
    change = _card(_title("③ 오늘 추천에 반영된 변화 — 어제 결과의 학습")
                   + f'<div style="font-family:{FONT};font-size:12.5px;color:#3a4657;line-height:1.8;">{ch_html}</div>')

    # CTA
    cta = (f'<div style="text-align:center;padding:12px 0 4px;">'
           f'<span style="display:inline-block;background:#2a78d6;'
           f'background-image:linear-gradient(105deg,#1c5cab 0%,#2a78d6 58%,#3f8ce4 100%);color:#ffffff;'
           f'font-family:{FONT};font-size:13px;font-weight:700;padding:10px 34px;border-radius:10px;">'
           f'AI 리뷰보드에서 상세 보기</span></div>')

    body = header + perf + trend + change + cta
    subject = (f'[AI 성과] {kst.month}/{kst.day} | 관심그룹 적중권 '
               f'{g["hz"] if g else 0}/{g["n"] if g else 0} · 저가 {g["low"] if g else 0}건'
               + (f' · 변화 {len(changes)}건' if changes else ""))
    return body, subject, cur


def render(body: str) -> bytes | None:
    from playwright.sync_api import sync_playwright
    wrap = ('<!DOCTYPE html><html><head><meta charset="utf-8"><style>'
            f'body{{margin:0;background:#f3f7fc;}}'
            f'#cap{{width:{IMG_W}px;box-sizing:border-box;background:#f3f7fc;padding:10px 12px 16px;}}'
            '</style></head><body><div id="cap">' + body + "</div></body></html>")
    try:
        with tempfile.TemporaryDirectory() as td, sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 680, "height": 400}, device_scale_factor=2)
            f = Path(td) / "report.html"
            f.write_text(wrap, encoding="utf-8")
            page.goto(f.as_uri())
            page.wait_for_timeout(150)
            shot = page.locator("#cap").screenshot()
            browser.close()
        return shot
    except Exception as e:
        print(f"[ai-report] render failed: {e}", file=sys.stderr)
        return None


def compose(png_cid: str) -> str:
    return (f'<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"></head>'
            f'<body style="margin:0;padding:0;" bgcolor="#f3f7fc">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="#f3f7fc" style="border-collapse:collapse;">'
            f'<tr><td align="center" style="padding:0;">'
            f'<table role="presentation" width="{IMG_W}" cellpadding="0" cellspacing="0" style="width:{IMG_W}px;max-width:100%;border-collapse:collapse;">'
            f'<tr><td style="padding:0;"><a href="{REVIEW_URL}" target="_blank" style="text-decoration:none;">'
            f'<img src="cid:{png_cid}" width="{IMG_W}" alt="AI 성과 리포트" '
            f'style="display:block;border:0;width:{IMG_W}px;max-width:100%;"></a></td></tr>'
            f'<tr><td align="center" style="padding:6px 0 10px;">'
            f'<div style="font-family:{FONT};font-size:12px;color:#8592a6;">'
            f'AI 투찰 추천 성과 리포트 · 관리자 전용 · 평일 오전 8시 30분 · '
            f'<a href="{REVIEW_URL}" style="color:#8592a6;">리뷰보드</a></div></td></tr>'
            f'</table></td></tr></table></body></html>')


def send_outlook(subject: str, html: str, png: bytes) -> bool:
    import win32com.client
    try:
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "ai_report.png")
            with open(path, "wb") as f:
                f.write(png)
            outlook = win32com.client.Dispatch("Outlook.Application")
            mail = outlook.CreateItem(0)
            mail.To = ADMIN
            mail.Subject = subject
            att = mail.Attachments.Add(path)
            att.PropertyAccessor.SetProperty(
                "http://schemas.microsoft.com/mapi/proptag/0x3712001F", "ai_report")
            att.PropertyAccessor.SetProperty(
                "http://schemas.microsoft.com/mapi/id/{00062008-0000-0000-C000-000000000046}/8514000B", True)
            mail.HTMLBody = html
            mail.Send()
        return True
    except Exception as e:
        print(f"[ai-report] send failed: {e}", file=sys.stderr)
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    now = datetime.now(timezone.utc) + timedelta(hours=9)
    if not args.dry_run and now.weekday() >= 5:
        print(f"[ai-report] 주말({now:%Y-%m-%d %a}) — skip")
        return 0

    c = collect()
    body, subject, cur_flags = build_html(c)
    print(f"[ai-report] subject: {subject}")
    png = render(body)
    if not png:
        return 1
    print(f"[ai-report] render {len(png) // 1024}KB")

    if args.dry_run:
        out = Path(ROOT) / "data" / "ai_report_preview"
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.png").write_bytes(png)
        (out / "report.html").write_text(compose("ai_report"), encoding="utf-8")
        print(f"[ai-report] (dry-run) 미리보기: {out}")
        return 0

    ok = send_outlook(subject, compose("ai_report"), png)
    if ok:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps({"flags": cur_flags, "sent_at": now.isoformat()},
                                         ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[ai-report] sent={'1' if ok else '0'}/1 → {ADMIN}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
