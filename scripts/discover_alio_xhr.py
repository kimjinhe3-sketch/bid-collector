"""Open ALIO bidList page with Playwright and capture any XHR/fetch requests
that return JSON. Print their URLs, methods, params, and a response preview.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "https://www.alio.go.kr/occasional/bidList.do"
OUT_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tests/fixtures")
OUT_DIR.mkdir(parents=True, exist_ok=True)

captured: list[dict] = []


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(locale="ko-KR",
                              user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    page = ctx.new_page()

    def on_response(resp):
        try:
            ct = resp.headers.get("content-type", "")
            if "json" in ct.lower():
                try:
                    body = resp.json()
                except Exception:
                    body = None
                captured.append({
                    "url": resp.url,
                    "method": resp.request.method,
                    "status": resp.status,
                    "post_data": resp.request.post_data,
                    "body_preview": json.dumps(body, ensure_ascii=False)[:600] if body else resp.text()[:600],
                    "body_full": body,
                })
        except Exception as e:
            print(f"  (capture error: {e})", flush=True)

    page.on("response", on_response)
    print(f"[alio] navigating to {URL}", flush=True)
    page.goto(URL, wait_until="networkidle", timeout=60_000)
    page.wait_for_timeout(3000)
    browser.close()

print(f"\n[alio] captured {len(captured)} JSON responses:")
for i, c in enumerate(captured):
    print(f"\n--- [{i}] {c['method']} {c['url']}  → {c['status']}")
    if c["post_data"]:
        print(f"    POST body: {c['post_data'][:400]}")
    print(f"    response preview: {c['body_preview']}")

# Save any response that looks like a bid list (has >0 rows/items)
saved = 0
for i, c in enumerate(captured):
    body = c.get("body_full")
    if not body:
        continue
    if isinstance(body, dict):
        total = body.get("totalCount") or body.get("total") or 0
        rows_field = None
        for key in ("list", "resultList", "items", "data", "rows"):
            if isinstance(body.get(key), list) and body[key]:
                rows_field = key
                break
        if rows_field or (isinstance(total, int) and total > 0):
            fn = OUT_DIR / f"alio_xhr_{i}.json"
            fn.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"\n[save] {fn} (rows_field={rows_field}, total={total})")
            saved += 1

print(f"\n[alio] saved {saved} fixture(s) to {OUT_DIR}")
