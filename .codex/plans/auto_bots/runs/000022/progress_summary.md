# Run 000022 Progress Summary

## Scope

Continued Stonecore Corborus route validation from run 000021 / commit 40509c5475. The pass focused on preserving boss-route focus after activation fallback and preventing report evidence from losing earlier boss engagement when `.botauto trace` windows roll forward.

## Worker Routing

- `worker_focus_lifecycle`
  - complexity: medium
  - model: gpt-5.5
  - reasoning effort: medium
  - role: inspection worker only
  - artifacts:
    - `.codex/plans/auto_bots/runs/000022/worker_focus_lifecycle_prompt.md`
    - `.codex/plans/auto_bots/runs/000022/worker_focus_lifecycle.jsonl`
    - `.codex/plans/auto_bots/runs/000022/worker_focus_lifecycle.stderr`
    - `.codex/plans/auto_bots/runs/000022/worker_focus_lifecycle.last_message.md`

## Code Changes

- `src/server/game/Bots/BotWorldPopulationMgr.cpp`
  - `tryValidationRouteActivation` now persists the activated boss target through `rememberValidationRouteFocus`.
  - The activating bot now seeds `state.TargetGuid` from the activation target.
  - Authoritative focus recovery accepts the configured boss `ValidationRouteTargetEntry` after route activation if the remembered exact focus GUID cannot be resolved.
  - Near-anchor stuck recovery now follows the remembered boss focus instead of clearing it for boss validation routes.
- `tools/bot_ml/run_live_bot_validation.py`
  - Aggregates trace evidence across heartbeat windows with deduplication for sequenced rows, preserving boss engagement that rolled out of the final trace window.
  - Counts `move_to_validation_route_assist_target` and `assist_tank_focus` as tank-positioning evidence.
- Tests updated in:
  - `tests/test_autonomy_pipeline_smoke.py`
  - `tests/test_ml_pipeline.py`

## Validation

- `pixi run pytest tests/test_autonomy_pipeline_smoke.py tests/test_ml_pipeline.py -q`
  - passed: 172 tests
  - warning: existing `dvclive`/`pynvml` deprecation warning
- `cmake --build build --target worldserver -j$(nproc)`
  - passed

## Live Evidence

Ran route-directed Corborus validation:

```bash
pixi run bot-live-validate --duration-policy completion-watchdog --validation-scenario-id stonecore_5n --validation-segment-id 02_corborus --validation-route-node-id 01edc5e26872e5d5 --validation-route-label Corborus --validation-route-kind boss --validation-route-step 2 --validation-mechanic-profile burrow_adds_ground_danger --validation-scenario-dir dataset/validation_scenarios --apply-validation-provisioning --reset-bot-pool --bot-pool-tag stonecore_5n --keep-bot-pool-position --observe-sec 300 --timeout-sec 900 --heartbeat-sec 30 --no-progress-window-sec 60 --output-dir artifacts/live_validation_instances/stonecore_corborus_route_target_assist_r11
```

The harness wrote `artifacts/live_validation_instances/stonecore_corborus_route_target_assist_r11/report.json`, then the PTY wrapper was interrupted after `ps` showed no `worldserver` / validation child process but the console read loop was still waiting.

r11 report highlights:

- `heartbeat_index`: 2
- `failure_labels`: []
- `boss_kill_evidence`: 2
- `boss_engagement_actions`: 2
- `action_counts.boss_killed`: 2
- `action_counts.boss_started`: 1
- `action_counts.boss_action`: 1
- `action_counts.validation_route_boss_action`: 1
- `action_counts.move_to_validation_route_assist_target`: 9
- `result_counts.assist_tank_focus`: 9
- `result_counts.follow_last_known_tank_focus`: 3
- `result_counts.follow_anchor_last_known_tank_focus`: 2

This is stronger than r10: boss engagement and kill evidence are retained in the final report, and the new focus-follow paths are visible. It is not checklist-acceptable final evidence yet because the segment contract still lacks healer-assignment and target-priority evidence, and the interrupted harness did not produce a clean final process exit.

## DVC

- Added and pushed:
  - `artifacts/live_validation_instances/stonecore_corborus_route_target_assist_r11.dvc`
- `dvc push artifacts/live_validation_instances/stonecore_corborus_route_target_assist_r11.dvc`: pushed 4 files.
- `dvc status` still reports the known stale aggregate stages:
  - `live_scenario_reports`
  - `validation_run_plan`
  - `live_validation_combined`

## Checklist

No checklist item was promoted. Stonecore boss/clear evidence is improved but still does not satisfy accepted uninterrupted segment/full-clear evidence.

## Next Handoff Prompt

Continue from run 000022 / latest commit. Focused smoke+ML tests pass and `worldserver` builds. Inspect DVC-tracked artifact `artifacts/live_validation_instances/stonecore_corborus_route_target_assist_r11/report.json`: r11 now preserves Corborus boss engagement and kill evidence (`boss_kill_evidence=2`, `boss_engagement_actions=2`, `boss_killed=2`) and shows focus-follow behavior (`move_to_validation_route_focus`, `follow_last_known_tank_focus`, `assist_tank_focus`). The segment still is not accepted because healer-assignment and target-priority evidence remain missing, and the live validation harness can hang waiting for command output after the worldserver child is gone. Next likely work: add generic boss-route healer/target-priority evidence from actual group behavior or validated teacher-assist actions, harden `run_worldserver_completion_watchdog` so stale console reads exit cleanly when the process disappears, then rerun Corborus with the same route-directed long budget. Only update checklist acceptance after clean Stonecore segment/full-clear evidence proves required evidence and uninterrupted completion.
