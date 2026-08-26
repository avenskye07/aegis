"""Self-heal clerk. Closes orphan Gate shorts. Cancels stale XRPL dust.

The LLM never calls place_order. This routine may flatten an unmanaged
short so a dump cannot sit naked if the executor died.
"""

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
heal_verdict = _math.heal_verdict
STOP = _math.STOP
HEALTHY = _math.HEALTHY
REDEPLOY = _math.REDEPLOY
SET_LEVERAGE = _math.SET_LEVERAGE
SET_ONEWAY = _math.SET_ONEWAY
WARM_BOOK = _math.WARM_BOOK
CLOSE_ORPHAN = _math.CLOSE_ORPHAN
CANCEL_STALE = _math.CANCEL_STALE

logger = logging.getLogger(__name__)
CATEGORY = "Monitoring"


class Config(BaseModel):
    """Detect and fix race-killers before quoting."""

    hedge_connector: str = Field(default="gate_io_perpetual")
    hedge_pair: str = Field(default="XRP-USDT")
    bot_name: str = Field(default="aegis-aegis_operator")
    account_name: str = Field(default="master_account")
    controller_id: str = Field(default="aegis")
    apply: bool = Field(default=True, description="If true, close orphans / cancel stale")


def _rows(payload) -> list:
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
    if isinstance(payload, list):
        return payload
    return []


def _gate_short_usd(positions) -> float:
    total = 0.0
    for row in _rows(positions):
        if not isinstance(row, dict):
            continue
        conn = str(row.get("connector_name") or "")
        pair = str(row.get("trading_pair") or "")
        if "gate" not in conn or "XRP" not in pair.upper():
            continue
        amt = float(row.get("amount") or 0)
        px = float(row.get("entry_price") or row.get("mark") or 0)
        if amt < 0:
            total += abs(amt) * (px or 1.0)
        elif str(row.get("side") or "").upper() == "SHORT" and amt:
            total += abs(amt) * (px or 1.0)
    return total


def _managed_short_usd(executors) -> float:
    total = 0.0
    for row in _rows(executors):
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "").upper()
        if status not in {"RUNNING", "ACTIVE", "TRADING"}:
            continue
        cfg = row.get("config") if isinstance(row.get("config"), dict) else row
        pair = str(cfg.get("trading_pair") or row.get("trading_pair") or "")
        conn = str(cfg.get("connector_name") or row.get("connector_name") or "")
        if "XRP" not in pair.upper() or "gate" not in conn:
            continue
        filled = float(row.get("filled_amount_quote") or 0)
        if filled > 0:
            total += filled
    return total


def _stale_xrpl(orders) -> list[dict]:
    out = []
    for row in _rows(orders):
        if not isinstance(row, dict):
            continue
        conn = str(row.get("connector_name") or "")
        if conn != "xrpl":
            continue
        status = str(row.get("status") or "").upper()
        if status in {"OPEN", "SUBMITTED", "PENDING_CREATE"}:
            out.append(row)
    return out


async def run(config: Config, context: ContextTypes.DEFAULT_TYPE) -> str:
    client = await get_client(context._chat_id, context=context)
    lines = ["=== AEGIS HEAL ==="]
    if not client:
        return f"verdict: {STOP}\nreason: no hummingbot server\napplied: none"

    server_ok = True
    books_ok = True
    leverage_ok = True
    oneway_ok = True
    bot_running = False
    applied: list[str] = []

    try:
        pos = await client.trading.get_positions(account_names=[config.account_name])
    except Exception as exc:
        pos = {}
        server_ok = False
        lines.append(f"positions: ERROR {type(exc).__name__}")

    try:
        orders = await client.trading.get_active_orders(account_names=[config.account_name])
    except Exception as exc:
        orders = {}
        lines.append(f"orders: ERROR {type(exc).__name__}")

    try:
        ex = await client.executors.search_executors(
            account_names=[config.account_name],
            connector_names=[config.hedge_connector],
        )
    except Exception as exc:
        ex = {}
        lines.append(f"executors: ERROR {type(exc).__name__}")

    try:
        mode = await client.trading.get_position_mode(
            account_name=config.account_name, connector_name=config.hedge_connector
        )
        raw = str((mode or {}).get("position_mode") or mode).upper()
        oneway_ok = "HEDGE" not in raw
        lines.append(f"position_mode: {mode}")
    except Exception as exc:
        lines.append(f"position_mode: ERROR {type(exc).__name__}")
        oneway_ok = False

    try:
        status = await client.bot_orchestration.get_active_bots_status()
        data = (status or {}).get("data") if isinstance(status, dict) else {}
        if isinstance(data, dict):
            for name, info in data.items():
                if config.bot_name in str(name):
                    st = str((info or {}).get("status") or "").lower()
                    if st == "running":
                        bot_running = True
                        break
        lines.append(f"bot {config.bot_name}: {'RUNNING' if bot_running else 'DOWN'}")
    except Exception as exc:
        lines.append(f"bot: ERROR {type(exc).__name__}")

    live_short = _gate_short_usd(pos)
    managed = _managed_short_usd(ex)
    orphan = max(0.0, live_short - managed)
    stale = _stale_xrpl(orders)
    # If the bot is running, its XRPL offers are not stale.
    stale_n = 0 if bot_running else len(stale)

    lines.append(f"live_short_usd: {live_short:.2f}")
    lines.append(f"managed_short_usd: {managed:.2f}")
    lines.append(f"orphan_short_usd: {orphan:.2f}")
    lines.append(f"stale_xrpl_orders: {stale_n}")

    verdict = heal_verdict(
        server_ok=server_ok,
        books_ok=books_ok,
        leverage_ok=leverage_ok,
        oneway_ok=oneway_ok,
        bot_running=bot_running,
        orphan_short_usd=orphan,
        stale_quote_count=stale_n,
    )

    if config.apply and verdict == CLOSE_ORPHAN:
        try:
            try:
                await client.trading.set_position_mode(
                    config.account_name, config.hedge_connector, "ONEWAY"
                )
            except Exception:
                pass
            amt = 0.0
            for row in _rows(pos):
                if str(row.get("connector_name") or "") == config.hedge_connector:
                    amt = abs(float(row.get("amount") or 0))
            if amt > 0:
                res = await client.trading.place_order(
                    account_name=config.account_name,
                    connector_name=config.hedge_connector,
                    trading_pair=config.hedge_pair,
                    trade_type="BUY",
                    amount=amt,
                    order_type="MARKET",
                    position_action="CLOSE",
                )
                applied.append(f"close_orphan {res}")
                lines.append(f"applied close_orphan: {res}")
        except Exception as exc:
            lines.append(f"close_orphan FAIL {type(exc).__name__}: {exc}")
            lines.append("retry next tick — do not quote while an orphan short is unmanaged")

    if config.apply and verdict == CANCEL_STALE:
        for row in stale:
            oid = row.get("order_id") or row.get("client_order_id")
            if not oid:
                continue
            try:
                res = await client.trading.cancel_order(
                    config.account_name, "xrpl", oid
                )
                applied.append(f"cancel {oid}")
                lines.append(f"cancel {oid}: {res}")
            except Exception as exc:
                lines.append(f"cancel {oid} FAIL {exc}")

    if config.apply and verdict == SET_ONEWAY:
        try:
            res = await client.trading.set_position_mode(
                config.account_name, config.hedge_connector, "ONEWAY"
            )
            applied.append(f"oneway {res}")
        except Exception as exc:
            lines.append(f"set_oneway FAIL {exc}")

    if config.apply and verdict == SET_LEVERAGE:
        try:
            res = await client.trading.set_leverage(
                account_name=config.account_name,
                connector_name=config.hedge_connector,
                trading_pair=config.hedge_pair,
                leverage=1,
            )
            applied.append(f"leverage {res}")
        except Exception as exc:
            lines.append(f"set_leverage FAIL {exc}")

    lines.append(f"verdict: {verdict}")
    lines.append(f"applied: {', '.join(applied) if applied else 'none'}")
    if verdict == REDEPLOY:
        lines.append("action: deploy bot aegis-aegis_operator with both pmm_simple configs")
        lines.append("if deploy fails this tick: FALLBACK_EXEC (LIMIT_MAKER both books)")
    text = "\n".join(lines)
    rows = _rep.parse_kv_lines(text)
    await _rep.save_clerk_report(
        title="AEGIS — Self-Heal",
        source="aegis_heal",
        text=text,
        kpis=[
            ("Verdict", _rep.pick(rows, "verdict")),
            ("Orphan $", _rep.pick(rows, "orphan_short_usd")),
            ("Applied", _rep.pick(rows, "applied")),
        ],
        section="02 / HEAL",
        description="Orphan Gate shorts, stale XRPL dust, ONEWAY, 1x, bot up/down.",
    )
    return text
