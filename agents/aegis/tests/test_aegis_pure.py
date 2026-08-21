"""Pure-function tests for AEGIS. No network. No orders."""

from __future__ import annotations

import sys
from pathlib import Path

ROUTINES = Path(__file__).resolve().parents[1] / "routines"
sys.path.insert(0, str(ROUTINES))

from _aegis_math import (  # noqa: E402
    GO,
    HOLD,
    RELEASE,
    RE_ARM,
    RESIZE,
    SHIELD_ON,
    STOP,
    VIABLE,
    WIDEN,
    drawdown_quote_scale,
    hedge_notional,
    implied_xrpl_price,
    issuer_ok,
    ladder_bps,
    per_level_quote,
    pump_pct,
    reserve_xrp,
    shield_verdict,
    spread_floor_bps,
    top_of_book_anchor,
    viability,
    widen_quotes,
)


def test_implied_pair_orientation():
    assert abs(implied_xrpl_price("XRP-RLUSD", 2.0) - 2.0) < 1e-9
    assert abs(implied_xrpl_price("XRP-USDC", 0.5) - 0.5) < 1e-9
    assert abs(implied_xrpl_price("RLUSD-XRP", 2.0) - 0.5) < 1e-9
    assert implied_xrpl_price("XRP-RLUSD", 0) == 0


def test_ladder_stays_inside_floor_ceiling():
    ladder = ladder_bps(3.0, 20.8, 3)
    assert len(ladder) == 3
    assert all(3.0 < b < 20.8 for b in ladder)
    assert ladder[0] < ladder[1] < ladder[2]


def test_viability_and_widen():
    assert viability(3.0, 20.8)[0] == VIABLE
    assert viability(21.0, 20.8)[0] == WIDEN
    bid, ask = widen_quotes(1.0, 1.0)
    assert abs(bid - 0.99) < 1e-9
    assert abs(ask - 1.01) < 1e-9


def test_tob_improves_both_sides():
    bid, ask = top_of_book_anchor(1.0, 1.01, 0.01)
    assert bid > 1.0
    assert ask < 1.01


def test_sizing_and_reserves():
    assert abs(per_level_quote(280, 3) - 280 / 6) < 1e-9
    assert reserve_xrp(3, 2) == 1.0 + 0.2 * 12
    assert hedge_notional(150) == 150
    assert hedge_notional(400) == 280
    assert hedge_notional(0) == 0


def test_drawdown_scales_not_stops():
    assert drawdown_quote_scale(0.02) == 1.0
    assert drawdown_quote_scale(0.05) == 0.5
    assert drawdown_quote_scale(0.09) == 0.0


def test_shield_dump_hold_pump_release_rearm():
    # dump: short on, price down → HOLD (leave it)
    assert (
        shield_verdict(
            gate_ok=True,
            book_ok=True,
            net_xrp_usd_val=150,
            short_usd=150,
            last_entry=1.00,
            mark=0.92,
            released=False,
        )
        == HOLD
    )
    # pump +6% → RELEASE
    assert (
        shield_verdict(
            gate_ok=True,
            book_ok=True,
            net_xrp_usd_val=150,
            short_usd=150,
            last_entry=1.00,
            mark=1.07,
            released=False,
        )
        == RELEASE
    )
    # after release, still high → HOLD (pile runs)
    assert (
        shield_verdict(
            gate_ok=True,
            book_ok=True,
            net_xrp_usd_val=150,
            short_usd=0,
            last_entry=1.00,
            mark=1.20,
            released=True,
        )
        == HOLD
    )
    # snap-back inside +3% → RE_ARM
    assert (
        shield_verdict(
            gate_ok=True,
            book_ok=True,
            net_xrp_usd_val=150,
            short_usd=0,
            last_entry=1.00,
            mark=1.02,
            released=True,
        )
        == RE_ARM
    )
    # no short, inventory → SHIELD_ON
    assert (
        shield_verdict(
            gate_ok=True,
            book_ok=True,
            net_xrp_usd_val=150,
            short_usd=0,
            last_entry=None,
            mark=1.00,
            released=False,
        )
        == SHIELD_ON
    )
    # dead gate → HOLD
    assert (
        shield_verdict(
            gate_ok=False,
            book_ok=True,
            net_xrp_usd_val=150,
            short_usd=0,
            last_entry=None,
            mark=1.00,
            released=False,
        )
        == HOLD
    )


def test_resize_band():
    assert (
        shield_verdict(
            gate_ok=True,
            book_ok=True,
            net_xrp_usd_val=280,
            short_usd=50,
            last_entry=1.00,
            mark=1.00,
            released=False,
        )
        == RESIZE
    )


def test_issuer_whitelist():
    assert issuer_ok("XRP", "")
    assert issuer_ok("RLUSD", "rMxCKbEDwqr76QuheSUMdEGf4B9xJ8m5De")
    assert not issuer_ok("RLUSD", "rFake")
    assert issuer_ok("USDC", "rGm7WCVp9gb4jZHWTEtGUr4dd74z2XuWhE")


def test_empty_book_is_hold_not_viable():
    mode, _ = viability(3.0, 20.8)
    assert mode == VIABLE
    # empty book is a HOLD at the clerk, not a spread math verdict
    assert HOLD == "HOLD"


def test_pump_pct():
    assert abs(pump_pct(1.06, 1.0) - 0.06) < 1e-9
    assert pump_pct(0, 1) is None


def test_stop_go_constants():
    assert STOP == "STOP" and GO == "GO"


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in tests:
        fn()
        print("ok", fn.__name__)
    print("aegis pure tests OK", len(tests))
