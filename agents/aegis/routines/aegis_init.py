"""Venue hygiene before a tick. Idempotent. No quotes, no shorts."""

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
GO = _math.GO
STOP = _math.STOP
HOLD = _math.HOLD

logger = logging.getLogger(__name__)
CATEGORY = "Monitoring"


class Config(BaseModel):
    """Warm books, pin Gate 1x + ONEWAY, report whether a bot can run."""

    xrpl_pair_a: str = Field(default="XRP-RLUSD")
    xrpl_pair_b: str = Field(default="XRP-USDC")
    hedge_connector: str = Field(default="gate_io_perpetual")
    hedge_pair: str = Field(default="XRP-USDT")
    bot_name: str = Field(default="aegis-aegis_operator")
    account_name: str = Field(default="master_account")


def _book_ok(raw) -> bool:
    if not raw or isinstance(raw, str):
        return False
    data = raw if isinstance(raw, dict) else {}
    bids = data.get("bids") or data.get("buy") or []
    asks = data.get("asks") or data.get("sell") or []
    return bool(bids) and bool(asks)


async def run(config: Config, context: ContextTypes.DEFAULT_TYPE) -> str:
    client = await get_client(context._chat_id, context=context)
    lines = ["=== AEGIS INIT ==="]
    if not client:
        return f"verdict: {STOP}\nreason: no hummingbot server"

    books = 0
    for conn, pair in (
        ("xrpl", config.xrpl_pair_a),
        ("xrpl", config.xrpl_pair_b),
        (config.hedge_connector, config.hedge_pair),
    ):
        try:
            book = await client.market_data.get_order_book(conn, pair)
            ok = _book_ok(book)
            books += int(ok)
            lines.append(f"book {conn} {pair}: {'OK' if ok else 'EMPTY'}")
        except Exception as exc:
            lines.append(f"book {conn} {pair}: ERROR {type(exc).__name__}")

    lev_ok = False
    try:
        lev = await client.trading.set_leverage(
            account_name=config.account_name,
            connector_name=config.hedge_connector,
            trading_pair=config.hedge_pair,
            leverage=1,
        )
        lev_ok = True
        lines.append(f"leverage: {lev}")
    except Exception as exc:
        lines.append(f"leverage: ERROR {type(exc).__name__}: {exc}")

    mode_ok = False
    try:
        await client.trading.set_position_mode(
            config.account_name, config.hedge_connector, "ONEWAY"
        )
        mode = await client.trading.get_position_mode(
            account_name=config.account_name, connector_name=config.hedge_connector
        )
        raw = str((mode or {}).get("position_mode") or mode).upper()
        mode_ok = "HEDGE" not in raw or "ONE" in raw
        lines.append(f"position_mode: {mode}")
    except Exception as exc:
        lines.append(f"position_mode: ERROR {type(exc).__name__}: {exc}")

    bot_seen = False
    try:
        status = await client.bot_orchestration.get_active_bots_status()
        data = (status or {}).get("data") if isinstance(status, dict) else {}
        if isinstance(data, dict):
            for name, info in data.items():
                if config.bot_name in str(name):
                    st = str((info or {}).get("status") or "").lower()
                    if st == "running":
                        bot_seen = True
                        break
        lines.append(f"bot {config.bot_name}: {'SEEN' if bot_seen else 'ABSENT'}")
    except Exception as exc:
        lines.append(f"bot status: ERROR {type(exc).__name__} — treat as ABSENT")

    if books < 3:
        lines.append(f"verdict: {HOLD}")
        lines.append("reason: a book is not warm — do not quote this tick")
        text = "\n".join(lines)
        await _rep.save_clerk_report(
            title="AEGIS — Init",
            source="aegis_init",
            text=text,
            kpis=[("Verdict", HOLD), ("Books", str(books))],
            section="00 / STARTUP HYGIENE",
            description="Warm books, pin leverage 1x, Gate ONEWAY, see if the quote bot is up.",
        )
        return text

    lines.append(f"verdict: {GO}")
    lines.append(f"leverage_ok: {str(lev_ok).lower()}")
    lines.append(f"oneway_ok: {str(mode_ok).lower()}")
    lines.append(f"bot_running: {str(bot_seen).lower()}")
    lines.append("note: deploy is the agent's job if bot_running is false")
    text = "\n".join(lines)
    rows = _rep.parse_kv_lines(text)
    await _rep.save_clerk_report(
        title="AEGIS — Init",
        source="aegis_init",
        text=text,
        kpis=[
            ("Verdict", _rep.pick(rows, "verdict")),
            ("1x / ONEWAY", f"{_rep.pick(rows, 'leverage_ok')} / {_rep.pick(rows, 'oneway_ok')}"),
            ("Bot", "UP" if bot_seen else "DOWN"),
        ],
        section="00 / STARTUP HYGIENE",
        description="Warm books, pin leverage 1x, Gate ONEWAY, see if the quote bot is up.",
    )
    return text
