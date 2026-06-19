# Foundation Data Gates Round 1

Current date: 2026-06-19

## Latest Commit

- Commit: `c81a253934` (`Enforce uninterrupted bot clear evidence`).
- Lane: `foundation-data-gates`
- Branch: `bot-autonomy/lane-foundation-data-gates-round-1` merged into `master` and deleted after fast-forward.

## Changed Files

- `tools/bot_ml/build_live_scenario_reports.py`
- `tools/bot_ml/build_validation_run_plan.py`
- `tools/bot_ml/build_validation_run_status.py`
- `tools/bot_ml/run_live_bot_validation.py`
- `tools/bot_ml/validate_world_planner.py`
- `tools/bot_ml/README.md`
- `tests/test_ml_pipeline.py`
- `dvc.lock`

## Claimed Behavior

- Segment validation remains usable for trash/boss debugging and label quality.
- Final dungeon/raid `clear_complete=true` now requires an uninterrupted whole-instance live report with explicit `completion_claim_valid=true` and non-segment completion mode.
- Scenario gates reject segment-stitched, stale, missing-metadata, route-mismatched, and failure-labeled completion claims.
- The generated validation run plan now emits a whole-scenario `bot-live-validate` command before route segments and includes that report in scenario aggregation.

## Data Domains

- `dungeon_trash`
- `dungeon_boss`
- `dungeon_full_clear`
- `raid_trash`
- `raid_boss`
- `raid_full_clear`
- `group_coordination`
- `recovery`

## Verification

- `pixi run pytest -q`: passed, 105 passed, 1 `dvclive`/`pynvml` warning.
- `cmake --build build --target worldserver -j"$(nproc)"`: passed.
- `pixi run dvc repro live_scenario_reports world_planner_validate live_validation_combined validation_run_status quest_profession_report`: passed.
- `pixi run dvc status`: data and pipelines are up to date.
- `pixi run dvc status -c`: cache and remote `object` are in sync after push.
- `pixi run dvc push`: pushed 10 files.

## Live Run State

- Current checked-in Stonecore and BWD artifacts remain segment-only and do not satisfy final full-clear acceptance.
- `dataset/live_validation_scenario_reports_built/stonecore_5n.json`: `clear_complete=false`, `completion_evidence_mode=segment_debug_only`.
- `dataset/live_validation_scenario_reports_built/blackwing_descent_10n.json`: `clear_complete=false`, `completion_evidence_mode=segment_debug_only`.
- `dataset/validation_run_status/manifest.json`: `ready_scenarios=0`, `blocked_scenarios=2`.

## Reviewer Findings

- No separate reviewer pass was run in this single-agent cleanup. The automated regression suite, DVC repro/status, DVC push, and worldserver build passed.
