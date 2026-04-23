@echo off
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
