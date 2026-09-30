# AEGIS — isolated Condor agent

Drop-in Builders Cup entry. **Does not modify Condor engine or any other agent.**

```
agents/aegis/
  AGENT.md                         # BRAIN
  loops/aegis_operator/
    loop.md                        # HANDS
  controllers/
    aegis_ward_mm.py               # XRPL book maker (copy into Hummingbot API)
  routines/
    _aegis_math.py                 # pure math (not a routine)
    _aegis_desk.py                 # reads sizes from loop.md (not a routine)
    aegis_health.py
    aegis_init.py
    aegis_heal.py
    aegis_quote_planner.py
    aegis_inventory.py
    aegis_shield.py
    _aegis_report.py               # dashboard ReportBuilder helper
  tests/
    test_aegis_pure.py
    validate_agent.py
  README.md
```

## Checks (no trading)

```bash
# from condor repo root
./.venv/bin/python agents/aegis/tests/test_aegis_pure.py
./.venv/bin/python agents/aegis/tests/validate_agent.py
```

## Controller install

Copy `controllers/aegis_ward_mm.py` into the Hummingbot API
`bots/controllers/market_making/` before the first deploy. It is the only
controller this agent uses. Requotes every 300 s, or early when mid walks
> 50 bps from the book's anchor (checked every 60 s, in code — no LLM).

Always set `buy_amounts_pct` / `sell_amounts_pct` explicitly (e.g. `[100]` per
level). Leaving them null crashes the controller with `sum(None)`.

## Executor contract (do not "fix" in the engine)

Standalone creates are blocked unless `controller_id` is passed as an argument
(`prompts.py` vs `risk.py`). Pass **this session's `agent_id`**
(`aegis.aegis_operator_1`), not the slug `aegis`.

The retired `manage_executors` mega-tool is gone: one tool per operation now,
so a missing argument is a validation error instead of silently routing to a
different branch. `create_position_executor` takes **flat keyword arguments** —
there is no `executor_config` dict and no `action="create"`, and
`total_amount_quote` does not exist for position executors (`amount` is in
**base** currency). Barriers are flat too: `stop_loss` / `take_profit` are
decimals (`0.06` = 6%), never `6`. No trailing stop on the hedge.
