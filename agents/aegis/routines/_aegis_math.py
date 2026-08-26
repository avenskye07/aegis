"""Pure AEGIS desk math. No network. No orders."""

from __future__ import annotations

STOP = "STOP"
GO = "GO"
VIABLE = "VIABLE"
WIDEN = "WIDEN"
HOLD = "HOLD"
SHIELD_ON = "SHIELD_ON"
RESIZE = "RESIZE"
RELEASE = "RELEASE"
RE_ARM = "RE_ARM"
HEALTHY = "HEALTHY"
REDEPLOY = "REDEPLOY"
SET_LEVERAGE = "SET_LEVERAGE"
SET_ONEWAY = "SET_ONEWAY"
WARM_BOOK = "WARM_BOOK"
CLOSE_ORPHAN = "CLOSE_ORPHAN"
CANCEL_STALE = "CANCEL_STALE"
FALLBACK_EXEC = "FALLBACK_EXEC"

# Official issuers (whitelist). Never quote a copycat.
RLUSD_ISSUER = "rMxCKbEDwqr76QuheSUMdEGf4B9xJ8m5De"
USDC_ISSUER = "rGm7WCVp9gb4jZHWTEtGUr4dd74z2XuWhE"

BASE_RESERVE_XRP = 1.0
OWNER_RESERVE_XRP = 0.2

PUMP_CUT = 0.06
REARM_BAND = 0.03
RESIZE_BAND = 0.08
HEDGE_CAP = 280.0
CORE_MIN = 80.0
CORE_MAX = 120.0


def split_pair(xrpl_pair: str) -> tuple[str, str]:
    base, _, quote = (xrpl_pair or "").upper().partition("-")
    return base, quote


def implied_xrpl_price(xrpl_pair: str, xrp_usd: float) -> float:
    """Fair value of the XRPL pair from a CEX XRP-USD reference.

    XRP-RLUSD / XRP-USDC (XRP base, ~$1 stable quote) → price ≈ xrp_usd.
    RLUSD-XRP (XRP quote) → price ≈ 1 / xrp_usd.
    """
    if xrp_usd <= 0:
        return 0.0
    base, quote = split_pair(xrpl_pair)
    if quote == "XRP":
        return 1.0 / xrp_usd
    if base == "XRP":
        return xrp_usd
    return 0.0


def spread_floor_bps(vol_per_sec: float, requote_sec: float, adverse_k: float = 1.0) -> float:
    import math

    t = max(float(requote_sec), 1.0)
    k = max(float(adverse_k), 0.0)
    v = max(float(vol_per_sec), 0.0)
    return k * v * math.sqrt(t) * 10_000.0


def ceiling_bps_from_amm_pct(amm_fee_pct: float) -> float:
    return max(float(amm_fee_pct), 0.0) * 100.0


def viability(floor_bps: float, ceiling_bps: float) -> tuple[str, float]:
    headroom = ceiling_bps - floor_bps
    if floor_bps < ceiling_bps:
        return VIABLE, headroom
    return WIDEN, headroom


def ladder_bps(floor_bps: float, ceiling_bps: float, levels: int) -> list[float]:
    n = max(int(levels), 1)
    headroom = ceiling_bps - floor_bps
    if headroom <= 0:
        return []
    return [floor_bps + headroom * (i + 1) / (n + 1) for i in range(n)]


def spreads_as_fractions(ladder: list[float]) -> list[float]:
    return [b / 10_000.0 for b in ladder]


def top_of_book_anchor(best_bid: float, best_ask: float, improve_pct: float = 0.01) -> tuple[float, float]:
    p = abs(improve_pct) / 100.0
    return best_bid * (1.0 + p), best_ask * (1.0 - p)


def widen_quotes(mid: float, distance_pct: float = 1.0) -> tuple[float, float]:
    d = abs(distance_pct) / 100.0
    return mid * (1.0 - d), mid * (1.0 + d)


def reserve_xrp(levels_per_side: int, n_pairs: int = 1) -> float:
    offers = max(int(levels_per_side), 0) * 2 * max(int(n_pairs), 0)
    return BASE_RESERVE_XRP + OWNER_RESERVE_XRP * offers


def per_level_quote(total_amount_quote: float, levels_per_side: int) -> float:
    n = max(int(levels_per_side), 1) * 2
    return float(total_amount_quote) / n if n else 0.0


def net_xrp_usd(xrp_units: float, xrp_usd: float) -> float:
    return max(0.0, float(xrp_units)) * max(0.0, float(xrp_usd))


def hedge_notional(net_xrp_usd_val: float, cap: float = HEDGE_CAP) -> float:
    return max(0.0, min(float(net_xrp_usd_val), float(cap)))


def core_intact(xrp_usd_in_pile: float, core_min: float = CORE_MIN) -> bool:
    return float(xrp_usd_in_pile) + 1e-9 >= float(core_min)


def drawdown_quote_scale(drawdown_pct: float) -> float:
    """Scale quoting capital. 0–4% full, 4–8% half, >8% no new size."""
    d = abs(float(drawdown_pct))
    if d <= 0.04:
        return 1.0
    if d <= 0.08:
        return 0.5
    return 0.0


def pump_pct(mark: float, entry: float) -> float | None:
    if mark <= 0 or entry <= 0:
        return None
    return (mark - entry) / entry


def shield_verdict(
    *,
    gate_ok: bool,
    book_ok: bool,
    net_xrp_usd_val: float,
    short_usd: float,
    last_entry: float | None,
    mark: float | None,
    released: bool,
    cap: float = HEDGE_CAP,
    pump_cut: float = PUMP_CUT,
    rearm_band: float = REARM_BAND,
    resize_band: float = RESIZE_BAND,
) -> str:
    """One shield mode. Clerks print this; the LLM must not invent RELEASE."""
    if not gate_ok or not book_ok:
        return HOLD
    target = hedge_notional(net_xrp_usd_val, cap)
    short = max(0.0, float(short_usd))

    if released:
        if last_entry and mark and last_entry > 0:
            move = pump_pct(mark, last_entry)
            if move is not None and move <= rearm_band and target > 0:
                return RE_ARM
        return HOLD

    if short > 0 and last_entry and mark and last_entry > 0:
        move = pump_pct(mark, last_entry)
        if move is not None and move >= pump_cut:
            return RELEASE

    if target <= 0:
        return HOLD if short <= 1 else RESIZE

    if short <= 1:
        return SHIELD_ON

    if abs(short - target) / max(cap, 1.0) >= resize_band:
        return RESIZE
    return HOLD


def heal_verdict(
    *,
    server_ok: bool,
    books_ok: bool,
    leverage_ok: bool,
    oneway_ok: bool,
    bot_running: bool,
    orphan_short_usd: float,
    stale_quote_count: int,
) -> str:
    """One heal action. Order is safety first, then venue, then quotes."""
    if not server_ok:
        return STOP
    if float(orphan_short_usd) > 1:
        return CLOSE_ORPHAN
    if int(stale_quote_count) > 0:
        return CANCEL_STALE
    if not oneway_ok:
        return SET_ONEWAY
    if not leverage_ok:
        return SET_LEVERAGE
    if not books_ok:
        return WARM_BOOK
    if not bot_running:
        return REDEPLOY
    return HEALTHY


def issuer_ok(code: str, issuer: str) -> bool:
    c = (code or "").upper()
    i = (issuer or "").strip()
    if c == "XRP":
        return True
    if c == "RLUSD":
        return i == RLUSD_ISSUER
    if c == "USDC":
        return i == USDC_ISSUER
    return False


MIN_PAIR_QUOTE = 2.0
BUDGET_HAIRCUT = 0.80


def cap_quote_budget(
    plan: float,
    quote_free: float,
    base_free: float,
    px: float,
    haircut: float = BUDGET_HAIRCUT,
    min_quote: float = MIN_PAIR_QUOTE,
) -> tuple[float, str]:
    """Fit pmm_simple total_amount_quote to live inventory.

    One number feeds both bids and asks. Oversizing the thin side is what
    floods Hummingbot with INSUFFICIENT_BALANCE. Never return a budget the
    wallet cannot open on *both* sides.
    """
    plan = max(float(plan or 0), 0.0)
    px = max(float(px or 0), 0.0)
    h = min(max(float(haircut), 0.0), 1.0)
    buy_cap = max(float(quote_free or 0), 0.0) * h
    sell_cap = max(float(base_free or 0), 0.0) * px * h
    capped = min(plan, buy_cap, sell_cap)
    if capped < min_quote:
        return 0.0, (
            f"HOLD budget: plan={plan:.2f} buy_cap={buy_cap:.2f} "
            f"sell_cap={sell_cap:.2f} — do not deploy this pair"
        )
    note = (
        f"budget: plan={plan:.2f} buy_cap={buy_cap:.2f} sell_cap={sell_cap:.2f} "
        f"controller_total_amount_quote={capped:.2f}"
    )
    return capped, note
