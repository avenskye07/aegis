"""Gate shield clerk. Only this routine may print RELEASE / RE_ARM."""

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
HEDGE_CAP = _math.HEDGE_CAP
HOLD = _math.HOLD
PUMP_CUT = _math.PUMP_CUT
REARM_BAND = _math.REARM_BAND
hedge_notional = _math.hedge_notional
pump_pct = _math.pump_pct
shield_verdict = _math.shield_verdict

logger = logging.getLogger(__name__)
CATEGORY = "Analysis"


class Config(BaseModel):
    """Size the Gate short. Dump-hedge, pump-release."""

    net_xrp_usd: float = Field(default=0.0)
    short_usd: float = Field(default=0.0)
    last_entry: float = Field(default=0.0)
    mark: float = Field(default=0.0)
    released: bool = Field(default=False)
    gate_ok: bool = Field(default=True)
    book_ok: bool = Field(default=True)
    hedge_cap: float = Field(default=HEDGE_CAP)
    hedge_connector: str = Field(default="gate_io_perpetual")
    hedge_pair: str = Field(default="XRP-USDT")


def format_verdict(
    mode: str,
    net_xrp_usd: float,
    short_usd: float,
    target: float,
    mark: float,
    last_entry: float,
) -> str:
    move = pump_pct(mark, last_entry) if mark and last_entry else None
    lines = [
        "=== AEGIS SHIELD ===",
        f"verdict: {mode}",
        f"net_xrp_usd: {net_xrp_usd:.2f}",
        f"short_usd: {short_usd:.2f}",
        f"target_short_usd: {target:.2f}",
        f"hedge_cap: {HEDGE_CAP:.0f}",
        f"mark: {mark:.6f}",
        f"last_entry: {last_entry:.6f}",
        f"pump_pct: {move if move is not None else 'n/a'}",
        f"pump_cut: {PUMP_CUT}",
        f"rearm_band: {REARM_BAND}",
        "barrier: SL 0.06 / TP 0.80 / 48h / no trail / leverage 1",
        "RELEASE → cut short ONLY. Do not sell XRPL XRP.",
        "DUMP → leave the short on.",
        "cap: min(net_xrp_usd, 280) — not a standing $280",
    ]
    return "\n".join(lines)


async def run(config: Config, context: ContextTypes.DEFAULT_TYPE) -> str:
    mark = config.mark
    if mark <= 0:
        client = await get_client(context._chat_id, context=context)
        if client:
            try:
                prices = await client.market_data.get_prices(
                    config.hedge_connector, [config.hedge_pair]
                )
                if isinstance(prices, dict):
                    raw = prices.get(config.hedge_pair)
                    mark = float(raw or 0)
            except Exception as exc:
                logger.warning("gate mark: %s", exc)
    target = hedge_notional(config.net_xrp_usd, config.hedge_cap)
    mode = shield_verdict(
        gate_ok=config.gate_ok,
        book_ok=config.book_ok,
        net_xrp_usd_val=config.net_xrp_usd,
        short_usd=config.short_usd,
        last_entry=config.last_entry or None,
        mark=mark or None,
        released=config.released,
        cap=config.hedge_cap,
    )
    if not config.gate_ok:
        mode = HOLD
    return format_verdict(mode, config.net_xrp_usd, config.short_usd, target, mark, config.last_entry)
