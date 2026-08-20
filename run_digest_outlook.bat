@echo off
rem BIDLIVE 일일 다이제스트 — 이미지 렌더 + Outlook 발송 (월·수·금 08:00 작업 스케줄러)
rem python 절대경로 사용 (스케줄러 컨텍스트는 사용자 PATH 미보장)
cd /d "C:\Users\user\BID SEARCHING TOOL\bid_collector"
set PYTHONIOENCODING=utf-8
if not exist logs mkdir logs
echo [%date% %time%] digest start >> logs\digest_outlook.log
"C:\Users\user\AppData\Local\Python\pythoncore-3.14-64\python.exe" -m scripts.send_digest_outlook >> logs\digest_outlook.log 2>&1
echo [%date% %time%] digest end (exit %errorlevel%) >> logs\digest_outlook.log
