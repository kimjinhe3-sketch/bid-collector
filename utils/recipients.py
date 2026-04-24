"""메일링 수신자 목록 CRUD (로컬 JSON 파일).

영구 저장 경로: ``data/recipients.json`` — 사용자가 대시보드에서 추가/삭제한 이메일.
config.yaml의 ``notifier.email.to_addrs`` 와 합쳐서 실제 발송 대상이 됨 (merge).

Streamlit Cloud는 filesystem이 ephemeral이지만 세션 내엔 유지됨. 영구 보관을
원하면 config.yaml 또는 st.secrets 에 추가.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

RECIPIENTS_FILE = Path(__file__).resolve().parent.parent / "data" / "recipients.json"
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def is_valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match((email or "").strip()))


def load(path: Path = RECIPIENTS_FILE) -> list[str]:
    """저장된 수신자 목록 읽기. 파일 없거나 깨지면 빈 리스트."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [str(e).strip() for e in data if isinstance(e, str) and e.strip()]
    except (json.JSONDecodeError, OSError):
        pass
    return []


def save(emails: list[str], path: Path = RECIPIENTS_FILE) -> None:
    """수신자 목록 저장 (중복 제거 + 정렬)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    uniq = sorted({e.strip() for e in emails if isinstance(e, str) and e.strip()})
    path.write_text(json.dumps(uniq, ensure_ascii=False, indent=2), encoding="utf-8")


def add(email: str, path: Path = RECIPIENTS_FILE) -> bool:
    """이메일 추가. 형식 유효 + 중복 아니면 True 리턴 후 저장."""
    email = (email or "").strip()
    if not is_valid_email(email):
        return False
    current = load(path)
    if email in current:
        return False
    current.append(email)
    save(current, path)
    return True


def remove(email: str, path: Path = RECIPIENTS_FILE) -> bool:
    """이메일 삭제. 존재하면 True."""
    email = (email or "").strip()
    current = load(path)
    if email not in current:
        return False
    current = [e for e in current if e != email]
    save(current, path)
    return True


def resolve_to_addrs(config: dict, path: Path = RECIPIENTS_FILE) -> list[str]:
    """config.yaml의 to_addrs + 사용자 편집 recipients.json 의 합집합."""
    cfg_list = ((config or {}).get("notifier") or {}).get("email", {}).get("to_addrs") or []
    stored = load(path)
    merged = []
    seen = set()
    for e in list(cfg_list) + stored:
        e = (e or "").strip()
        if e and e not in seen and is_valid_email(e):
            seen.add(e)
            merged.append(e)
    return merged
