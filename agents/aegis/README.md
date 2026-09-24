# AEGIS — isolated Condor agent

Drop-in Builders Cup entry. **Does not modify Condor engine or any other agent.**

```
agents/aegis/
  AGENT.md                         # BRAIN
  strategies/aegis_operator/
    strategy.md                    # HANDS
  routines/
    _aegis_math.py                 # pure math (not a routine)
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
