# -*- coding: utf-8 -*-
"""일일 다이제스트 — 이미지 모드 · 사내 Outlook 발신 (이 PC 로컬 실행 전용).

배경(2026-08-19): Gmail 외부발신은 사내 아웃룩이 이미지를 차단하고, 텍스트(VML)는
워드엔진이 레이아웃을 깨뜨림 → 내부(Outlook) 발신 + 이미지 임베드가 유일하게
디자인(라운드·Pretendard)이 100% 보장되는 경로.

구성: digest_v2 의 데이터·블록·렌더 재사용 → Outlook COM 으로 구독자별 발송.
      이미지(CID) 는 공용, 구독해지 링크만 수신자별.

Usage (이 PC, Outlook 로그인 상태):
    python -m scripts.send_digest_outlook --test-only   # 관리자 1명에게만
    python -m scripts.send_digest_outlook --dry-run     # 발송 없이 렌더 점검
    python -m scripts.send_digest_outlook               # 전체 구독자 (평일만)

스케줄: Windows 작업 스케줄러 평일 08:00 (등록은 별도 — 인수인계 문서 참조)
전제: .env 에 SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY / SITE_URL
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT, ".env"))

from scripts import digest_v2  # noqa: E402


def fetch_subscribers() -> list[dict]:
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
    import requests
    from datetime import datetime, timezone
    base = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    now = datetime.now(timezone.utc).isoformat()
    # in.(...) 필터 — 이메일에 콤마가 없다는 전제 (등록 검증상 안전)
    emails_q = ",".join(f'"{e}"' for e in emails)
    r = requests.patch(f"{base}/rest/v1/bid_subscribers",
                       headers={"apikey": key, "Authorization": f"Bearer {key}",
                                "Content-Type": "application/json", "Prefer": "return=minimal"},
                       params={"email": f"in.({emails_q})"},
                       json={"last_sent_at": now}, timeout=30)
    if r.status_code >= 300:
        print(f"[digest-outlook] last_sent_at 갱신 실패: {r.status_code}", file=sys.stderr)


def send_via_outlook(to: str, subject: str, html: str, images: dict[str, bytes], tmpdir: str) -> bool:
    """Outlook COM 발송 — PNG 를 임시파일로 저장 후 CID 첨부."""
    import win32com.client
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        mail = outlook.CreateItem(0)
        mail.To = to
        mail.Subject = subject
        for cid, data in images.items():
            path = os.path.join(tmpdir, f"{cid}.png")
            if not os.path.exists(path):
                with open(path, "wb") as f:
                    f.write(data)
            att = mail.Attachments.Add(path)
            att.PropertyAccessor.SetProperty(
                "http://schemas.microsoft.com/mapi/proptag/0x3712001F", cid)
            att.PropertyAccessor.SetProperty(
                "http://schemas.microsoft.com/mapi/id/{00062008-0000-0000-C000-000000000046}/8514000B", True)
        mail.HTMLBody = html
        mail.Send()
        return True
    except Exception as e:
        print(f"[digest-outlook] send failed to={to}: {e}", file=sys.stderr)
        return False


def run(dry_run: bool = False, test_only: bool = False) -> int:
    import tempfile

    now = digest_v2.kst_now()
    if not test_only and not dry_run and now.weekday() >= 5:
        print(f"[digest-outlook] 주말({now:%Y-%m-%d %a}) — 발송 skip")
        return 0

    print("[digest-outlook] 빌드 시작")
    data = digest_v2.build_digest_data()
    blocks = digest_v2.build_blocks(data)
    subject = digest_v2.subject_line(data)
    print(f"[digest-outlook] subject: {subject}")
    print(f"[digest-outlook] counts: {data['counts']}")

    rendered = digest_v2.render_blocks(blocks)
    if not rendered:
        print("[digest-outlook] 렌더 실패 — 발송 중단 (이미지 모드 전용)", file=sys.stderr)
        return 1
    images, footer_segs = rendered
    print(f"[digest-outlook] render: {sum(len(v) for v in images.values()) // 1024}KB, {len(images)}블록")

    if dry_run:
        out = os.path.join(ROOT, "data", "digest_preview")
        os.makedirs(out, exist_ok=True)
        html = digest_v2.compose_image_mail(blocks, "preview-token", footer_segs)
        open(os.path.join(out, "preview_outlook.html"), "w", encoding="utf-8").write(html)
        subs = fetch_subscribers()
        print(f"[digest-outlook] (dry-run) subscribers={len(subs)} → 미리보기: {out}")
        return 0

    if test_only:
        admin = os.environ.get("ADMIN_EMAIL") or "jihyeong.kim@kt.com"
        subs = [{"email": admin, "unsubscribe_token": "test"}]
        print(f"[digest-outlook] TEST MODE → {admin} 에게만")
    else:
        subs = fetch_subscribers()
    print(f"[digest-outlook] subscribers={len(subs)}")

    sent, sent_emails = 0, []
    with tempfile.TemporaryDirectory() as td:
        for s in subs:
            token = s.get("unsubscribe_token") or ""
            html = digest_v2.compose_image_mail(blocks, token, footer_segs)
            if send_via_outlook(s["email"], subject, html, images, td):
                sent += 1
                sent_emails.append(s["email"])
            time.sleep(0.3)  # Outlook 큐 과부하 방지

    if not test_only:
        mark_sent(sent_emails)
    print(f"[digest-outlook] sent={sent}/{len(subs)}")
    return 0 if sent == len(subs) else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--test-only", action="store_true")
    args = ap.parse_args()
    return run(dry_run=args.dry_run, test_only=args.test_only)


if __name__ == "__main__":
    sys.exit(main())
