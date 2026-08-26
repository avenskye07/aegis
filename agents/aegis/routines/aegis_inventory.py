"""Net XRP pile across both books. Core sleeve must stay unsellable."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field
from telegram.ext import ContextTypes

from config_manager import get_client

import importlib.util
from pathlib import Path as _P


def _aegis_mod(name: str):
    path = _P(__file__).with_name(name + ".py")
    spec = importlib.util.spec_from_file_location("aegis_" + name, path)
    if spec is None or spec.loader is None:
        raise ImportError(name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_math = _aegis_mod("_aegis_math")
_rep = _aegis_mod("_aegis_report")
CORE_MIN = _math.CORE_MIN
HOLD = _math.HOLD
core_intact = _math.core_intact
net_xrp_usd = _math.net_xrp_usd
reserve_xrp = _math.reserve_xrp

logger = logging.getLogger(__name__)
CATEGORY = "Analysis"


class Config(BaseModel):
    """Read XRPL XRP inventory and whether the core sleeve is intact."""

    xrp_usd: float = Field(default=0.0, description="If 0, try CEX XRP-USDT")
    reference_connector: str = Field(default="binance_perpetual")
    reference_pair: str = Field(default="XRP-USDT")
    core_min_usd: float = Field(default=CORE_MIN)
    levels_per_side: int = Field(default=3)
    n_pairs: int = Field(default=2)


def _xrpl_rows(state) -> list:
    """Pull the xrpl connector rows from Hummingbot portfolio.get_state()."""
    if not isinstance(state, dict):
        return []
    acct = state.get("master_account")
    if isinstance(acct, dict) and isinstance(acct.get("xrpl"), list):
        return acct["xrpl"]
    if isinstance(state.get("xrpl"), list):
        return state["xrpl"]
    for v in state.values():
        if isinstance(v, dict) and isinstance(v.get("xrpl"), list):
            return v["xrpl"]
    return []


def _asset_qty(balances, code: str) -> float:
    if not balances:
        return 0.0
    if isinstance(balances, dict):
        rows = _xrpl_rows(balances)
        if rows:
            return _asset_qty(rows, code)
        for k, v in balances.items():
            if str(k).upper() == code.upper():
                try:
                    if isinstance(v, dict):
                        return float(v.get("units") or v.get("free") or v.get("total") or 0)
                    return float(v)
                except (TypeError, ValueError):
                    continue
        data = balances.get("data") or balances.get("balances") or []
        return _asset_qty(data, code)
    if isinstance(balances, list):
        for row in balances:
            if not isinstance(row, dict):
                continue
            asset = str(row.get("asset") or row.get("currency") or row.get("token") or "")
            if asset.upper() == code.upper():
                try:
                    return float(
                        row.get("units")
                        or row.get("available_units")
                        or row.get("free")
                        or row.get("available")
                        or row.get("total")
                        or 0
                    )
                except (TypeError, ValueError):
                    return 0.0
    return 0.0


def inventory_verdict(xrp_units: float, xrp_usd: float, core_min: float, reserved: float) -> str:
    tradable = max(0.0, xrp_units - reserved)
    usd = net_xrp_usd(tradable, xrp_usd)
    intact = core_intact(usd, core_min)
    rebalance = HOLD
    lines = [
        "=== AEGIS INVENTORY ===",
        f"xrp_units: {xrp_units:.6f}",
        f"reserve_xrp: {reserved:.2f}",
        f"tradable_xrp: {tradable:.6f}",
        f"xrp_usd: {xrp_usd:.6f}",
        f"net_xrp_usd: {usd:.2f}",
        f"core_min_usd: {core_min:.0f}",
        f"core_intact: {str(intact).lower()}",
        f"rebalance: {rebalance}",
        "note: never sell the core sleeve to flatten after RELEASE",
    ]
    return "\n".join(lines)


async def run(config: Config, context: ContextTypes.DEFAULT_TYPE) -> str:
    client = await get_client(context._chat_id, context=context)
    xrp_usd = config.xrp_usd
    xrp_units = 0.0
    if client:
        try:
            if xrp_usd <= 0:
                prices = await client.market_data.get_prices(
                    config.reference_connector, [config.reference_pair]
                )
                if isinstance(prices, dict):
                    raw = prices.get(config.reference_pair)
                    if raw is None:
                        for v in prices.values():
                            if isinstance(v, dict) and config.reference_pair in v:
                                raw = v[config.reference_pair]
                                break
                    xrp_usd = float(raw or 0)
        except Exception as exc:
            logger.warning("ref price: %s", exc)
        port = {}
        try:
            if hasattr(client, "portfolio") and hasattr(client.portfolio, "get_state"):
                port = await client.portfolio.get_state()
        except Exception as exc:
            logger.warning("portfolio.get_state: %s", exc)
            port = {}
        xrp_units = _asset_qty(port, "XRP")
    reserved = reserve_xrp(config.levels_per_side, config.n_pairs)
    text = inventory_verdict(xrp_units, xrp_usd or 0.0, config.core_min_usd, reserved)
    rows = _rep.parse_kv_lines(text)
    await _rep.save_clerk_report(
        title="AEGIS — Inventory",
        source="aegis_inventory",
        text=text,
        kpis=[
            ("Net XRP $", _rep.pick(rows, "net_xrp_usd")),
            ("Tradable", _rep.pick(rows, "tradable_xrp")),
            ("Core", _rep.pick(rows, "core_intact")),
        ],
        section="03 / PILE",
        description="One XRP pile across both books. Core sleeve is unsellable.",
    )
    return text
