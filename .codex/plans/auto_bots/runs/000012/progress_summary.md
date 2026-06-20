# Auto Bots Run 000012

## Scope

Continued from pass 000011 on Stonecore entrance route progression after recovered trash kill evidence. No worker or reviewer sessions were launched; the task was handled directly by the orchestrator because the changes were scoped to validation-route focus selection/cleanup.

## Code Changes

- Added validation-route cleanup for killed route focus targets in `BotWorldPopulationMgr::TryValidationRouteObjective`.
- Cleared matching cohort `TargetGuid`, combat progress target, pack progress target, and last decision target when a route recovery kill or boss kill is confirmed.
- Tightened tank/authoritative focus selection so non-tanks do not treat a cohort's saved `TargetGuid` as an assist focus unless the owning member or target has active combat/victim evidence.
- Added source smoke assertions for the killed-focus cleanup and active-cohort-focus guard.

## Validation

- `pixi run pytest tests/test_autonomy_pipeline_smoke.py -q`
  - Passed: 14 tests.
- `pixi run pytest tests/test_ml_pipeline.py -q -k 'route_mob_killed or trace_mob_killed or stuck_heavy_trash_route'`
  - Passed: 3 tests, 147 deselected.
- `cmake --build build --target worldserver -j"$(nproc)"`
  - Passed after each C++ change.
- Live Stonecore entrance validation, first fix:
  - Command output directory: `artifacts/live_validation_instances/stonecore_entrance_focus_cleanup_r1`
  - Final report: `artifacts/live_validation_instances/stonecore_entrance_focus_cleanup_r1/report.json`
  - Result: failed with `failure_labels=["validation_route_stuck_loop"]`.
  - Evidence: recovery kill recorded (`kills=1`), no final pull evidence (`trash_pulls=0` in final window), `validation_route_actions=18`, `stuck_events=14`.
- Live Stonecore entrance validation, active focus guard:
  - Command output directory: `artifacts/live_validation_instances/stonecore_entrance_active_focus_guard_r1`
  - Final report: `artifacts/live_validation_instances/stonecore_entrance_active_focus_guard_r1/report.json`
  - Result: failed with `failure_labels=["validation_route_stuck_loop"]`.
  - Evidence: recovery kill recorded (`kills=1`), no final pull evidence (`trash_pulls=0` in final window), `validation_route_actions=18`, `stuck_events=28`, diagnosis `repeated_decision_loop`, current action `move_to_validation_route_anchor`.

## Outcome

The stale killed-focus cleanup is useful and compile/test validated, but it does not complete the Stonecore entrance route. The remaining blocker is route behavior after the recovery kill: bots alternate between prerequisite assist/focus records and anchor regrouping, then hit repeated-decision/stuck guardrails without advancing to a new pull.

## Next Handoff Prompt

Continue from run 000012. Commit includes validation-route killed-focus cleanup and active-cohort-focus guards, but Stonecore entrance still fails after the recovered kill. Fresh artifacts:

- `artifacts/live_validation_instances/stonecore_entrance_focus_cleanup_r1/report.json`: `failure_labels=["validation_route_stuck_loop"]`, `kills=1`, final-window `trash_pulls=0`, `validation_route_actions=18`, `stuck_events=14`.
- `artifacts/live_validation_instances/stonecore_entrance_active_focus_guard_r1/report.json`: `failure_labels=["validation_route_stuck_loop"]`, diagnosis `repeated_decision_loop`, current action `move_to_validation_route_anchor`, `kills=1`, final-window `trash_pulls=0`, `validation_route_actions=18`, `stuck_events=28`.

Inspect the active-focus-guard trace around target IDs 20 and 45 and the safe-memory override (`validation_route_safe_memory_after_danger`). The likely remaining fix is not parser-level: after `mob_killed` recovery, route advancement must either mark the killed/prerequisite pack complete and search the next route target/pack from the tank, or temporarily blacklist the repeated anchor/focus target so the tank does not keep dragging the group into `follow_anchor_no_focus` / `move_to_validation_route_anchor` loops. Rerun the Stonecore entrance route with the long budget before proceeding to segment/full-clear validation.
