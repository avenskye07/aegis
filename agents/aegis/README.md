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

## Executor bug (do not "fix" in the engine)

Standalone creates are blocked if `controller_id` is only a top-level
`manage_executors` arg (`prompts.py` vs `risk.py`). AEGIS follows GateForum /
MIDAS: put `controller_id` **inside** `executor_config`, and always send
`action="create"` + `total_amount_quote` + a full `triple_barrier_config`.
`stop_loss` is `0.06` (6%), never `6`. No trailing stop on the hedge.
