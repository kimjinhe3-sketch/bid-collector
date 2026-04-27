"""Playwright 모바일 시각 검증 — Streamlit 앱이 모바일에서 어떻게 보이는지
스크린샷으로 확인. 이슈 발생 시 PNG 들을 사람/AI 가 직접 확인.

사용:
  python scripts/mobile_check.py [URL]

기본 URL: https://bidlivekorea.streamlit.app
출력 디렉토리: scripts/mobile_check_output/
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

DEFAULT_URL = "https://bidlivekorea.streamlit.app"
OUT = Path(__file__).parent / "mobile_check_output"
OUT.mkdir(exist_ok=True)


def shot(target, name: str, *, full: bool = False) -> Path:
    """target 은 page 또는 frame_locator. frame 이면 frame_element 영역만 캡처."""
    p = OUT / name
    try:
        # target 이 Frame 인지 Page 인지 분기
        if hasattr(target, "frame_element"):
            # Frame 객체 — 해당 frame 의 element 영역 screenshot
            fe = target.frame_element()
            fe.screenshot(path=str(p))
        else:
            target.screenshot(path=str(p), full_page=full)
    except Exception:
        # fallback: page screenshot
        target.screenshot(path=str(p), full_page=full)
    print(f"  📸 {p.name}  ({p.stat().st_size // 1024}KB)")
    return p


def wait_for_streamlit_ready(page, timeout_ms: int = 60000) -> None:
    """Streamlit 앱이 첫 렌더 완료될 때까지 대기.
    'Yes, get this app back up!' (sleep state) 도 자동 클릭.
    """
    # Sleep state 처리 — 'Zzzz' 페이지에 wake-up 버튼이 보이면 클릭
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        try:
            wake_btn = page.get_by_role("button",
                                          name="Yes, get this app back up!")
            if wake_btn.is_visible(timeout=1500):
                print("  💤 앱이 sleep 상태 → wake up 버튼 클릭")
                wake_btn.click()
                # wake-up 후 상당한 시간 소요 (~30s)
                page.wait_for_timeout(5000)
                continue
        except Exception:
            pass
        # 실제 앱 콘텐츠 확인 (사이드바 또는 dataframe)
        try:
            if (page.locator('[data-testid="stSidebar"]').count() > 0
                or page.locator('[data-testid="stDataFrame"]').count() > 0):
                break
        except Exception:
            pass
        page.wait_for_timeout(1500)
    # 추가 대기 (캐시·CSS 안정화 + 첫 렌더 완료)
    try:
        page.wait_for_selector('[data-testid="stStatusWidget"]',
                               state="detached", timeout=10000)
    except PWTimeout:
        pass
    page.wait_for_timeout(3000)


def run(url: str) -> int:
    with sync_playwright() as p:
        # iPhone 14 Pro 프로파일 — viewport 393x852, deviceScaleFactor 3, touch
        device = p.devices["iPhone 14 Pro"]
        browser = p.chromium.launch()
        ctx = browser.new_context(**device)
        page = ctx.new_page()

        print(f"🌐 navigating: {url}")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except PWTimeout:
            print("  ⚠️ navigation timeout — continuing anyway")

        try:
            wait_for_streamlit_ready(page)
        except PWTimeout:
            print("  ⚠️ Streamlit ready timeout — continuing")

        # Streamlit Cloud 가 모바일에서 앱을 iframe(/~/+/) 으로 감쌈.
        # 진짜 app frame 을 잡아 거기서 작업.
        app_frame = next((f for f in page.frames if "/~/+/" in f.url), page)
        if app_frame is not page:
            print(f"  ↪ app iframe: {app_frame.url[:80]}")
        # frame.wait_for_selector to ensure ready
        try:
            app_frame.wait_for_selector('[data-testid="stApp"]', timeout=15000)
        except PWTimeout:
            print("  ⚠️ stApp not found in app frame")

        print("\n[1/5] 초기 진입 — 사이드바 자동 접힘 + 햄버거 보이는지")
        shot(app_frame, "01_initial_appframe.png")
        shot(page, "01_initial_wrapper.png")
        shot(page, "01_initial_full.png", full=True)

        print("\n[2/5] 햄버거 버튼 클릭 → 사이드바 펼치기")
        hamburger_selectors = [
            '[data-testid="stExpandSidebarButton"]',  # Streamlit 1.56
            '[data-testid="stSidebarCollapsedControl"]',
            '[data-testid="collapsedControl"]',
            '[data-testid="stBaseButton-headerNoPadding"]',
            '[data-testid="baseButton-headerNoPadding"]',
        ]
        clicked = False
        for sel in hamburger_selectors:
            try:
                el = app_frame.locator(sel).first
                if el.is_visible(timeout=1000):
                    el.click(timeout=2000)
                    print(f"  ✓ clicked: {sel}")
                    clicked = True
                    break
            except Exception:
                continue
        if not clicked:
            print("  ⚠️ 햄버거 버튼을 찾지 못함")
        page.wait_for_timeout(800)
        shot(app_frame, "02_sidebar_open.png")

        print("\n[3/5] 사이드바 닫기 (« 버튼) — 본문 보이기")
        close_selectors = [
            '[data-testid="stSidebarCollapseButton"]',
            'button[aria-label*="Close"]',
            'button[aria-label*="collapse"]',
        ]
        for sel in close_selectors:
            try:
                el = app_frame.locator(sel).first
                if el.is_visible(timeout=500):
                    el.click(timeout=1500)
                    print(f"  ✓ closed: {sel}")
                    break
            except Exception:
                continue
        page.wait_for_timeout(800)
        shot(page, "03_sidebar_closed.png")

        print("\n[4/5] 표 영역까지 스크롤 + 표 자체 캡처")
        try:
            df = app_frame.locator('[data-testid="stDataFrame"]').first
            df.scroll_into_view_if_needed(timeout=5000)
            page.wait_for_timeout(500)
            shot(page, "04_table_view.png")
            shot(page, "04_table_full.png", full=True)
        except Exception as e:
            print(f"  ⚠️ 표 스크롤 실패: {e}")

        print("\n[5/5] 표 위에서 세로 스와이프 시뮬레이션 (페이지 스크롤 검증)")
        try:
            df = app_frame.locator('[data-testid="stDataFrame"]').first
            box = df.bounding_box()
            if box:
                cx = box["x"] + box["width"] / 2
                start_y = box["y"] + box["height"] * 0.6
                end_y = box["y"] + box["height"] * 0.1
                # touch_screen.tap 만 있고 swipe API 가 없어 mouse 로 대체
                # (모바일 viewport 이라 touch event 로 디스패치됨)
                page.mouse.move(cx, start_y)
                page.mouse.down()
                # 점진적 이동 (관성 스크롤 트리거)
                steps = 20
                for i in range(1, steps + 1):
                    y = start_y + (end_y - start_y) * (i / steps)
                    page.mouse.move(cx, y, steps=2)
                    page.wait_for_timeout(20)
                page.mouse.up()
                page.wait_for_timeout(800)
                shot(page, "05_after_swipe.png")
                # 페이지가 실제로 스크롤됐는지 확인
                scroll_y = page.evaluate("window.scrollY")
                print(f"  → window.scrollY = {scroll_y}px (>0 이면 페이지 스크롤 동작)")
        except Exception as e:
            print(f"  ⚠️ 스와이프 검증 실패: {e}")

        # JS 패치 설치 여부 (app frame 기준)
        try:
            patched = app_frame.evaluate(
                "typeof window.__bidTouchCleanup === 'function'")
        except Exception:
            patched = False
        print(f"\n🔧 JS touch fix installed: {patched}")

        # 사이드바 토글 진단 (count + visibility)
        print("\n🔍 사이드바 toggle 진단:")
        for sel in hamburger_selectors + close_selectors:
            try:
                count = app_frame.locator(sel).count()
                visible = (app_frame.locator(sel).first.is_visible(timeout=200)
                           if count else False)
                if count:
                    print(f"  {sel}: count={count} visible={visible}")
            except Exception as e:
                pass

        # 페이지 내 모든 data-testid 덤프 — 사이드바 관련 자식 검색
        print("\n🔍 sidebar/header 관련 testid 덤프:")
        testids = app_frame.evaluate("""
          () => {
            const els = document.querySelectorAll('[data-testid]');
            const out = {};
            els.forEach(el => {
              const t = el.getAttribute('data-testid');
              if (!t) return;
              if (/sidebar|header|collaps|toolbar|menu|drawer/i.test(t)) {
                if (!(t in out)) {
                  const r = el.getBoundingClientRect();
                  const cs = getComputedStyle(el);
                  out[t] = {
                    count: 1,
                    visible: cs.display !== 'none' && cs.visibility !== 'hidden',
                    rect: [Math.round(r.x), Math.round(r.y),
                           Math.round(r.width), Math.round(r.height)],
                    display: cs.display,
                    transform: cs.transform === 'none' ? '' : cs.transform,
                  };
                } else {
                  out[t].count++;
                }
              }
            });
            return out;
          }
        """)
        for k, v in sorted(testids.items()):
            print(f"  {k}: {v}")

        browser.close()
        print(f"\n✅ Done. 스크린샷: {OUT}")
        return 0


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    sys.exit(run(url))
