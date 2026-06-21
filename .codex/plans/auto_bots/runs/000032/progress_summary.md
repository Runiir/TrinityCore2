# Run 000032 Progress Summary

## Scope

Continued the autonomous bot validation pass from run 000031 / commit `23db5dad55`, focused on the final Stonecore route blocker at High Priestess Azil.

## Worker Routing

- Worker: `worker_azil_route_investigation`
- Complexity: `large`
- Model: `gpt-5.5`
- Reasoning effort: `high`
- Artifacts:
  - `.codex/plans/auto_bots/runs/000032/worker_azil_route_investigation.prompt.md`
  - `.codex/plans/auto_bots/runs/000032/worker_azil_route_investigation.jsonl`
  - `.codex/plans/auto_bots/runs/000032/worker_azil_route_investigation.stderr`
  - `.codex/plans/auto_bots/runs/000032/worker_azil_route_investigation.last_message.md`

## Implementation

- Added durable validation-route manifest completion state in `BotWorldPopulationMgr`, so the final manifest node records `validation_route_manifest_complete`, marks the cohort terminal, and keeps subsequent route ticks in `validation_route_complete` instead of re-entering the final boss route.
- Adjusted activated boss-route no-focus behavior so non-tank bots fall through to route target search instead of repeatedly returning to the anchor after activation.
- Extended the live validation parser to count raw `validation_route_manifest_complete` events when `.botauto trace` JSON is interleaved with prompt/output text.
- Added focused regression coverage for the C++ manifest-completion latch and the raw manifest-complete parser path.

## Validation

- `pixi run pytest tests/test_autonomy_pipeline_smoke.py -k validation_route`
- `cmake --build build --target worldserver -j$(nproc)`
- `pixi run pytest tests/test_ml_pipeline.py -k "manifest_complete or group_mechanic_evidence"`
- Re-scored `artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r11/worldserver_output.log`; the patched parser reports `completion_reason=validation_route_manifest_complete`, acceptable final evidence, no rejections, and 23 raw manifest-complete events.
- `pixi run pytest tests/test_ml_pipeline.py`
- `pixi run pytest tests/test_autonomy_pipeline_smoke.py -k validation_route`
- `cmake --build build --target worldserver -j$(nproc)`

## Live Evidence

- `artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r11/report.json` reproduced the previous timeout report because the old parser missed interleaved manifest-complete trace output.
- `artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r12/report.json` completed with:
  - `completion_reason`: `validation_route_manifest_complete`
  - `acceptable_final_evidence`: `true`
  - `failure_labels`: `[]`
  - `command_errors`: `[]`
  - `diagnosis_code`: `validation_route_terminal`
  - `validation_route_manifest_complete`: `1`

## DVC

- Added `artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r11.dvc`.
- Added `artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r12.dvc`.
- Ran `pixi run dvc status`; aggregate stages `live_scenario_reports` and `live_validation_combined` are out of date because `tools/bot_ml/run_live_bot_validation.py` changed.
- Ran `pixi run dvc push artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r11.dvc artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r12.dvc`; 29 files were pushed.

## Checklist

Promoted the Stonecore dungeon deliverables to accepted using `artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r12/report.json`:

- `normal_dungeon_trash`
- `dungeon_boss`
- `full_stonecore_clear`

Remaining checklist blockers are the Blackwing Descent raid deliverables.

## Next Handoff

Continue from run 000032 after the commit for this pass. Stonecore 5N now has accepted uninterrupted full-clear evidence at `artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r12/report.json`. Next focus should be Blackwing Descent 10N validation: inspect the current BWD scenario reports and route manifests, run or repair the uninterrupted BWD route validation, and DVC-track any produced artifacts.
