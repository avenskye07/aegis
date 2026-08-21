"""Quote planner for one XRPL XRP/stable pair. Signal only — no orders."""

from __future__ import annotations

import asyncio
import logging
import math
import time
from datetime import datetime, timezone

import httpx
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
HOLD = _math.HOLD
VIABLE = _math.VIABLE
WIDEN = _math.WIDEN
ceiling_bps_from_amm_pct = _math.ceiling_bps_from_amm_pct
implied_xrpl_price = _math.implied_xrpl_price
ladder_bps = _math.ladder_bps
per_level_quote = _math.per_level_quote
reserve_xrp = _math.reserve_xrp
split_pair = _math.split_pair
spreads_as_fractions = _math.spreads_as_fractions
spread_floor_bps = _math.spread_floor_bps
top_of_book_anchor = _math.top_of_book_anchor
viability = _math.viability
widen_quotes = _math.widen_quotes

logger = logging.getLogger(__name__)
CATEGORY = "Analysis"

XRPL_RPC = "https://xrplcluster.com/"
HOUR_VOL_MULT = {
    0: 1.03, 1: 1.10, 2: 0.95, 3: 0.89, 4: 0.82, 5: 0.85,
    6: 0.82, 7: 0.82, 8: 0.91, 9: 0.83, 10: 0.78, 11: 0.82,
    12: 0.92, 13: 1.28, 14: 1.50, 15: 1.40, 16: 1.16, 17: 1.21,
    18: 1.07, 19: 1.04, 20: 1.02, 21: 0.97, 22: 0.97, 23: 0.82,
}
MS_PER_HOUR = 3_600_000


class Config(BaseModel):
    """Plan maker quotes for one XRPL pair against a CEX XRP-USD reference."""

    xrpl_pair: str = Field(default="XRP-RLUSD")
    reference_connector: str = Field(default="binance_perpetual")
    reference_pair: str = Field(default="XRP-USDT")
    tick_interval_sec: int = Field(default=600)
    requote_interval_sec: int = Field(default=45)
    levels_per_side: int = Field(default=3)
    total_amount_quote: float = Field(default=280.0)
    adverse_k: float = Field(default=1.0)
    amm_fee_pct_fallback: float = Field(default=0.20)
    base_issuer: str = Field(default="", description="Issuer if base is not XRP")
    quote_issuer: str = Field(
        default="rMxCKbEDwqr76QuheSUMdEGf4B9xJ8m5De",
        description="RLUSD issuer when quote is RLUSD; USDC issuer when quote is USDC",
    )
    widen_distance_pct: float = Field(default=1.0)
    top_of_book_improve_pct: float = Field(default=0.01)


def _hour_mult_span(start_ms: int, end_ms: int) -> float:
    if end_ms <= start_ms:
        hour = datetime.fromtimestamp(start_ms / 1000, timezone.utc).hour
        return HOUR_VOL_MULT.get(hour, 1.0)
    total = weight = 0.0
    cursor = start_ms
    while cursor < end_ms:
        hour = datetime.fromtimestamp(cursor / 1000, timezone.utc).hour
        seg_end = min((cursor // MS_PER_HOUR + 1) * MS_PER_HOUR, end_ms)
        w = seg_end - cursor
        total += HOUR_VOL_MULT.get(hour, 1.0) * w
        weight += w
        cursor = seg_end
    return total / weight if weight else 1.0


def _realized_vol_per_sec(closes: list[float], interval_sec: int) -> float:
    good = [c for c in closes if c > 0]
    if len(good) < 3:
        return 0.0
    rets = []
    for a, b in zip(good, good[1:]):
        if a > 0 and b > 0:
            rets.append(math.log(b / a))
    if len(rets) < 2:
        return 0.0
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(max(var, 0.0)) / max(interval_sec, 1)


def _norm_candles(raw) -> list:
    return raw if isinstance(raw, list) else (raw or {}).get("data", (raw or {}).get("candles", []))


def _extract_ref_price(raw, pair: str, fallback: float) -> float:
    if not isinstance(raw, dict):
        return fallback

    def _positive(value):
        try:
            num = float(value)
        except (TypeError, ValueError):
            return None
        return num if num > 0 else None

    direct = _positive(raw.get(pair))
    if direct is not None:
        return direct
    for value in raw.values():
        if isinstance(value, dict):
            nested = _positive(value.get(pair))
            if nested is not None:
                return nested
    return fallback


def _issue_currency_code(code: str) -> str:
    if len(code) <= 3:
        return code
    return code.encode("ascii").hex().upper().ljust(40, "0")


async def _amm_fee_pct(base: str, quote: str, base_issuer: str, quote_issuer: str) -> tuple[float | None, str]:
    def issue(code: str, issuer: str):
        if code == "XRP":
            return {"currency": "XRP"}
        if not issuer:
            return None
        return {"currency": _issue_currency_code(code), "issuer": issuer}

    asset = issue(quote, quote_issuer)
    asset2 = issue(base, base_issuer)
    if asset is None or asset2 is None:
        return None, "no issuer for issued leg"
    payload = {
        "method": "amm_info",
        "params": [{"asset": asset, "asset2": asset2, "ledger_index": "validated"}],
    }
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.post(XRPL_RPC, json=payload)
            data = resp.json().get("result", {})
        amm = data.get("amm")
        if not amm:
            return None, f"no pool ({data.get('error', 'unknown')})"
        raw_fee = amm.get("trading_fee", amm.get("TradingFee", 0)) or 0
        return float(raw_fee) / 1000.0, "live from amm_info"
    except Exception as exc:
        logger.warning("amm_info failed: %s", exc)
        return None, f"unreachable ({type(exc).__name__})"


def plan_from_inputs(
    *,
    xrpl_pair: str,
    xrp_usd: float,
    vol_per_sec: float,
    requote_sec: int,
    adverse_k: float,
    amm_fee_pct: float,
    levels: int,
    total_amount_quote: float,
    best_bid: float | None,
    best_ask: float | None,
    improve_pct: float,
    widen_pct: float,
) -> str:
    mid = implied_xrpl_price(xrpl_pair, xrp_usd)
    floor = spread_floor_bps(vol_per_sec, requote_sec, adverse_k)
    ceiling = ceiling_bps_from_amm_pct(amm_fee_pct)
    mode, headroom = viability(floor, ceiling)
    out = [
        "=== AEGIS QUOTE PLAN ===",
        f"xrpl_pair: {xrpl_pair}",
        f"xrp_usd: {xrp_usd:.6f}",
        f"implied_mid: {mid:.6f}",
        f"requote_sec: {requote_sec}",
        f"spread_floor_bps: {floor:.2f}",
        f"spread_ceiling_bps: {ceiling:.2f}",
        f"headroom_bps: {headroom:.2f}",
        f"verdict: {mode}",
    ]
    if best_bid and best_ask and best_bid > 0 and best_ask > best_bid:
        tob_bid, tob_ask = top_of_book_anchor(best_bid, best_ask, improve_pct)
        out.append("book_ok: true")
        out.append(f"best_bid: {best_bid:.6f}  best_ask: {best_ask:.6f}")
        out.append(f"tob_bid: {tob_bid:.6f}  tob_ask: {tob_ask:.6f}")
    else:
        out.append("book_ok: false")
        out.append(f"verdict: {HOLD}")
        out.append("reason: empty book — do not quote")
        return "\n".join(out)

    if mode == VIABLE:
        ladder = ladder_bps(floor, ceiling, levels)
        fracs = spreads_as_fractions(ladder)
        out.append("ladder_bps: " + ",".join(f"{b:.2f}" for b in ladder))
        out.append("controller_spreads: " + ",".join(f"{f:.6f}" for f in fracs))
        out.append("quote_mode: top_of_book")
        out.append(f"levels_per_side: {levels}  offers: {levels * 2}")
    else:
        wbid, wask = widen_quotes(mid, widen_pct)
        out.append(f"verdict: {WIDEN}")
        out.append(f"widen_bid: {wbid:.6f}  widen_ask: {wask:.6f}")
        out.append(f"widen_spread_fraction: {widen_pct / 100:.6f}")
        out.append("levels_per_side: 1  (widen — keep quoting)")

    out.append(f"per_level_quote: {per_level_quote(total_amount_quote, levels):.2f}")
    out.append(f"reserve_xrp_this_pair: {reserve_xrp(levels if mode == VIABLE else 1, 1):.2f}")
    return "\n".join(out)


async def run(config: Config, context: ContextTypes.DEFAULT_TYPE) -> str:
    client = await get_client(context._chat_id, context=context)
    if not client:
        return "verdict: HOLD\nreason: no hummingbot server"

    try:
        candles_raw, ref_prices = await asyncio.gather(
            client.market_data.get_candles(
                config.reference_connector,
                config.reference_pair,
                interval="1m",
                max_records=120,
            ),
            client.market_data.get_prices(
                config.reference_connector, [config.reference_pair]
            ),
        )
    except Exception as exc:
        return f"verdict: HOLD\nreason: CEX reference ERROR — {exc}"

    candles = _norm_candles(candles_raw)
    closes = [float(c.get("close", 0)) for c in candles if float(c.get("close", 0)) > 0]
    if not closes:
        return f"verdict: HOLD\nreason: no candle data for {config.reference_pair}"
    xrp_usd = _extract_ref_price(ref_prices, config.reference_pair, closes[-1])

    requote = max(config.requote_interval_sec or config.tick_interval_sec, 1)
    vol_raw = _realized_vol_per_sec(closes, 60)
    now_ms = int(time.time() * 1000)
    look_start = now_ms - len(closes) * 60_000
    fwd_end = now_ms + requote * 1000
    mult_look = _hour_mult_span(look_start, now_ms)
    mult_fwd = _hour_mult_span(now_ms, fwd_end)
    vol = (vol_raw / mult_look * mult_fwd) if mult_look > 0 else vol_raw

    base, quote = split_pair(config.xrpl_pair)
    amm_pct, amm_note = await _amm_fee_pct(
        base, quote, config.base_issuer, config.quote_issuer
    )
    if amm_pct is None:
        amm_pct = config.amm_fee_pct_fallback
        amm_note = f"FALLBACK {amm_pct}% — {amm_note}"

    best_bid = best_ask = None
    try:
        book = await client.market_data.get_order_book("xrpl", config.xrpl_pair)
    except Exception as exc:
        err = str(exc).lower()
        if "notsynced" in err:
            return f"verdict: HOLD\nreason: XRPL notSynced on {config.xrpl_pair}"
        return f"verdict: HOLD\nreason: book ERROR — {exc}"
    if isinstance(book, dict):
        bids = book.get("bids") or book.get("buy") or []
        asks = book.get("asks") or book.get("sell") or []
        if bids and asks:
            try:
                best_bid = float(bids[0][0] if isinstance(bids[0], (list, tuple)) else bids[0].get("price"))
                best_ask = float(asks[0][0] if isinstance(asks[0], (list, tuple)) else asks[0].get("price"))
            except (TypeError, ValueError, IndexError, KeyError):
                best_bid = best_ask = None

    text = plan_from_inputs(
        xrpl_pair=config.xrpl_pair,
        xrp_usd=xrp_usd,
        vol_per_sec=vol,
        requote_sec=requote,
        adverse_k=config.adverse_k,
        amm_fee_pct=amm_pct,
        levels=config.levels_per_side,
        total_amount_quote=config.total_amount_quote,
        best_bid=best_bid,
        best_ask=best_ask,
        improve_pct=config.top_of_book_improve_pct,
        widen_pct=config.widen_distance_pct,
    )
    return text + f"\namm_note: {amm_note}"
