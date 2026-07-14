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

## 2026-06-20

- Hardened `tools/bot_ml/build_validation_run_status.py` so route-node id drift between regenerated validation plans and older live segment artifacts is reported as `warnings: ["route_node_id_drift"]` instead of invalidating otherwise matching segment evidence.
- Added regressions in `tests/test_ml_pipeline.py` for direct live segment reports and aggregate `segment_results` with route-node drift.
- Rebuilt `dataset/validation_run_status/manifest.json` with `pixi run dvc repro validation_run_status`; DVC pushed the updated validation status and scenario report outputs.
- Current evidence paths: `dataset/validation_run_status/manifest.json`, `dataset/live_validation_scenario_reports_built/stonecore_5n.json`, `dataset/live_validation_scenario_reports_built/blackwing_descent_10n.json`, `.codex/plans/auto_bots/master_checklist.json`.
- Current status: Stonecore trash segments `01_entrance_packs`, `03_crystalspawn_corridor`, `05_stonecore_sentry_gauntlet`, and `07_twilight_flayer_packs` are recognized as ready despite route-node drift. Stonecore boss segments still lack required pull/tank/healer/regroup evidence. Blackwing Descent segments still carry failures or missing required group/mechanic evidence. Both full clears remain blocked by `missing_uninterrupted_full_clear_report`.
- Validation run: `pixi run pytest -q tests/test_ml_pipeline.py` passed with 122 tests.
- DVC status after push still reports pre-existing `live_validation_combined` stale dependency on `tools/bot_ml/run_live_bot_validation.py`; no live validation run was launched in this pass.
