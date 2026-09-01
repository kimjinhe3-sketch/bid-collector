@echo off
rem BIDLIVE AI performance report - admin only, weekdays 08:30 (Task Scheduler)
cd /d "C:\Users\user\BID SEARCHING TOOL\bid_collector"
set PYTHONIOENCODING=utf-8
echo [%date% %time%] ai-report start >> logs\ai_report.log
"C:\Users\user\AppData\Local\Python\pythoncore-3.14-64\python.exe" -m scripts.send_ai_report >> logs\ai_report.log 2>&1
echo [%date% %time%] ai-report end (exit %errorlevel%) >> logs\ai_report.log
