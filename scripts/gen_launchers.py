"""Generate .bat launcher files in CP949 (Korean Windows default) so cmd.exe
displays Korean text correctly without relying on UTF-8 + chcp gymnastics."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # bid_collector/
PARENT = ROOT.parent                            # BID SEARCHING TOOL/


DASHBOARD = r"""@echo off
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo ==========================================
echo   입찰공고 대시보드 기동 중...
echo   브라우저가 자동으로 열립니다.
echo   종료: 이 창에서 Ctrl+C
echo ==========================================
echo.
python -m streamlit run dashboard/app.py
echo.
echo 종료되었습니다. 아무 키나 누르면 창이 닫힙니다.
pause > nul
"""

COLLECT = r"""@echo off
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo ==========================================
echo   어제자 입찰공고를 수집합니다.
echo   약 2~3분 소요.
echo ==========================================
echo.
python main.py --collect-only
echo.
echo [완료] 아무 키나 누르면 창이 닫힙니다.
pause > nul
"""

PREVIEW = r"""@echo off
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo ==========================================
echo   오늘 알림 전송 대상 공고 미리보기
echo   (실제 이메일/Slack 발송은 안 됩니다)
echo ==========================================
echo.
python main.py --notify-only --dry-run
echo.
echo [완료] 아무 키나 누르면 창이 닫힙니다.
pause > nul
"""

SCHEDULE = r"""@echo off
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo ==========================================
echo   자동 스케줄러 시작
echo   매일 08:00 수집, 08:30 알림
echo   (이 창이 켜져 있어야 동작합니다)
echo   종료: Ctrl+C
echo ==========================================
echo.
python main.py
echo.
echo 스케줄러 종료. 아무 키나 누르면 창이 닫힙니다.
pause > nul
"""

MENU = r"""@echo off
cd /d "%~dp0bid_collector"
set PYTHONIOENCODING=utf-8

:MENU
cls
echo.
echo    =========================================================
echo           대한민국 입찰공고 수집 툴
echo    =========================================================
echo.
echo      [1] 대시보드 열기              (브라우저에서 현황 보기)
echo      [2] 오늘 공고 수집              (약 2~3분)
echo      [3] 알림 미리보기               (dry-run)
echo      [4] 자동 스케줄러 시작          (매일 08:00 자동)
echo.
echo      [0] 종료
echo.
echo    =========================================================
set /p choice=    원하시는 번호를 입력하세요:

if "%choice%"=="1" goto DASHBOARD
if "%choice%"=="2" goto COLLECT
if "%choice%"=="3" goto PREVIEW
if "%choice%"=="4" goto SCHEDULE
if "%choice%"=="0" goto END
goto MENU

:DASHBOARD
cls
echo 대시보드 기동 중... 브라우저가 자동으로 열립니다.
echo 종료하려면 이 창에서 Ctrl+C를 누르세요.
echo.
python -m streamlit run dashboard/app.py
goto END

:COLLECT
cls
echo 어제자 입찰공고를 수집합니다...
echo.
python main.py --collect-only
echo.
echo [완료] 아무 키나 누르면 메뉴로 돌아갑니다.
pause > nul
goto MENU

:PREVIEW
cls
echo 알림 전송 대상 공고 미리보기 (실제 발송 안됨)...
echo.
python main.py --notify-only --dry-run
echo.
echo [완료] 아무 키나 누르면 메뉴로 돌아갑니다.
pause > nul
goto MENU

:SCHEDULE
cls
echo 자동 스케줄러 시작. 매일 08:00 수집, 08:30 알림.
echo 종료: Ctrl+C
echo.
python main.py
goto END

:END
echo.
echo 종료합니다.
timeout /t 2 > nul
"""

FILES = [
    (ROOT / "1_대시보드_열기.bat", DASHBOARD),
    (ROOT / "2_오늘_공고_수집.bat", COLLECT),
    (ROOT / "3_알림_미리보기.bat", PREVIEW),
    (ROOT / "4_자동_스케줄러_시작.bat", SCHEDULE),
    (PARENT / "시작.bat", MENU),
]

for path, content in FILES:
    # CP949 is the default code page on Korean Windows — cmd.exe reads .bat
    # files in the active code page, so saving in CP949 avoids garbled Korean.
    path.write_text(content, encoding="cp949")
    print(f"wrote (cp949): {path}")

print(f"\nDone. {len(FILES)} launcher files created.")
