# Group Validation Progress

## 2026-06-19

- Added generated validation evidence contracts for party/raid formation, role assignments, pulls, target priority, interrupts, healer assignments, tank positioning, regrouping, recovery, and instance reset.
- Propagated those contracts through scenario manifests, route manifests, run plans, live validation reports, aggregated scenario reports, and run-status blockers.
- Integration tightened scenario report labels so missing required evidence blocks full-clear status and candidate ML labels; Stonecore summary `boss_kills` now counts toward non-raid boss evidence.
- Generated deterministic Stonecore 5N and Blackwing Descent 10N validation manifests and a long-budget run plan with `--observe-sec 300` and `--timeout-sec 900`.
- Generated run-status output from the plan. Both scenarios remain blocked by incomplete/stale live segment evidence rather than being marked clear.
- Focused pytest passed: `pixi run pytest tests/test_ml_pipeline.py -k 'live_bot_validation or live_scenario_report or validation_scenario or validation_run_plan or validation_run_status'` with 43 passed.
- `pixi run dvc repro validation_run_status`, `pixi run dvc repro world_planner_validate`, and `pixi run dvc repro live_validation_combined` completed.
- `pixi run dvc status` reports data and pipelines up to date.

## 2026-07-14

- Stonecore run 081 naturally killed Corborus and demonstrated wipe recovery through ordinary tactical retreat, combat disengagement, and native resurrection; it used no forced combat, death, resurrection, or terminal state.
- The run then exposed a forward-progress defect: two damage dealers selected the previous route anchor while retreating after the Crystalspawn corridor wipe and became stranded behind the Corborus transition.
- Tactical retreat is now pinned to the current route node's navigation anchor. This preserves natural leash recovery without allowing recovery movement to cross a completed one-way encounter transition.
- Raw run 081 diagnostics and its compact role-efficiency report were pushed to DVC, then evicted locally to minimize disk use.
- Run 082 remained deathless for 31 kills with no stuck or repeated-decision events. Role telemetry showed 97.3% successful healing casts, zero tank cast failures, and strong DPS active-action coverage before the route blocker.
- The remaining hunter cast failures and reduced threat-retention sample were attempts against transitioned, mechanic-immune Millhouse. The pending scripted-transition GUID was being re-enrolled from a stale combat reference after each discovered pack terminal.
- Pending final-transition GUIDs are now excluded from natural pack enrollment until node completion promotes them to the final exclusion set. Run 082 raw evidence and its compact audit were pushed to DVC and evicted locally before this change.
- Run 083 cleared four discovery packs and reached 37 deathless kills with no stuck, repath, or repeated-decision events. Tank threat retention improved to 90.7%, confirming the run 082 threat flag was transition-contaminated.
- The completed fourth pack could not become terminal because party-wide active-combat detection still counted Millhouse's pending-transition stale combat reference. Pending/final transition GUIDs are now excluded from that predicate, and ineligible route targets are hard-rejected before profile action submission.
- Run 083 raw evidence and compact role audit were pushed to DVC and evicted locally. Its 86.5% healing submission success remains a separate role-quality signal for later matched evidence; the party had zero deaths.
- Run 084 naturally killed Corborus, recovered the entire group after a four-death Crystalspawn wipe, advanced through the corridor, and engaged Slabhide. It ended with a worldserver SIGSEGV at Slabhide 11.5%, not a route or watchdog failure; no core was retained by the host crash handler.
- Matched role telemetry improved to 97.3% healing success and 93.7% tank threat retention. The only role gate was 22.5% hunter cast failure, all `TOO_CLOSE` on large bosses.
- Hunter minimum range is now derived from each spell's hostile minimum plus caster/target melee reach, with the profile minimum as a floor. The resolved action carries that range into movement planning before cast submission.
- Run 084 raw evidence and compact role audit were pushed to DVC and evicted locally.
- Run 085 killed Corborus and Slabhide naturally, recovered one Slabhide death, advanced to Ozruk at route index 9, and did not reproduce the run 084 SIGSEGV. It was stopped only by the semantic plateau watchdog while all five bots were alive and moving seven yards per decision toward the boss.
- Spell-aware hunter spacing reduced cast failures from 22.5% to 3.8%; fire and enhancement had zero cast failures, healing succeeded at 95.1%, and the tank had zero cast failures. The matched tank threat-retention sample was 79.9% and remains under observation.
- The completion watchdog now counts route-terminal evidence as progress and will not declare a semantic plateau while diagnosis reports active movement. Run 085 raw evidence and compact role audit were pushed to DVC and evicted locally.
- Run 086 naturally killed Corborus and Slabhide without deaths, cleared the 39-member sentry-gauntlet ledger, and then correctly stopped on a real combat deadlock: two naturally pulled attackers remained outside the configured entry allowlist, so the cohort could neither target them nor leave combat.
- Natural creatures present in the active cohort's PvE combat references are now enrolled in the persisted route pack even when their entries are not in the discovery list. This keeps enrollment bounded to actual combat while allowing every legitimate attacker to be finished.
- The matched role audit passed tank threat retention at 91.7%, with zero tank and enhancement cast failures; fire and hunter failures were 1.8% and 1.4%. Healing narrowly missed at 94.4% because Prayer of Mending was guarded by spell 33076 rather than its applied aura 41635. The priest profiles now suppress recasts using aura 41635.
- Run 086 raw evidence and compact role audit were pushed to DVC before diagnosis; their materialized files are evicted after the fix is recorded.

## 2026-06-20

- Hardened `tools/bot_ml/build_validation_run_status.py` so route-node id drift between regenerated validation plans and older live segment artifacts is reported as `warnings: ["route_node_id_drift"]` instead of invalidating otherwise matching segment evidence.
- Added regressions in `tests/test_ml_pipeline.py` for direct live segment reports and aggregate `segment_results` with route-node drift.
- Rebuilt `dataset/validation_run_status/manifest.json` with `pixi run dvc repro validation_run_status`; DVC pushed the updated validation status and scenario report outputs.
- Current evidence paths: `dataset/validation_run_status/manifest.json`, `dataset/live_validation_scenario_reports_built/stonecore_5n.json`, `dataset/live_validation_scenario_reports_built/blackwing_descent_10n.json`, `.codex/plans/auto_bots/master_checklist.json`.
- Current status: Stonecore trash segments `01_entrance_packs`, `03_crystalspawn_corridor`, `05_stonecore_sentry_gauntlet`, and `07_twilight_flayer_packs` are recognized as ready despite route-node drift. Stonecore boss segments still lack required pull/tank/healer/regroup evidence. Blackwing Descent segments still carry failures or missing required group/mechanic evidence. Both full clears remain blocked by `missing_uninterrupted_full_clear_report`.
- Validation run: `pixi run pytest -q tests/test_ml_pipeline.py` passed with 122 tests.
- DVC status after push still reports pre-existing `live_validation_combined` stale dependency on `tools/bot_ml/run_live_bot_validation.py`; no live validation run was launched in this pass.
