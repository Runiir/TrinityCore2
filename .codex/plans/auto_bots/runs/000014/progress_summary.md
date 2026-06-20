# Run 000014 Progress Summary

## Scope

- Continued from run 000013 / commit `1651062560`.
- Focused on Stonecore 5N route step 1, `01_entrance_packs`, route node `bafdc27f1d35bc27`.
- No worker/reviewer Codex sessions were launched; this pass was handled directly by the orchestrator, so no worker tier was selected.

## Repository Inspection

- Starting git status snapshot was clean.
- Checklist still has 9 accepted gates and blocks on Stonecore/BWD live evidence.
- Previous failing artifact: `artifacts/live_validation_instances/stonecore_entrance_active_combat_anchor_guard_r1/report.json`.
- Previous failure signature: `validation_route_stuck_loop`, 4 kills, repeated `move_to_validation_route_anchor` / `follow_anchor_no_focus` around route destination `920.382,963.89,316.865`.

## Attempted Fix

- Tested an experimental C++ change in `BotWorldPopulationMgr::TryValidationRouteObjective` to:
  - search generic route blockers when the configured Stonecore entrance source-entry target was missing,
  - emit trash-completion evidence after prior route kills when no route target remained,
  - then tighten missing-blocker no-progress recovery.
- Both validation attempts failed and the final evidence was worse than the run 000013 baseline, so the experimental C++ changes were removed before exit.
- Source tree was restored to the pre-pass state; no failed C++ code was kept.

## Validation

- `pixi run pytest tests/test_ml_pipeline.py -q`
  - Passed: `150 passed, 1 warning`.
- `cmake --build build --target worldserver -j2`
  - Passed before both live validation attempts.

### Failed Live Validation Artifacts

1. `artifacts/live_validation_instances/stonecore_entrance_missing_target_blocker_r1/report.json`
   - `completion_reason`: `machine_failure_predicate`
   - `failure_labels`: `["validation_route_stuck_loop"]`
   - final counters: `kills=1`, `trash_pulls=0`, `stuck_events=14`, `repath_events=0`, `validation_route_actions=18`
   - result: blocker search shifted the loop from anchor-only toward `move_to_validation_route_assist_target`, but did not preserve trash progress.

2. `artifacts/live_validation_instances/stonecore_entrance_missing_blocker_recovery_r1/report.json`
   - `completion_reason`: `machine_failure_predicate`
   - `failure_labels`: `["validation_route_stuck_loop"]`
   - final counters: `kills=1`, `trash_pulls=0`, `stuck_events=30`, `repath_events=4`, `validation_route_actions=16`
   - final diagnosis: `stuck_repath_loop`, `current_action=unstuck`, `last_recovery_result=fallback_unavailable`
   - trace shows repeated `validation_route_stuck_follow_anchor` at canonical route destination `903.255,985.352,317.198`, target churn around target IDs `9`, `14`, and anchor `1262`.

## DVC

- DVC-added generated artifact directories:
  - `artifacts/live_validation_instances/stonecore_entrance_missing_target_blocker_r1.dvc`
  - `artifacts/live_validation_instances/stonecore_entrance_missing_blocker_recovery_r1.dvc`

## Next Handoff Prompt

Continue from run 000014. The attempted generic missing-route-target blocker search was reverted because both long Stonecore entrance validations regressed versus run 000013. New evidence is DVC-tracked:

- `artifacts/live_validation_instances/stonecore_entrance_missing_target_blocker_r1/report.json`: failed `validation_route_stuck_loop`, `kills=1`, `trash_pulls=0`, `stuck_events=14`, `validation_route_actions=18`.
- `artifacts/live_validation_instances/stonecore_entrance_missing_blocker_recovery_r1/report.json`: failed `validation_route_stuck_loop`, `kills=1`, `trash_pulls=0`, `stuck_events=30`, `repath_events=4`, final diagnosis `stuck_repath_loop`, `current_action=unstuck`, `last_recovery_result=fallback_unavailable`.

Do not reapply the reverted generic blocker-search approach as-is. The remaining evidence points to a lower-level route recovery/pathing issue: after the route returns to the canonical Stonecore entrance anchor `903.255,985.352,317.198`, followers/tank recovery can repeatedly issue `validation_route_stuck_follow_anchor` or failed unstuck around anchor `1262` while target IDs `9`/`14` remain in traces. Next likely fix: change validation-route stuck recovery so a bot already near the canonical route anchor does not follow the tank anchor again; instead clear stale tank/focus state, force the tank to reacquire a reachable combat target from a canonical-anchor-centered search, and if no reachable target exists after prior real kills, mark the segment as exhausted with a non-repeating terminal route state. Add a per-route terminal/exhausted state to avoid repeated `dungeon_trash_cleared`/anchor decisions causing loop guardrails. Rerun the same long route-directed Stonecore entrance validation with `--observe-sec 300 --timeout-sec 900` before trying full Stonecore.
