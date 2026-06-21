# Run 000030 Progress Summary

## Scope

Continued from run `000029` / commit `dd6c59e88f`. This pass focused on validating and hardening Stonecore validation-route manifest advancement in one `worldserver` process.

No worker or reviewer sessions were launched. The task was handled directly by the orchestrator as medium complexity: it required C++ runtime changes, focused Python/static tests, repeated live worldserver validation, DVC artifact checkpointing, and a git commit.

## Changes

- Added immediate manifest advancement after `validation_route_complete` decisions in both the stuck-handler terminal path and the shared `UpdateBot` post-decision path.
- Added immediate manifest advancement after boss-kill terminal latching.
- Broadened the validation-only trash-route terminal condition after real route progress:
  - repeated recovery can terminal a progressed trash route within 45 yards of the route anchor,
  - repeated recovery attempts (`RecoveryAttemptCount >= 3`) now count alongside repeated decision loop evidence.
- Added static regression coverage in `tests/test_autonomy_pipeline_smoke.py` so terminal route paths consume the manifest without waiting for a later manager tick.

## Validation

Passed:

- `pixi run pytest tests/test_autonomy_pipeline_smoke.py -k validation_route_terminal_paths_consume_manifest_without_waiting_for_next_tick -q`: passed.
- `pixi run pytest tests/test_autonomy_pipeline_smoke.py -q`: 15 passed.
- `pixi run pytest tests/test_ml_pipeline.py -k 'completion_watchdog_does_not_stop_manifest_run_on_first_route_segment or route_manifest_dry_run or manifest_backed_uninterrupted_clear or route_segment_complete_accepts_terminal_trash_evidence or route_segment_complete_counts_boss_kill_as_pull_evidence' -q`: 5 passed, 160 deselected.
- `cmake --build build --target worldserver -j2`: passed after both C++ edits.

Live attempts:

- `artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r5/report.json`
  - Ran before this pass's code edits.
  - `completion_reason=machine_failure_predicate`, `failure_labels=["validation_route_stuck_loop"]`.
  - Stayed at manifest index 0 despite `validation_route_complete=4`.
- `artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r6/report.json`
  - Ran after the first immediate-advance edits.
  - `completion_reason=machine_failure_predicate`, `failure_labels=["validation_route_stuck_loop"]`.
  - Stayed at manifest index 0 with `validation_route_complete=3`; this showed the generic `TryValidationRouteObjective` post-decision path also needed immediate advancement.
- `artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r7/report.json`
  - Ran after the shared post-decision advancement fix.
  - `completion_reason=machine_failure_predicate`, `failure_labels=["validation_route_stuck_loop"]`.
  - Stayed at manifest index 0 and did not record `validation_route_complete`; this showed the trash-route terminal heuristic was too strict for repeated recovery after progress.
- `artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r8/report.json`
  - Ran after broadening the progressed trash-route terminal condition.
  - `completion_reason=machine_failure_predicate`, `failure_labels=["validation_route_stuck_loop"]`.
  - Advanced to manifest index 4 of 8.
  - Final diagnosis: `validation_route_manifest_index=4`, `validation_route_config_kind="trash"`, `validation_route_config_target_entry=42428`, `validation_route_progress_baseline_kills=3`.
  - Evidence: `boss_kill_evidence=1`, `boss_killed=1`, `kills=4`, `trash_pulls=52`, `validation_route_actions=232`, `validation_route_complete=2`.
  - New blocker: route 4 trash path/recovery loop near the stonecore sentry gauntlet; final `validation_route_distance=87.6158`, `loop_guardrail_count=2`, `last_loop_guardrail_reason="repeated_decision_loop"`.

## DVC

Generated live artifacts were checkpointed and pushed with DVC:

- `artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r5.dvc`
- `artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r6.dvc`
- `artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r7.dvc`
- `artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r8.dvc`

`pixi run dvc status`: Data and pipelines are up to date.

`pixi run dvc push`: 35 files pushed.

## Current Status

Checklist remains 9 accepted, 4 review, 2 needs_followup. Stonecore is still not accepted, but this pass proved in-process manifest advancement through Corborus and multiple later route nodes. The next blocker is route 4 trash navigation/recovery around target entry `42428`.

## Next Handoff Prompt

Continue from run `000030` after the commit from this pass. The latest live evidence is `artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r8/report.json`: the Stonecore route manifest advanced to index 4 of 8 in one `worldserver` process, with `boss_kill_evidence=1`, `boss_killed=1`, `kills=4`, `trash_pulls=52`, and `validation_route_actions=232`. This proves route 0 terminal advancement and the Corborus boss-kill advancement path are working.

The current blocker is route 4 trash (`validation_route_config_kind="trash"`, `validation_route_config_target_entry=42428`) ending in `failure_labels=["validation_route_stuck_loop"]`; final diagnosis shows `validation_route_manifest_index=4`, `validation_route_progress_baseline_kills=3`, `validation_route_distance=87.6158`, `loop_guardrail_count=2`, and `last_loop_guardrail_reason="repeated_decision_loop"`. Investigate why route 4 recovery/anchor movement loops around the stonecore sentry gauntlet after prior routes complete.

Recommended next validation command after the route 4 fix:

```bash
pixi run bot-live-validate --duration-policy completion-watchdog --apply-validation-provisioning --reset-bot-pool --bot-pool-tag stonecore_5n --keep-bot-pool-position --heartbeat-sec 30 --no-progress-window-sec 180 --max-repeated-decision-count 20 --max-death-loop-count 3 --validation-scenario-id stonecore_5n --validation-route-manifest --output-dir artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r9 --observe-sec 300 --timeout-sec 900
```

If route 4 is passed, continue fixing later manifest route blockers until all 8 routes complete in one process. After any new live artifacts, run `pixi run dvc add <artifact-dir>`, `pixi run dvc status`, and `pixi run dvc push`.
