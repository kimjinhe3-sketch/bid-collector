"""구독자에게 입찰공고 알림 메일 발송.

알림 종류 (bid_subscribers.preferences.alerts):
  - new      : 오늘 신규 공고 (open_date = KST 오늘)
  - closing  : 마감 임박 (close_date D-3 이내)
  - keyword  : 키워드/지역/금액 조건 매칭 (오늘 신규 중)

Usage:
    python -m scripts.send_alerts --kind new
    python -m scripts.send_alerts --kind closing
    python -m scripts.send_alerts --kind keyword
    python -m scripts.send_alerts --kind all        # 셋 다 (조건 맞는 구독자에게)

환경변수:
    DATABASE_URL          (필수)
    RESEND_API_KEY 또는 SMTP_*  (mail_sender 참조)
    SITE_URL              대시보드 base URL (기본 Cloudtype URL)
"""
from __future__ import annotations

import argparse
import os
import sys
import html as html_mod

import psycopg2
from psycopg2.extras import RealDictCursor

# notifiers.mail_sender 를 패키지 경로로 import (python -m scripts.send_alerts)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from notifiers.mail_sender import send_mail  # noqa: E402

EOK = 100_000_000
SITE_URL = os.environ.get("SITE_URL", "https://port-next-bidlive-korea-web-mozlrrj98331a064.sel3.cloudtype.app")


def _db():
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("[send_alerts] DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)
    if "sslmode=" not in url:
        url = f"{url}{'&' if '?' in url else '?'}sslmode=require"
    return psycopg2.connect(url, cursor_factory=RealDictCursor)


def _fmt_amount(price) -> str:
    if not price:
        return "-"
    try:
        p = int(price)
    except (ValueError, TypeError):
        return "-"
    if p >= EOK:
        return f"{p / EOK:,.1f}억"
    return f"{p:,}원"


def _norm_date(s) -> str:
    if not s:
        return "-"
    t = str(s).strip()
    if t[:8].isdigit() and len(t) >= 8:
        return f"{t[0:4]}-{t[4:6]}-{t[6:8]}"
    return t[:10].replace("/", "-")


# ─────────── 공고 조회 ───────────

SQL_NEW = """
SELECT bid_no, title, org_name, region, estimated_price, close_date, open_date, bid_type, detail_url, source
FROM bid_announcements
WHERE SUBSTR(open_date, 1, 10) = to_char((NOW() AT TIME ZONE 'Asia/Seoul')::date, 'YYYY-MM-DD')
ORDER BY estimated_price DESC NULLS LAST
LIMIT 200
"""

SQL_CLOSING = """
SELECT bid_no, title, org_name, region, estimated_price, close_date, open_date, bid_type, detail_url, source
FROM bid_announcements
WHERE close_date IS NOT NULL AND close_date <> ''
  AND SUBSTR(REPLACE(close_date,'/','-'), 1, 10) >= to_char((NOW() AT TIME ZONE 'Asia/Seoul')::date, 'YYYY-MM-DD')
  AND SUBSTR(REPLACE(close_date,'/','-'), 1, 10) <= to_char((NOW() AT TIME ZONE 'Asia/Seoul')::date + 3, 'YYYY-MM-DD')
ORDER BY SUBSTR(REPLACE(close_date,'/','-'), 1, 10) ASC
LIMIT 200
"""


def fetch_new(cur) -> list[dict]:
    cur.execute(SQL_NEW)
    return cur.fetchall()


def fetch_closing(cur) -> list[dict]:
    cur.execute(SQL_CLOSING)
    return cur.fetchall()


def fetch_subscribers(cur, kind: str) -> list[dict]:
    """preferences.alerts 에 kind 가 포함된 active 구독자."""
    cur.execute(
        """
        SELECT email, unsubscribe_token, preferences
        FROM bid_subscribers
        WHERE active = TRUE
          AND preferences -> 'alerts' ? %s
        """,
        (kind,),
    )
    return cur.fetchall()


# ─────────── 키워드 매칭 필터 ───────────

def match_prefs(row: dict, prefs: dict) -> bool:
    kws = [k.lower() for k in (prefs.get("keywords") or [])]
    regions = prefs.get("regions") or []
    amount_min = prefs.get("amountMinEok")

    title = (row.get("title") or "").lower()
    if kws and not any(k in title for k in kws):
        return False

    if regions:
        text = " ".join(str(row.get(f) or "") for f in ("region", "org_name", "title"))
        if not any(rg in text for rg in regions):
            return False

    if amount_min:
        price = row.get("estimated_price") or 0
        try:
            if int(price) < float(amount_min) * EOK:
                return False
        except (ValueError, TypeError):
            return False

    return True


# ─────────── HTML 템플릿 ───────────

def _row_block(r: dict) -> str:
    title = html_mod.escape(r.get("title") or "")
    url = r.get("detail_url") or f"{SITE_URL}/bids"
    org = html_mod.escape(r.get("org_name") or "-")
    region = html_mod.escape(r.get("region") or "")
    bid_type = html_mod.escape(r.get("bid_type") or "")
    amount = _fmt_amount(r.get("estimated_price"))
    close = _norm_date(r.get("close_date"))
    meta = " · ".join(x for x in [org, region, bid_type] if x)
    return f"""
    <tr><td style="padding:12px 14px;border-bottom:1px solid #eee;">
      <a href="{html_mod.escape(url)}" style="color:#1a1a1a;font-weight:600;font-size:14px;text-decoration:none;line-height:1.4;">{title}</a>
      <div style="color:#888;font-size:12px;margin-top:4px;">{meta}</div>
      <div style="font-size:12px;margin-top:2px;">
        <span style="color:#FE2E36;font-weight:700;">{amount}</span>
        <span style="color:#aaa;"> · 마감 {close}</span>
      </div>
    </td></tr>"""


def build_email(title: str, rows: list[dict], unsubscribe_token: str) -> str:
    body = "".join(_row_block(r) for r in rows) or (
        '<tr><td style="padding:20px;text-align:center;color:#888;">해당 공고가 없습니다.</td></tr>'
    )
    unsub = f"{SITE_URL}/unsubscribe?token={unsubscribe_token}"
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:'Apple SD Gothic Neo','Malgun Gothic',sans-serif;">
  <div style="max-width:600px;margin:0 auto;background:#fff;">
    <div style="background:#1a1a1a;padding:18px 20px;">
      <span style="color:#fff;font-size:16px;font-weight:800;">공공입찰 수집 시스템</span>
    </div>
    <div style="padding:18px 20px 8px;">
      <h2 style="margin:0;font-size:18px;color:#1a1a1a;">{html_mod.escape(title)}</h2>
      <p style="margin:6px 0 0;color:#888;font-size:13px;">총 {len(rows)}건</p>
    </div>
    <table style="width:100%;border-collapse:collapse;">{body}</table>
    <div style="padding:16px 20px;text-align:center;">
      <a href="{SITE_URL}/bids" style="display:inline-block;background:#FE2E36;color:#fff;padding:10px 24px;border-radius:6px;text-decoration:none;font-weight:700;font-size:13px;">전체 보기</a>
    </div>
    <div style="padding:14px 20px;border-top:1px solid #eee;text-align:center;color:#aaa;font-size:11px;">
      이 메일은 공공입찰 수집 시스템 알림 구독자에게 발송됩니다.<br>
      <a href="{unsub}" style="color:#aaa;">구독 해지</a>
    </div>
  </div>
</body></html>"""


# ─────────── 발송 ───────────

def run_kind(cur, kind: str) -> int:
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    sent = 0

    if kind in ("new", "keyword"):
        new_rows = fetch_new(cur)

    if kind == "new":
        subs = fetch_subscribers(cur, "new")
        for s in subs:
            html = build_email(f"[{today}] 신규 입찰공고", new_rows, s["unsubscribe_token"])
            if send_mail(s["email"], f"[공공입찰] {today} 신규 {len(new_rows)}건", html):
                sent += 1

    elif kind == "closing":
        closing_rows = fetch_closing(cur)
        subs = fetch_subscribers(cur, "closing")
        for s in subs:
            html = build_email("마감 임박 (D-3 이내)", closing_rows, s["unsubscribe_token"])
            if send_mail(s["email"], f"[공공입찰] 마감임박 {len(closing_rows)}건", html):
                sent += 1

    elif kind == "keyword":
        subs = fetch_subscribers(cur, "keyword")
        for s in subs:
            prefs = s.get("preferences") or {}
            matched = [r for r in new_rows if match_prefs(r, prefs)]
            if not matched:
                continue  # 매칭 0 이면 발송 안 함
            html = build_email("키워드·조건 매칭 신규 공고", matched, s["unsubscribe_token"])
            if send_mail(s["email"], f"[공공입찰 매칭] 신규 {len(matched)}건", html):
                sent += 1

    print(f"[send_alerts] kind={kind} sent={sent}")
    return sent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=["new", "closing", "keyword", "all"], required=True)
    args = ap.parse_args()

    conn = _db()
    try:
        with conn.cursor() as cur:
            kinds = ["new", "closing", "keyword"] if args.kind == "all" else [args.kind]
            for k in kinds:
                run_kind(cur, k)
        conn.commit()
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
