# Run 000021 Progress Summary

## Scope

Continued from run 000020 / commit `b343719d31`. Launched one inspection worker:

- `worker_inspect_corborus_activation`
  - Complexity: medium
  - Model: `gpt-5.5`
  - Reasoning effort: medium
  - Prompt: `.codex/plans/auto_bots/runs/000021/worker_inspect_corborus_activation.prompt.md`
  - Result: completed, no file edits. The worker identified that the activation latch is global while diagnosis fields are per-bot and only synced inside `tryValidationRouteActivation`.

## Changes

- Extended `.botauto diagnose` evidence with validation-route config and activation gate state:
  - config kind, target entry, activation data id, spawn/action/summon entries, opener summon entry
  - computed `validation_route_has_activation`
  - global manager activation applied/attempt counts
  - current distance to the validation route anchor
- Updated the boss no-focus branch to sync the global activation latch back into the current bot state and record `boss_route_no_focus_activation_already_applied` before continuing to anchor movement/hold logic.
- Broadened the data-driven target-entry activation fallback so configured `ValidationRoute.TargetEntry` can be summoned when the configured activation mechanisms apply but do not produce a visible target object.
- Extended `tests/test_autonomy_pipeline_smoke.py` coverage for the new diagnosis fields, already-applied telemetry, and broader target-entry fallback.

## Validation

- `pixi run pytest tests/test_autonomy_pipeline_smoke.py -q`: 14 passed.
- `pixi run pytest tests/test_ml_pipeline.py -q`: 156 passed, 1 `dvclive`/`pynvml` warning.
- `cmake --build build --target worldserver -j2`: passed after C++ edits.
- Live Corborus reruns used route node `01edc5e26872e5d5` with `--observe-sec 300 --timeout-sec 900`. The runner wrote reports but then hung waiting for console prompt output; stale PTY reads were interrupted after confirming no `worldserver` or validation process remained.

### Live Evidence

- `artifacts/live_validation_instances/stonecore_corborus_route_target_assist_r9/report.json`
  - `completion_reason=incomplete_evidence`
  - `validation_route_activation_attempts=1`
  - diagnosis confirms `validation_route_config_kind=boss`, `validation_route_config_target_entry=43438`, `validation_route_config_activation_data_id=10`, `validation_route_has_activation=true`, `validation_route_manager_activation_applied=true`, `validation_route_manager_activation_attempts=1`
  - final report still has `boss_engagement_actions=0`, `boss_kill_evidence=0`
- `artifacts/live_validation_instances/stonecore_corborus_route_target_assist_r10/report.json`
  - `completion_reason=incomplete_evidence`
  - final report has `validation_route_activation_attempts=1`, `kills=3`, `boss_engagement_actions=0`, `boss_kill_evidence=0`
  - heartbeat 2 showed transient improvement: `boss_engagement_actions=2`, `kills=3`, and no failure labels
  - later heartbeats/final trace regressed to repeated `boss_route_no_focus_activation_already_applied` and `validation_route_hold_anchor` with no boss kill evidence

## Current Blocker

The config overlay and activation gate are no longer the blocker: live diagnosis proves the Corborus route config is present and the global activation latch is applied. The broader target-entry fallback produced at least transient boss engagement in r10 heartbeat 2, but the final report still loses boss focus and records no boss kill evidence. The next likely fix is to persist/recover the configured boss focus after activation/target-entry fallback: when `_validationRouteActivationApplied` is true and the configured target entry was summoned or briefly engaged, store it as authoritative route focus and make non-tank followers assist it instead of returning to hold-anchor no-focus. Also inspect whether `recordValidationRouteBossKill` is missing the target because the final trace window drops earlier `boss_action` events.

## DVC

- Added DVC metadata for:
  - `artifacts/live_validation_instances/stonecore_corborus_route_target_assist_r9.dvc`
  - `artifacts/live_validation_instances/stonecore_corborus_route_target_assist_r10.dvc`
- `dvc status` was run and still reports the known stale aggregate stages:
  - `live_scenario_reports`
  - `validation_run_plan`
  - `live_validation_combined`
- `dvc push artifacts/live_validation_instances/stonecore_corborus_route_target_assist_r9.dvc artifacts/live_validation_instances/stonecore_corborus_route_target_assist_r10.dvc`: 13 files pushed.

## Next Handoff Prompt

Continue from run 000021 / the latest commit containing this progress summary. Focused smoke and ML pytest suites pass, and `worldserver` builds. Inspect DVC-tracked artifacts `artifacts/live_validation_instances/stonecore_corborus_route_target_assist_r9/report.json` and `artifacts/live_validation_instances/stonecore_corborus_route_target_assist_r10/report.json`. r9 proves runtime validation route config hydration and global activation state: kind boss, target entry 43438, activation data id 10, has activation true, manager activation applied true, attempts 1. r10 broadens target-entry fallback and heartbeat 2 briefly records `boss_engagement_actions=2` and `kills=3`, but the final report still ends incomplete with `boss_kill_evidence=0` and repeated `boss_route_no_focus_activation_already_applied` / hold-anchor no-focus. Next likely fix: persist the configured boss target/focus after activation fallback and make followers assist that authoritative focus instead of returning to anchor hold; also inspect whether final report evidence aggregation loses earlier heartbeat boss engagement due trace-window truncation. Only update checklist acceptance after valid Stonecore segment/full-clear evidence proves boss engagement and kill/clear completion.
