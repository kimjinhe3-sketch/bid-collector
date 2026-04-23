@echo off
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
