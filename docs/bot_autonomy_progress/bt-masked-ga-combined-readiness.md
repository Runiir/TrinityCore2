# BT Masked GA Combined Readiness

## 2026-06-28 Orchestrator Pass 000196

Branch `codex/ml/bt-masked-ga-combined` remains the selected Stonecore ML path: behavior-tree learned scoring plus masked ranker, with GA retained only as an offline helper. No new strategy lane or worker session was launched, and no C++ runtime control was added; the lane remains offline/shadow-only.

Current status: not merge-ready.

The blocker is unchanged and current as of pass 000196. `dataset/bot_ml/decision_dataset_manifest.json` still contains the fixture-scale dataset: 4 candidate rows, 2 decision rows, and 2 observed-label rows. Acceptance requires real telemetry scale, so this pass does not claim merge readiness.

DB export attempts:

- `pixi run bot-ml-export --database-url mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1 --output-dir dataset/bot_ml/raw`: failed, no route to host. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000196/bot_ml_export_172_20_0_2_lane_r1.log`.
- `pixi run bot-ml-export --database-url mysql://trinity:trinity@127.0.0.1:3306/characters --output-dir dataset/bot_ml/raw`: failed, connection refused. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000196/bot_ml_export_127_0_0_1_characters.log`.

DB availability evidence:

- Docker only showed an unrelated Postgres container and `ss -ltnp` showed no local MySQL listener on port 3306. Logs: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000196/docker_ps.log`, `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000196/db_listener_check.log`.
- No alternate characters DB URL was present in the environment. Search log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000196/db_env_search.log`.

DVC and validation evidence:

- Main worktree `git status --short --branch`: clean on `master...origin/master [ahead 90]`. Main `pixi run dvc status`: clean. Logs: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000196/git_status_main_initial.log`, `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000196/dvc_status_main_initial.log`.
- Combined worktree is clean on `codex/ml/bt-masked-ga-combined` before this doc update. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000196/git_status_combined_initial.log`.
- Combined DVC config has the same remote settings as main; `.dvc/config.local` is byte-equivalent to main and remains uncommitted. Redacted logs: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000196/dvc_config_main_redacted.log`, `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000196/dvc_config_combined_redacted.log`, `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000196/dvc_config_local_cmp.log`.
- No stale nested `generated/orchestrator_worktrees` directories were found inside the combined worktree. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000196/stale_orchestrator_worktrees.log`.
- `pixi run dvc pull bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, everything is up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000196/dvc_pull_selected_stage_targets.log`.
- `pixi run dvc status bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, data and pipelines are up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000196/dvc_status_selected_after_pull.log`.
- Broad combined `pixi run dvc status`: still reports historical deleted-output state outside the selected combined lane. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000196/dvc_status_combined_full_initial.log`.
- Focused/full ML tests, `bt_masked_ga_combined` repro, and `worldserver` build were not rerun in pass 000196 because DB export remained unavailable and the prompt says to stop and write a blocker report when DB access is not available.
- No selected DVC artifacts changed, so `pixi run dvc push` was not run.

Selected lane artifacts:

- `artifacts/ml_strategy_eval/bt_masked_ga_combined/report.json`
- `artifacts/ml_strategy_eval/bt_masked_ga_combined/metrics.json`
- `artifacts/ml_strategy_eval/bt_masked_ga_combined/stonecore_baseline_comparison.json`

Current metrics from fixture data:

- candidate rows: 4
- decision rows: 2
- observed-label rows: 2
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
- Focused and full ML tests pass: latest passing evidence remains pass 000004; not rerun in pass 000196 due the DB blocker stop condition.
- Dataset has real telemetry scale: no, blocked by unreachable characters DB.
- Server-valid candidate masks are preserved: yes in current fixture metrics.
- Stonecore baseline comparison shows no regression: yes in current fixture metrics.
- `control_eligible=false` and runtime mode remains offline/shadow only: yes.

Next prompt:

Continue `codex/ml/bt-masked-ga-combined` only. Do not launch new strategy lanes. Restore reachable characters DB access for `mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1` or provide the correct characters DB URL, then run `pixi run bot-ml-export --database-url <characters-db-url> --output-dir dataset/bot_ml/raw`, `pixi run dvc repro bot_ml_build_decisions`, `pixi run dvc repro bot_ml_validate`, and `pixi run dvc repro bt_masked_ga_combined`. Confirm `dataset/bot_ml/decision_dataset_manifest.json` is no longer 4 candidate rows / 2 decision rows, inspect the combined metrics and Stonecore comparison, run `pixi run pytest -q tests/test_ml_pipeline.py`, `cmake --build build --target worldserver -j2`, `pixi run dvc status`, `pixi run dvc push` if DVC artifacts changed, then commit the dataset/artifact pointer and docs updates. Mark merge-ready only if all acceptance criteria pass.

## 2026-06-28 Orchestrator Pass 000195

Branch `codex/ml/bt-masked-ga-combined` remains the selected Stonecore ML path: behavior-tree learned scoring plus masked ranker, with GA retained only as an offline helper. No new strategy lane or worker session was launched, and no C++ runtime control was added; the lane remains offline/shadow-only.

Current status: not merge-ready.

The blocker is unchanged and current as of pass 000195. `dataset/bot_ml/decision_dataset_manifest.json` still contains the fixture-scale dataset: 4 candidate rows, 2 decision rows, and 2 observed-label rows. Acceptance requires real telemetry scale, so this pass does not claim merge readiness.

DB export attempts:

- `pixi run bot-ml-export --database-url mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1 --output-dir dataset/bot_ml/raw`: failed, no route to host. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000195/bot_ml_export_172_20_0_2_lane_r1.log`.
- `pixi run bot-ml-export --database-url mysql://trinity:trinity@127.0.0.1:3306/characters --output-dir dataset/bot_ml/raw`: failed, connection refused. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000195/bot_ml_export_127_0_0_1_characters.log`.

DB availability evidence:

- Docker only showed an unrelated Postgres container and `ss -ltnp` showed no local MySQL listener on port 3306. Logs: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000195/docker_ps.log`, `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000195/db_listener_check.log`.
- The documented Stonecore lane characters DB endpoint remains `172.20.0.2:3306`; the Makefile default remains localhost `characters`. Search log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000195/db_url_search.log`.

DVC and validation evidence:

- Main worktree `git status --short`: clean. Main `pixi run dvc status`: clean. Logs: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000195/git_status_main_final.log`, `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000195/dvc_status_main_final.log`.
- Combined worktree is clean on `codex/ml/bt-masked-ga-combined` before this doc update. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000195/git_status_combined_final.log`.
- Combined DVC config has the same remote settings as main; redacted logs: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000195/dvc_config_main_redacted.log`, `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000195/dvc_config_combined_redacted.log`.
- No stale nested `generated/orchestrator_worktrees` directories were found inside the combined worktree.
- `pixi run dvc pull bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, everything is up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000195/dvc_pull_selected_stage_targets.log`.
- `pixi run dvc status bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, data and pipelines are up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000195/dvc_status_selected_after_pull.log`.
- Broad combined `pixi run dvc status`: still reports historical deleted-output state outside the selected combined lane. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000195/dvc_status_combined_full.log`.
- Focused/full ML tests, `bt_masked_ga_combined` repro, and `worldserver` build were not rerun in pass 000195 because DB export remained unavailable and the prompt says to stop and write a blocker report when DB access is not available.
- No selected DVC artifacts changed, so `pixi run dvc push` was not run.

Selected lane artifacts:

- `artifacts/ml_strategy_eval/bt_masked_ga_combined/report.json`
- `artifacts/ml_strategy_eval/bt_masked_ga_combined/metrics.json`
- `artifacts/ml_strategy_eval/bt_masked_ga_combined/stonecore_baseline_comparison.json`

Current metrics from fixture data:

- candidate rows: 4
- decision rows: 2
- observed-label rows: 2
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
- Focused and full ML tests pass: latest passing evidence remains pass 000004; not rerun in pass 000195 due the DB blocker stop condition.
- Dataset has real telemetry scale: no, blocked by unreachable characters DB.
- Server-valid candidate masks are preserved: yes in current fixture metrics.
- Stonecore baseline comparison shows no regression: yes in current fixture metrics.
- `control_eligible=false` and runtime mode remains offline/shadow only: yes.

Next prompt:

Continue `codex/ml/bt-masked-ga-combined` only. Do not launch new strategy lanes. Restore reachable characters DB access for `mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1` or provide the correct characters DB URL, then run `pixi run bot-ml-export --database-url <characters-db-url> --output-dir dataset/bot_ml/raw`, `pixi run dvc repro bot_ml_build_decisions`, `pixi run dvc repro bot_ml_validate`, and `pixi run dvc repro bt_masked_ga_combined`. Confirm `dataset/bot_ml/decision_dataset_manifest.json` is no longer 4 candidate rows / 2 decision rows, inspect the combined metrics and Stonecore comparison, run `pixi run pytest -q tests/test_ml_pipeline.py`, `cmake --build build --target worldserver -j2`, `pixi run dvc status`, `pixi run dvc push` if DVC artifacts changed, then commit the dataset/artifact pointer and docs updates. Mark merge-ready only if all acceptance criteria pass.

## 2026-06-28 Orchestrator Pass 000194

Branch `codex/ml/bt-masked-ga-combined` remains the selected Stonecore ML path: behavior-tree learned scoring plus masked ranker, with GA retained only as an offline helper. No new strategy lane or worker session was launched, and no C++ runtime control was added; the lane remains offline/shadow-only.

Current status: not merge-ready.

The blocker is unchanged and current as of pass 000194. `dataset/bot_ml/decision_dataset_manifest.json` still contains the fixture-scale dataset: 4 candidate rows, 2 decision rows, and 2 observed-label rows. Acceptance requires real telemetry scale, so this pass does not claim merge readiness.

DB export attempt:

- `pixi run bot-ml-export --database-url mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1 --output-dir dataset/bot_ml/raw`: failed, no route to host. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000194/bot_ml_export_172_20_0_2_lane_r1.log`.

DB availability evidence:

- Docker only showed an unrelated Postgres container and `ss -ltnp` showed no local MySQL listener on port 3306. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000194/db_listener_check.log`.
- The documented Stonecore lane characters DB endpoint remains `172.20.0.2:3306`. Search log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000194/db_url_search.log`.

DVC and validation evidence:

- Main worktree `pixi run dvc status`: clean. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000194/dvc_status_main_initial.log`.
- Combined worktree `git status --short --branch`: clean on `codex/ml/bt-masked-ga-combined` before this doc update. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000194/git_status_combined_initial.log`.
- Combined `.dvc/config.local`: present, gitignored, and byte-equivalent to main DVC local credentials. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000194/dvc_config_local_cmp.log`.
- No stale nested `generated/orchestrator_worktrees` directories were found inside the combined worktree. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000194/stale_orchestrator_worktrees.log`.
- `pixi run dvc pull bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, everything is up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000194/dvc_pull_selected_stage_targets.log`.
- `pixi run dvc status bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, data and pipelines are up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000194/dvc_status_selected_after_pull.log`.
- Broad combined `pixi run dvc status`: still reports historical deleted-output state outside the selected combined lane. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000194/dvc_status_combined_initial.log`.
- Focused/full ML tests, `bt_masked_ga_combined` repro, and `worldserver` build were not rerun in pass 000194 because DB export remained unavailable and the prompt says to stop and write a blocker report when DB access is not available.
- No selected DVC artifacts changed, so `pixi run dvc push` was not run.

Selected lane artifacts:

- `artifacts/ml_strategy_eval/bt_masked_ga_combined/report.json`
- `artifacts/ml_strategy_eval/bt_masked_ga_combined/metrics.json`
- `artifacts/ml_strategy_eval/bt_masked_ga_combined/stonecore_baseline_comparison.json`

Current metrics from fixture data:

- candidate rows: 4
- decision rows: 2
- observed-label rows: 2
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
- Focused and full ML tests pass: latest passing evidence remains pass 000004; not rerun in pass 000194 due the DB blocker stop condition.
- Dataset has real telemetry scale: no, blocked by unreachable characters DB.
- Server-valid candidate masks are preserved: yes in current fixture metrics.
- Stonecore baseline comparison shows no regression: yes in current fixture metrics.
- `control_eligible=false` and runtime mode remains offline/shadow only: yes.

Next prompt:

Continue `codex/ml/bt-masked-ga-combined` only. Do not launch new strategy lanes. Restore reachable characters DB access for `mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1` or provide the correct characters DB URL, then run `pixi run bot-ml-export --database-url <characters-db-url> --output-dir dataset/bot_ml/raw`, `pixi run dvc repro bot_ml_build_decisions`, `pixi run dvc repro bot_ml_validate`, and `pixi run dvc repro bt_masked_ga_combined`. Confirm `dataset/bot_ml/decision_dataset_manifest.json` is no longer 4 candidate rows / 2 decision rows, inspect the combined metrics and Stonecore comparison, run `pixi run pytest -q tests/test_ml_pipeline.py`, `cmake --build build --target worldserver -j2`, `pixi run dvc status`, `pixi run dvc push` if DVC artifacts changed, then commit the dataset/artifact pointer and docs updates. Mark merge-ready only if all acceptance criteria pass.

## 2026-06-28 Orchestrator Pass 000193

Branch `codex/ml/bt-masked-ga-combined` remains the selected Stonecore ML path: behavior-tree learned scoring plus masked ranker, with GA retained only as an offline helper. No new strategy lane or worker session was launched, and no C++ runtime control was added; the lane remains offline/shadow-only.

Current status: not merge-ready.

The blocker is unchanged and current as of pass 000193. `dataset/bot_ml/decision_dataset_manifest.json` still contains the fixture-scale dataset: 4 candidate rows, 2 decision rows, and 2 observed-label rows. Acceptance requires real telemetry scale, so this pass does not claim merge readiness.

DB export attempt:

- `pixi run bot-ml-export --database-url mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1 --output-dir dataset/bot_ml/raw`: failed, no route to host. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000193/bot_ml_export_172_20_0_2_lane_r1.log`.

DB availability evidence:

- Docker only showed an unrelated Postgres container. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000193/service_probe_docker.log`.
- `ss -ltnp` showed no local MySQL listener on port 3306. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000193/service_probe_ss.log`.
- The documented Stonecore lane characters DB endpoint remains `172.20.0.2:3306`. Search log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000193/db_url_search.log`.

DVC and validation evidence:

- Main worktree `pixi run dvc status`: clean. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000193/dvc_status_main_initial.log`.
- Combined worktree `git status --short --branch`: clean on `codex/ml/bt-masked-ga-combined` before this doc update. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000193/git_status_combined_initial.log`.
- Combined `.dvc/config.local`: present, gitignored, and byte-equivalent to main DVC local credentials. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000193/dvc_config_local_cmp.log`.
- No stale nested `generated/orchestrator_worktrees` directories were found inside the combined worktree; existing generated worktrees are under the main repo orchestration area. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000193/stale_orchestrator_worktrees.log`.
- `pixi run dvc pull bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, everything is up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000193/dvc_pull_selected_stage_targets.log`.
- `pixi run dvc status bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, data and pipelines are up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000193/dvc_status_selected_after_pull.log`.
- Broad combined `pixi run dvc status`: still reports historical deleted-output state outside the selected combined lane. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000193/dvc_status_combined_initial.log`.
- Focused/full ML tests, `bt_masked_ga_combined` repro, and `worldserver` build were not rerun in pass 000193 because DB export remained unavailable and the prompt says to stop and write a blocker report when DB access is not available.
- No selected DVC artifacts changed, so `pixi run dvc push` was not run.

Selected lane artifacts:

- `artifacts/ml_strategy_eval/bt_masked_ga_combined/report.json`
- `artifacts/ml_strategy_eval/bt_masked_ga_combined/metrics.json`
- `artifacts/ml_strategy_eval/bt_masked_ga_combined/stonecore_baseline_comparison.json`

Current metrics from fixture data:

- candidate rows: 4
- decision rows: 2
- observed-label rows: 2
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
- Focused and full ML tests pass: latest passing evidence remains pass 000004; not rerun in pass 000193 due the DB blocker stop condition.
- Dataset has real telemetry scale: no, blocked by unreachable characters DB.
- Server-valid candidate masks are preserved: yes in current fixture metrics.
- Stonecore baseline comparison shows no regression: yes in current fixture metrics.
- `control_eligible=false` and runtime mode remains offline/shadow only: yes.

Next prompt:

Continue `codex/ml/bt-masked-ga-combined` only. Do not launch new strategy lanes. Restore reachable characters DB access for `mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1` or provide the correct characters DB URL, then run `pixi run bot-ml-export --database-url <characters-db-url> --output-dir dataset/bot_ml/raw`, `pixi run dvc repro bot_ml_build_decisions`, `pixi run dvc repro bot_ml_validate`, and `pixi run dvc repro bt_masked_ga_combined`. Confirm `dataset/bot_ml/decision_dataset_manifest.json` is no longer 4 candidate rows / 2 decision rows, inspect the combined metrics and Stonecore comparison, run `pixi run pytest -q tests/test_ml_pipeline.py`, `cmake --build build --target worldserver -j2`, `pixi run dvc status`, `pixi run dvc push` if DVC artifacts changed, then commit the dataset/artifact pointer and docs updates. Mark merge-ready only if all acceptance criteria pass.

## 2026-06-28 Orchestrator Pass 000192

Branch `codex/ml/bt-masked-ga-combined` remains the selected Stonecore ML path: behavior-tree learned scoring plus masked ranker, with GA retained only as an offline helper. No new strategy lane or worker session was launched, and no C++ runtime control was added; the lane remains offline/shadow-only.

Current status: not merge-ready.

The blocker is unchanged and current as of pass 000192. `dataset/bot_ml/decision_dataset_manifest.json` still contains the fixture-scale dataset: 4 candidate rows, 2 decision rows, and 2 observed-label rows. Acceptance requires real telemetry scale, so this pass does not claim merge readiness.

DB export attempt:

- `pixi run bot-ml-export --database-url mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1 --output-dir dataset/bot_ml/raw`: failed, no route to host. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000192/bot_ml_export_172_20_0_2_lane_r1.log`.

DB availability evidence:

- Docker only showed an unrelated Postgres container. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000192/service_probe_docker.log`.
- `ss -ltnp` showed no local MySQL listener on port 3306. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000192/service_probe_ss.log`.

DVC and validation evidence:

- Main worktree `pixi run dvc status`: clean. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000192/dvc_status_main_initial.log`.
- Combined worktree `git status --short --branch`: clean on `codex/ml/bt-masked-ga-combined` before this doc update.
- Combined `.dvc/config.local`: present, gitignored, and byte-equivalent to main DVC local credentials. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000192/dvc_config_local_cmp.log`.
- No stale nested `generated/orchestrator_worktrees` directories were found inside the combined worktree. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000192/stale_orchestrator_worktrees.log`.
- `pixi run dvc pull bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, everything is up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000192/dvc_pull_selected_stage_targets.log`.
- `pixi run dvc status bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, data and pipelines are up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000192/dvc_status_selected_after_pull.log`.
- Broad combined `pixi run dvc status`: still reports historical deleted-output state outside the selected combined lane. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000192/dvc_status_combined_initial.log`.
- Focused/full ML tests, `bt_masked_ga_combined` repro, and `worldserver` build were not rerun in pass 000192 because DB export remained unavailable and the prompt says to stop and write a blocker report when DB access is not available.
- No selected DVC artifacts changed, so `pixi run dvc push` was not run.

Selected lane artifacts:

- `artifacts/ml_strategy_eval/bt_masked_ga_combined/report.json`
- `artifacts/ml_strategy_eval/bt_masked_ga_combined/metrics.json`
- `artifacts/ml_strategy_eval/bt_masked_ga_combined/stonecore_baseline_comparison.json`

Current metrics from fixture data:

- candidate rows: 4
- decision rows: 2
- observed-label rows: 2
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
- Focused and full ML tests pass: latest passing evidence remains pass 000004; not rerun in pass 000192 due the DB blocker stop condition.
- Dataset has real telemetry scale: no, blocked by unreachable characters DB.
- Server-valid candidate masks are preserved: yes in current fixture metrics.
- Stonecore baseline comparison shows no regression: yes in current fixture metrics.
- `control_eligible=false` and runtime mode remains offline/shadow only: yes.

Next prompt:

Continue `codex/ml/bt-masked-ga-combined` only. Do not launch new strategy lanes. Restore reachable characters DB access for `mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1` or provide the correct characters DB URL, then run `pixi run bot-ml-export --database-url <characters-db-url> --output-dir dataset/bot_ml/raw`, `pixi run dvc repro bot_ml_build_decisions`, `pixi run dvc repro bot_ml_validate`, and `pixi run dvc repro bt_masked_ga_combined`. Confirm `dataset/bot_ml/decision_dataset_manifest.json` is no longer 4 candidate rows / 2 decision rows, inspect the combined metrics and Stonecore comparison, run `pixi run pytest -q tests/test_ml_pipeline.py`, `cmake --build build --target worldserver -j2`, `pixi run dvc status`, `pixi run dvc push` if DVC artifacts changed, then commit the dataset/artifact pointer and docs updates. Mark merge-ready only if all acceptance criteria pass.

## 2026-06-28 Orchestrator Pass 000191

Branch `codex/ml/bt-masked-ga-combined` remains the selected Stonecore ML path: behavior-tree learned scoring plus masked ranker, with GA retained only as an offline helper. No new strategy lane or worker session was launched, and no C++ runtime control was added; the lane remains offline/shadow-only.

Current status: not merge-ready.

The blocker is unchanged and current as of pass 000191. `dataset/bot_ml/decision_dataset_manifest.json` still contains the fixture-scale dataset: 4 candidate rows, 2 decision rows, and 2 observed-label rows. Acceptance requires real telemetry scale, so this pass does not claim merge readiness.

DB export attempt:

- `pixi run bot-ml-export --database-url mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1 --output-dir dataset/bot_ml/raw`: failed, no route to host. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000191/bot_ml_export_172_20_0_2_lane_r1.log`.

DB availability evidence:

- Docker only showed an unrelated Postgres container. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000191/service_probe_docker.log`.
- `ss -ltnp` showed no local MySQL listener on port 3306. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000191/service_probe_ss.log`.

DVC and validation evidence:

- Main worktree `pixi run dvc status`: clean.
- Combined worktree `git status --short --branch`: clean on `codex/ml/bt-masked-ga-combined` before this doc update.
- Combined `.dvc/config.local`: present, gitignored, and byte-equivalent to main DVC local credentials.
- No stale nested `generated/orchestrator_worktrees` directories were found inside the combined worktree.
- Targeted selected-lane DVC pull for `dataset/bot_ml/decision_dataset_manifest.json`, `artifacts/ml_strategy_eval/bt_masked_ga_combined/report.json`, `metrics.json`, and `stonecore_baseline_comparison.json`: passed, everything is up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000191/dvc_pull_selected.log`.
- Targeted selected-lane `pixi run dvc status` for the same outputs: passed, data and pipelines are up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000191/dvc_status_selected_after_pull.log`.
- Broad combined `pixi run dvc status`: still reports historical deleted-output state outside the selected combined lane. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000191/dvc_status_combined_initial.log`.
- Focused/full ML tests, `bt_masked_ga_combined` repro, and `worldserver` build were not rerun in pass 000191 because DB export remained unavailable and the prompt says to stop and write a blocker report when DB access is not available.
- No selected DVC artifacts changed, so `pixi run dvc push` was not run.

Selected lane artifacts:

- `artifacts/ml_strategy_eval/bt_masked_ga_combined/report.json`
- `artifacts/ml_strategy_eval/bt_masked_ga_combined/metrics.json`
- `artifacts/ml_strategy_eval/bt_masked_ga_combined/stonecore_baseline_comparison.json`

Current metrics from fixture data:

- candidate rows: 4
- decision rows: 2
- observed-label rows: 2
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
- Focused and full ML tests pass: latest passing evidence remains pass 000004; not rerun in pass 000191 due the DB blocker stop condition.
- Dataset has real telemetry scale: no, blocked by unreachable characters DB.
- Server-valid candidate masks are preserved: yes in current fixture metrics.
- Stonecore baseline comparison shows no regression: yes in current fixture metrics.
- `control_eligible=false` and runtime mode remains offline/shadow only: yes.

Next prompt:

Continue `codex/ml/bt-masked-ga-combined` only. Do not launch new strategy lanes. Restore reachable characters DB access for `mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1` or provide the correct characters DB URL, then run `pixi run bot-ml-export --database-url <characters-db-url> --output-dir dataset/bot_ml/raw`, `pixi run dvc repro bot_ml_build_decisions`, `pixi run dvc repro bot_ml_validate`, and `pixi run dvc repro bt_masked_ga_combined`. Confirm `dataset/bot_ml/decision_dataset_manifest.json` is no longer 4 candidate rows / 2 decision rows, inspect the combined metrics and Stonecore comparison, run `pixi run pytest -q tests/test_ml_pipeline.py`, `cmake --build build --target worldserver -j2`, `pixi run dvc status`, `pixi run dvc push` if DVC artifacts changed, then commit the dataset/artifact pointer and docs updates. Mark merge-ready only if all acceptance criteria pass.

## 2026-06-28 Orchestrator Pass 000190

Branch `codex/ml/bt-masked-ga-combined` remains the selected Stonecore ML path: behavior-tree learned scoring plus masked ranker, with GA retained only as an offline helper. No new strategy lane or worker session was launched, and no C++ runtime control was added; the lane remains offline/shadow-only.

Current status: not merge-ready.

The blocker is unchanged and current as of pass 000190. `dataset/bot_ml/decision_dataset_manifest.json` still contains the fixture-scale dataset: 4 candidate rows, 2 decision rows, and 2 observed-label rows. Acceptance requires real telemetry scale, so this pass does not claim merge readiness.

DB export attempts:

- `pixi run bot-ml-export --database-url mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1 --output-dir dataset/bot_ml/raw`: failed, no route to host. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000190/bot_ml_export_172_20_0_2_lane_r1.log`.
- `pixi run bot-ml-export --database-url mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r2 --output-dir dataset/bot_ml/raw`: failed, no route to host. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000190/bot_ml_export_172_20_0_2_lane_r2.log`.
- `pixi run bot-ml-export --database-url mysql://trinity:trinity@127.0.0.1:3306/characters --output-dir dataset/bot_ml/raw`: failed, connection refused. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000190/bot_ml_export_127_0_0_1_characters.log`.

DB availability evidence:

- Docker only showed an unrelated Postgres container. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000190/service_probe_docker.log`.
- `ss -ltnp` showed no local MySQL listener on port 3306. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000190/service_probe_ss.log`.
- The documented Stonecore lane characters DB endpoints still point at `172.20.0.2:3306`. Search log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000190/db_url_search.log`.

DVC and validation evidence:

- Main worktree `pixi run dvc status`: clean. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000190/dvc_status_main_initial.log`.
- Combined worktree `git status --short --branch`: clean on `codex/ml/bt-masked-ga-combined` before this doc update.
- Combined `.dvc/config.local`: present, gitignored, and byte-equivalent to main DVC local credentials. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000190/dvc_config_local_cmp.log`.
- No stale nested `generated/orchestrator_worktrees` directories were found inside the combined worktree. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000190/stale_orchestrator_worktrees.log`.
- `pixi run dvc pull bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, everything is up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000190/dvc_pull_selected.log`.
- `pixi run dvc status bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, data and pipelines are up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000190/dvc_status_selected_after_pull.log`.
- `pixi run dvc status`: still reports broad historical deleted-output state outside the selected combined lane. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000190/dvc_status_combined_initial.log`.
- Focused/full ML tests, `bt_masked_ga_combined` repro, and `worldserver` build were not rerun in pass 000190 because DB export remained unavailable and the prompt says to stop and write a blocker report when DB access is not available.
- No selected DVC artifacts changed, so `pixi run dvc push` was not run.

Selected lane artifacts:

- `artifacts/ml_strategy_eval/bt_masked_ga_combined/report.json`
- `artifacts/ml_strategy_eval/bt_masked_ga_combined/metrics.json`
- `artifacts/ml_strategy_eval/bt_masked_ga_combined/stonecore_baseline_comparison.json`

Current metrics from fixture data:

- candidate rows: 4
- decision rows: 2
- observed-label rows: 2
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
- Focused and full ML tests pass: latest passing evidence remains pass 000004; not rerun in pass 000190 due the DB blocker stop condition.
- Dataset has real telemetry scale: no, blocked by unreachable characters DB.
- Server-valid candidate masks are preserved: yes in current fixture metrics.
- Stonecore baseline comparison shows no regression: yes in current fixture metrics.
- `control_eligible=false` and runtime mode remains offline/shadow only: yes.

Next prompt:

Continue `codex/ml/bt-masked-ga-combined` only. Do not launch new strategy lanes. Restore reachable characters DB access for `mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1` or provide the correct characters DB URL, then run `pixi run bot-ml-export --database-url <characters-db-url> --output-dir dataset/bot_ml/raw`, `pixi run dvc repro bot_ml_build_decisions`, `pixi run dvc repro bot_ml_validate`, and `pixi run dvc repro bt_masked_ga_combined`. Confirm `dataset/bot_ml/decision_dataset_manifest.json` is no longer 4 candidate rows / 2 decision rows, inspect the combined metrics and Stonecore comparison, run `pixi run pytest -q tests/test_ml_pipeline.py`, `cmake --build build --target worldserver -j2`, `pixi run dvc status`, `pixi run dvc push` if DVC artifacts changed, then commit the dataset/artifact pointer and docs updates. Mark merge-ready only if all acceptance criteria pass.

## 2026-06-28 Orchestrator Pass 000189

Branch `codex/ml/bt-masked-ga-combined` remains the selected Stonecore ML path: behavior-tree learned scoring plus masked ranker, with GA retained only as an offline helper. No new strategy lane was launched, no worker session was needed, and no C++ runtime control was added; the lane remains offline/shadow-only.

Current status: not merge-ready.

The blocker is unchanged and current as of pass 000189. `dataset/bot_ml/decision_dataset_manifest.json` still contains the fixture-scale dataset: 4 candidate rows, 2 decision rows, and 2 observed-label rows. Acceptance requires real telemetry scale, so this pass does not claim merge readiness.

DB export attempts:

- `pixi run bot-ml-export --database-url mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1 --output-dir dataset/bot_ml/raw`: failed, no route to host. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000189/bot_ml_export_172_20_0_2_lane_r1.log`.
- `pixi run bot-ml-export --database-url mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r2 --output-dir dataset/bot_ml/raw`: failed, no route to host. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000189/bot_ml_export_172_20_0_2_lane_r2.log`.
- `pixi run bot-ml-export --database-url mysql://trinity:trinity@127.0.0.1:3306/characters --output-dir dataset/bot_ml/raw`: failed, connection refused. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000189/bot_ml_export_127_0_0_1_characters.log`.

DB availability evidence:

- Docker only showed an unrelated Postgres container. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000189/service_probe_docker.log`.
- `ss -ltnp` showed no local MySQL listener on port 3306. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000189/service_probe_ss.log`.
- The documented Stonecore lane characters DB endpoints still point at `172.20.0.2:3306`. Search log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000189/db_url_search.log`.

DVC and validation evidence:

- Main worktree `git status --short --branch`: `master...origin/master [ahead 90]` with no file changes.
- Main worktree `pixi run dvc status`: clean. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000189/dvc_status_main_initial.log`.
- Combined worktree `git status --short --branch`: clean on `codex/ml/bt-masked-ga-combined` before this doc update.
- Combined `.dvc/config.local`: present, gitignored, and byte-equivalent to main DVC local credentials. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000189/dvc_config_local_cmp.log`.
- No stale nested `generated/orchestrator_worktrees` directories were found inside the combined worktree. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000189/stale_worktrees_combined.log`.
- `pixi run dvc pull bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, everything is up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000189/dvc_pull_selected.log`.
- `pixi run dvc status bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, data and pipelines are up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000189/dvc_status_selected_after_pull.log`.
- `pixi run dvc status`: still reports broad historical deleted-output state outside the selected combined lane. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000189/dvc_status_combined_broad_after_pull.log`.
- Focused/full ML tests and `worldserver` build were not rerun in pass 000189 because DB export remained unavailable and the prompt says to stop and write a blocker report when DB access is not available.
- No selected DVC artifacts changed, so `pixi run dvc push` was not run.

Selected lane artifacts:

- `artifacts/ml_strategy_eval/bt_masked_ga_combined/report.json`
- `artifacts/ml_strategy_eval/bt_masked_ga_combined/metrics.json`
- `artifacts/ml_strategy_eval/bt_masked_ga_combined/stonecore_baseline_comparison.json`

Current metrics from fixture data:

- candidate rows: 4
- decision rows: 2
- observed-label rows: 2
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
- Focused and full ML tests pass: latest passing evidence remains pass 000004; not rerun in pass 000189 due the DB blocker stop condition.
- Dataset has real telemetry scale: no, blocked by unreachable characters DB.
- Server-valid candidate masks are preserved: yes in current fixture metrics.
- Stonecore baseline comparison shows no regression: yes in current fixture metrics.
- `control_eligible=false` and runtime mode remains offline/shadow only: yes.

Next prompt:

Continue `codex/ml/bt-masked-ga-combined` only. Do not launch new strategy lanes. Restore reachable characters DB access for `mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1` or provide the correct characters DB URL, then run `pixi run bot-ml-export --database-url <characters-db-url> --output-dir dataset/bot_ml/raw`, `pixi run dvc repro bot_ml_build_decisions`, `pixi run dvc repro bot_ml_validate`, and `pixi run dvc repro bt_masked_ga_combined`. Confirm `dataset/bot_ml/decision_dataset_manifest.json` is no longer 4 candidate rows / 2 decision rows, inspect the combined metrics and Stonecore comparison, run `pixi run pytest -q tests/test_ml_pipeline.py`, `cmake --build build --target worldserver -j2`, `pixi run dvc status`, `pixi run dvc push` if DVC artifacts changed, then commit the dataset/artifact pointer and docs updates. Mark merge-ready only if all acceptance criteria pass.

## 2026-06-28 Orchestrator Pass 000188

Branch `codex/ml/bt-masked-ga-combined` remains the selected Stonecore ML path: behavior-tree learned scoring plus masked ranker, with GA retained only as an offline helper. No new strategy lane was launched, no worker session was needed, and no C++ runtime control was added; the lane remains offline/shadow-only.

Current status: not merge-ready.

The blocker is unchanged and current as of pass 000188. `dataset/bot_ml/decision_dataset_manifest.json` still contains the fixture-scale dataset: 4 candidate rows, 2 decision rows, and 2 observed-label rows. Acceptance requires real telemetry scale, so this pass does not claim merge readiness.

DB export attempts:

- `pixi run bot-ml-export --database-url mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1 --output-dir dataset/bot_ml/raw`: failed, no route to host. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000188/bot_ml_export_172_20_0_2_lane_r1.log`.
- `pixi run bot-ml-export --database-url mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r2 --output-dir dataset/bot_ml/raw`: failed, no route to host. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000188/bot_ml_export_172_20_0_2_lane_r2.log`.
- `pixi run bot-ml-export --database-url mysql://trinity:trinity@127.0.0.1:3306/characters --output-dir dataset/bot_ml/raw`: failed, connection refused. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000188/bot_ml_export_127_0_0_1_characters.log`.

DB availability evidence:

- Docker only showed an unrelated Postgres container. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000188/service_probe_docker.log`.
- `ss -ltnp` showed no local MySQL listener on port 3306. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000188/service_probe_ss.log`.
- The documented Stonecore lane characters DB endpoints still point at `172.20.0.2:3306`.

DVC and validation evidence:

- Main worktree `git status --short --branch`: `master...origin/master [ahead 90]` with no file changes. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000188/git_status_main_initial.log`.
- Main worktree `pixi run dvc status`: clean. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000188/dvc_status_main_initial.log`.
- Combined worktree `git status --short --branch`: clean on `codex/ml/bt-masked-ga-combined` before this doc update. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000188/git_status_combined_initial.log`.
- Combined `.dvc/config.local`: present, gitignored, and byte-equivalent to main DVC local credentials. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000188/dvc_config_local_cmp.log`.
- No stale nested `generated/orchestrator_worktrees` directories were found inside the combined worktree.
- `pixi run dvc pull bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, everything is up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000188/dvc_pull_selected.log`.
- `pixi run dvc status bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, data and pipelines are up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000188/dvc_status_selected_after_pull.log`.
- `pixi run dvc status`: still reports broad historical deleted-output state outside the selected combined lane. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000188/dvc_status_combined_broad_after_pull.log`.
- Focused/full ML tests and `worldserver` build were not rerun in pass 000188 because DB export remained unavailable and the prompt says to stop and write a blocker report when DB access is not available.
- No selected DVC artifacts changed, so `pixi run dvc push` was not run.

Selected lane artifacts:

- `artifacts/ml_strategy_eval/bt_masked_ga_combined/report.json`
- `artifacts/ml_strategy_eval/bt_masked_ga_combined/metrics.json`
- `artifacts/ml_strategy_eval/bt_masked_ga_combined/stonecore_baseline_comparison.json`

Current metrics from fixture data:

- candidate rows: 4
- decision rows: 2
- observed-label rows: 2
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
- Focused and full ML tests pass: latest passing evidence remains pass 000004; not rerun in pass 000188 due the DB blocker stop condition.
- Dataset has real telemetry scale: no, blocked by unreachable characters DB.
- Server-valid candidate masks are preserved: yes in current fixture metrics.
- Stonecore baseline comparison shows no regression: yes in current fixture metrics.
- `control_eligible=false` and runtime mode remains offline/shadow only: yes.

Next prompt:

Continue `codex/ml/bt-masked-ga-combined` only. Do not launch new strategy lanes. Restore reachable characters DB access for `mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1` or provide the correct characters DB URL, then run `pixi run bot-ml-export --database-url <characters-db-url> --output-dir dataset/bot_ml/raw`, `pixi run dvc repro bot_ml_build_decisions`, `pixi run dvc repro bot_ml_validate`, and `pixi run dvc repro bt_masked_ga_combined`. Confirm `dataset/bot_ml/decision_dataset_manifest.json` is no longer 4 candidate rows / 2 decision rows, inspect the combined metrics and Stonecore comparison, run `pixi run pytest -q tests/test_ml_pipeline.py`, `cmake --build build --target worldserver -j2`, `pixi run dvc status`, `pixi run dvc push` if DVC artifacts changed, then commit the dataset/artifact pointer and docs updates. Mark merge-ready only if all acceptance criteria pass.

## 2026-06-28 Orchestrator Pass 000187

Branch `codex/ml/bt-masked-ga-combined` remains the selected Stonecore ML path: behavior-tree learned scoring plus masked ranker, with GA retained only as an offline helper. No new strategy lane was launched, no worker session was needed, and no C++ runtime control was added; the lane remains offline/shadow-only.

Current status: not merge-ready.

The blocker is unchanged and current as of pass 000187. `dataset/bot_ml/decision_dataset_manifest.json` still contains the fixture-scale dataset: 4 candidate rows, 2 decision rows, and 2 observed-label rows. Acceptance requires real telemetry scale, so this pass does not claim merge readiness.

DB export attempts:

- `pixi run bot-ml-export --database-url mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1 --output-dir dataset/bot_ml/raw`: failed, no route to host. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000187/bot_ml_export_172_20_0_2_lane_r1.log`.
- `pixi run bot-ml-export --database-url mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r2 --output-dir dataset/bot_ml/raw`: failed, no route to host. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000187/bot_ml_export_172_20_0_2_lane_r2.log`.
- `pixi run bot-ml-export --database-url mysql://trinity:trinity@127.0.0.1:3306/characters --output-dir dataset/bot_ml/raw`: failed, connection refused. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000187/bot_ml_export_127_0_0_1_characters.log`.

DB availability evidence:

- Docker only showed an unrelated Postgres container. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000187/service_probe_docker.log`.
- `ss -ltnp` showed no local MySQL listener on port 3306. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000187/service_probe_ss.log`.
- The documented Stonecore lane characters DB endpoints still point at `172.20.0.2:3306`.

DVC and validation evidence:

- Main worktree `git status --short --branch`: `master...origin/master [ahead 90]` with no file changes. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000187/git_status_main_initial.log`.
- Main worktree `pixi run dvc status`: clean. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000187/dvc_status_main_initial.log`.
- Combined worktree `git status --short --branch`: clean on `codex/ml/bt-masked-ga-combined` before this doc update. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000187/git_status_combined_initial.log`.
- Combined `.dvc/config.local`: present, gitignored, and byte-equivalent to main DVC local credentials; redacted config logs were recorded.
- No stale nested `generated/orchestrator_worktrees` directories were found inside the combined worktree.
- `pixi run dvc pull bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, everything is up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000187/dvc_pull_selected_stages.log`.
- `pixi run dvc status bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, data and pipelines are up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000187/dvc_status_selected_after_pull.log`.
- `pixi run dvc status`: still reports broad historical deleted-output state outside the selected combined lane. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000187/dvc_status_combined_final.log`.
- Focused/full ML tests and `worldserver` build were not rerun in pass 000187 because DB export remained unavailable and the prompt says to stop and write a blocker report when DB access is not available.
- No selected DVC artifacts changed, so `pixi run dvc push` was not run.

Selected lane artifacts:

- `artifacts/ml_strategy_eval/bt_masked_ga_combined/report.json`
- `artifacts/ml_strategy_eval/bt_masked_ga_combined/metrics.json`
- `artifacts/ml_strategy_eval/bt_masked_ga_combined/stonecore_baseline_comparison.json`

Current metrics from fixture data:

- candidate rows: 4
- decision rows: 2
- observed-label rows: 2
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
- Focused and full ML tests pass: latest passing evidence remains pass 000004; not rerun in pass 000187 due the DB blocker stop condition.
- Dataset has real telemetry scale: no, blocked by unreachable characters DB.
- Server-valid candidate masks are preserved: yes in current fixture metrics.
- Stonecore baseline comparison shows no regression: yes in current fixture metrics.
- `control_eligible=false` and runtime mode remains offline/shadow only: yes.

Next prompt:

Continue `codex/ml/bt-masked-ga-combined` only. Do not launch new strategy lanes. Restore reachable characters DB access for `mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1` or provide the correct characters DB URL, then run `pixi run bot-ml-export --database-url <characters-db-url> --output-dir dataset/bot_ml/raw`, `pixi run dvc repro bot_ml_build_decisions`, `pixi run dvc repro bot_ml_validate`, and `pixi run dvc repro bt_masked_ga_combined`. Confirm `dataset/bot_ml/decision_dataset_manifest.json` is no longer 4 candidate rows / 2 decision rows, inspect the combined metrics and Stonecore comparison, run `pixi run pytest -q tests/test_ml_pipeline.py`, `cmake --build build --target worldserver -j2`, `pixi run dvc status`, `pixi run dvc push` if DVC artifacts changed, then commit the dataset/artifact pointer and docs updates. Mark merge-ready only if all acceptance criteria pass.

## 2026-06-28 Orchestrator Pass 000186

Branch `codex/ml/bt-masked-ga-combined` remains the selected Stonecore ML path: behavior-tree learned scoring plus masked ranker, with GA retained only as an offline helper. No new strategy lane was launched, no worker session was needed, and no C++ runtime control was added; the lane remains offline/shadow-only.

Current status: not merge-ready.

The blocker is unchanged and current as of pass 000186. `dataset/bot_ml/decision_dataset_manifest.json` still contains the fixture-scale dataset: 4 candidate rows, 2 decision rows, and 2 observed-label rows. Acceptance requires real telemetry scale, so this pass does not claim merge readiness.

DB export attempts:

- `pixi run bot-ml-export --database-url mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1 --output-dir dataset/bot_ml/raw`: failed, no route to host. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000186/bot_ml_export_172_20_0_2_lane_r1.log`.
- `pixi run bot-ml-export --database-url mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r2 --output-dir dataset/bot_ml/raw`: failed, no route to host. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000186/bot_ml_export_172_20_0_2_lane_r2.log`.
- `pixi run bot-ml-export --database-url mysql://trinity:trinity@127.0.0.1:3306/characters --output-dir dataset/bot_ml/raw`: failed, connection refused. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000186/bot_ml_export_127_0_0_1_characters.log`.

DB availability evidence:

- Docker only showed an unrelated Postgres container. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000186/service_probe_docker.log`.
- `ss -ltnp` showed no local MySQL listener on port 3306. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000186/service_probe_ss.log`.
- The documented Stonecore lane characters DB endpoints still point at `172.20.0.2:3306`. Search log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000186/db_url_search.log`.

DVC and validation evidence:

- Main worktree `pixi run dvc status`: clean. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000186/dvc_status_main_initial.log`.
- Combined `.dvc/config.local`: present, gitignored, and byte-equivalent to main DVC local credentials; redacted config logs were recorded.
- No stale nested `generated/orchestrator_worktrees` directories were found inside the combined worktree.
- `git worktree list --porcelain` was recorded for temporary-worktree visibility. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000186/git_worktree_list.log`.
- `pixi run dvc pull bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, everything is up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000186/dvc_pull_selected_stages.log`.
- `pixi run dvc status bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, data and pipelines are up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000186/dvc_status_selected_after_pull.log`.
- `pixi run dvc status`: still reports broad historical deleted-output state outside the selected combined lane. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000186/dvc_status_combined_initial.log`.
- Focused/full ML tests and `worldserver` build were not rerun in pass 000186 because DB export remained unavailable and the prompt says to stop and write a blocker report when DB access is not available.
- No selected DVC artifacts changed, so `pixi run dvc push` was not run.

Selected lane artifacts:

- `artifacts/ml_strategy_eval/bt_masked_ga_combined/report.json`
- `artifacts/ml_strategy_eval/bt_masked_ga_combined/metrics.json`
- `artifacts/ml_strategy_eval/bt_masked_ga_combined/stonecore_baseline_comparison.json`

Current metrics from fixture data:

- candidate rows: 4
- decision rows: 2
- observed-label rows: 2
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
- Focused and full ML tests pass: latest passing evidence remains pass 000004; not rerun in pass 000186 due the DB blocker stop condition.
- Dataset has real telemetry scale: no, blocked by unreachable characters DB.
- Server-valid candidate masks are preserved: yes in current fixture metrics.
- Stonecore baseline comparison shows no regression: yes in current fixture metrics.
- `control_eligible=false` and runtime mode remains offline/shadow only: yes.

Next prompt:

Continue `codex/ml/bt-masked-ga-combined` only. Do not launch new strategy lanes. Restore reachable characters DB access for `mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1` or provide the correct characters DB URL, then run `pixi run bot-ml-export --database-url <characters-db-url> --output-dir dataset/bot_ml/raw`, `pixi run dvc repro bot_ml_build_decisions`, `pixi run dvc repro bot_ml_validate`, and `pixi run dvc repro bt_masked_ga_combined`. Confirm `dataset/bot_ml/decision_dataset_manifest.json` is no longer 4 candidate rows / 2 decision rows, inspect the combined metrics and Stonecore comparison, run `pixi run pytest -q tests/test_ml_pipeline.py`, `cmake --build build --target worldserver -j2`, `pixi run dvc status`, `pixi run dvc push` if DVC artifacts changed, then commit the dataset/artifact pointer and docs updates. Mark merge-ready only if all acceptance criteria pass.

## 2026-06-28 Orchestrator Pass 000185

Branch `codex/ml/bt-masked-ga-combined` remains the selected Stonecore ML path: behavior-tree learned scoring plus masked ranker, with GA retained only as an offline helper. No new strategy lane was launched, no worker session was needed, and no C++ runtime control was added; the lane remains offline/shadow-only.

Current status: not merge-ready.

The blocker is unchanged and current as of pass 000185. `dataset/bot_ml/decision_dataset_manifest.json` still contains the fixture-scale dataset: 4 candidate rows, 2 decision rows, and 2 observed-label rows. Acceptance requires real telemetry scale, so this pass does not claim merge readiness.

DB export attempts:

- `pixi run bot-ml-export --database-url mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1 --output-dir dataset/bot_ml/raw`: failed, no route to host. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000185/bot_ml_export_172_20_0_2_lane_r1.log`.
- `pixi run bot-ml-export --database-url mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r2 --output-dir dataset/bot_ml/raw`: failed, no route to host. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000185/bot_ml_export_172_20_0_2_lane_r2.log`.
- `pixi run bot-ml-export --database-url mysql://trinity:trinity@127.0.0.1:3306/characters --output-dir dataset/bot_ml/raw`: failed, connection refused. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000185/bot_ml_export_127_0_0_1_characters.log`.

DB availability evidence:

- Docker only showed an unrelated Postgres container. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000185/service_probe_docker.log`.
- `ss -ltnp` showed no local MySQL listener on port 3306. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000185/service_probe_ss.log`.
- The documented Stonecore lane characters DB endpoints still point at `172.20.0.2:3306`.

DVC and validation evidence:

- Main worktree `pixi run dvc status`: clean. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000185/dvc_status_main_initial.log`.
- Combined `.dvc/config.local`: present, gitignored, and byte-equivalent to main DVC local credentials; redacted config logs were recorded.
- No stale nested `generated/orchestrator_worktrees` directories were found inside the combined worktree.
- `git worktree list --porcelain` was recorded for temporary-worktree visibility. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000185/git_worktree_list.log`.
- `pixi run dvc pull bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, everything is up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000185/dvc_pull_selected_stages.log`.
- `pixi run dvc status bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, data and pipelines are up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000185/dvc_status_selected_after_pull.log`.
- `pixi run dvc status`: still reports broad historical deleted-output state outside the selected combined lane. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000185/dvc_status_combined_final.log`.
- Focused/full ML tests and `worldserver` build were not rerun in pass 000185 because DB export remained unavailable and the prompt says to stop and write a blocker report when DB access is not available.
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
- Focused and full ML tests pass: latest passing evidence remains pass 000004; not rerun in pass 000185 due the DB blocker stop condition.
- Dataset has real telemetry scale: no, blocked by unreachable characters DB.
- Server-valid candidate masks are preserved: yes in current fixture metrics.
- Stonecore baseline comparison shows no regression: yes in current fixture metrics.
- `control_eligible=false` and runtime mode remains offline/shadow only: yes.

Next prompt:

Continue `codex/ml/bt-masked-ga-combined` only. Do not launch new strategy lanes. Restore reachable characters DB access for `mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1` or provide the correct characters DB URL, then run `pixi run bot-ml-export --database-url <characters-db-url> --output-dir dataset/bot_ml/raw`, `pixi run dvc repro bot_ml_build_decisions`, `pixi run dvc repro bot_ml_validate`, and `pixi run dvc repro bt_masked_ga_combined`. Confirm `dataset/bot_ml/decision_dataset_manifest.json` is no longer 4 candidate rows / 2 decision rows, inspect the combined metrics and Stonecore comparison, run `pixi run pytest -q tests/test_ml_pipeline.py`, `cmake --build build --target worldserver -j2`, `pixi run dvc status`, `pixi run dvc push` if DVC artifacts changed, then commit the dataset/artifact pointer and docs updates. Mark merge-ready only if all acceptance criteria pass.

## 2026-06-28 Orchestrator Pass 000184

Branch `codex/ml/bt-masked-ga-combined` remains the selected Stonecore ML path: behavior-tree learned scoring plus masked ranker, with GA retained only as an offline helper. No new strategy lane was launched, no worker session was needed, and no C++ runtime control was added; the lane remains offline/shadow-only.

Current status: not merge-ready.

The blocker is unchanged and current as of pass 000184. `dataset/bot_ml/decision_dataset_manifest.json` still contains the fixture-scale dataset: 4 candidate rows, 2 decision rows, and 2 observed-label rows. Acceptance requires real telemetry scale, so this pass does not claim merge readiness.

DB export attempts:

- `pixi run bot-ml-export --database-url mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1 --output-dir dataset/bot_ml/raw`: failed, no route to host. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000184/bot_ml_export_172_20_0_2_lane_r1.log`.
- `pixi run bot-ml-export --database-url mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r2 --output-dir dataset/bot_ml/raw`: failed, no route to host. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000184/bot_ml_export_172_20_0_2_lane_r2.log`.
- `pixi run bot-ml-export --database-url mysql://trinity:trinity@127.0.0.1:3306/characters --output-dir dataset/bot_ml/raw`: failed, connection refused. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000184/bot_ml_export_127_0_0_1_characters.log`.

DB availability evidence:

- Docker service probe and local socket probe were refreshed. Logs: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000184/service_probe_docker.log` and `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000184/service_probe_ss.log`.
- The only discovered Stonecore lane characters DB configs still point at `172.20.0.2:3306`. Search log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000184/db_url_search.log`.

DVC and validation evidence:

- Main worktree `pixi run dvc status`: clean. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000184/dvc_status_main_initial.log`.
- Combined `.dvc/config.local`: present, gitignored, and byte-equivalent to main DVC local credentials; redacted config logs were recorded.
- `git worktree list` was recorded for temporary-worktree visibility. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000184/git_worktree_list.log`.
- `pixi run dvc pull --with-deps bt_masked_ga_combined`: passed. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000184/dvc_pull_selected.log`.
- `pixi run dvc status bt_masked_ga_combined` and `pixi run dvc status bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, data and pipelines are up to date. Logs: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000184/dvc_status_selected_after_pull.log` and `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000184/dvc_status_selected_three_stages_final.log`.
- `pixi run dvc status`: still reports broad historical deleted-output state outside the selected combined lane. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000184/dvc_status_combined_after_pull.log`.
- Focused/full ML tests and `worldserver` build were not rerun in pass 000184 because DB export remained unavailable and the prompt says to stop and write a blocker report when DB access is not available. Latest passing evidence remains pass 000004.
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
- Focused and full ML tests pass: yes in latest pass 000004 evidence; not rerun in pass 000184 due the DB blocker stop condition.
- Dataset has real telemetry scale: no, blocked by unreachable characters DB.
- Server-valid candidate masks are preserved: yes in current fixture metrics.
- Stonecore baseline comparison shows no regression: yes in current fixture metrics.
- `control_eligible=false` and runtime mode remains offline/shadow only: yes.

Next prompt:

Continue `codex/ml/bt-masked-ga-combined` only. Do not launch new strategy lanes. Restore reachable characters DB access for `mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1` or provide the correct characters DB URL, then run `pixi run bot-ml-export --database-url <characters-db-url> --output-dir dataset/bot_ml/raw`, `pixi run dvc repro bot_ml_build_decisions`, `pixi run dvc repro bot_ml_validate`, and `pixi run dvc repro bt_masked_ga_combined`. Confirm `dataset/bot_ml/decision_dataset_manifest.json` is no longer 4 candidate rows / 2 decision rows, inspect the combined metrics and Stonecore comparison, run `pixi run pytest -q tests/test_ml_pipeline.py`, `cmake --build build --target worldserver -j2`, `pixi run dvc status`, `pixi run dvc push` if DVC artifacts changed, then commit the dataset/artifact pointer and docs updates. Mark merge-ready only if all acceptance criteria pass.

## 2026-06-28 Orchestrator Pass 000183

Branch `codex/ml/bt-masked-ga-combined` remains the selected Stonecore ML path: behavior-tree learned scoring plus masked ranker, with GA retained only as an offline helper. No new strategy lane was launched, no worker session was needed, and no C++ runtime control was added; the lane remains offline/shadow-only.

Current status: not merge-ready.

The blocker is unchanged and current as of pass 000183. `dataset/bot_ml/decision_dataset_manifest.json` still contains the fixture-scale dataset: 4 candidate rows, 2 decision rows, and 2 observed-label rows. Acceptance requires real telemetry scale, so this pass does not claim merge readiness.

DB export attempts:

- `pixi run bot-ml-export --database-url mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1 --output-dir dataset/bot_ml/raw`: failed, no route to host. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000183/bot_ml_export_172_20_0_2_lane_r1.log`.
- `pixi run bot-ml-export --database-url mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r2 --output-dir dataset/bot_ml/raw`: failed, no route to host. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000183/bot_ml_export_172_20_0_2_lane_r2.log`.
- `pixi run bot-ml-export --database-url mysql://trinity:trinity@127.0.0.1:3306/characters --output-dir dataset/bot_ml/raw`: failed, connection refused. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000183/bot_ml_export_127_0_0_1_characters.log`.

DB availability evidence:

- Docker only showed an unrelated Postgres container. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000183/service_probe_docker.log`.
- `ss -ltnp` showed no local MySQL listener on port 3306. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000183/service_probe_ss.log`.
- The only discovered Stonecore lane characters DB configs still point at `172.20.0.2:3306`.

DVC and validation evidence:

- Main worktree `pixi run dvc status`: clean. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000183/dvc_status_main_initial.log`.
- Combined `.dvc/config.local`: present, gitignored, and equivalent to main DVC local credentials with evidence redacted. Logs: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000183/dvc_config_main_redacted.log` and `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000183/dvc_config_combined_redacted.log`.
- `git worktree list --porcelain` was recorded for temporary-worktree visibility. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000183/git_worktree_list.log`.
- `pixi run dvc pull bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, everything up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000183/dvc_pull_selected.log`.
- `pixi run dvc status bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, everything up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000183/dvc_status_selected_after_pull.log`.
- `pixi run dvc status`: still reports broad historical deleted-output state outside the selected combined lane. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000183/dvc_status_combined_final.log`.
- Focused/full ML tests and `worldserver` build were not rerun in pass 000183 because DB export remained unavailable and the prompt says to stop and write a blocker report when DB access is not available. Latest passing evidence remains pass 000004.
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
- Focused and full ML tests pass: yes in latest pass 000004 evidence; not rerun in pass 000183 due the DB blocker stop condition.
- Dataset has real telemetry scale: no, blocked by unreachable characters DB.
- Server-valid candidate masks are preserved: yes in current fixture metrics.
- Stonecore baseline comparison shows no regression: yes in current fixture metrics.
- `control_eligible=false` and runtime mode remains offline/shadow only: yes.

Next prompt:

Continue `codex/ml/bt-masked-ga-combined` only. Do not launch new strategy lanes. Restore reachable characters DB access for `mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1` or provide the correct characters DB URL, then run `pixi run bot-ml-export --database-url <characters-db-url> --output-dir dataset/bot_ml/raw`, `pixi run dvc repro bot_ml_build_decisions`, `pixi run dvc repro bot_ml_validate`, and `pixi run dvc repro bt_masked_ga_combined`. Confirm `dataset/bot_ml/decision_dataset_manifest.json` is no longer 4 candidate rows / 2 decision rows, inspect the combined metrics and Stonecore comparison, run `pixi run pytest -q tests/test_ml_pipeline.py`, `cmake --build build --target worldserver -j2`, `pixi run dvc status`, `pixi run dvc push` if DVC artifacts changed, then commit the dataset/artifact pointer and docs updates. Mark merge-ready only if all acceptance criteria pass.

## 2026-06-28 Orchestrator Pass 000182

Branch `codex/ml/bt-masked-ga-combined` remains the selected Stonecore ML path: behavior-tree learned scoring plus masked ranker, with GA retained only as an offline helper. No new strategy lane was launched, no worker session was needed, and no C++ runtime control was added; the lane remains offline/shadow-only.

Current status: not merge-ready.

The blocker is unchanged and current as of pass 000182. `dataset/bot_ml/decision_dataset_manifest.json` still contains the fixture-scale dataset: 4 candidate rows, 2 decision rows, and 2 observed-label rows. Acceptance requires real telemetry scale, so this pass does not claim merge readiness.

DB export attempts:

- `pixi run bot-ml-export --database-url mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1 --output-dir dataset/bot_ml/raw`: failed, no route to host. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000182/bot_ml_export_172_20_0_2_lane_r1.log`.
- `pixi run bot-ml-export --database-url mysql://trinity:trinity@127.0.0.1:3306/characters --output-dir dataset/bot_ml/raw`: failed, connection refused. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000182/bot_ml_export_127_0_0_1_characters.log`.

DB availability evidence:

- Docker only showed an unrelated Postgres container. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000182/service_probe_docker.log`.
- `ss -ltnp` showed no local MySQL listener on port 3306. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000182/service_probe_ss.log`.
- No alternate configured characters DB URL was found beyond the existing readiness notes.

DVC and validation evidence:

- Main worktree `pixi run dvc status`: clean. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000182/dvc_status_main_initial.log`.
- Combined `.dvc/config.local`: present, gitignored, and equivalent to main DVC local credentials with evidence redacted. Logs: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000182/dvc_config_main_initial.log` and `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000182/dvc_config_combined_initial.log`.
- `git worktree list --porcelain` was recorded for temporary-worktree visibility. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000182/git_worktree_list.log`.
- `pixi run dvc pull bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, everything up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000182/dvc_pull_selected.log`.
- `pixi run dvc status bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, everything up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000182/dvc_status_selected_after_pull.log`.
- `pixi run dvc status`: still reports broad historical deleted-output state outside the selected combined lane. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000182/dvc_status_combined_initial.log`.
- Focused/full ML tests and `worldserver` build were not rerun in pass 000182 because DB export remained unavailable and the prompt says to stop and write a blocker report when DB access is not available. Latest passing evidence remains pass 000004.
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
- Focused and full ML tests pass: yes in latest pass 000004 evidence; not rerun in pass 000182 due the DB blocker stop condition.
- Dataset has real telemetry scale: no, blocked by unreachable characters DB.
- Server-valid candidate masks are preserved: yes in current fixture metrics.
- Stonecore baseline comparison shows no regression: yes in current fixture metrics.
- `control_eligible=false` and runtime mode remains offline/shadow only: yes.

Next prompt:

Continue `codex/ml/bt-masked-ga-combined` only. Do not launch new strategy lanes. Restore reachable characters DB access for `mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1` or provide the correct characters DB URL, then run `pixi run bot-ml-export --database-url <characters-db-url> --output-dir dataset/bot_ml/raw`, `pixi run dvc repro bot_ml_build_decisions`, `pixi run dvc repro bot_ml_validate`, and `pixi run dvc repro bt_masked_ga_combined`. Confirm `dataset/bot_ml/decision_dataset_manifest.json` is no longer 4 candidate rows / 2 decision rows, inspect the combined metrics and Stonecore comparison, run `pixi run pytest -q tests/test_ml_pipeline.py`, `cmake --build build --target worldserver -j2`, `pixi run dvc status`, `pixi run dvc push` if DVC artifacts changed, then commit the dataset/artifact pointer and docs updates. Mark merge-ready only if all acceptance criteria pass.

## 2026-06-28 Orchestrator Pass 000181

Branch `codex/ml/bt-masked-ga-combined` remains the selected Stonecore ML path: behavior-tree learned scoring plus masked ranker, with GA retained only as an offline helper. No new strategy lane was launched, no worker session was needed, and no C++ runtime control was added; the lane remains offline/shadow-only.

Current status: not merge-ready.

The blocker is unchanged and current as of pass 000181. `dataset/bot_ml/decision_dataset_manifest.json` still contains the fixture-scale dataset: 4 candidate rows, 2 decision rows, and 2 observed-label rows. Acceptance requires real telemetry scale, so this pass does not claim merge readiness.

DB export attempts:

- `pixi run bot-ml-export --database-url mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1 --output-dir dataset/bot_ml/raw`: failed, no route to host. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000181/bot_ml_export_172_20_0_2_lane_r1.log`.
- `pixi run bot-ml-export --database-url mysql://trinity:trinity@127.0.0.1:3306/characters --output-dir dataset/bot_ml/raw`: failed, connection refused. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000181/bot_ml_export_127_0_0_1_characters.log`.

DB availability evidence:

- Docker only showed an unrelated Postgres container. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000181/service_probe_docker.log`.
- `ss -ltnp` showed no local MySQL listener on port 3306. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000181/service_probe_ss.log`.
- Lane configs still point Stonecore r1/r2 characters DBs at `172.20.0.2:3306`.

DVC and validation evidence:

- Main worktree `pixi run dvc status`: clean. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000181/dvc_status_main_initial.log`.
- Combined `.dvc/config.local`: present, gitignored, and byte-equivalent to main DVC local credentials.
- `git worktree list` was recorded for temporary-worktree visibility. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000181/git_worktree_list.log`.
- `pixi run dvc pull dataset/bot_ml/raw.dvc dvc.yaml:bot_ml_build_decisions dvc.yaml:bot_ml_validate dvc.yaml:bt_masked_ga_combined artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r12.dvc`: passed, everything up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000181/dvc_pull_selected.log`.
- `pixi run dvc status dvc.yaml:bot_ml_build_decisions dvc.yaml:bot_ml_validate dvc.yaml:bt_masked_ga_combined`: passed, everything up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000181/dvc_status_selected_after_pull.log`.
- `pixi run dvc status`: still reports broad historical deleted-output state outside the selected combined lane. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000181/dvc_status_combined_initial.log`.
- Focused/full ML tests and `worldserver` build were not rerun in pass 000181 because DB export remained unavailable and the prompt says to stop and write a blocker report when DB access is not available. Latest passing evidence remains pass 000004.
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
- Focused and full ML tests pass: yes in latest pass 000004 evidence; not rerun in pass 000181 due the DB blocker stop condition.
- Dataset has real telemetry scale: no, blocked by unreachable characters DB.
- Server-valid candidate masks are preserved: yes in current fixture metrics.
- Stonecore baseline comparison shows no regression: yes in current fixture metrics.
- `control_eligible=false` and runtime mode remains offline/shadow only: yes.

Next prompt:

Continue `codex/ml/bt-masked-ga-combined` only. Do not launch new strategy lanes. Restore reachable characters DB access for `mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1` or provide the correct characters DB URL, then run `pixi run bot-ml-export --database-url <characters-db-url> --output-dir dataset/bot_ml/raw`, `pixi run dvc repro bot_ml_build_decisions`, `pixi run dvc repro bot_ml_validate`, and `pixi run dvc repro bt_masked_ga_combined`. Confirm `dataset/bot_ml/decision_dataset_manifest.json` is no longer 4 candidate rows / 2 decision rows, inspect the combined metrics and Stonecore comparison, run `pixi run pytest -q tests/test_ml_pipeline.py`, `cmake --build build --target worldserver -j2`, `pixi run dvc status`, `pixi run dvc push` if DVC artifacts changed, then commit the dataset/artifact pointer and docs updates. Mark merge-ready only if all acceptance criteria pass.

## 2026-06-28 Orchestrator Pass 000180

Branch `codex/ml/bt-masked-ga-combined` remains the selected Stonecore ML path: behavior-tree learned scoring plus masked ranker, with GA retained only as an offline helper. No new strategy lane was launched, no worker session was needed, and no C++ runtime control was added; the lane remains offline/shadow-only.

Current status: not merge-ready.

The blocker is unchanged and current as of pass 000180. `dataset/bot_ml/decision_dataset_manifest.json` still contains the fixture-scale dataset: 4 candidate rows, 2 decision rows, and 2 observed-label rows. Acceptance requires real telemetry scale, so this pass does not claim merge readiness.

DB export attempts:

- `pixi run bot-ml-export --database-url mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1 --output-dir dataset/bot_ml/raw`: failed, no route to host. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000180/bot_ml_export_172_20_0_2_lane_r1.log`.
- `pixi run bot-ml-export --database-url mysql://trinity:trinity@127.0.0.1:3306/characters --output-dir dataset/bot_ml/raw`: failed, connection refused. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000180/bot_ml_export_127_0_0_1_characters.log`.

DB availability evidence:

- Docker only showed an unrelated Postgres container. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000180/service_probe_docker.log`.
- `ss -ltnp` showed no local MySQL listener on port 3306. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000180/service_probe_ss.log`.
- Lane configs still point Stonecore r1/r2 characters DBs at `172.20.0.2:3306`.

DVC and validation evidence:

- Main worktree `pixi run dvc status`: clean. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000180/dvc_status_main_initial.log`.
- Combined `.dvc/config.local`: present, gitignored, and byte-equivalent to main DVC local credentials. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000180/dvc_config_local_cmp.log`.
- `git worktree list --porcelain` was recorded for temporary-worktree visibility. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000180/git_worktree_list.log`.
- `pixi run dvc pull bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, everything up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000180/dvc_pull_selected.log`.
- `pixi run dvc status bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, everything up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000180/dvc_status_selected_initial.log`.
- `pixi run dvc status`: still reports broad historical deleted-output state outside the selected combined lane. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000180/dvc_status_combined_broad_initial.log`.
- Focused/full ML tests and `worldserver` build were not rerun in pass 000180 because DB export remained unavailable and the prompt says to stop and write a blocker report when DB access is not available. Latest passing evidence remains pass 000004.
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
- Focused and full ML tests pass: yes in latest pass 000004 evidence; not rerun in pass 000180 due the DB blocker stop condition.
- Dataset has real telemetry scale: no, blocked by unreachable characters DB.
- Server-valid candidate masks are preserved: yes in current fixture metrics.
- Stonecore baseline comparison shows no regression: yes in current fixture metrics.
- `control_eligible=false` and runtime mode remains offline/shadow only: yes.

Next prompt:

Continue `codex/ml/bt-masked-ga-combined` only. Do not launch new strategy lanes. Restore reachable characters DB access for `mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1` or provide the correct characters DB URL, then run `pixi run bot-ml-export --database-url <characters-db-url> --output-dir dataset/bot_ml/raw`, `pixi run dvc repro bot_ml_build_decisions`, `pixi run dvc repro bot_ml_validate`, and `pixi run dvc repro bt_masked_ga_combined`. Confirm `dataset/bot_ml/decision_dataset_manifest.json` is no longer 4 candidate rows / 2 decision rows, inspect the combined metrics and Stonecore comparison, run `pixi run pytest -q tests/test_ml_pipeline.py`, `cmake --build build --target worldserver -j2`, `pixi run dvc status`, `pixi run dvc push` if DVC artifacts changed, then commit the dataset/artifact pointer and docs updates. Mark merge-ready only if all acceptance criteria pass.

## 2026-06-28 Orchestrator Pass 000179

Branch `codex/ml/bt-masked-ga-combined` remains the selected Stonecore ML path: behavior-tree learned scoring plus masked ranker, with GA retained only as an offline helper. No new strategy lane was launched, no worker session was needed, and no C++ runtime control was added; the lane remains offline/shadow-only.

Current status: not merge-ready.

The blocker is unchanged and current as of pass 000179. `dataset/bot_ml/decision_dataset_manifest.json` still contains the fixture-scale dataset: 4 candidate rows, 2 decision rows, and 2 observed-label rows. Acceptance requires real telemetry scale, so this pass does not claim merge readiness.

DB export attempts:

- `pixi run bot-ml-export --database-url mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1 --output-dir dataset/bot_ml/raw`: failed, no route to host. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000179/bot_ml_export_172_20_0_2_lane_r1.log`.
- `pixi run bot-ml-export --database-url mysql://trinity:trinity@127.0.0.1:3306/characters --output-dir dataset/bot_ml/raw`: failed, connection refused. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000179/bot_ml_export_127_0_0_1_characters.log`.

DB availability evidence:

- Docker only showed an unrelated Postgres container. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000179/service_probe_docker.log`.
- `ss -ltnp` showed no local MySQL listener on port 3306. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000179/service_probe_ss.log`.
- Lane configs still point Stonecore r1/r2 characters DBs at `172.20.0.2:3306`.

DVC and validation evidence:

- Main worktree `pixi run dvc status`: clean. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000179/dvc_status_main_initial.log`.
- Combined `.dvc/config.local`: present, gitignored, and equivalent to main DVC credentials. Logs: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000179/dvc_config_main_redacted.log` and `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000179/dvc_config_combined_redacted.log`.
- No stale `generated/orchestrator_worktrees` directory was present inside the combined worktree. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000179/generated_orchestrator_worktrees_combined.log`.
- `pixi run dvc pull bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, everything up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000179/dvc_pull_selected.log`.
- `pixi run dvc status bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, everything up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000179/dvc_status_selected_after_pull.log`.
- `pixi run dvc status`: still reports broad historical deleted-output state outside the selected combined lane. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000179/dvc_status_combined_final.log`.
- Focused/full ML tests and `worldserver` build were not rerun in pass 000179 because DB export remained unavailable and the prompt says to stop and write a blocker report when DB access is not available. Latest passing evidence remains pass 000004.
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
- Focused and full ML tests pass: yes in latest pass 000004 evidence; not rerun in pass 000179 due the DB blocker stop condition.
- Dataset has real telemetry scale: no, blocked by unreachable characters DB.
- Server-valid candidate masks are preserved: yes in current fixture metrics.
- Stonecore baseline comparison shows no regression: yes in current fixture metrics.
- `control_eligible=false` and runtime mode remains offline/shadow only: yes.

Next prompt:

Continue `codex/ml/bt-masked-ga-combined` only. Do not launch new strategy lanes. Restore reachable characters DB access for `mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1` or provide the correct characters DB URL, then run `pixi run bot-ml-export --database-url <characters-db-url> --output-dir dataset/bot_ml/raw`, `pixi run dvc repro bot_ml_build_decisions`, `pixi run dvc repro bot_ml_validate`, and `pixi run dvc repro bt_masked_ga_combined`. Confirm `dataset/bot_ml/decision_dataset_manifest.json` is no longer 4 candidate rows / 2 decision rows, inspect the combined metrics and Stonecore comparison, run `pixi run pytest -q tests/test_ml_pipeline.py`, `cmake --build build --target worldserver -j2`, `pixi run dvc status`, `pixi run dvc push` if DVC artifacts changed, then commit the dataset/artifact pointer and docs updates. Mark merge-ready only if all acceptance criteria pass.

## 2026-06-28 Orchestrator Pass 000178

Branch `codex/ml/bt-masked-ga-combined` remains the selected Stonecore ML path: behavior-tree learned scoring plus masked ranker, with GA retained only as an offline helper. No new strategy lane was launched, no worker session was needed, and no C++ runtime control was added; the lane remains offline/shadow-only.

Current status: not merge-ready.

The blocker is unchanged and current as of pass 000178. `dataset/bot_ml/decision_dataset_manifest.json` still contains the fixture-scale dataset: 4 candidate rows, 2 decision rows, and 2 observed-label rows. Acceptance requires real telemetry scale, so this pass does not claim merge readiness.

DB export attempts:

- `pixi run bot-ml-export --database-url mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1 --output-dir dataset/bot_ml/raw`: failed, no route to host. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000178/bot_ml_export_172_20_0_2_lane_r1.log`.
- `pixi run bot-ml-export --database-url mysql://trinity:trinity@127.0.0.1:3306/characters --output-dir dataset/bot_ml/raw`: failed, connection refused. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000178/bot_ml_export_127_0_0_1_characters.log`.

DB availability evidence:

- Docker only showed an unrelated Postgres container. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000178/service_probe_docker.log`.
- `ss -ltnp` showed no local MySQL listener on port 3306. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000178/service_probe_ss.log`.

DVC and validation evidence:

- Main worktree `pixi run dvc status`: clean. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000178/dvc_status_main_initial.log`.
- Combined `.dvc/config.local`: present, gitignored, and equivalent to main DVC credentials. Logs: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000178/dvc_config_main_redacted.log`, `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000178/dvc_config_combined_redacted.log`, and `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000178/dvc_config_compare_redacted.log`.
- No stale `generated/orchestrator_worktrees` directory was present inside the combined worktree. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000178/generated_orchestrator_worktrees_combined.log`.
- `pixi run dvc pull bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, everything up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000178/dvc_pull_selected.log`.
- `pixi run dvc status bot_ml_build_decisions bot_ml_validate bt_masked_ga_combined`: passed, everything up to date. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000178/dvc_status_selected_after_pull.log`.
- `pixi run dvc status`: still reports broad historical deleted-output state outside the selected combined lane. Log: `/home/runiir/Games/trinity-cata/.codex/plans/orchestrator/instances/ml-discovery-final/runs/000178/dvc_status_combined_final.log`.
- Focused/full ML tests and `worldserver` build were not rerun in pass 000178 because DB export remained unavailable and the prompt says to stop and write a blocker report when DB access is not available. Latest passing evidence remains pass 000004.
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
- Focused and full ML tests pass: yes in latest pass 000004 evidence; not rerun in pass 000178 due the DB blocker stop condition.
- Dataset has real telemetry scale: no, blocked by unreachable characters DB.
- Server-valid candidate masks are preserved: yes in current fixture metrics.
- Stonecore baseline comparison shows no regression: yes in current fixture metrics.
- `control_eligible=false` and runtime mode remains offline/shadow only: yes.

Next prompt:

Continue `codex/ml/bt-masked-ga-combined` only. Do not launch new strategy lanes. Restore reachable characters DB access for `mysql://trinity:trinity@172.20.0.2:3306/characters_lane_stonecore_full_clear_r1` or provide the correct characters DB URL, then run `pixi run bot-ml-export --database-url <characters-db-url> --output-dir dataset/bot_ml/raw`, `pixi run dvc repro bot_ml_build_decisions`, `pixi run dvc repro bot_ml_validate`, and `pixi run dvc repro bt_masked_ga_combined`. Confirm `dataset/bot_ml/decision_dataset_manifest.json` is no longer 4 candidate rows / 2 decision rows, inspect the combined metrics and Stonecore comparison, run `pixi run pytest -q tests/test_ml_pipeline.py`, `cmake --build build --target worldserver -j2`, `pixi run dvc status`, `pixi run dvc push` if DVC artifacts changed, then commit the dataset/artifact pointer and docs updates. Mark merge-ready only if all acceptance criteria pass.

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
