@echo off
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
