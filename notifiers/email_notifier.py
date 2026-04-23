from __future__ import annotations

import html
import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Iterable

from utils.logger import get_logger

logger = get_logger("bid_collector.email")

EOK = 100_000_000


def _fmt_amount(price: int | None) -> str:
    if price is None:
        return "-"
    if price >= EOK:
        return f"{price / EOK:,.1f}억"
    return f"{price:,}원"


def _row_html(r: dict) -> str:
    title = html.escape(r.get("title") or "")
    url = r.get("detail_url") or "#"
    title_html = f'<a href="{html.escape(url)}">{title}</a>' if url != "#" else title
    return (
        "<tr>"
        f"<td>{html.escape(str(r.get('bid_no') or ''))}</td>"
        f"<td>{title_html}</td>"
        f"<td>{html.escape(r.get('org_name') or '')}</td>"
        f"<td style='text-align:right'>{_fmt_amount(r.get('estimated_price'))}</td>"
        f"<td>{html.escape(r.get('close_date') or '')}</td>"
        f"<td>{html.escape(r.get('bid_type') or '')}</td>"
        "</tr>"
    )


def build_html(rows: Iterable[dict], title: str | None = None) -> str:
    rows = list(rows)
    subject = title or f"입찰공고 알림 ({datetime.now():%Y-%m-%d})"
    header = (
        "<tr>"
        "<th>공고번호</th><th>제목</th><th>기관</th>"
        "<th>금액</th><th>마감</th><th>업종</th>"
        "</tr>"
    )
    body_rows = "\n".join(_row_html(r) for r in rows) or (
        "<tr><td colspan='6' style='text-align:center;color:#888'>조건에 맞는 공고가 없습니다.</td></tr>"
    )
    return f"""<!DOCTYPE html>
<html><head><meta charset='utf-8'><title>{html.escape(subject)}</title>
<style>
 body {{ font-family: 'Segoe UI', sans-serif; font-size: 13px; }}
 table {{ border-collapse: collapse; width: 100%; }}
 th, td {{ border: 1px solid #ddd; padding: 6px 8px; }}
 th {{ background: #f4f4f4; }}
 tr:nth-child(even) td {{ background: #fafafa; }}
</style></head>
<body>
<h3>{html.escape(subject)} — 총 {len(rows)}건</h3>
<table>{header}{body_rows}</table>
</body></html>"""


def send_email(
    rows: Iterable[dict],
    config: dict,
    smtp_user: str | None = None,
    smtp_pass: str | None = None,
    smtp_client_factory=None,
) -> bool:
    """Send HTML email. Returns True on success.

    smtp_client_factory: optional callable (host, port) -> SMTP-like object, for tests.
    """
    rows = list(rows)
    email_cfg = config.get("email") or {}
    host = email_cfg.get("smtp_host")
    port = int(email_cfg.get("smtp_port") or 587)
    from_addr = email_cfg.get("from_addr")
    to_addrs = email_cfg.get("to_addrs") or []
    use_tls = bool(email_cfg.get("use_tls", True))

    if not host or not from_addr or not to_addrs:
        logger.error("email config incomplete: host=%s from=%s to=%s", host, from_addr, to_addrs)
        return False

    user = smtp_user or os.environ.get("SMTP_USER")
    pw = smtp_pass or os.environ.get("SMTP_PASS")

    subject = f"[입찰공고] {datetime.now():%Y-%m-%d} — {len(rows)}건"
    msg = MIMEMultipart("alternative")
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)
    msg["Subject"] = subject
    msg.attach(MIMEText(build_html(rows, title=subject), "html", "utf-8"))

    try:
        factory = smtp_client_factory or (lambda h, p: smtplib.SMTP(h, p, timeout=30))
        with factory(host, port) as s:
            if use_tls and hasattr(s, "starttls"):
                s.starttls()
            if user and pw:
                s.login(user, pw)
            s.sendmail(from_addr, to_addrs, msg.as_string())
        logger.info("email sent: %d rows -> %s", len(rows), to_addrs)
        return True
    except Exception:
        logger.exception("email send failed")
        return False
