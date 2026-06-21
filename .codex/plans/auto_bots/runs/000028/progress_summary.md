# Run 000028 Progress Summary

## Scope

Continued from run 000027 / commit `3437a5c1d7`. This pass focused on producing or unblocking uninterrupted Stonecore full-clear evidence after `stonecore_route_sequence_r8` completed all route segments but remained rejected as segment/debug evidence.

Launched one worker:

- `worker_uninterrupted_route_runtime`
- Complexity: `large`
- Model: `gpt-5.5`
- Reasoning effort: `high`
- Artifacts:
  - `.codex/plans/auto_bots/runs/000028/worker_uninterrupted_route_runtime.jsonl`
  - `.codex/plans/auto_bots/runs/000028/worker_uninterrupted_route_runtime.stderr`
  - `.codex/plans/auto_bots/runs/000028/worker_uninterrupted_route_runtime.last_message.md`

## Live Validation

Ran a real scenario-scoped Stonecore attempt:

```bash
pixi run bot-live-validate --duration-policy completion-watchdog --apply-validation-provisioning --reset-bot-pool --bot-pool-tag stonecore_5n --keep-bot-pool-position --heartbeat-sec 30 --no-progress-window-sec 180 --max-repeated-decision-count 20 --max-death-loop-count 3 --validation-scenario-id stonecore_5n --output-dir artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r1 --observe-sec 300 --timeout-sec 900
```

Result:

- `artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r1/report.json`
- `completion_reason=machine_failure_predicate`
- `failure_labels=["bot_diagnosis_error"]`
- diagnosis `bot_loaded_not_in_world`
- no validation-route evidence: `validation_route_actions=0`
- actions were generic questing in Stonecore: `accept_hub_quests`, `move_to_quest_hub`, `search_collect_mob`

Conclusion: the plain scenario-level command does not start dungeon route autonomy. It falls back to questing around quest `28815`, so uninterrupted full-clear validation needs a scenario-scoped route manifest path plus C++ runtime route advancement.

## Changes

- Added `--validation-route-manifest` to `tools/bot_ml/run_live_bot_validation.py`.
  - Writes `validation_route_manifest.json` for the scenario.
  - Keeps `validation_context` scenario-scoped, not segment-scoped.
  - Configures the first route node and writes forward-looking config keys:
    - `BotWorld.ValidationRoute.ManifestPath`
    - `BotWorld.ValidationRoute.AdvanceMode = "terminal"`
- Updated `tools/bot_ml/build_live_scenario_reports.py` so a single non-segment live report can claim `uninterrupted_live_clear` only when:
  - the embedded route manifest `scenario_id` matches the scenario,
  - no route/segment context is present,
  - expected boss kills are present,
  - required evidence is complete,
  - trash evidence exists when the manifest has trash routes.
- Added focused tests in `tests/test_ml_pipeline.py` proving:
  - manifest dry-run writes scenario-scoped route config,
  - manifest-backed non-segment evidence can be accepted as uninterrupted,
  - summary-only boss counters remain insufficient,
  - route-sequence/segmented evidence remains rejected as full clear.

Remaining runtime blocker: `BotWorldPopulationMgr` does not yet consume `BotWorld.ValidationRoute.ManifestPath` or advance to the next route node in one worldserver process. The new Python/reporting path is harness groundwork for that C++ implementation.

## Validation

- `pixi run pytest tests/test_ml_pipeline.py -k 'route_manifest_dry_run or manifest_backed_uninterrupted_clear or counts_stonecore_summary_boss_kills or route_sequence_dry_run or aggregates_segmented_raid_progress_without_full_clear'`: 5 passed, 159 deselected.
- `pixi run python -m py_compile tools/bot_ml/run_live_bot_validation.py tools/bot_ml/build_live_scenario_reports.py`: passed.
- `pixi run bot-live-validate --dry-run --duration-policy completion-watchdog --validation-route-manifest --validation-scenario-id stonecore_5n --output-dir .codex/plans/auto_bots/runs/000028/stonecore_route_manifest_dry_run`: passed and wrote manifest/config.
- `pixi run dvc repro live_scenario_reports validation_run_status live_validation_combined world_planner_validate`: passed.
- `pixi run bot-autonomy-checklist --evidence-report artifacts/live_validation_quest_mob_assist_150s/report.json --validation-status dataset/validation_run_status/manifest.json --scenario-report-root dataset/live_validation_scenario_reports_built --output .codex/plans/auto_bots/master_checklist.json`: passed.
- `pixi run dvc status`: data and pipelines are up to date.
- `pixi run dvc push`: 12 files pushed.

## Current Status

Checklist remains:

- 9 accepted
- 4 review
- 2 needs_followup

Stonecore remains blocked:

- `normal_dungeon_trash`: review
- `dungeon_boss`: review
- `full_stonecore_clear`: needs_followup
- blockers: `scenario_clear_not_complete`, `segment_evidence_debug_only`, `missing_uninterrupted_full_clear_report`, `missing_required_evidence`

## Next Handoff Prompt

Continue from run 000028 after the commit from this pass. A plain uninterrupted Stonecore run was attempted in `artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r1` and failed before dungeon progress: `completion_reason=machine_failure_predicate`, `failure_labels=["bot_diagnosis_error"]`, diagnosis `bot_loaded_not_in_world`, `validation_route_actions=0`, and only generic questing actions (`accept_hub_quests`, `move_to_quest_hub`, `search_collect_mob`) around quest `28815`. This proves the scenario-level command does not start dungeon route autonomy.

Harness groundwork is now in place: `tools/bot_ml/run_live_bot_validation.py` supports `--validation-route-manifest`, writes `validation_route_manifest.json`, keeps validation context scenario-scoped, and configures the first route plus `BotWorld.ValidationRoute.ManifestPath` / `AdvanceMode=terminal`. `tools/bot_ml/build_live_scenario_reports.py` can accept a single non-segment manifest-backed live report as `uninterrupted_live_clear`, but still rejects route-sequence/segment evidence and summary-only boss counts. Focused tests pass.

Next implementation target: add C++ runtime support in `BotWorldPopulationMgr` for `BotWorld.ValidationRoute.ManifestPath` and `BotWorld.ValidationRoute.AdvanceMode=terminal`: load ordered route nodes, apply the first node, detect `ValidationRouteTerminalState` / `validation_route_complete`, advance config/state to the next route node without restarting worldserver, reset per-route focus/activation/progress state, and emit machine-readable trace/diagnosis for current route index and advancement. Then run:

```bash
pixi run bot-live-validate --duration-policy completion-watchdog --apply-validation-provisioning --reset-bot-pool --bot-pool-tag stonecore_5n --keep-bot-pool-position --heartbeat-sec 30 --no-progress-window-sec 180 --max-repeated-decision-count 20 --max-death-loop-count 3 --validation-scenario-id stonecore_5n --validation-route-manifest --output-dir artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r2 --observe-sec 300 --timeout-sec 900
```

If r2 completes all manifest routes in one process, add it to `dvc.yaml` live_scenario_reports inputs or rebuild scenario reports with it, rerun `pixi run dvc repro live_scenario_reports validation_run_status live_validation_combined world_planner_validate`, refresh the checklist, run focused pixi tests, `pixi run dvc status`, and `pixi run dvc push`.
