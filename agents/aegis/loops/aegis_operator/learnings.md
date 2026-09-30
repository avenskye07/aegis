# Learnings

## Market Observations
- [2026-08-26 08:50] RLUSD quote_free hit $0 on tick #4 (buy_cap=0, sell_cap still $33) — RLUSD side of the wallet can drain to zero independent of XRP inventory; planner correctly HOLDs the pair rather than posting bids it can't fund.
- [2026-08-26 09:39] Tick #8: base_free reads -14.05 XRP identically on both RLUSD and USDC planner calls while inventory reports 37.5 tradable XRP — same magnitude negative value across both books points to a shared global lock/accounting bug, not a per-book issue.

## Execution Notes
- [2026-08-26 08:11] Gate position_executor create aborted: `controller_id` must equal session `agent_id` (`aegis.aegis_operator_1`), not slug `aegis`. Risk permission cancels that as unattributable.
- [2026-08-26 08:25] aegis_inventory and aegis_shield routines default core_min_usd=80 and hedge_cap=280 (strategy-file defaults) unless explicitly passed — must always pass this session's config values (core_min_usd=20, hedge_cap=30) or results are wrong.
- [2026-08-26 08:25] manage_bots update_config cannot add a controller that wasn't part of the original deploy (404 "not found for bot") — a controller skipped at deploy time (e.g. empty book) requires stop_bot + redeploy to add later, not update_config.
- [2026-08-26 08:35] Never upsert pmm_simple total_amount_quote above planner `controller_total_amount_quote`. That cap is min(plan, 80% quote_free, 80% base*px). Oversizing the thin side floods `INSUFFICIENT_BALANCE`.
- [2026-08-26 08:37] Repeated "Not enough budget to open position" on XRP sell-side (ask) orders both XRPL books, despite aegis_inventory reporting 45 tradable XRP (well above the ~24 XRP both ask ladders need) — likely a free-balance-vs-locked-in-open-orders mismatch on the XRPL wallet, not a real inventory shortfall.
- [2026-08-26 08:50] Only aegis_xrp_usdc controller was ever actually running on the live bot — aegis_xrp_rlusd was never deployed despite tick #2/#3 journal entries claiming both were live; always verify via manage_bots(action="status"/"get_config") on the actual (possibly timestamp-suffixed) bot name, don't trust prior journal claims.
- [2026-08-26 09:15] aegis_inventory reports tradable_xrp ~30.9 XRP while same-tick aegis_quote_planner base_free is only ~0.6 XRP on both books combined — gap this large points to stale/leftover XRPL DEX offers locking XRP that heal's stale-order check (backend-tracked only) doesn't see, not a true inventory shortfall.
- [2026-08-26 09:27] Tick #7 planner base_free went negative (-20.85 XRP) on both books simultaneously while aegis_inventory reports 29.6 tradable XRP — confirms the tick #6 lock-mismatch is worsening, not transient; likely stale XRPL DEX offers over-locking XRP beyond actual holdings.
- [2026-08-26 09:39] aegis_shield defaults short_usd=0 if not passed explicitly, causing a false SHIELD_ON verdict even when heal reports a live short — always pass short_usd from heal's live_short_usd every tick, not just hedge_cap/core_min_usd.
- [2026-08-26 10:25] base_free lock value has held flat at exactly -12.44 XRP across ticks #10-#12 (vs -13.51 at #9) — the stale-offer lock looks fixed/static, not accumulating further; likely one leftover XRPL DEX offer rather than a growing leak.

## Retired Insights
