# Run 000015 Progress Summary

## Scope

- Continued from run 000014 / commit `8e6032acf6`.
- Focused on the Stonecore 5N route step 1 blocker for `01_entrance_packs`, route node `bafdc27f1d35bc27`.
- No worker or reviewer Codex sessions were launched; this pass was handled directly by the orchestrator, so no worker tier was selected.

## Implementation

- Added validation-route terminal state to `WorldBotState` so a trash route can stop repeating after route-local progress is exhausted.
- Changed validation-route stuck recovery so a bot already near the canonical route anchor does not follow a party/tank anchor again; it clears stale route focus/targets and records `validation_route_stuck_anchor_focus_reset`.
- Added a tank-only canonical-anchor reacquire search for reachable trash targets near the configured route anchor before declaring the route exhausted.
- Extended `tools/bot_ml/run_live_bot_validation.py` so route-directed trash validations count status/summary kills as trash pull evidence when the recent trace window has rolled off the `mob_killed` event.
- Added regression coverage for route summary kills counted as trash engagement.

## Validation

- `cmake --build build --target worldserver -j2`
  - Passed.
- `pixi run pytest tests/test_ml_pipeline.py -q`
  - Passed: `151 passed, 1 warning`.

### Live Stonecore Evidence

1. `artifacts/live_validation_instances/stonecore_entrance_anchor_terminal_r1/report.json`
   - Completion-watchdog attempt stopped manually after the runner had written a partial report because it had no failure predicate and would otherwise continue toward the emergency cap.
   - `completion_reason`: `incomplete_evidence`
   - `failure_labels`: `[]`
   - counters: `kills=4`, `trash_pulls=0` before the parser fix, `validation_route_actions=17`, `stuck_events=8`, `unstuck_failures=0`, `repath_events=1`
   - Compared with run 000014, this removed `validation_route_stuck_loop` and improved kill progress, but the report did not yet count route kills as trash evidence.

2. `artifacts/live_validation_instances/stonecore_entrance_anchor_terminal_fixed_r1/report.json`
   - Fixed-window 300s observed route run using the same provisioning/reset/route flags.
   - `completion_reason`: `incomplete_evidence`
   - `failure_labels`: `[]`
   - `final_evidence_rejections`: `not_all_stages_passed`, `segment_or_route_context_is_debug_only`
   - counters: `kills=1`, `trash_pulls=1`, `validation_route_actions=83`, `stuck_events=16`, `unstuck_failures=0`, `repath_events=3`, `validation_route_prerequisite_repeats=29`
   - This is useful segment evidence, not final Stonecore clear evidence. It shows the previous hard `validation_route_stuck_loop` failure is gone and route trash progress is now visible to the validator, but the segment still needs better completion/exit behavior before full Stonecore.

## DVC

- DVC-added generated validation artifact directories:
  - `artifacts/live_validation_instances/stonecore_entrance_anchor_terminal_r1.dvc`
  - `artifacts/live_validation_instances/stonecore_entrance_anchor_terminal_fixed_r1.dvc`

## Next Handoff Prompt

Continue from run 000015. The previous run 000014 `validation_route_stuck_loop` blocker improved but is not fully solved. Current code adds route-anchor focus reset, tank-only canonical-anchor target reacquisition, per-route terminal state, and parser support for counting route-directed trash kills from status/summary when trace `mob_killed` rolls off. Validation passed for `cmake --build build --target worldserver -j2` and `pixi run pytest tests/test_ml_pipeline.py -q`.

New DVC-tracked artifacts:

- `artifacts/live_validation_instances/stonecore_entrance_anchor_terminal_r1/report.json`: partial completion-watchdog attempt, manually interrupted after report write; `failure_labels=[]`, `kills=4`, `validation_route_actions=17`, `stuck_events=8`, `unstuck_failures=0`, but `trash_pulls=0` before the parser fix.
- `artifacts/live_validation_instances/stonecore_entrance_anchor_terminal_fixed_r1/report.json`: fixed 300s route window; `failure_labels=[]`, `kills=1`, `trash_pulls=1`, `validation_route_actions=83`, `stuck_events=16`, `unstuck_failures=0`, `repath_events=3`, `validation_route_prerequisite_repeats=29`; still `completion_reason=incomplete_evidence` because it is segment/debug evidence, not a full clear.

Next likely fix: the tank is now reacquiring target entry `43430` near the Stonecore entrance, but the route remains in repeated `validation_route_prerequisite`/assist behavior against target IDs `9`/`14` and can end in repeated-decision guardrail instead of a clean segment terminal. Tighten trash-route completion so killed/reacquired prerequisite packs produce explicit `trash_action`/`dungeon_trash_cleared` evidence and transition followers out of `move_to_validation_route_anchor`/`follow_anchor_no_focus` once the tank has no reachable target and route-local kill progress exists. Then rerun `01_entrance_packs` with `--observe-sec 300 --timeout-sec 900`; if it remains free of failure labels and exits with clean segment evidence, proceed to the full `stonecore_5n` scenario.
