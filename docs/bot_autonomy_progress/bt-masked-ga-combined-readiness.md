# BT Masked GA Combined Readiness

## 2026-06-28 Orchestrator Pass 000013

Branch `codex/ml/bt-masked-ga-combined` remains the selected Stonecore ML path: behavior-tree learned scoring plus masked ranker, with GA retained only as an offline helper. No new strategy lane was launched, no worker session was needed, and no C++ runtime control was added; the lane remains offline/shadow-only.

Current status: not merge-ready.

The blocker is unchanged and current as of pass 000013. `dataset/bot_ml/decision_dataset_manifest.json` still contains the fixture-scale dataset: 4 candidate rows, 2 decision rows, and 2 observed-label rows. Acceptance requires real telemetry scale, so this pass does not claim merge readiness.

DB export attempts:

- `pixi run bot-ml-export --database-url mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1 --output-dir dataset/bot_ml/raw`: failed, no route to host. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000013/bot_ml_export_172_20_0_2_lane_r1.log`.
- `pixi run bot-ml-export --database-url mysql://trinity:trinity@127.0.0.1:3306/characters --output-dir dataset/bot_ml/raw`: failed, connection refused. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000013/bot_ml_export_127_0_0_1_characters.log`.

DB availability evidence:

- Docker only showed an unrelated Postgres container. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000013/service_probe_docker.log`.
- `ss -ltnp` showed no local MySQL listener on port 3306. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000013/service_probe_ss.log`.

DVC and validation evidence:

- Main worktree `pixi run dvc status`: clean. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000013/dvc_status_main_initial.log`.
- Combined `.dvc/config.local`: present, gitignored, and equivalent to main DVC credentials. Logs: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000013/dvc_config_main_redacted.log`, `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000013/dvc_config_combined_redacted.log`, and `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000013/dvc_config_compare_redacted.log`.
- No stale `generated/orchestrator_worktrees` directory was present inside the combined worktree. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000013/generated_orchestrator_worktrees_combined.log`.
- `pixi run dvc pull bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, everything up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000013/dvc_pull_selected.log`.
- `pixi run dvc status bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, everything up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000013/dvc_status_selected_after_pull.log`.
- `pixi run dvc status`: still reports broad historical deleted-output state outside the selected combined lane. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000013/dvc_status_combined_final.log`.
- Focused/full ML tests and `worldserver` build were not rerun in pass 000013 because DB export remained unavailable and the prompt says to stop and write a blocker report when DB access is not available. Latest passing evidence remains pass 000004.
- No selected DVC artifacts changed, so `pixi run dvc push` was not run.

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

- DVC stage reproduces cleanly: selected DVC graph is up to date, but real dataset repro is blocked by DB access.
- Focused and full ML tests pass: yes in latest pass 000004 evidence; not rerun in pass 000013 due the DB blocker stop condition.
- Dataset has real telemetry scale: no, blocked by unreachable characters DB.
- Server-valid candidate masks are preserved: yes in current fixture metrics.
- Stonecore baseline comparison shows no regression: yes in current fixture metrics.
- `control_eligible=false` and runtime mode remains offline/shadow only: yes.

Next prompt:

Continue `codex/ml/bt-masked-ga-combined` only. Do not launch new strategy lanes. Restore reachable characters DB access for `mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1` or provide the correct characters DB URL, then run `pixi run bot-ml-export --database-url <characters-db-url> --output-dir dataset/bot_ml/raw`, `pixi run dvc repro bot_ml_build_decisions`, `pixi run dvc repro bot_ml_validate`, and `pixi run dvc repro bt_masked_ga_combined`. Confirm `dataset/bot_ml/decision_dataset_manifest.json` is no longer 4 candidate rows / 2 decision rows, inspect the combined metrics and Stonecore comparison, run `pixi run pytest -q tests/test_ml_pipeline.py`, `cmake --build build --target worldserver -j2`, `pixi run dvc status`, `pixi run dvc push` if DVC artifacts changed, then commit the dataset/artifact pointer and docs updates. Mark merge-ready only if all acceptance criteria pass.

## 2026-06-28 Orchestrator Pass 000012

Branch `codex/ml/bt-masked-ga-combined` remains the selected Stonecore ML path: behavior-tree learned scoring plus masked ranker, with GA retained only as an offline helper. No new strategy lane was launched, no worker session was needed, and no C++ runtime control was added; the lane remains offline/shadow-only.

Current status: not merge-ready.

The blocker is unchanged and current as of pass 000012. `dataset/bot_ml/decision_dataset_manifest.json` still contains the fixture-scale dataset: 4 candidate rows, 2 decision rows, and 2 observed-label rows. Acceptance requires real telemetry scale, so this pass does not claim merge readiness.

DB export attempt:

- `pixi run bot-ml-export --database-url mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1 --output-dir dataset/bot_ml/raw`: failed, no route to host. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000012/bot_ml_export_172_20_0_2_lane_r1.log`.

DB availability evidence:

- Docker only showed an unrelated Postgres container. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000012/service_probe_docker.log`.
- `ss -ltnp` showed no local MySQL listener on port 3306. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000012/service_probe_ss.log`.

DVC and validation evidence:

- Main worktree `pixi run dvc status`: clean. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000012/dvc_status_main.log`.
- Combined `.dvc/config.local`: present, gitignored, and byte-equivalent to main DVC credentials. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000012/dvc_config_compare_redacted.log`.
- No stale `generated/orchestrator_worktrees` directory was present inside the combined worktree. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000012/generated_orchestrator_worktrees_combined.log`.
- `pixi run dvc pull bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, everything up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000012/dvc_pull_selected.log`.
- `pixi run dvc status bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, everything up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000012/dvc_status_selected.log`.
- `pixi run dvc status`: still reports broad historical deleted-output state outside the selected combined lane. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000012/dvc_status_combined_broad.log`.
- Focused/full ML tests and `worldserver` build were not rerun in pass 000012 because DB export remained unavailable and the prompt says to stop and write a blocker report when DB access is not available. Latest passing evidence remains pass 000004.
- No selected DVC artifacts changed, so `pixi run dvc push` was not run.

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

- DVC stage reproduces cleanly: selected DVC graph is up to date, but real dataset repro is blocked by DB access.
- Focused and full ML tests pass: yes in latest pass 000004 evidence; not rerun in pass 000012 due the DB blocker stop condition.
- Dataset has real telemetry scale: no, blocked by unreachable characters DB.
- Server-valid candidate masks are preserved: yes in current fixture metrics.
- Stonecore baseline comparison shows no regression: yes in current fixture metrics.
- `control_eligible=false` and runtime mode remains offline/shadow only: yes.

Next prompt:

Continue `codex/ml/bt-masked-ga-combined` only. Do not launch new strategy lanes. Restore reachable characters DB access for `mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1` or provide the correct characters DB URL, then run `pixi run bot-ml-export --database-url <characters-db-url> --output-dir dataset/bot_ml/raw`, `pixi run dvc repro bot_ml_build_decisions`, `pixi run dvc repro bot_ml_validate`, and `pixi run dvc repro bt_masked_ga_combined`. Confirm `dataset/bot_ml/decision_dataset_manifest.json` is no longer 4 candidate rows / 2 decision rows, inspect the combined metrics and Stonecore comparison, run `pixi run pytest -q tests/test_ml_pipeline.py`, `cmake --build build --target worldserver -j2`, `pixi run dvc status`, `pixi run dvc push` if DVC artifacts changed, then commit the dataset/artifact pointer and docs updates. Mark merge-ready only if all acceptance criteria pass.

## 2026-06-28 Orchestrator Pass 000011

Branch `codex/ml/bt-masked-ga-combined` remains the selected Stonecore ML path: behavior-tree learned scoring plus masked ranker, with GA retained only as an offline helper. No new strategy lane was launched, no worker session was needed, and no C++ runtime control was added; the lane remains offline/shadow-only.

Current status: not merge-ready.

The blocker is unchanged and current as of pass 000011. `dataset/bot_ml/decision_dataset_manifest.json` still contains the fixture-scale dataset: 4 candidate rows, 2 decision rows, and 2 observed-label rows. Acceptance requires real telemetry scale, so this pass does not claim merge readiness.

DB export attempts:

- `pixi run bot-ml-export --database-url mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1 --output-dir dataset/bot_ml/raw`: failed, no route to host. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000011/bot_ml_export_172_20_0_2_lane_r1.log`.
- `pixi run bot-ml-export --database-url mysql://trinity:trinity@127.0.0.1:3306/characters --output-dir dataset/bot_ml/raw`: failed, connection refused. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000011/bot_ml_export_127_0_0_1_characters.log`.

DB availability evidence:

- Docker only showed an unrelated Postgres container. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000011/service_probe_docker.log`.
- `ss -ltnp` showed no local MySQL listener on port 3306. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000011/service_probe_ss.log`.

DVC and validation evidence:

- Main worktree `pixi run dvc status`: clean. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000011/dvc_status_main.log`.
- Combined `.dvc/config.local`: present, gitignored, and byte-equivalent to main DVC credentials. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000011/dvc_config_compare_redacted.log`.
- No stale `generated/orchestrator_worktrees` directory was present inside the combined worktree. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000011/generated_orchestrator_worktrees_combined.log`.
- `pixi run dvc pull bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, everything up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000011/dvc_pull_selected.log`.
- `pixi run dvc status bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, everything up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000011/dvc_status_selected_after_pull.log`.
- `pixi run dvc status`: still reports broad historical deleted-output state outside the selected combined lane. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000011/dvc_status_combined_broad_initial.log`.
- Focused/full ML tests and `worldserver` build were not rerun in pass 000011 because DB export remained unavailable and the prompt says to stop and write a blocker report when DB access is not available. Latest passing evidence remains pass 000004.
- No selected DVC artifacts changed, so `pixi run dvc push` was not run.

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

- DVC stage reproduces cleanly: selected DVC graph is up to date, but real dataset repro is blocked by DB access.
- Focused and full ML tests pass: yes in latest pass 000004 evidence; not rerun in pass 000011 due the DB blocker stop condition.
- Dataset has real telemetry scale: no, blocked by unreachable characters DB.
- Server-valid candidate masks are preserved: yes in current fixture metrics.
- Stonecore baseline comparison shows no regression: yes in current fixture metrics.
- `control_eligible=false` and runtime mode remains offline/shadow only: yes.

Next prompt:

Continue `codex/ml/bt-masked-ga-combined` only. Do not launch new strategy lanes. Restore reachable characters DB access for `mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1` or provide the correct characters DB URL, then run `pixi run bot-ml-export --database-url <characters-db-url> --output-dir dataset/bot_ml/raw`, `pixi run dvc repro bot_ml_build_decisions`, `pixi run dvc repro bot_ml_validate`, and `pixi run dvc repro bt_masked_ga_combined`. Confirm `dataset/bot_ml/decision_dataset_manifest.json` is no longer 4 candidate rows / 2 decision rows, inspect the combined metrics and Stonecore comparison, run `pixi run pytest -q tests/test_ml_pipeline.py`, `cmake --build build --target worldserver -j2`, `pixi run dvc status`, `pixi run dvc push` if DVC artifacts changed, then commit the dataset/artifact pointer and docs updates. Mark merge-ready only if all acceptance criteria pass.

## 2026-06-28 Orchestrator Pass 000010

Branch `codex/ml/bt-masked-ga-combined` remains the selected Stonecore ML path: behavior-tree learned scoring plus masked ranker, with GA retained only as an offline helper. No new strategy lane was launched, no worker session was needed, and no C++ runtime control was added; the lane remains offline/shadow-only.

Current status: not merge-ready.

The blocker is unchanged and current as of pass 000010. `dataset/bot_ml/decision_dataset_manifest.json` still contains the fixture-scale dataset: 4 candidate rows, 2 decision rows, and 2 observed-label rows. Acceptance requires real telemetry scale, so this pass does not claim merge readiness.

DB export attempts:

- `pixi run bot-ml-export --database-url mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1 --output-dir dataset/bot_ml/raw`: failed, no route to host. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000010/bot_ml_export_172_20_0_2_lane_r1.log`.
- `pixi run bot-ml-export --database-url mysql://trinity:trinity@127.0.0.1:3306/characters --output-dir dataset/bot_ml/raw`: failed, connection refused. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000010/bot_ml_export_127_0_0_1_characters.log`.

DB availability evidence:

- Docker only showed an unrelated Postgres container. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000010/service_probe_docker.log`.
- `ss -ltnp` showed no local MySQL listener on port 3306. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000010/service_probe_ss.log`.

DVC and validation evidence:

- Main worktree `pixi run dvc status`: clean. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000010/dvc_status_main.log`.
- Combined `.dvc/config.local`: present, gitignored, and byte-equivalent to main DVC credentials. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000010/dvc_config_compare_redacted.log`.
- `pixi run dvc pull` for selected dataset and combined-lane artifacts: passed, everything up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000010/dvc_pull_selected.log`.
- `pixi run dvc status bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, everything up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000010/dvc_status_selected.log`.
- `pixi run dvc status`: still reports broad historical deleted-output state outside the selected combined lane. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000010/dvc_status_combined_broad.log`.
- Focused/full ML tests and `worldserver` build were not rerun in pass 000010 because DB export remained unavailable and the prompt says to stop and write a blocker report when DB access is not available. Latest passing evidence remains pass 000004.
- No selected DVC artifacts changed, so `pixi run dvc push` was not run.

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

- DVC stage reproduces cleanly: selected DVC graph is up to date, but real dataset repro is blocked by DB access.
- Focused and full ML tests pass: yes in latest pass 000004 evidence; not rerun in pass 000010 due the DB blocker stop condition.
- Dataset has real telemetry scale: no, blocked by unreachable characters DB.
- Server-valid candidate masks are preserved: yes in current fixture metrics.
- Stonecore baseline comparison shows no regression: yes in current fixture metrics.
- `control_eligible=false` and runtime mode remains offline/shadow only: yes.

Next prompt:

Continue `codex/ml/bt-masked-ga-combined` only. Do not launch new strategy lanes. Restore reachable characters DB access for `mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1` or provide the correct characters DB URL, then run `pixi run bot-ml-export --database-url <characters-db-url> --output-dir dataset/bot_ml/raw`, `pixi run dvc repro bot_ml_build_decisions`, `pixi run dvc repro bot_ml_validate`, and `pixi run dvc repro bt_masked_ga_combined`. Confirm `dataset/bot_ml/decision_dataset_manifest.json` is no longer 4 candidate rows / 2 decision rows, inspect the combined metrics and Stonecore comparison, run `pixi run pytest -q tests/test_ml_pipeline.py`, `cmake --build build --target worldserver -j2`, `pixi run dvc status`, `pixi run dvc push` if DVC artifacts changed, then commit the dataset/artifact pointer and docs updates. Mark merge-ready only if all acceptance criteria pass.

## 2026-06-28 Orchestrator Pass 000009

Branch `codex/ml/bt-masked-ga-combined` remains the selected Stonecore ML path: behavior-tree learned scoring plus masked ranker, with GA retained only as an offline helper. No new strategy lane was launched, no worker session was needed, and no C++ runtime control was added; the lane remains offline/shadow-only.

Current status: not merge-ready.

The blocker is unchanged and current as of pass 000009. `dataset/bot_ml/decision_dataset_manifest.json` still contains the fixture-scale dataset: 4 candidate rows, 2 decision rows, and 2 observed-label rows. Acceptance requires real telemetry scale, so this pass does not claim merge readiness.

DB export attempts:

- `pixi run bot-ml-export --database-url mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1 --output-dir dataset/bot_ml/raw`: failed, no route to host. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000009/bot_ml_export_172_20_0_2_lane_r1.log`.
- `pixi run bot-ml-export --database-url mysql://trinity:trinity@127.0.0.1:3306/characters --output-dir dataset/bot_ml/raw`: failed, connection refused. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000009/bot_ml_export_127_0_0_1_characters.log`.

DB availability evidence:

- Docker only showed an unrelated Postgres container. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000009/service_probe_docker.log`.
- `ss -ltnp` showed no local MySQL listener on port 3306. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000009/service_probe_ss.log`.

DVC and validation evidence:

- Main worktree `pixi run dvc status`: clean. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000009/dvc_status_main.log`.
- Combined `.dvc/config.local`: present, gitignored, and byte-equivalent to main DVC credentials.
- No stale `generated/orchestrator_worktrees` directory was present inside the combined worktree. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000009/generated_orchestrator_worktrees_combined.log`.
- `pixi run dvc pull bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, everything up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000009/dvc_pull_selected.log`.
- `pixi run dvc status bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, everything up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000009/dvc_status_selected.log`.
- `pixi run dvc status`: still reports broad historical deleted-output state outside the selected combined lane. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000009/dvc_status_combined_broad.log`.
- Focused/full ML tests and `worldserver` build were not rerun in pass 000009 because DB export remained unavailable and the prompt says to stop and write a blocker report when DB access is not available. Latest passing evidence remains pass 000004.
- No selected DVC artifacts changed, so `pixi run dvc push` was not run.

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

- DVC stage reproduces cleanly: selected DVC graph is up to date, but real dataset repro is blocked by DB access.
- Focused and full ML tests pass: yes in latest pass 000004 evidence; not rerun in pass 000009 due the DB blocker stop condition.
- Dataset has real telemetry scale: no, blocked by unreachable characters DB.
- Server-valid candidate masks are preserved: yes in current fixture metrics.
- Stonecore baseline comparison shows no regression: yes in current fixture metrics.
- `control_eligible=false` and runtime mode remains offline/shadow only: yes.

Next prompt:

Continue `codex/ml/bt-masked-ga-combined` only. Do not launch new strategy lanes. Restore reachable characters DB access for `mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1` or provide the correct characters DB URL, then run `pixi run bot-ml-export --database-url <characters-db-url> --output-dir dataset/bot_ml/raw`, `pixi run dvc repro bot_ml_build_decisions`, `pixi run dvc repro bot_ml_validate`, and `pixi run dvc repro bt_masked_ga_combined`. Confirm `dataset/bot_ml/decision_dataset_manifest.json` is no longer 4 candidate rows / 2 decision rows, inspect the combined metrics and Stonecore comparison, run `pixi run pytest -q tests/test_ml_pipeline.py`, `cmake --build build --target worldserver -j2`, `pixi run dvc status`, `pixi run dvc push` if DVC artifacts changed, then commit the dataset/artifact pointer and docs updates. Mark merge-ready only if all acceptance criteria pass.

## 2026-06-28 Orchestrator Pass 000008

Branch `codex/ml/bt-masked-ga-combined` remains the selected Stonecore ML path: behavior-tree learned scoring plus masked ranker, with GA retained only as an offline helper. No new strategy lane was launched, no worker session was needed, and no C++ runtime control was added; the lane remains offline/shadow-only.

Current status: not merge-ready.

The blocker is unchanged and current as of pass 000008. `dataset/bot_ml/decision_dataset_manifest.json` still contains the fixture-scale dataset: 4 candidate rows, 2 decision rows, and 2 observed-label rows. Acceptance requires real telemetry scale, so this pass does not claim merge readiness.

DB export attempts:

- `pixi run bot-ml-export --database-url mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1 --output-dir dataset/bot_ml/raw`: failed, no route to host. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000008/bot_ml_export_172_20_0_2_lane_r1.log`.
- `pixi run bot-ml-export --database-url mysql://trinity:trinity@127.0.0.1:3306/characters --output-dir dataset/bot_ml/raw`: failed, connection refused. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000008/bot_ml_export_127_0_0_1_characters.log`.

DB availability evidence:

- Docker only showed an unrelated Postgres container and `ss -ltnp` showed no local MySQL listener on port 3306. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000008/db_probe_services.log`.

DVC and validation evidence:

- Main worktree `pixi run dvc status`: clean. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000008/dvc_status_main.log`.
- Combined `.dvc/config.local`: present, gitignored, and equivalent to main DVC credentials when redacted. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000008/dvc_config_compare_redacted.log`.
- `generated/orchestrator_worktrees` remains temporary orchestration state and was not deleted because the active orchestrator is running from that tree family.
- `pixi run dvc pull bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, everything up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000008/dvc_pull_selected.log`.
- `pixi run dvc status bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, everything up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000008/dvc_status_selected_initial.log`.
- `pixi run dvc status`: still reports broad historical deleted-output state outside the selected combined lane. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000008/dvc_status_combined_initial.log`.
- Focused/full ML tests and `worldserver` build were not rerun in pass 000008 because DB export remained unavailable and the prompt says to stop and write a blocker report when DB access is not available. Latest passing evidence remains pass 000004.
- No selected DVC artifacts changed, so `pixi run dvc push` was not run.

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

- DVC stage reproduces cleanly: selected DVC graph is up to date, but real dataset repro is blocked by DB access.
- Focused and full ML tests pass: yes in latest pass 000004 evidence; not rerun in pass 000008 due the DB blocker stop condition.
- Dataset has real telemetry scale: no, blocked by unreachable characters DB.
- Server-valid candidate masks are preserved: yes in current fixture metrics.
- Stonecore baseline comparison shows no regression: yes in current fixture metrics.
- `control_eligible=false` and runtime mode remains offline/shadow only: yes.

Next prompt:

Continue `codex/ml/bt-masked-ga-combined` only. Do not launch new strategy lanes. Restore reachable characters DB access for `mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1` or provide the correct characters DB URL, then run `pixi run bot-ml-export --database-url <characters-db-url> --output-dir dataset/bot_ml/raw`, `pixi run dvc repro bot_ml_build_decisions`, `pixi run dvc repro bot_ml_validate`, and `pixi run dvc repro bt_masked_ga_combined`. Confirm `dataset/bot_ml/decision_dataset_manifest.json` is no longer 4 candidate rows / 2 decision rows, inspect the combined metrics and Stonecore comparison, run `pixi run pytest -q tests/test_ml_pipeline.py`, `cmake --build build --target worldserver -j2`, `pixi run dvc status`, `pixi run dvc push` if DVC artifacts changed, then commit the dataset/artifact pointer and docs updates. Mark merge-ready only if all acceptance criteria pass.

## 2026-06-28 Orchestrator Pass 000007

Branch `codex/ml/bt-masked-ga-combined` remains the selected Stonecore ML path: behavior-tree learned scoring plus masked ranker, with GA retained only as an offline helper. No new strategy lane was launched, no worker session was needed, and no C++ runtime control was added; the lane remains offline/shadow-only.

Current status: not merge-ready.

The blocker is unchanged and current as of pass 000007. `dataset/bot_ml/decision_dataset_manifest.json` still contains the fixture-scale dataset: 4 candidate rows, 2 decision rows, and 2 observed-label rows. Acceptance requires real telemetry scale, so this pass does not claim merge readiness.

DB export attempts:

- `pixi run bot-ml-export --database-url mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1 --output-dir dataset/bot_ml/raw`: failed, no route to host. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000007/bot_ml_export_172_20_0_2_lane_r1.log`.
- `pixi run bot-ml-export --database-url mysql://trinity:trinity@127.0.0.1:3306/characters --output-dir dataset/bot_ml/raw`: failed, connection refused. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000007/bot_ml_export_127_0_0_1_characters.log`.

DB availability evidence:

- Docker only showed an unrelated Postgres container. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000007/docker_ps.log`.
- `ss -ltnp` showed no local MySQL listener on port 3306. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000007/ss_ltnp.log`.

DVC and validation evidence:

- Main worktree `pixi run dvc status`: clean. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000007/dvc_status_main.log`.
- Combined `.dvc/config.local`: present, gitignored, and byte-equivalent to main DVC credentials.
- `generated/orchestrator_worktrees` is ignored temporary orchestration state, so none were deleted.
- `pixi run dvc pull bot_ml_build_decisions bt_masked_ga_combined`: passed, everything up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000007/dvc_pull_selected_stage.log`.
- `pixi run dvc status bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, everything up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000007/dvc_status_combined_selected.log`.
- `pixi run dvc status`: still reports broad historical missing-cache and deleted-dependency state outside the selected combined lane. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000007/dvc_status_combined_initial.log`.
- Focused/full ML tests and `worldserver` build were not rerun in pass 000007 because DB export remained unavailable and the prompt says to stop and write a blocker report when DB access is not available. Latest passing evidence remains pass 000004.
- No selected DVC artifacts changed, so `pixi run dvc push` was not run.

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

- DVC stage reproduces cleanly: selected DVC graph is up to date, but real dataset repro is blocked by DB access.
- Focused and full ML tests pass: yes in latest pass 000004 evidence; not rerun in pass 000007 due the DB blocker stop condition.
- Dataset has real telemetry scale: no, blocked by unreachable characters DB.
- Server-valid candidate masks are preserved: yes in current fixture metrics.
- Stonecore baseline comparison shows no regression: yes in current fixture metrics.
- `control_eligible=false` and runtime mode remains offline/shadow only: yes.

Next prompt:

Continue `codex/ml/bt-masked-ga-combined` only. Do not launch new strategy lanes. Restore reachable characters DB access for `mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1` or provide the correct characters DB URL, then run `pixi run bot-ml-export --database-url <characters-db-url> --output-dir dataset/bot_ml/raw`, `pixi run dvc repro bot_ml_build_decisions`, `pixi run dvc repro bot_ml_validate`, and `pixi run dvc repro bt_masked_ga_combined`. Confirm `dataset/bot_ml/decision_dataset_manifest.json` is no longer 4 candidate rows / 2 decision rows, inspect the combined metrics and Stonecore comparison, run `pixi run pytest -q tests/test_ml_pipeline.py`, `cmake --build build --target worldserver -j2`, `pixi run dvc status`, `pixi run dvc push` if DVC artifacts changed, then commit the dataset/artifact pointer and docs updates. Mark merge-ready only if all acceptance criteria pass.

## 2026-06-28 Orchestrator Pass 000006

Branch `codex/ml/bt-masked-ga-combined` remains the selected Stonecore ML path: behavior-tree learned scoring plus masked ranker, with GA retained only as an offline helper. No new strategy lane was launched, no worker session was needed, and no C++ runtime control was added; the lane remains offline/shadow-only.

Current status: not merge-ready.

The blocker is unchanged and current as of pass 000006. `dataset/bot_ml/decision_dataset_manifest.json` still contains the fixture-scale dataset: 4 candidate rows, 2 decision rows, and 2 observed-label rows. Acceptance requires real telemetry scale, so this pass does not claim merge readiness.

DB export attempts:

- `pixi run bot-ml-export --database-url mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1 --output-dir dataset/bot_ml/raw`: failed, no route to host. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000006/bot_ml_export_172_20_0_2_lane_r1.log`.
- `pixi run bot-ml-export --database-url mysql://trinity:trinity@127.0.0.1:3306/characters --output-dir dataset/bot_ml/raw`: failed, connection refused. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000006/bot_ml_export_127_0_0_1_characters.log`.

DB availability evidence:

- Docker only showed an unrelated Postgres container. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000006/docker_ps.log`.
- `ss -ltnp` showed no local MySQL listener on port 3306. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000006/ss_ltnp.log`.

DVC and validation evidence:

- Main worktree `pixi run dvc status`: clean. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000006/dvc_status_main.log`.
- Combined `.dvc/config.local`: present, gitignored, and byte-equivalent to main DVC credentials.
- `generated/orchestrator_worktrees` is ignored temporary orchestration state, so none were deleted.
- `pixi run dvc pull bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, everything up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000006/dvc_pull_selected.log`.
- `pixi run dvc status bt_masked_ga_combined`: clean/up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000006/dvc_status_combined_selected_final.log`.
- `pixi run dvc status`: still reports broad historical missing-cache and deleted-dependency state outside the selected combined lane. The selected `bot_ml_build_decisions`, `bot_ml_validate`, and `bt_masked_ga_combined` stages are present and up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000006/dvc_status_combined_broad.log`.
- Focused/full ML tests and `worldserver` build were not rerun in pass 000006 because DB export remained unavailable and the prompt says to stop and write a blocker report when DB access is not available. Latest passing evidence remains pass 000004.
- No selected DVC artifacts changed, so `pixi run dvc push` was not run.

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

- DVC stage reproduces cleanly: selected DVC graph is up to date, but real dataset repro is blocked by DB access.
- Focused and full ML tests pass: yes in latest pass 000004 evidence; not rerun in pass 000006 due the DB blocker stop condition.
- Dataset has real telemetry scale: no, blocked by unreachable characters DB.
- Server-valid candidate masks are preserved: yes in current fixture metrics.
- Stonecore baseline comparison shows no regression: yes in current fixture metrics.
- `control_eligible=false` and runtime mode remains offline/shadow only: yes.

Next prompt:

Continue `codex/ml/bt-masked-ga-combined` only. Do not launch new strategy lanes. Restore reachable characters DB access for `mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1` or provide the correct characters DB URL, then run `pixi run bot-ml-export --database-url <characters-db-url> --output-dir dataset/bot_ml/raw`, `pixi run dvc repro bot_ml_build_decisions`, `pixi run dvc repro bot_ml_validate`, and `pixi run dvc repro bt_masked_ga_combined`. Confirm `dataset/bot_ml/decision_dataset_manifest.json` is no longer 4 candidate rows / 2 decision rows, inspect the combined metrics and Stonecore comparison, run `pixi run pytest -q tests/test_ml_pipeline.py`, `cmake --build build --target worldserver -j2`, `pixi run dvc status`, `pixi run dvc push` if DVC artifacts changed, then commit the dataset/artifact pointer and docs updates. Mark merge-ready only if all acceptance criteria pass.

## 2026-06-28 Orchestrator Pass 000005

Branch `codex/ml/bt-masked-ga-combined` remains the selected Stonecore ML path: behavior-tree learned scoring plus masked ranker, with GA retained only as an offline helper. No new strategy lane was launched, no worker session was needed, and no C++ runtime control was added; the lane remains offline/shadow-only.

Current status: not merge-ready.

The blocker is unchanged and current as of pass 000005. `dataset/bot_ml/decision_dataset_manifest.json` still contains the fixture-scale dataset: 4 candidate rows, 2 decision rows, and 2 observed-label rows. Acceptance requires real telemetry scale, so this pass does not claim merge readiness.

DB export attempts:

- `pixi run bot-ml-export --database-url mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1 --output-dir dataset/bot_ml/raw`: failed, no route to host. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000005/bot_ml_export_172_20_0_2_lane_r1.log`.
- `pixi run bot-ml-export --database-url mysql://trinity:trinity@127.0.0.1:3306/characters --output-dir dataset/bot_ml/raw`: failed, connection refused. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000005/bot_ml_export_127_0_0_1_characters.log`.

DB availability evidence:

- Docker only showed an unrelated Postgres container. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000005/docker_ps.log`.
- `ss -ltnp` showed no local MySQL listener on port 3306. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000005/ss_ltnp.log`.

DVC and validation evidence:

- Main worktree `pixi run dvc status`: clean. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000005/dvc_status_main.log`.
- Combined `.dvc/config.local`: present, gitignored, and byte-equivalent to main DVC credentials.
- `generated/orchestrator_worktrees` is ignored temporary orchestration state, so none were deleted. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000005/orchestrator_worktrees_git_status.log`.
- `pixi run dvc pull bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, everything up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000005/dvc_pull_selected.log`.
- `pixi run dvc status dvc.yaml:bot_ml_build_decisions dvc.yaml:bot_ml_validate dvc.yaml:bt_masked_ga_combined`: clean/up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000005/dvc_status_selected.log`.
- `pixi run dvc status`: still reports broad historical missing-cache and deleted-dependency state outside the selected combined lane. The selected `bot_ml_build_decisions`, `bot_ml_validate`, and `bt_masked_ga_combined` stages are present and up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000005/dvc_status_combined.log`.
- Focused/full ML tests and `worldserver` build were not rerun in pass 000005 because DB export remained unavailable and the prompt says to stop and write a blocker report when DB access is not available. Latest passing evidence remains pass 000004.
- No selected DVC artifacts changed, so `pixi run dvc push` was not run.

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

- DVC stage reproduces cleanly: selected DVC graph is up to date, but real dataset repro is blocked by DB access.
- Focused and full ML tests pass: yes in latest pass 000004 evidence; not rerun in pass 000005 due the DB blocker stop condition.
- Dataset has real telemetry scale: no, blocked by unreachable characters DB.
- Server-valid candidate masks are preserved: yes in current fixture metrics.
- Stonecore baseline comparison shows no regression: yes in current fixture metrics.
- `control_eligible=false` and runtime mode remains offline/shadow only: yes.

Next prompt:

Continue `codex/ml/bt-masked-ga-combined` only. Do not launch new strategy lanes. Restore reachable characters DB access for `mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1` or provide the correct characters DB URL, then run `pixi run bot-ml-export --database-url <characters-db-url> --output-dir dataset/bot_ml/raw`, `pixi run dvc repro bot_ml_build_decisions`, `pixi run dvc repro bot_ml_validate`, and `pixi run dvc repro bt_masked_ga_combined`. Confirm `dataset/bot_ml/decision_dataset_manifest.json` is no longer 4 candidate rows / 2 decision rows, inspect the combined metrics and Stonecore comparison, run `pixi run pytest -q tests/test_ml_pipeline.py`, `cmake --build build --target worldserver -j2`, `pixi run dvc status`, `pixi run dvc push` if DVC artifacts changed, then commit the dataset/artifact pointer and docs updates. Mark merge-ready only if all acceptance criteria pass.

## 2026-06-28 Orchestrator Pass 000004

Branch `codex/ml/bt-masked-ga-combined` remains the selected Stonecore ML path: behavior-tree learned scoring plus masked ranker, with GA retained only as an offline helper. No new strategy lane was launched and no C++ runtime control was added; the lane remains offline/shadow-only.

Current status: not merge-ready.

The blocker is unchanged and current as of pass 000004. `dataset/bot_ml/decision_dataset_manifest.json` still contains the fixture-scale dataset: 4 candidate rows, 2 decision rows, and 2 observed-label rows. Acceptance requires real telemetry scale, so this pass does not claim merge readiness.

DB export attempts:

- `pixi run bot-ml-export --database-url mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1 --output-dir dataset/bot_ml/raw`: failed, no route to host. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000004/bot_ml_export_172_20_0_2_lane_r1.log`.
- `pixi run bot-ml-export --database-url mysql://trinity:trinity@172.20.0.2:3306/characters --output-dir dataset/bot_ml/raw`: failed, no route to host. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000004/bot_ml_export_172_20_0_2_characters.log`.
- `pixi run bot-ml-export --database-url mysql://trinity:trinity@127.0.0.1:3306/characters --output-dir dataset/bot_ml/raw`: failed, connection refused. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000004/bot_ml_export_127_0_0_1_characters.log`.

DVC and validation evidence:

- Main worktree `pixi run dvc status`: clean.
- Combined `.dvc/config.local`: present, gitignored, and equivalent to main DVC credentials.
- Registered generated/orchestrator worktrees are protected orchestration worktrees, so none were deleted.
- `pixi run dvc pull dataset/bot_ml/raw.dvc dvc.yaml:bot_ml_build_decisions dvc.yaml:bot_ml_validate dvc.yaml:bt_masked_ga_combined artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r12.dvc`: passed, everything up to date.
- `pixi run dvc status dvc.yaml:bot_ml_build_decisions dvc.yaml:bot_ml_validate dvc.yaml:bt_masked_ga_combined`: clean/up to date.
- `pixi run pytest -q tests/test_ml_pipeline.py -k bt_masked_ga_combined`: passed.
- `pixi run pytest -q tests/test_ml_pipeline.py`: passed.
- `cmake --build build --target worldserver -j2`: passed.
- `pixi run dvc status`: still reports broad historical missing-cache and deleted-dependency state outside the selected combined lane. The selected `bot_ml_build_decisions`, `bot_ml_validate`, and `bt_masked_ga_combined` stages are present and reproducible.
- No selected DVC artifacts changed, so `pixi run dvc push` was not run.

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

Continue `codex/ml/bt-masked-ga-combined` only. Do not launch new strategy lanes. Restore reachable characters DB access for `mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1` or provide the correct characters DB URL, then run `pixi run bot-ml-export --database-url <characters-db-url> --output-dir dataset/bot_ml/raw`, `pixi run dvc repro bot_ml_build_decisions`, `pixi run dvc repro bot_ml_validate`, and `pixi run dvc repro bt_masked_ga_combined`. Confirm `dataset/bot_ml/decision_dataset_manifest.json` is no longer 4 candidate rows / 2 decision rows, inspect the combined metrics and Stonecore comparison, run `pixi run pytest -q tests/test_ml_pipeline.py`, `cmake --build build --target worldserver -j2`, `pixi run dvc status`, `pixi run dvc push` if DVC artifacts changed, then commit the dataset/artifact pointer and docs updates. Mark merge-ready only if all acceptance criteria pass.

## 2026-06-28 Orchestrator Pass 000003

Branch `codex/ml/bt-masked-ga-combined` remains the selected Stonecore ML path: behavior-tree learned scoring plus masked ranker, with GA retained only as an offline helper. No new strategy lane was launched and no C++ runtime control was added; the lane remains offline/shadow-only.

Current status: not merge-ready.

The blocker is unchanged and current as of pass 000003. `dataset/bot_ml/decision_dataset_manifest.json` still contains the fixture-scale dataset: 4 candidate rows, 2 decision rows, and 2 observed-label rows. Acceptance requires real telemetry scale, so this pass does not claim merge readiness.

DB export attempts:

- `pixi run bot-ml-export --database-url mysql://trinity:trinity@172.20.0.2:3306/characters --output-dir dataset/bot_ml/raw`: failed, no route to host. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000003/bot_ml_export_172_20_0_2.log`.
- `pixi run bot-ml-export --database-url mysql://trinity:trinity@127.0.0.1:3306/characters --output-dir dataset/bot_ml/raw`: failed, connection refused. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000003/bot_ml_export_127_0_0_1.log`.

DVC and validation evidence:

- Main worktree `pixi run dvc status`: clean.
- Combined `.dvc/config.local`: present, gitignored, and equivalent to main DVC credentials.
- Registered generated/orchestrator worktrees are protected orchestration worktrees, so none were deleted.
- Broad `pixi run dvc pull`: failed because DVC would overwrite generated validation outputs; targeted selected-lane pull was used instead.
- `pixi run dvc pull bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, everything up to date.
- `pixi run dvc status bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: clean/up to date.
- `pixi run dvc repro bot_ml_validate`: passed, stages skipped as unchanged.
- `pixi run pytest -q tests/test_ml_pipeline.py -k bt_masked_ga_combined`: passed, 1 selected test, 176 deselected.
- `pixi run dvc repro bt_masked_ga_combined`: passed, stages skipped as unchanged.
- `pixi run pytest -q tests/test_ml_pipeline.py`: passed, 177 tests, 1 warning.
- `cmake --build build --target worldserver -j2`: passed.
- `pixi run dvc status`: still reports broad historical missing-cache and deleted-dependency state outside the selected combined lane. The selected `bot_ml_build_decisions`, `bot_ml_validate`, and `bt_masked_ga_combined` stages are present and reproducible.
- No selected DVC artifacts changed, so `pixi run dvc push` was not run.

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

## 2026-06-28 Orchestrator Pass 000002

Branch `codex/ml/bt-masked-ga-combined` remains the selected Stonecore ML path: behavior-tree learned scoring plus masked ranker, with GA retained only as an offline helper. No new strategy lane was launched and no C++ runtime control was added; the lane remains offline/shadow-only.

Current status: not merge-ready.

The blocker is unchanged and current as of pass 000002. `dataset/bot_ml/decision_dataset_manifest.json` still contains the fixture-scale dataset: 4 candidate rows, 2 decision rows, and 2 observed-label rows. Acceptance requires real telemetry scale, so this pass does not claim merge readiness.

DB export attempts:

- `pixi run bot-ml-export --database-url mysql://trinity:trinity@172.20.0.2:3306/characters --output-dir dataset/bot_ml/raw`: failed, no route to host. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000002/bot_ml_export_172_20_0_2.log`.
- `pixi run bot-ml-export --database-url mysql://trinity:trinity@127.0.0.1:3306/characters --output-dir dataset/bot_ml/raw`: failed, connection refused. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000002/bot_ml_export_127_0_0_1.log`.

DVC and validation evidence:

- Main worktree `pixi run dvc status`: clean.
- Combined `.dvc/config.local`: present, gitignored, and equivalent to main DVC credentials.
- `pixi run dvc pull dvc.yaml:bot_ml_build_decisions dvc.yaml:bot_ml_validate dvc.yaml:bt_masked_ga_combined artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r12.dvc`: passed, everything up to date.
- `pixi run dvc repro bot_ml_build_decisions`: passed, stages skipped as unchanged.
- `pixi run dvc repro bot_ml_validate`: passed, stages skipped as unchanged.
- `pixi run pytest -q tests/test_ml_pipeline.py -k bt_masked_ga_combined`: passed, 1 selected test, 176 deselected.
- `pixi run dvc repro bt_masked_ga_combined`: passed, stages skipped as unchanged.
- `pixi run pytest -q tests/test_ml_pipeline.py`: passed, 177 tests, 1 warning.
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
