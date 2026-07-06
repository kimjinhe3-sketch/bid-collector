"""구독자에게 입찰공고 일일 다이제스트 메일 발송 (하루 1통 통합).

한 통에 3개 섹션:
  - 신규 공고 (오늘 open_date, 최대 3건 + 더보기)
  - 키워드 매칭 (구독자 preferences 조건, 최대 3건 + 더보기) — keyword 구독자만
  - 마감 임박 (D-1 이내, 최대 3건 + 더보기)

각 섹션은 구독자의 preferences.alerts 에 해당 종류가 있을 때만 포함.
"더보기" 링크는 웹 대시보드의 해당 필터 화면으로 연결.

Usage:
    python -m scripts.send_alerts            # 일일 다이제스트 (기본)
    python -m scripts.send_alerts --dry-run  # 발송 없이 대상/건수만 출력

환경변수:
    DATABASE_URL              (필수)
    RESEND_API_KEY 또는 SMTP_*  (mail_sender 참조)
    SITE_URL                  대시보드 base URL
"""
from __future__ import annotations

import argparse
import os
import sys
import html as html_mod
from datetime import datetime
from urllib.parse import quote

import psycopg2
from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from notifiers.mail_sender import send_mail  # noqa: E402

EOK = 100_000_000
SITE_URL = os.environ.get(
    "SITE_URL",
    "https://port-next-bidlive-korea-web-mozlrrj98331a064.sel3.cloudtype.app",
).rstrip("/")
PREVIEW = 3  # 섹션당 최대 표시 건수


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

COLS = "bid_no, title, org_name, region, estimated_price, close_date, open_date, bid_type, detail_url, source"

# 신규 = 공고일(open_date) 이 당일(오늘) — 대시보드 TODAY 카드와 동일 기준
SQL_NEW = f"""
SELECT {COLS} FROM bid_announcements
WHERE SUBSTR(open_date, 1, 10) = to_char((NOW() AT TIME ZONE 'Asia/Seoul')::date, 'YYYY-MM-DD')
ORDER BY estimated_price DESC NULLS LAST
"""

# 마감 임박 = D-1 이내 (오늘~내일 마감)
SQL_CLOSING = f"""
SELECT {COLS} FROM bid_announcements
WHERE close_date IS NOT NULL AND close_date <> ''
  AND SUBSTR(REPLACE(close_date,'/','-'), 1, 10) >= to_char((NOW() AT TIME ZONE 'Asia/Seoul')::date, 'YYYY-MM-DD')
  AND SUBSTR(REPLACE(close_date,'/','-'), 1, 10) <= to_char((NOW() AT TIME ZONE 'Asia/Seoul')::date + 1, 'YYYY-MM-DD')
ORDER BY SUBSTR(REPLACE(close_date,'/','-'), 1, 10) ASC
"""

# 키워드 매칭 모집단 = 진행중(마감 안 지난) 전체. 마감 임박순 정렬.
SQL_ACTIVE = f"""
SELECT {COLS} FROM bid_announcements
WHERE close_date IS NULL OR close_date = ''
   OR SUBSTR(REPLACE(close_date,'/','-'), 1, 10) >= to_char((NOW() AT TIME ZONE 'Asia/Seoul')::date, 'YYYY-MM-DD')
ORDER BY
  (close_date IS NULL OR close_date = '') ASC,
  SUBSTR(REPLACE(close_date,'/','-'), 1, 10) ASC
"""


def fetch(cur, sql) -> list[dict]:
    cur.execute(sql)
    return cur.fetchall()


def fetch_subscribers(cur) -> list[dict]:
    cur.execute(
        "SELECT email, unsubscribe_token, preferences FROM bid_subscribers WHERE active = TRUE"
    )
    return cur.fetchall()


# ─────────── 키워드 매칭 ───────────

def _keyword_filter_url(prefs: dict) -> str:
    """구독자 preferences → 웹 대시보드 필터 URL (진행중 + 키워드 + 지역 + 금액)."""
    params = ["active=1"]
    kws = prefs.get("keywords") or []
    if kws:
        params.append("inc=" + quote(",".join(kws)))
    regions = prefs.get("regions") or []
    if regions:
        params.append("regions=" + quote(",".join(regions)))
    amin = prefs.get("amountMinEok")
    if amin:
        params.append(f"amin={amin}")
    return f"{SITE_URL}/bids?" + "&".join(params)


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


# ─────────── HTML ───────────

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
    <tr><td style="padding:10px 14px;border-bottom:1px solid #f0f0f0;">
      <a href="{html_mod.escape(url)}" style="color:#1a1a1a;font-weight:600;font-size:14px;text-decoration:none;line-height:1.4;">{title}</a>
      <div style="color:#888;font-size:12px;margin-top:3px;">{meta}</div>
      <div style="font-size:12px;margin-top:2px;">
        <span style="color:#FE2E36;font-weight:700;">{amount}</span>
        <span style="color:#aaa;"> · 마감 {close}</span>
      </div>
    </td></tr>"""


def _section(emoji: str, title: str, rows: list[dict], total: int, more_url: str) -> str:
    if total == 0:
        return ""
    preview = rows[:PREVIEW]
    body = "".join(_row_block(r) for r in preview)
    more = ""
    if total > PREVIEW:
        more = f"""
        <tr><td style="padding:10px 14px;">
          <a href="{more_url}" style="color:#FE2E36;font-size:13px;font-weight:700;text-decoration:none;">
            + 전체 {total}건 더보기 →
          </a>
        </td></tr>"""
    return f"""
    <div style="margin-top:20px;">
      <div style="padding:0 14px 8px;font-size:15px;font-weight:800;color:#1a1a1a;">
        {emoji} {html_mod.escape(title)}
        <span style="color:#888;font-weight:500;font-size:13px;">({total}건)</span>
      </div>
      <table style="width:100%;border-collapse:collapse;border-top:2px solid #1a1a1a;">{body}{more}</table>
    </div>"""


def build_digest(
    today: str,
    unsubscribe_token: str,
    new_rows: list[dict] | None,
    keyword_rows: list[dict] | None,
    closing_rows: list[dict] | None,
    keyword_more_url: str = "",
) -> tuple[str, str]:
    """returns (subject, html). 섹션은 None 이면 미포함 (구독 안 함)."""
    sections = ""
    counts = []

    if new_rows is not None:
        sections += _section("📢", "신규 공고", new_rows, len(new_rows), f"{SITE_URL}/bids?tags=new")
        counts.append(f"신규 {len(new_rows)}")
    if keyword_rows is not None:
        sections += _section("🎯", "키워드 매칭 (진행중)", keyword_rows, len(keyword_rows), keyword_more_url or f"{SITE_URL}/bids")
        counts.append(f"매칭 {len(keyword_rows)}")
    if closing_rows is not None:
        sections += _section("⏰", "마감 임박 (D-1 이내)", closing_rows, len(closing_rows), f"{SITE_URL}/bids?dday=1")
        counts.append(f"마감임박 {len(closing_rows)}")

    subject = f"[공공입찰] {today} 일일 리포트 — " + " / ".join(counts)
    unsub = f"{SITE_URL}/unsubscribe?token={unsubscribe_token}"

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:'Apple SD Gothic Neo','Malgun Gothic',sans-serif;">
  <div style="max-width:600px;margin:0 auto;background:#fff;">
    <div style="background:#1a1a1a;padding:18px 20px;">
      <span style="color:#fff;font-size:16px;font-weight:800;">공공입찰 수집 시스템</span>
      <div style="color:#aaa;font-size:12px;margin-top:3px;">{today} 일일 리포트</div>
    </div>
    <div style="padding:4px 6px 12px;">{sections}</div>
    <div style="padding:16px 20px;text-align:center;border-top:1px solid #eee;">
      <a href="{SITE_URL}/bids" style="display:inline-block;background:#FE2E36;color:#fff;padding:10px 28px;border-radius:6px;text-decoration:none;font-weight:700;font-size:13px;">대시보드 전체 보기</a>
    </div>
    <div style="padding:14px 20px;border-top:1px solid #eee;text-align:center;color:#aaa;font-size:11px;">
      매일 오전 8시 발송 · 공공입찰 수집 시스템<br>
      <a href="{unsub}" style="color:#aaa;">구독 해지</a>
    </div>
  </div>
</body></html>"""
    return subject, html


# ─────────── 발송 ───────────

def run(dry_run: bool = False, test_only: bool = False) -> int:
    from datetime import timedelta, timezone
    # KST 기준 요일 — runner 는 UTC 라 +9h 보정
    kst_now = datetime.now(timezone.utc) + timedelta(hours=9)
    # 주말(토=5, 일=6) 은 발송 skip — 공공기관 공고 거의 없음.
    # test_only(수동 테스트) 는 요일 무관 발송.
    if not test_only and kst_now.weekday() >= 5:
        print(f"[send_alerts] 주말({kst_now:%Y-%m-%d %a}) — 발송 skip")
        return 0

    today = kst_now.strftime("%Y-%m-%d")
    conn = _db()
    sent = 0
    try:
        with conn.cursor() as cur:
            all_new = fetch(cur, SQL_NEW)
            all_closing = fetch(cur, SQL_CLOSING)
            all_active = fetch(cur, SQL_ACTIVE)  # 키워드 매칭 모집단 (진행중 전체)
            subs = fetch_subscribers(cur)
            # test_only: 실제 구독자 무시, ADMIN_EMAIL 1명에게만 (모든 알림 켠 가상 구독자)
            if test_only:
                admin = os.environ.get("ADMIN_EMAIL", "jihyeong.kim@kt.com")
                subs = [{
                    "email": admin,
                    "unsubscribe_token": "test",
                    "preferences": {"alerts": ["new", "closing", "keyword"]},
                }]
                print(f"[send_alerts] TEST MODE → {admin} 에게만")
            print(f"[send_alerts] new={len(all_new)} closing={len(all_closing)} "
                  f"active={len(all_active)} subscribers={len(subs)}")

            for s in subs:
                prefs = s.get("preferences") or {}
                alerts = set(prefs.get("alerts") or ["new"])

                new_rows = all_new if "new" in alerts else None
                closing_rows = all_closing if "closing" in alerts else None
                keyword_rows = None
                keyword_more_url = ""
                if "keyword" in alerts:
                    # 진행중 전체 중 키워드/지역/금액 매칭 (마감 임박순 — SQL_ACTIVE 정렬 유지)
                    keyword_rows = [r for r in all_active if match_prefs(r, prefs)]
                    keyword_more_url = _keyword_filter_url(prefs)

                # 보낼 내용이 하나도 없으면 skip (전 섹션 0건/미구독)
                has_content = any(
                    x is not None and len(x) > 0
                    for x in (new_rows, keyword_rows, closing_rows)
                )
                if not has_content:
                    continue

                subject, html = build_digest(
                    today, s["unsubscribe_token"], new_rows, keyword_rows, closing_rows,
                    keyword_more_url=keyword_more_url,
                )

                if dry_run:
                    print(f"  [dry-run] {s['email']} ← {subject}")
                    sent += 1
                elif send_mail(s["email"], subject, html):
                    sent += 1
                    # 발송 성공 기록 (누가 언제 받았는지 추적용)
                    cur.execute(
                        "UPDATE bid_subscribers SET last_sent_at = NOW() WHERE email = %s",
                        (s["email"],),
                    )

        conn.commit()
        print(f"[send_alerts] {'(dry-run) ' if dry_run else ''}sent={sent}")
        return 0
    finally:
        conn.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="발송 없이 대상만 출력")
    ap.add_argument("--test-only", action="store_true",
                    help="실제 구독자 무시, ADMIN_EMAIL 1명에게만 (수동 테스트용)")
    # 하위호환: --kind 받아도 무시 (이제 통합 다이제스트)
    ap.add_argument("--kind", help="(deprecated, 무시됨)")
    args = ap.parse_args()
    return run(dry_run=args.dry_run, test_only=args.test_only)


if __name__ == "__main__":
    sys.exit(main())
