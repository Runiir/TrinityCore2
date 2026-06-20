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

## 2026-06-20

- Hardened `tools/bot_ml/build_validation_run_status.py` so route-node id drift between regenerated validation plans and older live segment artifacts is reported as `warnings: ["route_node_id_drift"]` instead of invalidating otherwise matching segment evidence.
- Added regressions in `tests/test_ml_pipeline.py` for direct live segment reports and aggregate `segment_results` with route-node drift.
- Rebuilt `dataset/validation_run_status/manifest.json` with `pixi run dvc repro validation_run_status`; DVC pushed the updated validation status and scenario report outputs.
- Current evidence paths: `dataset/validation_run_status/manifest.json`, `dataset/live_validation_scenario_reports_built/stonecore_5n.json`, `dataset/live_validation_scenario_reports_built/blackwing_descent_10n.json`, `.codex/plans/auto_bots/master_checklist.json`.
- Current status: Stonecore trash segments `01_entrance_packs`, `03_crystalspawn_corridor`, `05_stonecore_sentry_gauntlet`, and `07_twilight_flayer_packs` are recognized as ready despite route-node drift. Stonecore boss segments still lack required pull/tank/healer/regroup evidence. Blackwing Descent segments still carry failures or missing required group/mechanic evidence. Both full clears remain blocked by `missing_uninterrupted_full_clear_report`.
- Validation run: `pixi run pytest -q tests/test_ml_pipeline.py` passed with 122 tests.
- DVC status after push still reports pre-existing `live_validation_combined` stale dependency on `tools/bot_ml/run_live_bot_validation.py`; no live validation run was launched in this pass.
