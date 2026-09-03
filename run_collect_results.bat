@echo off
rem BIDLIVE local results collector (Korean IP required - g2b API blocks foreign IPs)
rem Runs --auto: recent 3 days + 5-day backfill. Scheduled weekdays 19:30.
set PYTHONIOENCODING=utf-8
cd /d "C:\Users\user\BID SEARCHING TOOL\bid_collector"
echo [%date% %time%] collect start >> logs\collect_results_local.log
"C:\Users\user\AppData\Local\Python\pythoncore-3.14-64\python.exe" -m scripts.collect_results --auto >> logs\collect_results_local.log 2>&1
echo [%date% %time%] collect end (exit %errorlevel%) >> logs\collect_results_local.log
