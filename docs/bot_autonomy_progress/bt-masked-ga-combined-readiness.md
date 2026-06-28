# BT Masked GA Combined Readiness

## 2026-06-28

Branch `codex/ml/bt-masked-ga-combined` was rebased cleanly onto current `master` at `6f0666e86a279fb8e13a57460be56e108677655a`.

DVC credentials were checked against the main worktree. `.dvc/config.local` in `/home/runiir/Games/trinity-cata-bt-masked-ga-combined` matches `/home/runiir/Games/trinity-cata/.dvc/config.local`, and `pixi run dvc config --list` reports the same `object` remote with local access keys redacted.

Validation completed:

- `pixi run dvc pull dvc.yaml:bt_masked_ga_combined`: passed, everything up to date.
- `pixi run pytest -q tests/test_ml_pipeline.py -k bt_masked_ga_combined`: passed, 1 selected test, 176 deselected, 1 `dvclive`/`pynvml` warning.
- `pixi run dvc repro bt_masked_ga_combined`: passed, all relevant stages skipped as unchanged and up to date.
- `pixi run dvc status`: completed. The combined lane stayed reproducible, while the worktree still reports broad pre-existing missing-cache and missing-output drift outside this lane.

The combined output report is `artifacts/ml_strategy_eval/bt_masked_ga_combined/report.json`. Current lane metrics include 4 candidate rows, 2 decision groups, server-valid action masks enabled, top-1 ranking accuracy 0.5, top-3 ranking accuracy 1.0, `runtime_ml_control=offline_shadow_only`, `control_eligible=false`, and `cpp_runtime_files_changed=0`.

Stonecore baseline comparison is `artifacts/ml_strategy_eval/bt_masked_ga_combined/stonecore_baseline_comparison.json`. It records the accepted Stonecore r12 baseline, no baseline failure labels, no C++ runtime/live-control changes, and `stonecore_regression=false`.

Real telemetry export was not rerun because no characters DB endpoint was reachable in this pass:

- `mysql://trinity:trinity@172.20.0.2:3306/characters`: no route to host.
- `mysql://trinity:trinity@127.0.0.1:3306/characters`: connection refused.

Merge readiness: the combined lane is merge-ready as an offline/shadow-only Python and DVC lane. It is not ready for runtime control, and this pass does not claim real-telemetry readiness beyond the existing DVC-tracked fixture dataset.
