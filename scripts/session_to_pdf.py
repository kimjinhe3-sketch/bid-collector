"""Claude Code 세션 JSONL → 한 개 PDF로 합치기.

사용법:
  python scripts/session_to_pdf.py                  # 전체 자동 (최근 2개 세션 합침)
  python scripts/session_to_pdf.py out.pdf          # 출력 경로 지정
  python scripts/session_to_pdf.py out.pdf *.jsonl  # 특정 JSONL들만
"""
from __future__ import annotations

import glob
import html
import json
import sys
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright


# ── Claude Code 세션 디렉터리 ──────────────────────────────
HOME = Path.home()
# 현재 작업 디렉터리의 프로젝트 slug를 찾아 세션 경로 구성
# (예: C:\Users\user\Downloads\연락처 → C--Users-user-Downloads----)
SESSIONS_DIR = HOME / ".claude" / "projects"


def discover_jsonl_files() -> list[Path]:
    """가장 최근 프로젝트 폴더의 JSONL 파일들 (시간순)을 반환."""
    if not SESSIONS_DIR.exists():
        return []
    # Find all project folders, sort by most recent modification
    project_dirs = sorted(
        [p for p in SESSIONS_DIR.iterdir() if p.is_dir()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not project_dirs:
        return []
    # Latest project's JSONL files (most recent first)
    files = sorted(
        project_dirs[0].glob("*.jsonl"),
        key=lambda p: p.stat().st_mtime,
    )
    return files


def load_messages(jsonl_files: list[Path]) -> list[dict]:
    """여러 JSONL에서 메시지들을 순서대로 합쳐 반환."""
    msgs: list[dict] = []
    for f in jsonl_files:
        with open(f, encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    msgs.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return msgs


def render_html(msgs: list[dict]) -> str:
    """간단한 HTML로 변환."""
    parts = ["""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>Claude Code Session</title>
<style>
  @page { size: A4; margin: 18mm 16mm; }
  body {
    font-family: -apple-system, "SF Pro Display", "Pretendard Variable", Pretendard,
                 "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
    font-size: 10.5pt; line-height: 1.5; color: #1d1d1f;
    background: #fff;
  }
  h1 { font-size: 16pt; border-bottom: 1px solid #86868b; padding-bottom: 6px; }
  .meta { color: #86868b; font-size: 9pt; margin-bottom: 16pt; }
  .msg { margin: 0 0 12pt 0; padding: 10pt 12pt; border-radius: 8px; break-inside: avoid; }
  .msg.user { background: #eef3ff; border-left: 3px solid #0071e3; }
  .msg.assistant { background: #f5f5f7; border-left: 3px solid #34c759; }
  .msg.tool { background: #fafafa; border-left: 3px solid #ff9500; font-size: 9pt; }
  .role { font-weight: 600; font-size: 9pt; color: #86868b;
          text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 4pt; }
  pre, code { font-family: "SF Mono", Consolas, "D2Coding", monospace;
              font-size: 9pt; background: #f0f0f2; padding: 2pt 4pt; border-radius: 4px; }
  pre { padding: 8pt 10pt; white-space: pre-wrap; word-wrap: break-word; }
  .tool-name { color: #ff9500; font-weight: 600; }
</style>
</head>
<body>
"""]
    parts.append(f"<h1>Claude Code 세션 기록</h1>")
    parts.append(f"<div class='meta'>생성: {datetime.now():%Y-%m-%d %H:%M} · 메시지 {len(msgs):,}개</div>")

    for m in msgs:
        mtype = m.get("type", "")
        if mtype == "user":
            content = m.get("message", {}).get("content", "")
            if isinstance(content, list):
                # tool result
                text_parts = []
                for c in content:
                    if isinstance(c, dict):
                        if c.get("type") == "text":
                            text_parts.append(c.get("text", ""))
                        elif c.get("type") == "tool_result":
                            # Summarize tool result briefly
                            r = c.get("content", "")
                            if isinstance(r, list):
                                r = "\n".join(str(x.get("text", "")) if isinstance(x, dict) else str(x) for x in r)
                            text_parts.append(f"[tool_result] {str(r)[:500]}")
                content = "\n\n".join(text_parts)
            if isinstance(content, str) and content.strip():
                parts.append(f"<div class='msg user'><div class='role'>User</div>"
                             f"<pre>{html.escape(content)}</pre></div>")
        elif mtype == "assistant":
            content = m.get("message", {}).get("content", [])
            if isinstance(content, list):
                for c in content:
                    if not isinstance(c, dict):
                        continue
                    if c.get("type") == "text":
                        txt = c.get("text", "")
                        if txt.strip():
                            parts.append(f"<div class='msg assistant'><div class='role'>Claude</div>"
                                         f"<pre>{html.escape(txt)}</pre></div>")
                    elif c.get("type") == "tool_use":
                        name = c.get("name", "?")
                        inp = c.get("input", {})
                        # Condense long input
                        inp_str = json.dumps(inp, ensure_ascii=False)[:400]
                        parts.append(f"<div class='msg tool'><div class='role'>"
                                     f"Tool · <span class='tool-name'>{html.escape(name)}</span></div>"
                                     f"<pre>{html.escape(inp_str)}</pre></div>")

    parts.append("</body></html>")
    return "".join(parts)


def html_to_pdf(html_str: str, out_path: Path):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(locale="ko-KR")
        page = ctx.new_page()
        page.set_content(html_str, wait_until="networkidle")
        page.pdf(path=str(out_path), format="A4",
                 margin={"top": "18mm", "bottom": "18mm",
                         "left": "16mm", "right": "16mm"},
                 print_background=True)
        browser.close()


def main():
    args = sys.argv[1:]
    if args and args[0].endswith(".pdf"):
        out_path = Path(args[0])
        jsonl_args = args[1:]
    else:
        out_path = Path(f"claude_session_{datetime.now():%Y%m%d_%H%M%S}.pdf")
        jsonl_args = args

    if jsonl_args:
        files = [Path(p) for pat in jsonl_args for p in glob.glob(pat)]
    else:
        files = discover_jsonl_files()

    if not files:
        print("❌ JSONL 파일을 찾지 못했습니다.")
        print(f"   세션 디렉터리: {SESSIONS_DIR}")
        sys.exit(1)

    print(f"📂 세션 파일 {len(files)}개:")
    for f in files:
        print(f"   - {f}")

    msgs = load_messages(files)
    print(f"💬 메시지 {len(msgs):,}개 로드됨")

    print("🖨️  HTML 렌더링 + PDF 생성 중...")
    html_str = render_html(msgs)
    html_to_pdf(html_str, out_path)

    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"✅ 완료: {out_path.resolve()} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
