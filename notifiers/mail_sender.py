"""메일 발송 추상화 — Resend (HTTP API) 또는 SMTP, 환경변수로 스위칭.

우선순위:
  1. RESEND_API_KEY 있으면 → Resend HTTP API
  2. SMTP_HOST 있으면 → SMTP (회사 메일 등)
  3. 둘 다 없으면 → dry-run (로그만, 실제 발송 X)

전환 비용 0 — IT 협의 완료 시 RESEND_API_KEY 빼고 SMTP_* 채우면 자동 SMTP.

환경변수:
  [Resend]
    RESEND_API_KEY    re_xxxx
    MAIL_FROM         "공공입찰 수집 시스템 <onboarding@resend.dev>"  (기본값 있음)
  [SMTP]
    SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASS / MAIL_FROM
"""
from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from utils.logger import get_logger

logger = get_logger("bid_collector.mail")

# Resend 무료 가입 직후엔 onboarding@resend.dev 로만 발송 가능 (도메인 인증 전).
# 도메인 인증 후 MAIL_FROM 을 자사 도메인으로 교체.
DEFAULT_FROM = "공공입찰 수집 시스템 <onboarding@resend.dev>"


def send_mail(to: str, subject: str, html: str) -> bool:
    """단일 수신자에게 HTML 메일 발송. 성공 시 True.

    우선순위: SMTP_HOST 있으면 SMTP, 없으면 Resend.
    (SMTP 가 누구에게나 발송 가능 — Gmail/Naver/사내 메일. Resend 는 도메인 인증 전 본인 주소만.)
    MAIL_PROVIDER 환경변수로 강제 지정 가능 ("smtp" | "resend").
    """
    resend_key = os.environ.get("RESEND_API_KEY")
    smtp_host = os.environ.get("SMTP_HOST")
    mail_from = os.environ.get("MAIL_FROM") or DEFAULT_FROM
    provider = (os.environ.get("MAIL_PROVIDER") or "").lower()

    if provider == "resend" and resend_key:
        return _send_resend(resend_key, mail_from, to, subject, html)
    if provider == "smtp" and smtp_host:
        return _send_smtp(smtp_host, mail_from, to, subject, html)

    # 자동 — SMTP 우선 (발송 범위 넓음), 없으면 Resend
    if smtp_host:
        return _send_smtp(smtp_host, mail_from, to, subject, html)
    if resend_key:
        return _send_resend(resend_key, mail_from, to, subject, html)

    logger.warning("[mail] no SMTP_HOST / RESEND_API_KEY — dry-run: to=%s subject=%s", to, subject)
    return False


def _send_resend(api_key: str, mail_from: str, to: str, subject: str, html: str) -> bool:
    import requests
    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={"from": mail_from, "to": [to], "subject": subject, "html": html},
            timeout=30,
        )
        if resp.status_code in (200, 201):
            return True
        logger.error("[mail:resend] %s %s — to=%s", resp.status_code, resp.text[:200], to)
        return False
    except Exception:
        logger.exception("[mail:resend] send failed to=%s", to)
        return False


def _send_smtp(host: str, mail_from: str, to: str, subject: str, html: str) -> bool:
    port = int(os.environ.get("SMTP_PORT") or 587)
    user = os.environ.get("SMTP_USER")
    pw = os.environ.get("SMTP_PASS")
    use_tls = (os.environ.get("SMTP_TLS", "1") != "0")

    msg = MIMEMultipart("alternative")
    msg["From"] = mail_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP(host, port, timeout=30) as s:
            if use_tls:
                s.starttls()
            if user and pw:
                s.login(user, pw)
            s.sendmail(_addr(mail_from), [to], msg.as_string())
        return True
    except Exception:
        logger.exception("[mail:smtp] send failed to=%s", to)
        return False


def _addr(from_field: str) -> str:
    """'name <addr@x>' → 'addr@x' 추출 (sendmail 의 envelope from 용)."""
    if "<" in from_field and ">" in from_field:
        return from_field.split("<", 1)[1].split(">", 1)[0].strip()
    return from_field.strip()
