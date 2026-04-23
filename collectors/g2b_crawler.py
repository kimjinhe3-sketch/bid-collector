"""나라장터 직접 크롤링 — DEPRECATED.

원 스펙: https://www.g2b.go.kr:8101/ep/tbid/tbidList.do (taskClCds=1/3/5/20)
2026-04-23 확인 시점:
  - 포트 8101 ECONNREFUSED (서버 사망)
  - /ep/tbid/* 경로 404 (사이트 개편)
  - g2b.go.kr 루트가 SSO(OIDC) 인증 요구

데이터 수집은 data.go.kr 공식 API (collectors/g2b_api.py)로 완전히 대체됩니다.
민간공고(taskClCd=20)가 필요하면 data.go.kr의
"나라장터 입찰공고정보서비스"의 민간공고 오퍼레이션(별도 API)을 검토하세요.

이 모듈은 스펙 호환을 위해 유지되며, 호출 시 빈 리스트를 반환하고 경고 로그를 남깁니다.
새로운 엔드포인트가 파악되면 이 파일을 다시 구현하세요.
"""
from __future__ import annotations

from utils.logger import get_logger

logger = get_logger("bid_collector.g2b_crawl")


def collect(*args, **kwargs) -> list[dict]:
    logger.warning(
        "g2b_crawler is deprecated: legacy endpoint "
        "(g2b.go.kr:8101/ep/tbid/tbidList.do) is unavailable. "
        "Use collectors.g2b_api (data.go.kr) instead."
    )
    return []
