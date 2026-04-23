"""Take desktop + mobile screenshots of the running Streamlit dashboard."""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "http://localhost:8789"
OUT_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(r"C:\Users\user\AppData\Local\Temp")
OUT_DIR.mkdir(parents=True, exist_ok=True)

VIEWPORTS = [
    ("desktop", 1600, 1800),
    ("mobile", 390, 1800),  # iPhone 15 Pro width
]


def shoot(name: str, width: int, height: int):
    out = OUT_DIR / f"dashboard_{name}.png"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": width, "height": height},
            locale="ko-KR",
            device_scale_factor=2 if name == "mobile" else 1,
        )
        page = ctx.new_page()
        page.goto(URL, wait_until="networkidle", timeout=60_000)
        page.wait_for_selector("text=대한민국 입찰공고 대시보드", timeout=30_000)
        try:
            page.wait_for_function(
                "() => document.querySelectorAll('[data-testid=stSkeleton]').length === 0",
                timeout=30_000,
            )
        except Exception:
            pass
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(2000)
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(1000)
        page.screenshot(path=str(out), full_page=True)
        browser.close()
    print(f"saved: {out}")


for name, w, h in VIEWPORTS:
    shoot(name, w, h)
