' 콘솔 창 없이 배치 실행 — 창이 닫혀 작업이 죽는 문제 방지 (2026-08-20)
Set sh = CreateObject("WScript.Shell")
sh.Run """C:\Users\user\BID SEARCHING TOOL\bid_collector\run_digest_outlook.bat""", 0, True
