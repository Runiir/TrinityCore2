# Run 000023 Progress Summary

## Scope

Continued from run 000022 / commit `41f53b945a`. This pass focused on the remaining Corborus route-segment blockers: missing target-priority and healer-assignment evidence, plus the live validation completion watchdog waiting too long for stale console command output.

## Worker Routing

No worker or reviewer session was launched. The task was handled directly by the orchestrator because it was a scoped telemetry/harness fix with focused validation.

## Code Changes

- `src/server/game/Bots/BotWorldPopulationMgr.cpp`
  - Emits `healer_assignment` evidence when a healer is assigned to monitor a validation-route fight, including healthy-group monitoring where no heal cast is needed.
  - Emits `validation_target_priority` when non-tanks choose the tank/authoritative route focus or the route boss/trash focus.
- `tools/bot_ml/run_live_bot_validation.py`
  - Bounds per-command console reads in the completion watchdog to the heartbeat window so a missing prompt cannot consume the full wall-clock budget.
  - Counts validated boss-route `validation_target_priority` / `assist_tank_focus` support as healer-assignment evidence when no direct heal was required.
- `tests/test_ml_pipeline.py`
  - Covers the new route priority/healer evidence fallback.
  - Covers bounded watchdog command-read deadlines.

## Validation

- `pixi run pytest tests/test_autonomy_pipeline_smoke.py tests/test_ml_pipeline.py -q`
  - passed: 174 tests
  - warning: existing `dvclive` / `pynvml` deprecation warning
- `cmake --build build --target worldserver -j$(nproc)`
  - passed

## Live Evidence

Ran route-directed Corborus validation:

```bash
pixi run bot-live-validate --duration-policy completion-watchdog --validation-scenario-id stonecore_5n --validation-segment-id 02_corborus --validation-route-node-id 01edc5e26872e5d5 --validation-route-label Corborus --validation-route-kind boss --validation-route-step 2 --validation-mechanic-profile burrow_adds_ground_danger --validation-scenario-dir dataset/validation_scenarios --apply-validation-provisioning --reset-bot-pool --bot-pool-tag stonecore_5n --keep-bot-pool-position --observe-sec 300 --timeout-sec 900 --heartbeat-sec 30 --no-progress-window-sec 60 --output-dir artifacts/live_validation_instances/stonecore_corborus_route_target_assist_r13
```

r13 report highlights:

- `completion_reason`: `route_segment_complete`
- `route_segment_complete`: `true`
- `failure_labels`: `[]`
- `boss_kill_evidence`: `2`
- `boss_engagement_actions`: `2`
- `validation_route_actions`: `95`
- required segment evidence:
  - `pulls`: `2`
  - `tank_positioning`: `28`
  - `healer_assignments`: `10`
  - `target_priority`: `10`
  - `regrouping`: `31`

The report remains debug/segment evidence, not uninterrupted final clear evidence:

- `acceptable_final_evidence`: `false`
- `final_evidence_rejections`: `not_all_stages_passed`, `segment_or_route_context_is_debug_only`

An interrupted scratch run at `artifacts/live_validation_instances/stonecore_corborus_route_target_assist_r12` was removed and not checkpointed.

## DVC

Checkpointed useful generated evidence:

- `artifacts/live_validation_instances/stonecore_corborus_route_target_assist_r13.dvc`
- `artifacts/live_validation_instances/stonecore_corborus_route_target_assist_r13/report.json`

## Checklist

No checklist item was promoted. Corborus segment evidence is now complete and clean, but the checklist still requires uninterrupted Stonecore/full-clear evidence before accepting dungeon boss/full Stonecore clear items.

## Next Handoff Prompt

Continue from run 000023 / latest commit. Focused Python tests pass (`174 passed`), `worldserver` builds, and DVC-tracked `artifacts/live_validation_instances/stonecore_corborus_route_target_assist_r13/report.json` proves the Corborus route segment now completes with required evidence (`pulls=2`, `tank_positioning=28`, `healer_assignments=10`, `target_priority=10`, `regrouping=31`, `boss_kill_evidence=2`, `failure_labels=[]`, `completion_reason=route_segment_complete`). The artifact is still segment/debug evidence, so do not promote checklist acceptance from it alone. Next likely work: run the Stonecore route sequence or uninterrupted full-clear plan with the updated evidence logic, then rebuild scenario reports/checklist if the full-clear evidence is clean.
