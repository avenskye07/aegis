"""Save a Condor dashboard report from an AEGIS clerk text dump.

When a routine is launched from the dashboard, ``default_source`` already
stamps the report. We still set ``source`` so a direct Python run shows up
under the same name the Routines page groups on (the bare clerk slug).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def parse_kv_lines(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("==="):
            continue
        if ":" not in line:
            rows.append({"Field": "note", "Value": line})
            continue
        key, val = line.split(":", 1)
        rows.append({"Field": key.strip(), "Value": val.strip()})
    return rows


def pick(rows: list[dict[str, str]], *keys: str) -> str:
    want = {k.lower() for k in keys}
    for row in rows:
        if row["Field"].lower() in want:
            return row["Value"]
    return "—"


async def save_clerk_report(
    *,
    title: str,
    source: str,
    text: str,
    kpis: list[tuple[str, str]] | None = None,
    section: str = "01 / CLERK",
    description: str = "Live AEGIS clerk output for the race desk.",
) -> None:
    try:
        from condor.reports import ReportBuilder

        rows = parse_kv_lines(text)
        builder = ReportBuilder(title)
        builder.source("routine", source)
        builder.tags(["aegis", "xrpl", source])
        for label, value in kpis or []:
            builder.kpi(label, value)
        builder.kpi("Checked", datetime.now(timezone.utc).strftime("%H:%M:%S UTC"))
        builder.section(section, description)
        builder.table(rows or [{"Field": "raw", "Value": text[:800]}], ["Field", "Value"])
        builder.manual_order()
        await builder.save()
    except Exception as exc:  # noqa: BLE001 — reports must never break the tick
        logger.warning("aegis report %s failed: %s", source, exc)
