"""Generate 0_최초_설치.bat + 다른PC_설치방법.txt in CP949 encoding."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PARENT = ROOT.parent

SETUP_BAT = r"""@echo off
cd /d "%~dp0"
echo ==========================================
echo   의존성 설치 (최초 1회만 실행)
echo ==========================================
echo.
where python > nul 2>&1
if errorlevel 1 (
    echo [오류] Python이 설치되어 있지 않습니다.
    echo https://www.python.org/downloads/ 에서 Python 3.11 이상 설치 후 다시 실행하세요.
    echo 설치 시 Add Python to PATH 체크박스를 꼭 켜세요.
    pause
    exit /b 1
)
python --version
echo.
echo pip 업그레이드 중...
python -m pip install --upgrade pip
echo.
echo 필수 패키지 설치 중 (수 분 소요)...
python -m pip install -r requirements.txt
echo.
if not exist .env (
    echo .env 파일이 없습니다. .env.example에서 복사합니다.
    copy .env.example .env
    echo.
    echo [필수] .env 파일을 메모장으로 열어 G2B_SERVICE_KEY에
    echo 본인의 data.go.kr 서비스키를 입력하세요.
    echo.
)
echo ==========================================
echo   설치 완료. 이제 상위 폴더의 시작.bat을 실행하세요.
echo ==========================================
pause
"""

README = """다른 PC로 옮기는 방법
=======================

1단계 - 파일 복사
  아래 두 개를 USB 또는 네트워크로 복사하세요:
    - 시작.bat
    - bid_collector 폴더 전체

  복사할 때 제외 권장 (용량만 차지):
    - bid_collector\\data\\bids.sqlite    (새 PC에서 처음부터 수집)
    - bid_collector\\logs\\               (로그)
    - bid_collector\\__pycache__\\         (캐시)
    - bid_collector\\.env                 (보안상 복사 금지, 새 PC에서 재입력)

2단계 - Python 설치 (새 PC에 Python이 없으면)
  - https://www.python.org/downloads/ 에서 Python 3.11 이상 다운로드
  - 설치할 때 "Add Python to PATH" 체크박스를 반드시 켜세요.

3단계 - 의존성 설치
  - 복사한 bid_collector 폴더에서 0_최초_설치.bat 더블클릭
  - 자동으로 pip install 실행 + .env 템플릿 생성

4단계 - API 키 입력
  - bid_collector\\.env 파일을 메모장으로 열어서
  - G2B_SERVICE_KEY= 뒤에 본인 서비스키 입력 후 저장
  - (선택) 이메일 알림 쓰려면 SMTP_USER / SMTP_PASS
  - (선택) Slack 알림 쓰려면 SLACK_WEBHOOK_URL

5단계 - 실행
  - 시작.bat 더블클릭
  - 메뉴에서 [1] 대시보드 또는 [2] 공고 수집 선택

문제가 생기면
  - Python 버전: python --version (3.11 이상이어야 함)
  - 한글 깨짐: cmd 창에서 chcp 949 입력 후 다시 실행
  - SSL 오류: truststore 패키지가 requirements.txt로 자동 설치됨
"""

(ROOT / "0_최초_설치.bat").write_text(SETUP_BAT, encoding="cp949")
(PARENT / "다른PC_설치방법.txt").write_text(README, encoding="cp949")

print(f"wrote: {ROOT / '0_최초_설치.bat'}")
print(f"wrote: {PARENT / '다른PC_설치방법.txt'}")
