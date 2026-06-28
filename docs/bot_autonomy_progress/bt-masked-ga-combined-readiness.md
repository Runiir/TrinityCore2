# BT Masked GA Combined Readiness

## 2026-06-28 Orchestrator Pass 000001

Branch `codex/ml/bt-masked-ga-combined` remains the selected Stonecore ML path: behavior-tree learned scoring plus masked ranker, with GA retained only as an offline helper. No C++ runtime control was added; the lane remains offline/shadow-only.

Current status: not merge-ready.

The blocker is real telemetry data. `dataset/bot_ml/decision_dataset_manifest.json` still contains the fixture-scale dataset: 4 candidate rows, 2 decision rows, and 2 observed-label rows. Acceptance requires real telemetry scale, so this pass does not claim merge readiness.

DB export attempts:

- `pixi run bot-ml-export --database-url mysql://trinity:trinity@172.20.0.2:3306/characters --output-dir dataset/bot_ml/raw`: failed, no route to host.
- `pixi run bot-ml-export --database-url mysql://trinity:trinity@127.0.0.1:3306/characters --output-dir dataset/bot_ml/raw`: failed, connection refused.

DVC and validation evidence:

- Main worktree `pixi run dvc status`: clean.
- Combined `.dvc/config.local`: present, gitignored, and equivalent to main DVC credentials.
- `pixi run dvc pull dvc.yaml:bot_ml_build_decisions dvc.yaml:bot_ml_validate dvc.yaml:bt_masked_ga_combined artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r12.dvc`: passed, everything up to date.
- `pixi run dvc repro bot_ml_validate`: passed, stages skipped as unchanged.
- `pixi run pytest -q tests/test_ml_pipeline.py -k bt_masked_ga_combined`: passed, 1 selected test, 176 deselected.
- `pixi run dvc repro bt_masked_ga_combined`: passed, stages skipped as unchanged.
- `pixi run pytest -q tests/test_ml_pipeline.py`: passed, 177 tests.
- `cmake -S . -B build -DCMAKE_BUILD_TYPE=RelWithDebInfo`: passed.
- `cmake --build build --target worldserver -j2`: passed.
- `pixi run dvc status`: still reports broad historical missing-cache and deleted-dependency state outside the selected combined lane. The selected `bot_ml_build_decisions`, `bot_ml_validate`, and `bt_masked_ga_combined` stages are present and reproducible.

Selected lane artifacts:

- `artifacts/ml_strategy_eval/bt_masked_ga_combined/report.json`
- `artifacts/ml_strategy_eval/bt_masked_ga_combined/metrics.json`
- `artifacts/ml_strategy_eval/bt_masked_ga_combined/stonecore_baseline_comparison.json`

Current metrics from fixture data:

- candidate rows: 4
- decision groups: 2
- server-valid candidate rows: 4
- uses server-valid action masks: true
- top-1 candidate ranking accuracy: 0.5
- top-3 candidate ranking accuracy: 1.0
- GA teacher match rate: 0.5
- runtime ML control: `offline_shadow_only`
- control eligible: false
- C++ runtime files changed: 0
- Stonecore regression: false
- baseline failure labels: none

Acceptance checklist:

- DVC stage reproduces cleanly: yes for the selected combined lane.
- Focused and full ML tests pass: yes.
- Dataset has real telemetry scale: no, blocked by unreachable characters DB.
- Server-valid candidate masks are preserved: yes.
- Stonecore baseline comparison shows no regression: yes.
- `control_eligible=false` and runtime mode remains offline/shadow only: yes.

Next prompt:

Continue `codex/ml/bt-masked-ga-combined` only. Do not launch new strategy lanes. Restore reachable characters DB access for `mysql://trinity:trinity@172.20.0.2:3306/characters` or provide the correct characters DB URL, then run `pixi run bot-ml-export --database-url <characters-db-url> --output-dir dataset/bot_ml/raw`, `pixi run dvc repro bot_ml_build_decisions`, `pixi run dvc repro bot_ml_validate`, and `pixi run dvc repro bt_masked_ga_combined`. Confirm `dataset/bot_ml/decision_dataset_manifest.json` is no longer 4 candidate rows / 2 decision rows, inspect the combined metrics and Stonecore comparison, run `pixi run pytest -q tests/test_ml_pipeline.py`, `cmake --build build --target worldserver -j2`, `pixi run dvc status`, `pixi run dvc push` if DVC artifacts changed, then commit the dataset/artifact pointer and docs updates. Mark merge-ready only if all acceptance criteria pass.
