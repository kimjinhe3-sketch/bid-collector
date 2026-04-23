from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Callable, Iterable

from utils.logger import get_logger

logger = get_logger("bid_collector.slack")

EOK = 100_000_000
MAX_ROWS_IN_BLOCKS = 20


def _fmt_amount(price: int | None) -> str:
    if price is None:
        return "-"
    if price >= EOK:
        return f"{price / EOK:,.1f}억"
    return f"{price:,}원"


def build_blocks(rows: list[dict]) -> list[dict]:
    header = {
        "type": "header",
        "text": {"type": "plain_text", "text": f"입찰공고 {datetime.now():%Y-%m-%d} — {len(rows)}건"},
    }
    blocks: list[dict] = [header, {"type": "divider"}]
    shown = rows[:MAX_ROWS_IN_BLOCKS]
    for r in shown:
        title = r.get("title") or ""
        url = r.get("detail_url")
        if url:
            headline = f"*<{url}|{title}>*"
        else:
            headline = f"*{title}*"
        line = (
            f"{headline}\n"
            f"`{r.get('bid_no','')}` · {r.get('org_name','-')} · "
            f"{_fmt_amount(r.get('estimated_price'))} · 마감 {r.get('close_date','-')} · {r.get('bid_type','-')}"
        )
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": line}})

    if len(rows) > MAX_ROWS_IN_BLOCKS:
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"외 {len(rows) - MAX_ROWS_IN_BLOCKS}건 (대시보드 확인)"}
                ],
            }
        )
    return blocks


def send_slack(
    rows: Iterable[dict],
    config: dict,
    webhook_url: str | None = None,
    post_fn: Callable | None = None,
) -> bool:
    rows = list(rows)
    slack_cfg = config.get("slack") or {}
    env_key = slack_cfg.get("webhook_url_env") or "SLACK_WEBHOOK_URL"
    url = webhook_url or os.environ.get(env_key)
    if not url:
        logger.error("slack webhook URL missing (env=%s)", env_key)
        return False

    payload = {
        "text": f"입찰공고 알림 — {len(rows)}건",
        "blocks": build_blocks(rows),
    }

    try:
        if post_fn is None:
            import requests
            resp = requests.post(url, data=json.dumps(payload),
                                 headers={"Content-Type": "application/json"}, timeout=15)
            ok = resp.status_code < 300
            if not ok:
                logger.error("slack webhook returned %d: %s", resp.status_code, resp.text[:200])
            else:
                logger.info("slack sent: %d rows", len(rows))
            return ok
        else:
            post_fn(url, payload)
            logger.info("slack (test) posted: %d rows", len(rows))
            return True
    except Exception:
        logger.exception("slack send failed")
        return False
