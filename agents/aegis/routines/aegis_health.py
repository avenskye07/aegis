"""Venue truth gate. STOP the tick if XRPL or Gate cannot shield a fill."""

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
GO = _math.GO
STOP = _math.STOP
issuer_ok = _math.issuer_ok

logger = logging.getLogger(__name__)
CATEGORY = "Monitoring"


class Config(BaseModel):
    """Check XRPL + Gate are reachable before quoting."""

    xrpl_pair_a: str = Field(default="XRP-RLUSD")
    xrpl_pair_b: str = Field(default="XRP-USDC")
    hedge_connector: str = Field(default="gate_io_perpetual")
    hedge_pair: str = Field(default="XRP-USDT")
    rlusd_issuer: str = Field(default="rMxCKbEDwqr76QuheSUMdEGf4B9xJ8m5De")
    usdc_issuer: str = Field(default="rGm7WCVp9gb4jZHWTEtGUr4dd74z2XuWhE")


def _book_ok(raw) -> bool:
    if not raw or isinstance(raw, str):
        return False
    data = raw if isinstance(raw, dict) else {}
    err = str(data.get("error") or data.get("status") or "").lower()
    if "notsynced" in err or err == "error":
        return False
    bids = data.get("bids") or data.get("buy") or []
    asks = data.get("asks") or data.get("sell") or []
    return bool(bids) and bool(asks)


async def run(config: Config, context: ContextTypes.DEFAULT_TYPE) -> str:
    client = await get_client(context._chat_id, context=context)
    if not client:
        return f"verdict: {STOP}\nreason: no hummingbot server"

    lines = ["=== AEGIS HEALTH ==="]
    if not issuer_ok("RLUSD", config.rlusd_issuer) or not issuer_ok("USDC", config.usdc_issuer):
        return f"verdict: {STOP}\nreason: issuer whitelist failed"

    xrpl_ok = True
    for pair in (config.xrpl_pair_a, config.xrpl_pair_b):
        try:
            book = await client.market_data.get_order_book("xrpl", pair)
        except Exception as exc:
            logger.warning("xrpl book %s: %s", pair, exc)
            err = str(exc).lower()
            if "notsynced" in err or "500" in err:
                return (
                    f"verdict: {STOP}\nreason: XRPL notSynced on {pair} — HOLD entire tick"
                )
            xrpl_ok = False
            lines.append(f"{pair}: ERROR {type(exc).__name__}")
            continue
        ok = _book_ok(book)
        xrpl_ok = xrpl_ok and ok
        lines.append(f"{pair}: {'BOOK_OK' if ok else 'EMPTY_OR_STALE'}")

    gate_ok = True
    try:
        gbook = await client.market_data.get_order_book(
            config.hedge_connector, config.hedge_pair
        )
        gate_ok = _book_ok(gbook)
        lines.append(f"gate {config.hedge_pair}: {'BOOK_OK' if gate_ok else 'DEAD'}")
    except Exception as exc:
        gate_ok = False
        lines.append(f"gate: ERROR {type(exc).__name__} — {exc}")

    if not gate_ok:
        lines.append(f"verdict: {STOP}")
        lines.append("reason: Gate unreachable — do not quote (cannot shield a fill)")
        return "\n".join(lines)
    if not xrpl_ok:
        lines.append(f"verdict: {STOP}")
        lines.append("reason: XRPL book missing — HOLD")
        return "\n".join(lines)
    lines.append(f"verdict: {GO}")
    return "\n".join(lines)
