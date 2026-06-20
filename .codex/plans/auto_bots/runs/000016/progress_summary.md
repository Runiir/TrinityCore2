# Run 000016 Progress Summary

## Scope

- Continued from run 000015 / commit `4e1b01a6b5`.
- Focused on the Stonecore 5N route step 1 blocker for `01_entrance_packs`, route node `bafdc27f1d35bc27`.
- No worker or reviewer Codex sessions were launched; this pass was handled directly by the orchestrator, so no worker tier was selected.

## Implementation

- Added post-progress trash-route terminalization for repeated route-anchor / prerequisite loops near the configured route anchor.
- Reused route terminalization for the existing no-target-after-progress path so all cohort members clear focus, targets, anchor overrides, and route progress state consistently.
- Added `dungeon_trash_cleared` and `validation_route_recovery` evidence with reason `route_loop_exhausted_after_progress` when a trash route has local kill progress and repeats near the anchor.
- Added `.botauto diagnose` classification `validation_route_terminal` so repeated `validation_route_complete` terminal holds report as info-level completed-route state rather than `repeated_decision_loop`.
- Extended the autonomy smoke contract test to cover the new terminal evidence and diagnosis surface.

## Validation

- `cmake --build build --target worldserver -j2`
  - Passed.
- `pixi run pytest tests/test_autonomy_pipeline_smoke.py tests/test_ml_pipeline.py -q`
  - Passed: `165 passed, 1 warning`.

### Live Stonecore Evidence

1. `artifacts/live_validation_instances/stonecore_entrance_route_loop_terminal_r1/report.json`
   - Fixed-window 300s observed run using deterministic Stonecore provisioning/reset.
   - `completion_reason`: `incomplete_evidence`
   - `failure_labels`: `[]`
   - counters: `kills=1`, `trash_pulls=1`, `dungeon_trash_cleared=1`, `validation_route_actions=94`, `stuck_events=14`, `unstuck_failures=0`
   - Confirmed `route_loop_exhausted_after_progress` and terminal `validation_route_complete` behavior, but diagnosis still reported `repeated_decision_loop` before the diagnosis fix.

2. `artifacts/live_validation_instances/stonecore_entrance_route_loop_terminal_diag_r1/report.json`
   - Fixed-window 300s observed rerun after the diagnosis fix.
   - `completion_reason`: `incomplete_evidence`
   - `failure_labels`: `[]`
   - `final_evidence_rejections`: `not_all_stages_passed`, `segment_or_route_context_is_debug_only`
   - counters: `kills=1`, `trash_pulls=1`, `dungeon_trash_cleared=1`, `validation_route_actions=87`, `stuck_events=18`, `unstuck_failures=0`
   - diagnosis: `validation_route_terminal=5`, severity `info=5`; watchdog `repeated_decision_loop=false`, `no_progress=false`, `death_loop=false`.
   - This is useful segment/debug evidence, not final Stonecore clear evidence.

## DVC

- DVC-added generated validation artifact directories:
  - `artifacts/live_validation_instances/stonecore_entrance_route_loop_terminal_r1.dvc`
  - `artifacts/live_validation_instances/stonecore_entrance_route_loop_terminal_diag_r1.dvc`
- `dvc status` still reports stale `live_scenario_reports` and `live_validation_combined` deps because `tools/bot_ml/run_live_bot_validation.py` changed in the prior run; this pass did not rebuild those aggregate pipeline stages.

## Next Handoff Prompt

Continue from run 000016. Current code adds post-progress Stonecore trash-route terminalization and `validation_route_terminal` diagnosis. Validation passed for `cmake --build build --target worldserver -j2` and `pixi run pytest tests/test_autonomy_pipeline_smoke.py tests/test_ml_pipeline.py -q`.

New DVC-tracked artifacts:

- `artifacts/live_validation_instances/stonecore_entrance_route_loop_terminal_r1/report.json`: 300s fixed-window entrance route run; `failure_labels=[]`, `kills=1`, `trash_pulls=1`, `dungeon_trash_cleared=1`, `validation_route_actions=94`, `stuck_events=14`, `unstuck_failures=0`; terminal event works but pre-diagnosis-fix report still showed `repeated_decision_loop` warnings.
- `artifacts/live_validation_instances/stonecore_entrance_route_loop_terminal_diag_r1/report.json`: 300s fixed-window rerun after diagnosis fix; `failure_labels=[]`, `kills=1`, `trash_pulls=1`, `dungeon_trash_cleared=1`, `validation_route_actions=87`, `stuck_events=18`, `unstuck_failures=0`, diagnosis `validation_route_terminal=5`, severity `info=5`, watchdog `repeated_decision_loop=false`; still `completion_reason=incomplete_evidence` because this is route segment/debug evidence, not a full scenario clear.

Next likely fix: terminalization now stops the entrance route loop cleanly, but it still terminates after one route-local kill and remains debug-only segment evidence. Promote the route runner from terminal hold to segment advance/full-scenario orchestration: when `validation_route_terminal` is reached for `01_entrance_packs`, the validator or route executor should advance to the next Stonecore route node instead of holding `validation_route_complete` for the rest of the 300s window. Then rerun the full `stonecore_5n` scenario with `--observe-sec 300 --timeout-sec 900`; if the route advances through trash and boss segments without failure labels, update the checklist for normal dungeon trash/dungeon boss/full Stonecore evidence.
