# Run 000017 Progress Summary

## Scope

- Continued from run 000016 / commit `7376b56c7e`.
- Focused on promoting Stonecore validation-route terminal state into scenario-level route advancement.
- No worker or reviewer Codex sessions were launched. The change was handled directly by the orchestrator, so no worker complexity/model tier was selected.

## Implementation

- Added a route-segment completion predicate to `tools/bot_ml/run_live_bot_validation.py`.
  - Segment completion now requires no failure labels, validation-route action evidence, route-required evidence, and trash/boss-specific progress.
  - Completed route segments return process status 0 even though they remain rejected as final-clear evidence.
- Added `--validation-route-sequence` to `bot-live-validate`.
  - Scenario-level route sequence runs executable manifest routes in route-step order.
  - Each child route writes its own JSON report, stdout/stderr logs, and heartbeat evidence under the route output directory.
  - Sequence reports preserve the safety rule that route-segment evidence is not an uninterrupted full clear.
- Updated `tools/bot_ml/build_validation_run_plan.py` so full scenario commands use `--validation-route-sequence` instead of binding the full scenario run to the first route node.
- Fixed the completion watchdog progress timer so no-progress windows reset only when progress increases, not when sliding trace-window counters merely change.

## Validation

- `pixi run pytest tests/test_ml_pipeline.py -q`
  - Passed: `153 passed, 1 warning`.
- `pixi run pytest tests/test_autonomy_pipeline_smoke.py -q`
  - Passed: `14 passed`.
- `cmake --build build --target worldserver -j2`
  - Passed.
- `pixi run bot-live-validate --dry-run --validation-route-sequence --validation-scenario-id stonecore_5n --validation-scenario-dir dataset/validation_scenarios --output-dir .codex/plans/auto_bots/runs/000017/stonecore_route_sequence_dryrun`
  - Passed and produced eight ordered Stonecore route child commands.

## Live Stonecore Evidence

- DVC-tracked artifact: `artifacts/live_validation_instances/stonecore_route_sequence_r3.dvc`
- Aggregate report: `artifacts/live_validation_instances/stonecore_route_sequence_r3/report.json`
  - `completion_reason`: `route_sequence_incomplete`
  - `failure_labels`: `["validation_route_no_engagement", "no_progress_observed", "route_sequence_child_failed"]`
  - complete segments: `["01_entrance_packs"]`
  - failed command: `02_corborus`, route node `01edc5e26872e5d5`
  - aggregate counters: `trash_pulls=4`, `validation_route_actions=22`, `boss_kill_evidence=0`
- Segment report: `artifacts/live_validation_instances/stonecore_route_sequence_r3/01_entrance_packs/report.json`
  - `completion_reason`: `route_segment_complete`
  - `route_segment_complete`: `true`
  - `failure_labels`: `[]`
  - counters: `trash_pulls=4`, `validation_route_actions=6`, `stuck_events=0`
  - required route evidence: `pulls=4`
- Segment blocker: `artifacts/live_validation_instances/stonecore_route_sequence_r3/02_corborus/report.json`
  - `completion_reason`: `no_progress_watchdog`
  - `failure_labels`: `["validation_route_no_engagement", "no_progress_observed"]`
  - counters: `boss_kill_evidence=0`, `trash_pulls=0`, `validation_route_actions=16`, `stuck_events=0`
  - evidence: `regrouping=16`, `pulls=0`, `tank_positioning=0`, `healer_assignments=0`, `target_priority=0`
  - action/results show repeated anchor holding near Corborus: `validation_route_hold_anchor=7`, `validation_route_regroup=9`, `hold_anchor_no_focus=9`, `repeated_decision_loop=2`.

## Checklist

- No checklist item was promoted to accepted in this pass.
- Normal dungeon trash evidence is stronger than before because the first route now completes and sequence advancement is proven, but Stonecore remains blocked at Corborus and full-clear evidence is still missing.

## DVC

- Added `artifacts/live_validation_instances/stonecore_route_sequence_r3.dvc`.
- `dvc status` still reports stale pipeline deps for `validation_run_plan`, `live_scenario_reports`, and `live_validation_combined` because the validation runner and run-plan generator changed; these aggregate stages were not rebuilt in this pass.

## Next Handoff Prompt

Continue from run 000017. Current commit should contain route-sequence validation support and the watchdog/segment-completion fixes. Validation passed for `pixi run pytest tests/test_ml_pipeline.py -q`, `pixi run pytest tests/test_autonomy_pipeline_smoke.py -q`, and `cmake --build build --target worldserver -j2`. DVC-tracked evidence `artifacts/live_validation_instances/stonecore_route_sequence_r3/report.json` proves the new scenario-level sequence advances past `01_entrance_packs` instead of idling: that segment has `completion_reason=route_segment_complete`, `failure_labels=[]`, `trash_pulls=4`, `validation_route_actions=6`, and required `pulls=4`. The next blocker is `02_corborus`: `artifacts/live_validation_instances/stonecore_route_sequence_r3/02_corborus/report.json` has `completion_reason=no_progress_watchdog`, `failure_labels=["validation_route_no_engagement","no_progress_observed"]`, `boss_kill_evidence=0`, `pulls=0`, `tank_positioning=0`, `healer_assignments=0`, `target_priority=0`, `validation_route_actions=16`, `validation_route_hold_anchor=7`, `validation_route_regroup=9`, `hold_anchor_no_focus=9`, and `repeated_decision_loop=2`. Next likely fix: for boss routes, when the configured boss target is not visible/engageable after a completed prior route, move the tank/group from the previous segment anchor toward the boss route coordinate or configured boss start/activation point instead of holding the dungeon anchor with no focus. Then rerun `pixi run bot-live-validate --validation-route-sequence --validation-scenario-id stonecore_5n --validation-scenario-dir dataset/validation_scenarios --apply-validation-provisioning --reset-bot-pool --bot-pool-tag stonecore_5n --keep-bot-pool-position --timeout-sec 900 --heartbeat-sec 30 --no-progress-window-sec 180 --output-dir artifacts/live_validation_instances/stonecore_route_sequence_corborus_fix_r1`, DVC-add/push the artifact, and only update the checklist if Stonecore boss/trash/full-clear evidence becomes non-debug and uninterrupted.
