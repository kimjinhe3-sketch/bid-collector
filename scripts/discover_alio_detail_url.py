"""Simpler: render ALIO list, dump a snippet of the rendered tbody,
then click a row and see what URL we land on."""
from playwright.sync_api import sync_playwright
from pathlib import Path

URL = "https://www.alio.go.kr/occasional/bidList.do"


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(locale="ko-KR")
    page = ctx.new_page()
    print(f"[1] opening {URL}")
    page.goto(URL, wait_until="networkidle", timeout=60_000)
    page.wait_for_timeout(4000)

    # Save full rendered HTML for inspection
    html = page.content()
    Path("C:/Users/user/AppData/Local/Temp/alio_rendered.html").write_text(html, encoding="utf-8")
    print(f"[2] saved rendered HTML ({len(html)} chars) to C:/Users/user/AppData/Local/Temp/alio_rendered.html")

    # Look for tbody
    tbody_html = page.evaluate("() => document.querySelector('tbody')?.outerHTML || ''")
    if tbody_html:
        snippet = tbody_html[:3000]
        Path("C:/Users/user/AppData/Local/Temp/alio_tbody.html").write_text(tbody_html, encoding="utf-8")
        print(f"[3] tbody snippet (first 3k):")
        print(snippet)

    # Try clicking first data row
    print(f"\n[4] Attempting click on first row...")
    first_row = page.query_selector("tbody tr")
    if first_row:
        txt = first_row.inner_text()[:80]
        print(f"    row text: {txt!r}")
        first_row.click()
        page.wait_for_timeout(4000)
        print(f"    AFTER CLICK URL: {page.url}")
        # After click, did a modal or new panel appear? Dump URL + visible HTML sample
        visible = page.evaluate("""
            () => {
                const modals = document.querySelectorAll('.modal, .layer, [class*=popup], [class*=detail], [ng-show], [ng-if]');
                const visibleOnes = Array.from(modals).filter(el => {
                    const s = getComputedStyle(el);
                    return s.display !== 'none' && s.visibility !== 'hidden' && el.offsetWidth > 0;
                });
                return visibleOnes.slice(0, 3).map(el => ({
                    tag: el.tagName,
                    cls: el.className,
                    inner: (el.innerText || '').slice(0, 300),
                }));
            }
        """)
        print(f"    visible popup/modal elements: {visible}")

    browser.close()
