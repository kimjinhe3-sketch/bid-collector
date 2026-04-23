@echo off
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
