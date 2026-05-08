"""DB 백엔드 dispatch.

DATABASE_URL 환경변수가 있으면 Postgres (Supabase) 백엔드,
없으면 SQLite 백엔드를 사용한다. 모든 함수는 두 백엔드의 동일 함수에
그대로 위임 — 호출자 코드는 변경 없음.

실행 시점에 환경변수를 확인하므로 .env 로드 이후라면 자동 분기.
"""
from __future__ import annotations

import os


def _is_postgres() -> bool:
    url = os.environ.get("DATABASE_URL", "")
    return url.startswith(("postgres://", "postgresql://"))


def _backend():
    """매 호출마다 평가 — env 가 .env 로드 이후 세팅되는 경우 대응."""
    if _is_postgres():
        from db import _postgres as backend
    else:
        from db import _sqlite as backend
    return backend


# Public API — 두 백엔드 공통 시그니처를 그대로 노출
def init_db(db_path):              return _backend().init_db(db_path)
def upsert_bids(db_path, rows):    return _backend().upsert_bids(db_path, rows)
def get_unnotified(db_path):       return _backend().get_unnotified(db_path)
def mark_notified(db_path, ids):   return _backend().mark_notified(db_path, ids)

def count_by_source(db_path, since_date=None):
    return _backend().count_by_source(db_path, since_date=since_date)

def fetch_for_dashboard(db_path, **kwargs):
    return _backend().fetch_for_dashboard(db_path, **kwargs)

def daily_counts(db_path, days=30):
    return _backend().daily_counts(db_path, days=days)
