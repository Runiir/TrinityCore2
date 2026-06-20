# Orchestrator Pass 000010

## Work completed

- Classified this pass as direct medium validation-route runtime and validator work; no worker or reviewer Codex session was launched.
- Added validation-route-specific stuck recovery in `BotWorldPopulationMgr.cpp`. When a route bot hits the generic stuck threshold, it now records the failed path, prefers recent safe-position memory, falls back to a living dungeon anchor or the route anchor, emits `validation_route_recovery`, and records recovery state instead of immediately recording a failed generic `unstuck` decision.
- Tightened `tools/bot_ml/run_live_bot_validation.py` so recovered validation-route stuck events with safe-memory recovery and continued pull/kill evidence do not immediately become `validation_route_stuck_loop`; unrecovered loops and repeated failed unstucks still fail.
- Preserved the daemon's stale latest orchestrator result as `previous_orchestrator_result` when a new cycle starts, so prior resume failures remain visible in the next prompt snapshot.
- DVC-checkpointed the useful Stonecore r2 validation artifact.

## Validation

- `pixi run pytest tests/test_autonomy_pipeline_smoke.py -q`
- `cmake --build build --target worldserver -j2`
- `pixi run pytest tests/test_ml_pipeline.py -k 'validation_route or live_bot_validation_main_preserves_watchdog_report' -q`
- `pixi run pytest tests/test_ml_pipeline.py -k 'validation_route or live_bot_validation_main_preserves_watchdog_report or recovered_route_stuck or stuck_heavy_trash_route' -q`
- `pixi run pytest tests/test_ml_pipeline.py -k 'orchestrator_daemon_new_cycle_moves_stale_latest_result_to_previous' -q`
- `pixi run bot-live-validate --duration-policy completion-watchdog --apply-validation-provisioning --reset-bot-pool --bot-pool-tag stonecore_5n --keep-bot-pool-position --heartbeat-sec 20 --no-progress-window-sec 120 --timeout-sec 260 --max-repeated-decision-count 20 --max-death-loop-count 3 --validation-scenario-id stonecore_5n --validation-route-node-id bafdc27f1d35bc27 --validation-route-label 'entrance packs' --validation-route-kind trash --validation-route-step 1 --validation-mechanic-profile '' --output-dir artifacts/live_validation_instances/stonecore_route_stuck_recovery_r2/stonecore_5n`

## Evidence

- Runtime fix: `src/server/game/Bots/BotWorldPopulationMgr.cpp`
- Validator fix: `tools/bot_ml/run_live_bot_validation.py`
- Regression tests: `tests/test_ml_pipeline.py`
- Daemon continuity fix: `tools/bot_ml/orchestrator_daemon.py`
- Stonecore r2 report: `artifacts/live_validation_instances/stonecore_route_stuck_recovery_r2/stonecore_5n/report.json`
- Stonecore r2 DVC metadata: `artifacts/live_validation_instances/stonecore_route_stuck_recovery_r2.dvc`

## Validation outcome

- The first smoke after the runtime patch still tripped `validation_route_stuck_loop`, but showed the new recovery path firing with `unstuck_failures=0`, `validation_route_recovery=5`, `trash_pulls=8`, and one mob kill.
- After the validator predicate fix, the r2 smoke no longer failed as `validation_route_stuck_loop`; it ran until `emergency_wall_clock_timeout` with `failure_labels=["worldserver_timeout"]`, `validation_route_actions=18`, `trash_pulls=2`, `validation_route_recovery=2`, `stuck_events=16`, and `unstuck_failures=0`.
- Stonecore remains follow-up work. The current blocker is incomplete route progression/kill completion after recovered stuck events, not immediate stuck-loop classification.

## Next handoff prompt

Continue from pass 000010. Stonecore entrance route no longer aborts on `validation_route_stuck_loop` after recovered safe-memory route stuck events, but the latest r2 smoke timed out at `artifacts/live_validation_instances/stonecore_route_stuck_recovery_r2/stonecore_5n/report.json` with `worldserver_timeout`, `validation_route_actions=18`, `trash_pulls=2`, `validation_route_recovery=2`, `unstuck_failures=0`, and no kill evidence. Inspect `worldserver_output.log`, `heartbeat_events.jsonl`, and the trace in that report to fix incomplete route target completion after recovery; likely focus areas are assist-target range/LOS after safe-memory fallback, tank focus persistence, and route pack kill confirmation. Then rerun the Stonecore route-directed validation with the normal long budget and rebuild scenario reports if it produces complete segment evidence.
