@echo off
rem BIDLIVE 일일 다이제스트 — 이미지 렌더 + Outlook 발송 (평일 08:00 작업 스케줄러)
cd /d "C:\Users\user\BID SEARCHING TOOL\bid_collector"
set PYTHONIOENCODING=utf-8
if not exist logs mkdir logs
python -m scripts.send_digest_outlook >> logs\digest_outlook.log 2>&1
