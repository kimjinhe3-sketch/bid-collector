"""Smoke test: hit real data.go.kr API with a small page size and print a sample."""
from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from utils.logger import setup_logger
from collectors import g2b_api

setup_logger(level="INFO")

KEY = os.environ.get("G2B_SERVICE_KEY")
if not KEY:
    raise SystemExit("G2B_SERVICE_KEY not set in .env")

print(f"[smoke] key loaded (len={len(KEY)})")

rows = g2b_api.collect_all(
    service_key=KEY,
    page_size=10,
    sleep_seconds=1.0,
    lookback_days=1,
)

print(f"\n[smoke] total collected: {len(rows)}")
for r in rows[:5]:
    print(f"  - [{r['source']}] {r['bid_no']} | {r['title'][:40]} | {r['org_name']} | {r['estimated_price']}")
if len(rows) == 0:
    print("  (no rows - check key/approval or yesterday had no postings)")
