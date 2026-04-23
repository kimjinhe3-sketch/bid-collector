"""Properly find ALIO detail URL.

Steps:
  1. Open list page, wait for Angular to render + XHR to populate rows.
  2. Use explicit wait for row anchor elements.
  3. Capture ALL XHRs and navigations during/after click.
  4. Dump HTML around a data row to see the exact click handler.
"""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "https://www.alio.go.kr/occasional/bidList.do"


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(locale="ko-KR")
    page = ctx.new_page()

    captured = []
    page.on("request", lambda r: captured.append(("REQ", r.method, r.url, r.post_data)))
    page.on("response", lambda r: captured.append(("RES", r.request.method, r.url, r.status)))
    page.on("framenavigated", lambda f: captured.append(("NAV", f.url, "", "")))

    print(f"[1] opening {URL}")
    page.goto(URL, wait_until="networkidle", timeout=60_000)
    # Wait longer for Angular + list XHR to complete
    page.wait_for_timeout(5000)

    # Give Angular plenty of time
    for attempt in range(20):
        page.wait_for_timeout(1000)
        count = page.evaluate("() => document.querySelectorAll('table tbody tr').length")
        if count > 0:
            print(f"    rows rendered after {attempt+1}s")
            break
    rows_count = page.evaluate("() => document.querySelectorAll('table tbody tr').length")
    print(f"[2] rendered rows: {rows_count}")

    # Get the HTML of the first data row
    first_row_html = page.evaluate("""
        () => {
            const tr = document.querySelector('table tbody tr');
            return tr ? tr.outerHTML : null;
        }
    """)
    print(f"\n[3] first row HTML (first 1000 chars):")
    if first_row_html:
        print(first_row_html[:1000])

    # Get all onclick/ng-click handlers in the row
    handlers = page.evaluate("""
        () => {
            const tr = document.querySelector('table tbody tr');
            if (!tr) return null;
            const els = tr.querySelectorAll('*');
            return Array.from(els).filter(el => el.getAttribute('ng-click') || el.getAttribute('onclick') || el.getAttribute('href')).map(el => ({
                tag: el.tagName,
                ngClick: el.getAttribute('ng-click'),
                onclick: el.getAttribute('onclick'),
                href: el.getAttribute('href'),
                text: (el.innerText || '').trim().slice(0, 60),
            }));
        }
    """)
    print(f"\n[4] row handlers:")
    if handlers:
        for h in handlers:
            print(f"   ", h)

    # Clear capture log before clicking
    captured.clear()

    # Try clicking — pick the <a> with text (title link)
    print(f"\n[5] clicking the title link...")
    link_selector = "table tbody tr a"
    link = page.query_selector(link_selector)
    if link:
        print(f"    link ng-click: {link.get_attribute('ng-click')!r}")
        print(f"    link onclick: {link.get_attribute('onclick')!r}")
        print(f"    link href: {link.get_attribute('href')!r}")
        link.click()
        page.wait_for_timeout(5000)
        print(f"\n[6] URL after click: {page.url}")

        print(f"\n[7] NETWORK activity during click (interesting entries):")
        for t, m, u, s in captured[-30:]:
            if "json" in u.lower() or "detail" in u.lower() or "view" in u.lower() or "bid" in u.lower() or t == "NAV":
                print(f"    {t} {m} {u}  ({s})")

    browser.close()
