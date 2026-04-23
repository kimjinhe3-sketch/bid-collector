from __future__ import annotations

from pathlib import Path

import yaml


def load_config(path: str | Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _cron_to_kwargs(expr: str) -> dict:
    parts = (expr or "").split()
    if len(parts) != 5:
        raise ValueError(f"invalid cron expression: {expr!r}")
    minute, hour, dom, month, dow = parts
    return {
        "minute": minute,
        "hour": hour,
        "day": dom,
        "month": month,
        "day_of_week": dow,
    }


def cron_kwargs(expr: str) -> dict:
    return _cron_to_kwargs(expr)
