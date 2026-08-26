"""Validate AEGIS against Condor's real loaders (no network, no trading).

Organizers: run from the Condor repo root
  .venv/bin/python agents/aegis/tests/validate_agent.py
"""
import ast
import inspect
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
os.chdir(REPO)

ok = True

from routines.base import discover_routines_from_path

rdir = REPO / "agents/aegis/routines"
found = discover_routines_from_path(rdir, agent_slug="aegis")
print("=== ROUTINE DISCOVERY ===")
for name in sorted(found):
    info = found[name]
    fields = list(info.config_class.model_fields) if getattr(info, "config_class", None) else []
    print(f"  [OK] {name:<22} category={info.category:<12} config_fields={fields}")
for expected in (
    "aegis_health",
    "aegis_quote_planner",
    "aegis_inventory",
    "aegis_shield",
    "aegis_init",
    "aegis_heal",
):
    if expected not in found:
        print(f"  [FAIL] {expected} NOT discovered")
        ok = False
if "_aegis_math" in found:
    print("  [FAIL] _aegis_math should not be a routine (helper only)")
    ok = False
if "_aegis_report" in found:
    print("  [FAIL] _aegis_report should not be a routine (helper only)")
    ok = False

print("\n=== ROUTINE CONTRACT ===")
VALID = {"Market Data", "Analysis", "Arbitrage", "Monitoring"}
for name, info in sorted(found.items()):
    has_run = inspect.iscoroutinefunction(info.run_fn)
    good = has_run and info.config_class is not None and info.category in VALID
    ok &= good
    print(
        f"  [{'OK' if good else 'FAIL'}] {name:<22} "
        f"async_run={has_run} Config={bool(info.config_class)} CATEGORY={info.category!r}"
    )

print("\n=== AGENT / STRATEGY LOADING ===")
from condor.agents.agent import AgentStore
from condor.agents.strategy import StrategyStore
from condor.frontmatter import slugify as _slugify

agent = AgentStore().get("aegis")
if not agent:
    print("  [FAIL] agent 'aegis' not loaded")
    ok = False
else:
    print(f"  [OK] agent slug={agent.slug} key={agent.agent_key} created_by={agent.created_by}")
    if str(agent.created_by).strip().isdigit() and str(agent.created_by).strip() != "0":
        print("  [FAIL] created_by must not be a raw numeric account id")
        ok = False
    body = (agent.instructions or "").lower()
    leaked = [b for b in ("hy3", "deepseek", "opencode-go") if b in body]
    if leaked:
        print(f"  [FAIL] AGENT.md body leaks provider names: {leaked}")
        ok = False
    else:
        print("  [OK] AGENT.md body has no provider names")
    banned = (
        "gateforum",
        "midas",
        "delta raptor",
        "delta_raptor",
        "theta",
        "smart_money",
        "sats",
    )
    hit = [b for b in banned if b in body]
    if hit:
        print(f"  [FAIL] AGENT.md names another entry: {hit}")
        ok = False
    else:
        print("  [OK] AGENT.md names no other entry")

strats = [s for s in StrategyStore().list_all() if s.agent_slug == "aegis"]
if not strats:
    print("  [FAIL] no strategy loaded for aegis")
    ok = False
for s in strats:
    rl = (s.default_config or {}).get("risk_limits") or {}
    print(f"  [OK] strategy key={s.key} name={s.name}")
    print(f"       freq={s.default_config.get('frequency_sec')}s risk={rl}")
    if not isinstance(rl, dict) or not rl.get("require_triple_barrier"):
        print("  [FAIL] risk_limits must be nested and require_triple_barrier=true")
        ok = False
    if rl.get("max_leverage", 1) != 1:
        print("  [FAIL] max_leverage must be 1")
        ok = False
    if rl.get("max_position_size_quote", 0) > 280:
        print("  [FAIL] hedge cap must be ≤ $280")
        ok = False
    if "---" in Path(s.path).read_text()[4:].split("---", 1)[0] if False else "":
        pass
    exp = _slugify(s.name)
    d = (REPO / "agents/aegis/strategies" / exp).is_dir()
    ok &= d
    print(f"  [{'OK' if d else 'FAIL'}] folder '{exp}' matches slugified name")
    md = (REPO / "agents/aegis/strategies" / exp / "strategy.md").read_text()
    fm = md.split("---", 2)[1]
    if "Small-wallet" in fm or fm.count("---") > 0:
        print("  [FAIL] strategy frontmatter may be truncated (--- inside YAML)")
        ok = False
    if "controller_id" in md.lower() and "inside" not in md.lower():
        print("  [FAIL] strategy must say controller_id INSIDE executor_config")
        ok = False
    else:
        print("  [OK] strategy documents controller_id inside executor_config")
    if "action=\"create\"" not in md and "action=\"create\"" not in md.replace("'", '"'):
        if 'action="create"' not in md:
            print("  [FAIL] strategy must require action=create")
            ok = False
    if "stop_loss\": 0.06" not in md and "stop_loss: 0.06" not in md:
        print("  [FAIL] pump cut must be 0.06 not 6")
        ok = False
    else:
        print("  [OK] stop_loss is decimal 0.06")

print("\n=== ISOLATION ===")
imports = []
for py in (REPO / "agents/aegis").rglob("*.py"):
    tree = ast.parse(py.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imports.append((py.name, node.module))
        elif isinstance(node, ast.Import):
            for a in node.names:
                imports.append((py.name, a.name))
bad = [
    f"{f}: {m}"
    for f, m in imports
    if m.startswith("agents.")
    or "gateforum" in m
    or "midas" in m
    or "delta_raptor" in m
    or m.endswith("theta")
]
if bad:
    print("  [FAIL] cross-agent imports:", bad)
    ok = False
else:
    print("  [OK] no other-agent imports")

print("\n=== RESULT:", "ALL CHECKS PASSED" if ok else "FAILURES PRESENT", "===")
sys.exit(0 if ok else 1)
