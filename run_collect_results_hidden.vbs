' BIDLIVE 개찰결과 로컬 수집 — 콘솔 창 숨김 실행
Dim sh
Set sh = CreateObject("WScript.Shell")
sh.Run """C:\Users\user\BID SEARCHING TOOL\bid_collector\run_collect_results.bat""", 0, True
