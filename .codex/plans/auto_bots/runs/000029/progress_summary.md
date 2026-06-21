# Run 000029 Progress Summary

## Scope

Continued from run 000028 / commit `adf4bf99e6`. This pass focused on runtime support for scenario-scoped validation route manifests so Stonecore can run multiple route nodes in one `worldserver` process.

No worker or reviewer sessions were launched. The implementation was handled directly by the orchestrator as a medium-complexity task because the change was localized to the live-validation harness and `BotWorldPopulationMgr`, with focused tests and live validation.

## Changes

- Added C++ support for `BotWorld.ValidationRoute.ManifestPath` and `BotWorld.ValidationRoute.AdvanceMode`.
- Added a manifest parser for the existing `bot_live_validation_route_manifest_v1` JSON shape emitted by `tools/bot_ml/run_live_bot_validation.py`.
- Applied manifest node 0 at config load, including route target, activation, opener, coordinates, kind, label, scenario, and expected bot count.
- Added route-manifest runtime state:
  - current index and count,
  - per-node kill baseline,
  - pending-advance latch,
  - manifest load error.
- Reset per-route focus, activation, target, terminal, combat-progress, anchor override, and loop-repeat state when applying a new manifest node.
- Added manager-level advancement from terminal state / `validation_route_complete`.
- Added boss-kill route advancement latch after `boss_killed`; this was implemented after `r4` proved boss routes can record kills without advancing.
- Extended status, trace, and `.botauto diagnose` evidence with manifest index/count, advance mode, pending advance, advance reason, load error, and per-node kill baseline.
- Updated `worldserver.conf.dist` with default manifest controls.
- Fixed `run_worldserver_completion_watchdog` so manifest-backed full-clear runs do not stop as `route_segment_complete` after the first node. Segment evidence remains debug-only outside manifest runs.
- Added regression coverage in `tests/test_ml_pipeline.py` and updated static autonomy smoke contracts.

## Validation

Passed:

- `pixi run pytest tests/test_autonomy_pipeline_smoke.py -q`: 14 passed.
- `pixi run pytest tests/test_ml_pipeline.py -k 'completion_watchdog_does_not_stop_manifest_run_on_first_route_segment or route_manifest_dry_run or manifest_backed_uninterrupted_clear' -q`: 3 passed, 162 deselected.
- `pixi run pytest tests/test_ml_pipeline.py -k 'completion_watchdog_does_not_stop_manifest_run_on_first_route_segment or route_manifest_dry_run or manifest_backed_uninterrupted_clear or route_segment_complete_accepts_terminal_trash_evidence' -q`: 4 passed, 161 deselected.
- `cmake --build build --target worldserver -j2`: passed after both C++ edits.
- `pixi run bot-live-validate --dry-run --duration-policy completion-watchdog --validation-route-manifest --validation-scenario-id stonecore_5n --output-dir .codex/plans/auto_bots/runs/000029/stonecore_route_manifest_dry_run`: passed and wrote `ManifestPath` / `AdvanceMode`.
- `pixi run bot-autonomy-checklist --evidence-report artifacts/live_validation_quest_mob_assist_150s/report.json --validation-status dataset/validation_run_status/manifest.json --scenario-report-root dataset/live_validation_scenario_reports_built --output .codex/plans/auto_bots/master_checklist.json`: passed; checklist remains 9 accepted, 4 review, 2 needs_followup.

Live attempts:

- `artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r2/report.json`
  - Ran before the harness early-exit fix.
  - `completion_reason=route_segment_complete`, `failure_labels=[]`.
  - Proved C++ manifest loading exposed `validation_route_manifest_index=0`, `validation_route_manifest_count=8`, `AdvanceMode=terminal`, and route actions instead of quest fallback.
  - Still invalid as final evidence because the Python watchdog stopped after first-node segment evidence.
- `artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r3/report.json`
  - Ran after the harness early-exit fix, before the route-complete latch.
  - `completion_reason=machine_failure_predicate`, `failure_labels=["validation_route_stuck_loop"]`.
  - Reached `kills=1`, `trash_pulls=33`, `validation_route_actions=117`, and `validation_route_complete=3`, but manifest index stayed 0.
  - This proved terminal decisions could be lost before manager-level advancement.
- `artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r4/report.json`
  - Ran after the route-complete latch, before the boss-kill latch.
  - `completion_reason=emergency_wall_clock_timeout`, `failure_labels=["worldserver_timeout"]`.
  - Proved manifest advancement from route 0 to route 1: final diagnosis had `validation_route_manifest_index=1`, `validation_route_config_kind="boss"`, `validation_route_config_target_entry=43438`, `validation_route_progress_baseline_kills=1`.
  - Corborus route produced `boss_started=5`, `boss_action=5`, `validation_route_boss_action=5`, `boss_killed=3`, `boss_kill_evidence=3`, `kills=7`, `validation_route_actions=607`.
  - It did not advance past route 1 before timeout. The boss-kill latch was added after this evidence.

## DVC

Generated live artifacts were checkpointed with DVC:

- `artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r2.dvc`
- `artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r3.dvc`
- `artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r4.dvc`

## Current Status

Checklist remains:

- 9 accepted
- 4 review
- 2 needs_followup

Stonecore is closer but still not accepted. This pass removed the quest-fallback blocker and proved in-process route advancement from the entrance trash node to Corborus. The next blocker is validating the newly added boss-kill advancement latch and then continuing through the full route manifest.

## Next Handoff Prompt

Continue from run 000029 after the commit from this pass. Runtime route-manifest support is now implemented in `BotWorldPopulationMgr`: it loads `BotWorld.ValidationRoute.ManifestPath`, applies manifest node 0, exposes manifest index/count/advance diagnostics, uses per-node kill baselines, advances on terminal route decisions, and now also latches manifest advancement on `boss_killed`. The Python completion watchdog no longer stops a manifest-backed full-clear run as `route_segment_complete` after the first node.

Validation evidence:

- `r2` proved manifest loading but exposed the Python early-exit bug: `artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r2/report.json`, `completion_reason=route_segment_complete`, route index 0.
- `r3` proved the harness fix but exposed lost terminal decisions: `artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r3/report.json`, `failure_labels=["validation_route_stuck_loop"]`, `validation_route_complete=3`, route index still 0.
- `r4` proved route 0 to route 1 advancement: `artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r4/report.json`, final diagnosis `validation_route_manifest_index=1`, `validation_route_config_kind="boss"`, `validation_route_config_target_entry=43438`, with Corborus evidence `boss_killed=3`, `boss_kill_evidence=3`, but it timed out because boss kills did not yet advance. The boss-kill advancement latch was added after this run and has only compile/static-test validation so far.

Next action: rerun the manifest live validation to verify the new boss-kill latch advances from Corborus to route 2:

```bash
pixi run bot-live-validate --duration-policy completion-watchdog --apply-validation-provisioning --reset-bot-pool --bot-pool-tag stonecore_5n --keep-bot-pool-position --heartbeat-sec 30 --no-progress-window-sec 180 --max-repeated-decision-count 20 --max-death-loop-count 3 --validation-scenario-id stonecore_5n --validation-route-manifest --output-dir artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r5 --observe-sec 300 --timeout-sec 900
```

If route 2 is reached, continue fixing any later route terminal/activation blockers. If all 8 routes complete in one process, rebuild scenario reports and status:

```bash
pixi run dvc repro live_scenario_reports validation_run_status live_validation_combined world_planner_validate
pixi run bot-autonomy-checklist --evidence-report artifacts/live_validation_quest_mob_assist_150s/report.json --validation-status dataset/validation_run_status/manifest.json --scenario-report-root dataset/live_validation_scenario_reports_built --output .codex/plans/auto_bots/master_checklist.json
pixi run dvc status
pixi run dvc push
```
