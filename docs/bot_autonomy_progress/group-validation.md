# Group Validation Progress

## 2026-06-19

- Added generated validation evidence contracts for party/raid formation, role assignments, pulls, target priority, interrupts, healer assignments, tank positioning, regrouping, recovery, and instance reset.
- Propagated those contracts through scenario manifests, route manifests, run plans, live validation reports, aggregated scenario reports, and run-status blockers.
- Generated deterministic Stonecore 5N and Blackwing Descent 10N validation manifests and a long-budget run plan with `--observe-sec 300` and `--timeout-sec 900`.
- Generated run-status output from the plan. Both scenarios are blocked locally by missing live segment reports, missing required segment evidence, and missing aggregated scenario reports.
- Live validation was not executed locally because this worktree lacks required DVC/cache inputs and live worldserver evidence artifacts. `dvc commit -f validation_scenarios validation_run_plan validation_run_status` failed because `dataset/validation_provisioning/report.json` is missing.
- Focused pytest passed: `pixi run pytest tests/test_ml_pipeline.py -k 'validation_scenario_manifests or validation_run_plan or validation_run_status or live_bot_validation or live_scenario_report_builder'`.
