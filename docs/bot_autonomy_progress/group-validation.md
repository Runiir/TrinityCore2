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
