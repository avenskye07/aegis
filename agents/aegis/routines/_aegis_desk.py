"""Read the desk settings from the loop file, so clerks never restate them.

``loops/aegis_operator/loop.md`` is the one place sizes, connectors and
intervals are written down. Every clerk ``Config`` takes its defaults from here,
so changing the loop file changes the clerks too; nothing drifts.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

LOOP_FILE = Path(__file__).resolve().parents[1] / "loops" / "aegis_operator" / "loop.md"


@lru_cache(maxsize=1)
def desk() -> dict:
    """The loop file's ``default_config`` block. Empty dict if it cannot be read."""
    try:
        text = LOOP_FILE.read_text(encoding="utf-8")
        _, front, _ = text.split("---", 2)
        cfg = (yaml.safe_load(front) or {}).get("default_config") or {}
        return cfg if isinstance(cfg, dict) else {}
    except (OSError, ValueError, yaml.YAMLError):
        return {}


def setting(key: str, fallback=None):
    value = desk().get(key)
    return fallback if value is None else value


def sleeve_for(xrpl_pair: str) -> float:
    """Quote sleeve (USD) the loop file assigns to one XRPL book. 0 if unassigned."""
    pair = (xrpl_pair or "").upper()
    for pair_key, usd_key in (("xrpl_pair_a", "quote_a_usd"), ("xrpl_pair_b", "quote_b_usd")):
        if str(setting(pair_key, "")).upper() == pair:
            return float(setting(usd_key, 0) or 0)
    return 0.0
