# Run 000031 Progress Summary

## Scope
- Continued from run 000030 / commit `cab0a0e2e9`.
- Targeted the uninterrupted Stonecore 5N validation blocker where route index 4 (`stonecore sentry gauntlet`, target entry `42428`) was being labeled `validation_route_stuck_loop` after real route progress.
- No worker/reviewer Codex sessions were launched; the fix was scoped and handled directly by the orchestrator.

## Changes
- Updated `tools/bot_ml/run_live_bot_validation.py` so recovered route-stuck evidence suppresses `validation_route_stuck_loop` for both high stuck counts and high repath counts. This prevents the completion watchdog from terminating a progressing trash route just because recovery generated repeated repaths.
- Expanded `tests/test_ml_pipeline.py::test_live_bot_validation_keeps_recovered_route_stuck_as_progress` to cover repeated repaths plus terminal route completion.
- Updated `src/server/game/Bots/BotWorldPopulationMgr.cpp` so non-tank bots on an already-activated boss validation route do not return early with `validation_route_hold_anchor` when no tank focus exists. They now record `search_after_activation_no_focus` and fall through to route target search/approach.
- Updated `tests/test_autonomy_pipeline_smoke.py` to assert the activated boss no-focus search path.

## Validation
- `pixi run pytest tests/test_ml_pipeline.py -k "route_stuck or stuck_heavy_trash_route or recovered_route_stuck"`: passed.
- `pixi run pytest tests/test_ml_pipeline.py`: 165 passed.
- `pixi run pytest tests/test_autonomy_pipeline_smoke.py -k "validation_route"`: passed.
- `cmake --build build --target worldserver -j$(nproc)`: passed.
- Re-scored `artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r8/worldserver_output.log` with the patched parser: `failure_labels=[]`, `completion_reason=incomplete_evidence`, `repath_events=8`, `stuck_events=17`, `kills=4`, `validation_route_actions=232`.

## Live Evidence
- `artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r9/report.json`
  - Ran with the parser fix before the C++ no-focus boss-route fix.
  - Improved beyond the prior route-4 blocker and reached route index 7 of 8 (`High Priestess Azil`, target entry `42333`).
  - Final result: `completion_reason=emergency_wall_clock_timeout`, `failure_labels=["worldserver_timeout"]`, `boss_kill_evidence=2`, `kills=7`, `trash_pulls=83`, `validation_route_actions=530`.
  - Final diagnosis showed repeated `validation_route_hold_anchor` after boss activation, motivating the C++ change.
- `artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r10/report.json`
  - Ran after the C++ no-focus boss-route fix.
  - Again passed the original route-4 sentry blocker and reached route index 7 of 8.
  - Final result: `completion_reason=emergency_wall_clock_timeout`, `failure_labels=["worldserver_timeout"]`, `boss_kill_evidence=2`, `kills=8`, `trash_pulls=89`, `validation_route_actions=508`.
  - Final diagnosis showed target `42333`, `validation_route_activation_applied=true`, chosen spell target `42333` with an in-range builder action at one point, and current action `move_to_validation_route_anchor`; this is progress over the prior hold-anchor-only loop, but Stonecore is still not complete.

## DVC
- Added:
  - `artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r9.dvc`
  - `artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r10.dvc`

## Current Blocker
Stonecore uninterrupted validation now reaches the final Azil route instead of failing at route 4, but still times out on route index 7/8. The next blocker is final boss engagement/completion for High Priestess Azil after activation: bots can see/select `42333`, but route movement/anchor recovery still fails to finish the encounter before the 900s wall-clock timeout.

## Next Handoff Prompt
Continue from run 000031 after the commit from this pass. The route-4 `validation_route_stuck_loop` parser false positive is fixed, and non-tank bots on already-activated boss routes now fall through from `search_after_activation_no_focus` into route target search instead of immediately holding anchor. Evidence:
- `artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r9/report.json`: reached route index 7/8 but timed out with repeated `validation_route_hold_anchor`.
- `artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r10/report.json`: after the C++ fix, again reached route index 7/8; final diagnosis target entry `42333`, `validation_route_activation_applied=true`, `kills=8`, `trash_pulls=89`, `validation_route_actions=508`, but still timed out with `worldserver_timeout`.
Investigate final High Priestess Azil route completion. Focus on why route index 7 remains at `move_to_validation_route_anchor`/route movement around `(1337.3, 964.894, 214.238)` despite a visible selected target `42333`, valid chosen spell, and prior boss engagement evidence. Check route target search, tank focus handoff, boss kill latch/terminal advancement, and whether active bots dropping to 0 at timeout is just harness shutdown or a bot lifecycle signal. After a fix, run:
`pixi run bot-live-validate --duration-policy completion-watchdog --apply-validation-provisioning --reset-bot-pool --bot-pool-tag stonecore_5n --keep-bot-pool-position --heartbeat-sec 30 --no-progress-window-sec 180 --max-repeated-decision-count 20 --max-death-loop-count 3 --validation-scenario-id stonecore_5n --validation-route-manifest --output-dir artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r11 --observe-sec 300 --timeout-sec 900`
If artifacts are produced, DVC-add them, run `pixi run dvc status`, and run `pixi run dvc push`.
