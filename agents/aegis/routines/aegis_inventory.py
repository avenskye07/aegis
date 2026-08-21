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


def _asset_qty(balances, code: str) -> float:
    if not balances:
        return 0.0
    if isinstance(balances, dict):
        for k, v in balances.items():
            if str(k).upper().startswith(code.upper()):
                try:
                    if isinstance(v, dict):
                        return float(v.get("free") or v.get("total") or 0)
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
            if asset.upper() == code.upper() or asset.upper().startswith(code.upper()):
                try:
                    return float(row.get("free") or row.get("available") or row.get("total") or 0)
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
        try:
            port = await client.trading.get_portfolio_state("xrpl") if hasattr(client, "trading") else None
        except Exception:
            port = None
        try:
            if port is None:
                ov = await client.portfolio.get_total_value() if hasattr(client, "portfolio") else {}
                port = ov
        except Exception as exc:
            logger.warning("portfolio: %s", exc)
            port = {}
        xrp_units = _asset_qty(port, "XRP")
    reserved = reserve_xrp(config.levels_per_side, config.n_pairs)
    return inventory_verdict(xrp_units, xrp_usd or 0.0, config.core_min_usd, reserved)
