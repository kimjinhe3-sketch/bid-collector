"""Check whether ALIO bidList URL with ?type=title&word=X pre-applies the search."""
from playwright.sync_api import sync_playwright

TITLE = "2026년 클라우드서비스 보안 교육 운영"
import urllib.parse
URL = f"https://www.alio.go.kr/occasional/bidList.do?type=title&word={urllib.parse.quote(TITLE[:30])}"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(locale="ko-KR",
                              user_agent="Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36")
    page = ctx.new_page()
    print(f"[1] opening: {URL}")
    page.goto(URL, wait_until="networkidle", timeout=60_000)
    page.wait_for_timeout(6000)

    # Check if search input has the value
    search_val = page.evaluate("""
        () => {
            const inputs = document.querySelectorAll('input[type=text], input:not([type])');
            return Array.from(inputs).map(i => ({name: i.name, id: i.id, value: i.value})).filter(x => x.value);
        }
    """)
    print(f"[2] inputs with values:")
    for i in (search_val or []):
        print(f"   ", i)

    rows_count = page.evaluate("() => document.querySelectorAll('table tbody tr').length")
    print(f"[3] rendered rows: {rows_count}")

    if rows_count:
        first_row_text = page.evaluate("""
            () => {
                const tr = document.querySelector('table tbody tr');
                return tr ? tr.innerText.slice(0, 200) : null;
            }
        """)
        print(f"[4] first row text:\n    {first_row_text}")

    page.screenshot(path=r"C:/Users/user/AppData/Local/Temp/alio_search_test.png", full_page=True)
    browser.close()
