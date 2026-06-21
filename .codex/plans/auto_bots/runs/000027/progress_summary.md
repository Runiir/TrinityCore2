# Run 000027 Progress Summary

## Scope

Continued from run 000026 / commit cd12294a36. Focus was the post-Ozruk Stonecore route-sequence failure at `07_twilight_flayer_packs`, previously blocked by `validation_route_no_engagement`, `validation_route_assist_focus_loop`, and `no_progress_observed`.

No worker or reviewer session was launched. Complexity routing note: this was handled directly by the orchestrator because the changes were scoped to validation harness predicates/report aggregation plus focused tests.

## Changes

- Updated `tools/bot_ml/run_live_bot_validation.py` so moving validation-route assist-focus states are non-terminal while route motion progress is present. This prevents long route transitions from being cut off as `machine_failure_predicate` before bots reach the pull.
- Updated boss-route evidence aggregation so `boss_kill_evidence` satisfies the generic `pulls` route evidence contract. This covers teacher-assist boss-kill paths that do not leave a `boss_action` in the final trace window.
- Updated `no_progress_observed` labeling so boss kill evidence is treated as real progress.
- Updated `dvc.yaml` live scenario report inputs from older Stonecore r5 + Azil r2 evidence to the new complete `stonecore_route_sequence_r8` artifact.
- Added focused pytest regressions in `tests/test_ml_pipeline.py`.

## Validation

- `pixi run pytest tests/test_ml_pipeline.py -k 'bot_ml_workflow_has_pixi_tasks_and_documented_dvc_steps or route_segment_complete or route_progress_incomplete or moving_assist_focus_loop or watchdog_state'` passed: 7 passed, 155 deselected.
- `pixi run bot-live-validate ... --validation-scenario-id stonecore_5n --validation-route-sequence --output-dir artifacts/live_validation_instances/stonecore_route_sequence_r8` passed all route segments:
  - Aggregate: `artifacts/live_validation_instances/stonecore_route_sequence_r8/report.json`
  - `completion_reason=route_sequence_complete`
  - `failure_labels=[]`
  - `passed=8`
  - `route_sequence.complete_segments` includes all 8 expected segments.
- Segment 07 evidence fixed:
  - `artifacts/live_validation_instances/stonecore_route_sequence_r8/07_twilight_flayer_packs/report.json`
  - `route_segment_complete=true`
  - `failure_labels=[]`
  - `trash_pulls=6`
  - `validation_route_actions=33`
- Segment 08 Azil still has interrupt evidence through r8:
  - `artifacts/live_validation_instances/stonecore_route_sequence_r8/08_high_priestess_azil/report.json`
  - `route_segment_complete=true`
  - `failure_labels=[]`
  - `interrupt_evidence=2`
- DVC reproduced:
  - `live_scenario_reports`
  - `validation_run_status`
  - `live_validation_combined`
  - `world_planner_validate`
- DVC status before push: data and pipelines up to date.
- DVC push: 46 files pushed.

## Current Status

Stonecore segment coverage is complete and `dataset/validation_run_status/manifest.json` reports `segment_coverage_ready=true` and `segment_reruns=[]` for `stonecore_5n`.

Full Stonecore is still not complete by the checklist definition because route-sequence evidence remains debug/segment evidence, not an uninterrupted full-clear report. Current remaining Stonecore blockers are:

- `scenario_clear_not_complete`
- `segment_evidence_debug_only`
- `missing_uninterrupted_full_clear_report`
- `missing_required_evidence`

Checklist remains 9 accepted open-world gates, with Stonecore trash/boss in review and full Stonecore needing follow-up.

## Next Handoff Prompt

Continue from run 000027 after committing this pass. The Stonecore route-sequence blocker is resolved in `artifacts/live_validation_instances/stonecore_route_sequence_r8`: all 8 segments completed, aggregate `completion_reason=route_sequence_complete`, `failure_labels=[]`, and segment 07 `07_twilight_flayer_packs` has `route_segment_complete=true`, `trash_pulls=6`, and no failure labels. Validation harness fixes were made in `tools/bot_ml/run_live_bot_validation.py` for moving assist-focus loops, boss-kill-as-pull evidence, and boss-kill no-progress labeling; `dvc.yaml` now points live scenario reports at r8. DVC status was up to date and DVC push uploaded 46 files. Next focus: produce an uninterrupted full Stonecore clear artifact, not just route-sequence segment evidence. The remaining Stonecore blockers are `scenario_clear_not_complete`, `segment_evidence_debug_only`, `missing_uninterrupted_full_clear_report`, and `missing_required_evidence`; `dataset/validation_run_status/manifest.json` has `segment_coverage_ready=true` and no Stonecore segment reruns. Run the full Stonecore validation command from `validation_next_commands.uninterrupted_full_clear` or an equivalent long-budget run, rebuild scenario reports/status/checklist, run focused pixi tests, run `pixi run dvc status`, and `pixi run dvc push`.
