from __future__ import annotations

from typing import Iterable

EOK = 100_000_000  # 1억원


def _match_any(text: str, keywords: Iterable[str], case_sensitive: bool = False) -> bool:
    if not keywords:
        return False
    t = text or ""
    if not case_sensitive:
        t_cmp = t.lower()
        return any(kw and kw.lower() in t_cmp for kw in keywords)
    return any(kw and kw in t for kw in keywords)


def passes(row: dict, config: dict) -> bool:
    """Return True if the row passes include/exclude/amount/bid_type filters."""
    title = row.get("title") or ""
    includes = config.get("include_keywords") or []
    excludes = config.get("exclude_keywords") or []
    bid_types = config.get("bid_types") or []
    case_sensitive = bool(config.get("case_sensitive", False))

    if excludes and _match_any(title, excludes, case_sensitive):
        return False

    if includes and not _match_any(title, includes, case_sensitive):
        return False

    if bid_types and row.get("bid_type") not in bid_types:
        return False

    price = row.get("estimated_price")
    min_eok = config.get("min_amount_eok")
    max_eok = config.get("max_amount_eok")
    if price is not None:
        if min_eok is not None and price < min_eok * EOK:
            return False
        if max_eok is not None and price > max_eok * EOK:
            return False

    return True


def apply_filters(rows: Iterable[dict], config: dict) -> list[dict]:
    return [r for r in rows if passes(r, config)]
