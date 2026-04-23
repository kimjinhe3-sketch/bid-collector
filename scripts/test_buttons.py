"""Click the 전체/해제/필터 기본값 buttons to reproduce potential widget-state errors."""
from playwright.sync_api import sync_playwright

URL = "http://localhost:8789"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1600, "height": 1000}, locale="ko-KR")
    page = ctx.new_page()
    page.goto(URL, wait_until="networkidle", timeout=60_000)
    page.wait_for_selector("text=국내 입찰공고 현황", timeout=30_000)
    page.wait_for_timeout(3000)

    for btn_text in ["전체", "해제", "↩️ 필터 기본값"]:
        try:
            btn = page.get_by_role("button", name=btn_text, exact=False).first
            btn.click()
            page.wait_for_timeout(2000)
            # Check for error
            errors = page.locator("[data-testid='stException']").all()
            if errors:
                err_text = errors[0].inner_text()[:300]
                print(f"❌ '{btn_text}' 클릭 후 에러:\n  {err_text}")
            else:
                print(f"✅ '{btn_text}' 클릭 OK")
        except Exception as e:
            print(f"⚠️ '{btn_text}' 클릭 실패: {e}")

    browser.close()
