@echo off
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
