# -*- coding: utf-8 -*-
"""구독자 일일 다이제스트 발송 — v2 그룹 세션형 이미지 메일 (2026-08-18 전면 리디자인).

구성·디자인은 scripts/digest_v2.py 참조. 이 스크립트는 오케스트레이션만:
  주말 skip → 데이터 빌드 → 이미지 렌더(실패 시 텍스트 폴백) → 구독자 루프 발송.

Usage:
    python -m scripts.send_alerts              # 전체 구독자 발송 (평일만)
    python -m scripts.send_alerts --test-only  # ADMIN_EMAIL 1명에게만 (요일 무관)
    python -m scripts.send_alerts --dry-run    # 발송 없이 빌드·렌더 점검 + 미리보기 저장

환경변수:
    DATABASE_URL             (운영 필수 — 데이터·구독자·last_sent_at)
    SMTP_* / MAIL_FROM       (Gmail SMTP — 이미지 임베드 발송)
    SITE_URL                 대시보드 base URL
    ADMIN_EMAIL              --test-only 수신자
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts import digest_v2  # noqa: E402
from notifiers.mail_sender import send_mail, send_mail_images  # noqa: E402


def _db():
    import psycopg2
    from psycopg2.extras import RealDictCursor
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        return None
    if "sslmode=" not in url:
        url = f"{url}{'&' if '?' in url else '?'}sslmode=require"
    return psycopg2.connect(url, cursor_factory=RealDictCursor)


def fetch_subscribers() -> list[dict]:
    conn = _db()
    if conn is not None:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT email, unsubscribe_token FROM bid_subscribers WHERE active = TRUE")
                return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()
    # 로컬 dry-run 폴백 (REST)
    import requests
    base = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    r = requests.get(f"{base}/rest/v1/bid_subscribers",
                     headers={"apikey": key, "Authorization": f"Bearer {key}"},
                     params={"select": "email,unsubscribe_token", "active": "eq.true"}, timeout=30)
    r.raise_for_status()
    return r.json()


def mark_sent(emails: list[str]) -> None:
    if not emails:
        return
    conn = _db()
    if conn is None:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE bid_subscribers SET last_sent_at = NOW() WHERE email = ANY(%s)", (emails,))
        conn.commit()
    finally:
        conn.close()


def run(dry_run: bool = False, test_only: bool = False) -> int:
    now = digest_v2.kst_now()
    # 주말(토5·일6) 발송 skip — 공공기관 공고 없음. test_only 는 요일 무관.
    if not test_only and not dry_run and now.weekday() >= 5:
        print(f"[send_alerts] 주말({now:%Y-%m-%d %a}) — 발송 skip")
        return 0

    print("[send_alerts] v2 다이제스트 빌드 시작")
    data = digest_v2.build_digest_data()
    blocks = digest_v2.build_blocks(data)
    subject = digest_v2.subject_line(data)
    print(f"[send_alerts] subject: {subject}")
    print(f"[send_alerts] counts: {data['counts']}")

    rendered = digest_v2.render_blocks(blocks)
    images, footer_segs = rendered if rendered else (None, None)
    mode = "image" if images else "text-fallback"
    print(f"[send_alerts] render: {mode}"
          + (f" ({sum(len(v) for v in images.values()) // 1024}KB, {len(images)}블록)" if images else ""))

    if dry_run:
        out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "digest_preview")
        os.makedirs(out, exist_ok=True)
        html = (digest_v2.compose_image_mail(blocks, "preview-token", footer_segs) if images
                else digest_v2.compose_text_mail(blocks, "preview-token"))
        open(os.path.join(out, "preview.html"), "w", encoding="utf-8").write(html)
        if images:
            for cid, b in images.items():
                open(os.path.join(out, f"{cid}.png"), "wb").write(b)
        subs = fetch_subscribers()
        print(f"[send_alerts] (dry-run) subscribers={len(subs)} mode={mode} → 미리보기 저장: {out}")
        return 0

    if test_only:
        # ADMIN_EMAIL 시크릿이 빈 문자열인 경우 방어 (or — 과거 admin-report 장애와 동일 원인)
        admin = os.environ.get("ADMIN_EMAIL") or "jihyeong.kim@kt.com"
        subs = [{"email": admin, "unsubscribe_token": "test"}]
        print(f"[send_alerts] TEST MODE → {admin} 에게만")
    else:
        subs = fetch_subscribers()
    print(f"[send_alerts] subscribers={len(subs)}")

    sent, sent_emails = 0, []
    for s in subs:
        token = s.get("unsubscribe_token") or ""
        if images:
            html = digest_v2.compose_image_mail(blocks, token, footer_segs)
            ok = send_mail_images(s["email"], subject, html, images)
            if not ok:  # 이미지 발송 불가(SMTP 미설정 등) → 텍스트 폴백
                ok = send_mail(s["email"], subject, digest_v2.compose_text_mail(blocks, token))
        else:
            ok = send_mail(s["email"], subject, digest_v2.compose_text_mail(blocks, token))
        if ok:
            sent += 1
            sent_emails.append(s["email"])
        else:
            print(f"[send_alerts] send FAILED: {s['email']}", file=sys.stderr)

    if not test_only:
        mark_sent(sent_emails)
    print(f"[send_alerts] sent={sent}/{len(subs)} mode={mode}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="발송 없이 빌드·렌더 점검")
    ap.add_argument("--test-only", action="store_true", help="ADMIN_EMAIL 1명에게만")
    ap.add_argument("--kind", help="(deprecated, 무시됨)")
    args = ap.parse_args()
    return run(dry_run=args.dry_run, test_only=args.test_only)


if __name__ == "__main__":
    sys.exit(main())
