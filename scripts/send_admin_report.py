"""관리자 일일 리포트 — 서비스 운영 현황을 관리자에게만 발송.

전일(어제 KST) 기준:
  - 방문자 수 (고유 visitor) / 세션 수 / 평균 체류시간
  - 알림 구독 증감 (신규 등록 - 해지) + 현재 활성 수
  - 현재 등록(활성) 이메일 목록

수신: ADMIN_EMAIL (기본 jihyeong.kim@kt.com)
발송: mail_sender (SMTP 우선)

Usage:
    python -m scripts.send_admin_report
    python -m scripts.send_admin_report --dry-run

환경변수:
    DATABASE_URL  (필수)
    ADMIN_EMAIL   (수신자, 기본 jihyeong.kim@kt.com)
    SMTP_* 또는 RESEND_API_KEY  (mail_sender 참조)
"""
from __future__ import annotations

import argparse
import os
import sys
import html as html_mod

import psycopg2
from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from notifiers.mail_sender import send_mail  # noqa: E402

# env var 가 존재하지만 빈 값이면 default arg 가 안 먹으므로 `or` 로 방어.
ADMIN_EMAIL = (os.environ.get("ADMIN_EMAIL") or "").strip() or "jihyeong.kim@kt.com"
SITE_URL = os.environ.get(
    "SITE_URL",
    "https://port-next-bidlive-korea-web-mozlrrj98331a064.sel3.cloudtype.app",
).rstrip("/")


def _db():
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("[admin_report] DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)
    if "sslmode=" not in url:
        url = f"{url}{'&' if '?' in url else '?'}sslmode=require"
    return psycopg2.connect(url, cursor_factory=RealDictCursor)


# ─────────── 집계 쿼리 (전일 KST) ───────────

SQL_VISITS = """
WITH y AS (
  SELECT *,
    EXTRACT(EPOCH FROM (last_seen_at - started_at)) AS dwell_sec
  FROM site_visits
  WHERE (started_at AT TIME ZONE 'Asia/Seoul')::date
        = ((NOW() AT TIME ZONE 'Asia/Seoul')::date - 1)
)
SELECT
  COUNT(DISTINCT visitor_id)              AS visitors,
  COUNT(DISTINCT session_id)              AS sessions,
  COALESCE(AVG(dwell_sec), 0)            AS avg_dwell_sec,
  COALESCE(MAX(dwell_sec), 0)            AS max_dwell_sec
FROM y
"""

# 시계열 비교용 — 전전일 방문자 (증감 표시)
SQL_VISITS_PREV = """
SELECT COUNT(DISTINCT visitor_id) AS visitors
FROM site_visits
WHERE (started_at AT TIME ZONE 'Asia/Seoul')::date
      = ((NOW() AT TIME ZONE 'Asia/Seoul')::date - 2)
"""

SQL_SUB_STATS = """
SELECT
  COUNT(*) FILTER (WHERE active)                                   AS active_now,
  COUNT(*) FILTER (
    WHERE (created_at AT TIME ZONE 'Asia/Seoul')::date
          = ((NOW() AT TIME ZONE 'Asia/Seoul')::date - 1))         AS new_yesterday,
  COUNT(*) FILTER (
    WHERE unsubscribed_at IS NOT NULL
      AND (unsubscribed_at AT TIME ZONE 'Asia/Seoul')::date
          = ((NOW() AT TIME ZONE 'Asia/Seoul')::date - 1))         AS churn_yesterday
FROM bid_subscribers
"""

SQL_SUB_LIST = """
SELECT email, preferences, created_at
FROM bid_subscribers
WHERE active = TRUE
ORDER BY created_at DESC
"""


def _fmt_dwell(sec: float) -> str:
    sec = int(sec or 0)
    m, s = divmod(sec, 60)
    if m >= 60:
        h, m = divmod(m, 60)
        return f"{h}시간 {m}분"
    if m:
        return f"{m}분 {s}초"
    return f"{s}초"


def _delta(cur: int, prev: int) -> str:
    d = cur - prev
    if d > 0:
        return f'<span style="color:#FE2E36;">▲ {d}</span>'
    if d < 0:
        return f'<span style="color:#2E6BFF;">▼ {abs(d)}</span>'
    return '<span style="color:#aaa;">±0</span>'


def build_report(v, vprev, sub, emails) -> tuple[str, str]:
    from datetime import datetime, timedelta
    y = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    visitors = int(v["visitors"])
    sessions = int(v["sessions"])
    avg_dwell = _fmt_dwell(v["avg_dwell_sec"])
    max_dwell = _fmt_dwell(v["max_dwell_sec"])
    prev_visitors = int(vprev["visitors"]) if vprev else 0

    active_now = int(sub["active_now"])
    new_y = int(sub["new_yesterday"])
    churn_y = int(sub["churn_yesterday"])
    net = new_y - churn_y
    net_str = (f"+{net}" if net > 0 else str(net))
    net_color = "#FE2E36" if net > 0 else ("#2E6BFF" if net < 0 else "#aaa")

    # 이메일 목록 행
    rows = ""
    for e in emails:
        al = ",".join((e.get("preferences") or {}).get("alerts") or [])
        reg = str(e.get("created_at") or "")[:10]
        rows += (
            f'<tr><td style="padding:6px 10px;border-bottom:1px solid #f0f0f0;font-size:13px;">{html_mod.escape(e["email"])}</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #f0f0f0;font-size:12px;color:#888;">{html_mod.escape(al)}</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #f0f0f0;font-size:12px;color:#aaa;">{reg}</td></tr>'
        )
    if not rows:
        rows = '<tr><td colspan="3" style="padding:12px;text-align:center;color:#aaa;">등록자 없음</td></tr>'

    subject = (
        f"[공공입찰 운영리포트] {y} — 방문 {visitors}명 / "
        f"구독 {active_now}명 (전일 {net_str})"
    )

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;background:#f5f5f5;font-family:'Apple SD Gothic Neo','Malgun Gothic',sans-serif;">
  <div style="max-width:640px;margin:0 auto;background:#fff;">
    <div style="background:#1a1a1a;padding:18px 20px;">
      <span style="color:#fff;font-size:16px;font-weight:800;">공공입찰 수집 시스템 · 운영 리포트</span>
      <div style="color:#aaa;font-size:12px;margin-top:3px;">{y} (전일) 기준 · 관리자 전용</div>
    </div>

    <!-- 방문 -->
    <div style="padding:18px 20px 6px;font-size:15px;font-weight:800;color:#1a1a1a;">📊 접속 현황</div>
    <table style="width:100%;border-collapse:collapse;">
      <tr>
        <td style="padding:8px 20px;font-size:13px;color:#444;">고유 방문자</td>
        <td style="padding:8px 20px;text-align:right;font-size:15px;font-weight:700;">
          {visitors}명 <span style="font-size:12px;">{_delta(visitors, prev_visitors)}</span>
          <span style="color:#aaa;font-size:11px;"> (전일 대비)</span>
        </td>
      </tr>
      <tr>
        <td style="padding:8px 20px;font-size:13px;color:#444;border-top:1px solid #f5f5f5;">방문 세션</td>
        <td style="padding:8px 20px;text-align:right;font-size:14px;border-top:1px solid #f5f5f5;">{sessions}회</td>
      </tr>
      <tr>
        <td style="padding:8px 20px;font-size:13px;color:#444;border-top:1px solid #f5f5f5;">평균 체류시간</td>
        <td style="padding:8px 20px;text-align:right;font-size:14px;border-top:1px solid #f5f5f5;">{avg_dwell} <span style="color:#aaa;font-size:11px;">(최대 {max_dwell})</span></td>
      </tr>
    </table>

    <!-- 구독 -->
    <div style="padding:18px 20px 6px;font-size:15px;font-weight:800;color:#1a1a1a;border-top:1px solid #eee;margin-top:8px;">✉️ 알림 구독</div>
    <table style="width:100%;border-collapse:collapse;">
      <tr>
        <td style="padding:8px 20px;font-size:13px;color:#444;">현재 활성 구독자</td>
        <td style="padding:8px 20px;text-align:right;font-size:15px;font-weight:700;">{active_now}명</td>
      </tr>
      <tr>
        <td style="padding:8px 20px;font-size:13px;color:#444;border-top:1px solid #f5f5f5;">전일 증감</td>
        <td style="padding:8px 20px;text-align:right;font-size:14px;border-top:1px solid #f5f5f5;">
          <span style="color:{net_color};font-weight:700;">{net_str}명</span>
          <span style="color:#aaa;font-size:12px;"> (신규 {new_y} · 해지 {churn_y})</span>
        </td>
      </tr>
    </table>

    <!-- 이메일 목록 -->
    <div style="padding:18px 20px 6px;font-size:15px;font-weight:800;color:#1a1a1a;border-top:1px solid #eee;margin-top:8px;">📋 등록 이메일 ({active_now}건)</div>
    <table style="width:100%;border-collapse:collapse;border-top:2px solid #1a1a1a;">
      <tr style="background:#fafafa;">
        <td style="padding:6px 10px;font-size:11px;color:#888;font-weight:700;">이메일</td>
        <td style="padding:6px 10px;font-size:11px;color:#888;font-weight:700;">알림</td>
        <td style="padding:6px 10px;font-size:11px;color:#888;font-weight:700;">등록일</td>
      </tr>
      {rows}
    </table>

    <div style="padding:16px 20px;text-align:center;border-top:1px solid #eee;">
      <a href="{SITE_URL}/bids" style="display:inline-block;background:#FE2E36;color:#fff;padding:10px 24px;border-radius:6px;text-decoration:none;font-weight:700;font-size:13px;">대시보드 열기</a>
    </div>
    <div style="padding:12px 20px;border-top:1px solid #eee;text-align:center;color:#aaa;font-size:11px;">
      매일 오전 8시 발송 · 관리자 전용 운영 리포트
    </div>
  </div>
</body></html>"""
    return subject, html


def run(dry_run: bool = False, force: bool = False) -> int:
    # 관리자 리포트는 매일 발송 (주말 포함) — 운영 모니터링 연속성.
    conn = _db()
    try:
        with conn.cursor() as cur:
            cur.execute(SQL_VISITS)
            v = cur.fetchone()
            cur.execute(SQL_VISITS_PREV)
            vprev = cur.fetchone()
            cur.execute(SQL_SUB_STATS)
            sub = cur.fetchone()
            cur.execute(SQL_SUB_LIST)
            emails = cur.fetchall()

        subject, html = build_report(v, vprev, sub, emails)
        # 발송 대상/설정 진단 로그 (secret 누락·오타 파악용)
        has_smtp = bool(os.environ.get("SMTP_HOST"))
        has_resend = bool(os.environ.get("RESEND_API_KEY"))
        print(f"[admin_report] to={ADMIN_EMAIL} smtp={has_smtp} resend={has_resend} "
              f"visitors={v['visitors']} sessions={v['sessions']} active={sub['active_now']}")

        if dry_run:
            print(f"  [dry-run] → {ADMIN_EMAIL}: {subject}")
            return 0
        if send_mail(ADMIN_EMAIL, subject, html):
            print(f"[admin_report] ✅ sent → {ADMIN_EMAIL}")
            return 0
        # 실패 시 step 을 빨강으로 (원인 파악 쉽게)
        print(f"[admin_report] ❌ send FAILED → {ADMIN_EMAIL} "
              f"(smtp={has_smtp} resend={has_resend})", file=sys.stderr)
        return 1
    finally:
        conn.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="주말에도 강제 발송 (수동 테스트)")
    args = ap.parse_args()
    return run(dry_run=args.dry_run, force=args.force)


if __name__ == "__main__":
    sys.exit(main())
