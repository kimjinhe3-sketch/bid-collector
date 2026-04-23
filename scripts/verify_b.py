"""Verify B (DB/filter/notifier) against live-collected data from A."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.config_loader import load_config
from db import database
from filters import keyword_filter
from notifiers import email_notifier, slack_notifier

config = load_config(ROOT / "config.yaml")
db_path = ROOT / (config.get("database", {}).get("path") or "data/bids.sqlite")

print(f"[B-verify] DB: {db_path}")

counts = database.count_by_source(db_path)
total = sum(counts.values())
print(f"\n[1] Source counts (total {total}):")
for src, n in sorted(counts.items()):
    print(f"    {src}: {n}")

rows = database.get_unnotified(db_path)
print(f"\n[2] Unnotified rows: {len(rows)}")

filter_cfg = config.get("filters", {})
print(f"\n[3] Applying filter: include={filter_cfg['include_keywords']} "
      f"exclude={filter_cfg['exclude_keywords']} "
      f"amount=[{filter_cfg['min_amount_eok']}, {filter_cfg['max_amount_eok']}]억")

filtered = keyword_filter.apply_filters(rows, filter_cfg)
print(f"    -> {len(filtered)} rows match")

print(f"\n[4] Top 5 matches:")
for r in filtered[:5]:
    amt = (r.get("estimated_price") or 0) / 1e8
    print(f"    [{r['bid_type']}] {r['bid_no'][:20]} | {r['title'][:50]} | {amt:.1f}억 | {r['org_name']}")

print(f"\n[5] Email HTML dry-run (first 300 chars):")
html = email_notifier.build_html(filtered[:10])
print(f"    {html[:300]}...")
print(f"    (full length: {len(html)} chars)")

print(f"\n[6] Slack blocks dry-run:")
blocks = slack_notifier.build_blocks(filtered[:10])
print(f"    block count: {len(blocks)}")
print(f"    header: {blocks[0]['text']['text']}")

# Idempotency check — re-upsert same rows
print(f"\n[7] Idempotency: re-upserting {len(rows)} rows...")
processed, skipped = database.upsert_bids(db_path, rows)
print(f"    processed={processed} skipped={skipped}")
counts_after = database.count_by_source(db_path)
total_after = sum(counts_after.values())
print(f"    total after re-upsert: {total_after} (should equal {total})")
assert total_after == total, "idempotency broken!"

print("\n[B-verify] ALL CHECKS PASSED")
