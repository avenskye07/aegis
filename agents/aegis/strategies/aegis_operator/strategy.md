---
name: Aegis Operator
description: >-
  Tick playbook for AEGIS — quote XRP-RLUSD and XRP-USDC on xrpl, shield
  net XRP with a 1x Gate short, dump-hedge / pump-release, journal.
agent_key: null
skills: []
default_config:
  frequency_sec: 600
  execution_mode: loop
  total_amount_quote: 800
  bot_mode: bot
  bot_name_rlusd: aegis-xrp-rlusd
  bot_name_usdc: aegis-xrp-usdc
  xrpl_pair_a: XRP-RLUSD
  xrpl_pair_b: XRP-USDC
  quote_a_usd: 280
  quote_b_usd: 140
  levels_per_side: 3
  executor_refresh_time: 45
  skip_rebalance: true
  adverse_k: 1.0
  widen_distance_pct: 1.0
  top_of_book_improve_pct: 0.01
  rlusd_issuer: rMxCKbEDwqr76QuheSUMdEGf4B9xJ8m5De
  usdc_issuer: rGm7WCVp9gb4jZHWTEtGUr4dd74z2XuWhE
  reference_connector: binance_perpetual
  reference_pair: XRP-USDT
  hedge_connector: gate_io_perpetual
  hedge_pair: XRP-USDT
  hedge_cap: 280
  core_min_usd: 80
  pump_cut: 0.06
  rearm_band: 0.03
  risk_limits:
    max_position_size_quote: 280
    max_open_executors: 2
    max_drawdown_pct: 8
    max_leverage: 1
    require_triple_barrier: true
    require_trailing_stop: false
default_trading_context: >-
  Trade XRP-RLUSD and XRP-USDC on xrpl. Shield net XRP with XRP-USDT on
  gate_io_perpetual at 1x. Both books stay on. No hunt.
created_by: 0
created_at: '2026-08-21T00:00:00+00:00'
---

# Aegis Operator

> Identity lives in AGENT.md. This file is the tick: connectors, sizes,
> barriers, call shapes. Follow it. Clerks print numbers; you apply one
> verdict. Do not invent a price, a size, or RELEASE.

Read every runtime value from `[CURRENT CONFIG]`.

## Locked wallet (one $800 race)

| Sleeve | $ | Duty |
|---|---|---|
| XRPL wallet | **500** | Quotes + XRP pile + reserves |
| XRP-RLUSD quotes | **280** | 3×2 offers, ~$47 / level when tight |
| XRP-USDC quotes | **140** | 3×2 offers, ~$23 / level when tight |
| Reserves / shock | **~80** | 1 + 0.2×offers XRP — not tradable |
| Gate USDT | **300** | 1x short margin. Used = min(net XRP Δ, **280**) |
| Core pile | **80–120** of the XRP leg | Unsellable. Inside inventory, not extra cash |

`$280` on Gate is a **cap**, not a standing short. Flat inventory → short **$0**. After RELEASE → short **$0**.

Bot names stay in the ownership namespace: `aegis-xrp-rlusd`, `aegis-xrp-usdc`. Do not use `rlusd-xrp-maker` or any other agent's bot name.

## Issuers (whitelist)

| Asset | Issuer |
|---|---|
| RLUSD | `rMxCKbEDwqr76QuheSUMdEGf4B9xJ8m5De` |
| USDC | `rGm7WCVp9gb4jZHWTEtGUr4dd74z2XuWhE` |

Never quote an issuer not in this table.

## Startup

- Tick #1/#2 XRPL `notSynced` / HTTP 500 → **HOLD entire tick**. No deploy, no cancel.
- Tick #3+ still failing → journal `category="execution"`.
- CEX reference errors are hard stops for quoting (do not quote blind).
- Gate unreachable → **do not quote** (cannot shield a fill).
- First Gate perp: `set_leverage(1)` on `XRP-USDT` before the first shield create.
- Bootstrap: if tradable XRP is ~0, post **bids only** (buy XRP). Asks wait until inventory exists. Shield stays HOLD.

## Each tick (600s)

**1 — Health.** `manage_routines(action="run", routine="aegis_health")`.
`STOP` → HOLD the whole tick. Journal why.

**2 — Quotes.** Run the planner **twice**, once per pair:

```
manage_routines(action="run", routine="aegis_quote_planner",
  config={"xrpl_pair": "XRP-RLUSD",
          "requote_interval_sec": 45,
          "levels_per_side": 3,
          "total_amount_quote": 280,
          "quote_issuer": "<RLUSD issuer>"})
manage_routines(action="run", routine="aegis_quote_planner",
  config={"xrpl_pair": "XRP-USDC",
          "requote_interval_sec": 45,
          "levels_per_side": 3,
          "total_amount_quote": 140,
          "quote_issuer": "<USDC issuer>"})
```

Use `requote_interval_sec` = `executor_refresh_time` (45), **not** `frequency_sec`. Wrong interval inflates the floor.

Per pair:

| Verdict | Action |
|---|---|
| `HOLD` / empty book / notSynced | Do not quote that pair |
| `VIABLE` | 6 offers (3 bid + 3 ask). L1 = TOB − 0.01%. Spreads = `controller_spreads` fractions |
| `WIDEN` | 1 bid + 1 ask at 1% from mid. Keep quoting. Do not stop |

**3 — Inventory.** `manage_routines(action="run", routine="aegis_inventory")`.
Pass live `xrp_usd` if you have it. `core_intact: false` after RELEASE is **not** a reason to sell XRP.

**4 — Shield.** `manage_routines(action="run", routine="aegis_shield")` with
`net_xrp_usd`, `short_usd`, `last_entry`, `mark`, `released` from journal/memory.

| Verdict | Action |
|---|---|
| `HOLD` | Leave the short (or stay flat) |
| `SHIELD_ON` | Open 1x short = `target_short_usd` with the barrier block below |
| `RESIZE` | Adjust short toward target. Band ±8% of cap. Not every tick |
| `RELEASE` | Stop the short **only**. Do **not** sell XRPL XRP. Write `released=true` + keep last_entry |
| `RE_ARM` | Price back inside +3% of last_entry → put the shield back. Clear released |

Dump → leave the short. Never take profit on a dump (TP is 80% so a crash cannot close it).

**5 — Quote deploy** (controller first).

`pmm_simple` only. `leverage=1`. Triple-barrier fields **null** on XRPL (no SL/TP on the book).

```
manage_bots(action="deploy", bot_name="aegis-xrp-rlusd",
  controller="pmm_simple",
  max_global_drawdown_quote=<from risk>,
  config={connector_name: "xrpl",
          trading_pair: "XRP-RLUSD",
          total_amount_quote: <planner controller_total_amount_quote or 280>,
          buy_spreads / sell_spreads: <controller_spreads>,
          executor_refresh_time: 45,
          skip_rebalance: true,
          leverage: 1,
          stop_loss: null, take_profit: null, time_limit: null, trailing_stop: null})
```

Same for `aegis-xrp-usdc` at $140. Retune **both** controller stores when spreads change. Fall back to LIMIT_MAKER executors only after a recorded controller failure — then still put `controller_id` **inside** `executor_config`.

If one pair HOLDs, do not kill the other.

**6 — Journal** every tick: health, both quote verdicts, net Δ, shield mode, pile kept yes/no, funding if any.

## Open / cut the Gate shield (REQUIRED call shape)

The risk gate refuses a create without `total_amount_quote` and a full barrier.
Put `controller_id` **INSIDE** `executor_config` (the gate reads it only there —
same as GateForum / MIDAS). Do **not** pass it only as a top-level arg.

`stop_loss` / `take_profit` are **decimals** (0.06 = 6%). Never write `6`.
Do not attach a trailing stop (a trail arms on dumps). Prefer no trail; if
the platform demands one, `activation_price: 0.45` and `trailing_delta: 0.02`
so a normal dump cannot arm it.

```
manage_executors(
  action="create",
  executor_type="position_executor",
  executor_config={
    connector_name="gate_io_perpetual",
    trading_pair="XRP-USDT",
    side=2,
    total_amount_quote=<target_short_usd>,
    amount=<target_short_usd / mark>,
    leverage=1,
    controller_id=<this session's controller_id>,
    triple_barrier_config={
      "stop_loss": 0.06,
      "take_profit": 0.80,
      "time_limit": 172800,
      "open_order_type": 1
    }
  }
)
```

`side=2` is the short. `amount` is base XRP. `action="create"` is required —
omit it and you only get the schema.

**Do not** `stop` a filled hedge to "refresh". Search executors first. A
RUNNING row with `filled_amount_quote > 0` is the shield. Only cancel unfilled
quotes.

RELEASE / flatten: `manage_executors(action="stop", ..., keep_position=False)`
on **that** short only.

## Drawdown (scale, don't kill)

| Account DD | Quotes | Hedge |
|---|---|---|
| 0–4% | full $420 | full Δ ≤ $280 |
| 4–8% | half, widen | keep hedge |
| >8% | widen, no new size | keep hedge if still long XRP |

`max_drawdown_pct: 8` is a scaler, not flatten. Never increase size in DD.

## Do not

- Do not hunt. Do not rotate 100% onto one pair.
- Do not sell the core pile after RELEASE.
- Do not flatten the short because funding flipped while you still hold XRP.
- Do not use `place_order`.
- Do not pass `controller_id` only top-level (gate treats it as missing).
- Do not set `stop_loss: 6` (that is 600%).
- Do not attach a real trailing stop on the hedge.
- Do not leverage above 1.
- Do not edit Condor engine files. This agent is only `agents/aegis/`.

## Cheat sheet

| # | Clerk | Verdicts |
|---|---|---|
| 1 | `aegis_health` | STOP / GO |
| 2 | `aegis_quote_planner` ×2 | VIABLE / WIDEN / HOLD |
| 3 | `aegis_inventory` | net Δ, core_intact |
| 4 | `aegis_shield` | SHIELD_ON / RESIZE / RELEASE / RE_ARM / HOLD |
| 5 | You | one hedge action + quote retune + journal |

## Organizer sandbox

Copy **only** `agents/aegis/`. No edits to `condor/agents/*.py`. No extra packages.

1. Connect `xrpl` (wallet + trustlines) and `gate_io_perpetual`.
2. Seed: reserve XRP always. Race: tradable XRP + RLUSD + USDC. Bootstrap: stables on bids first.
3. Start `aegis` / `aegis_operator`. Override `agent_key` if needed.
4. `python agents/aegis/tests/validate_agent.py` from the repo root.
5. `python agents/aegis/tests/test_aegis_pure.py`

Folder name must stay `aegis_operator` (slug of `Aegis Operator`).
