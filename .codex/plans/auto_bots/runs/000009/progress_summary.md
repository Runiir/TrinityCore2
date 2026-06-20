# Orchestrator Pass 000009

## Work completed

- Classified this pass as direct medium validation-route runtime work; no worker or reviewer Codex session was launched.
- Fixed non-tank validation-route assist evidence in `BotWorldPopulationMgr.cpp`: when DPS/healer bots assist the tank on the configured validation route target, the runtime now records route trash/boss evidence instead of prerequisite-loop evidence.
- Ran a route-directed Stonecore entrance validation smoke. It now produced route pull evidence (`trash_route_actions=5`, `trash_pulls=5`, `validation_route_actions=16`, `validation_evidence_ready.pulls=true`) against route node `bafdc27f1d35bc27`.
- The smoke still failed as `validation_route_stuck_loop`, so Stonecore remains follow-up work; the pass narrows the next blocker from missing engagement evidence to movement/stuck recovery around the first entrance route pack.
- DVC-checkpointed and pushed the new validation artifact.

## Validation

- `cmake --build build --target worldserver -j2`
- `pixi run pytest tests/test_ml_pipeline.py -k 'validation_route or live_bot_validation_main_preserves_watchdog_report'`
- `pixi run bot-live-validate --duration-policy completion-watchdog --apply-validation-provisioning --reset-bot-pool --bot-pool-tag stonecore_5n --keep-bot-pool-position --heartbeat-sec 20 --no-progress-window-sec 120 --timeout-sec 260 --max-repeated-decision-count 20 --max-death-loop-count 3 --validation-scenario-id stonecore_5n --validation-route-node-id bafdc27f1d35bc27 --validation-route-label 'entrance packs' --validation-route-kind trash --validation-route-step 1 --validation-mechanic-profile '' --output-dir artifacts/live_validation_instances/stonecore_route_assist_evidence_r1/stonecore_5n`
- `dvc add artifacts/live_validation_instances/stonecore_route_assist_evidence_r1`
- `dvc status`
- `dvc push` (`7 files pushed`)

## Evidence

- Runtime fix: `src/server/game/Bots/BotWorldPopulationMgr.cpp`
- Stonecore smoke report: `artifacts/live_validation_instances/stonecore_route_assist_evidence_r1/stonecore_5n/report.json`
- Stonecore smoke log: `artifacts/live_validation_instances/stonecore_route_assist_evidence_r1/stonecore_5n/worldserver_output.log`
- DVC metadata: `artifacts/live_validation_instances/stonecore_route_assist_evidence_r1.dvc`

## Next blocker

Stonecore route engagement is now visible as pull evidence, but the entrance route still trips `validation_route_stuck_loop`. Next work should inspect the route pack movement and stuck recovery traces in `artifacts/live_validation_instances/stonecore_route_assist_evidence_r1/stonecore_5n/report.json` and `worldserver_output.log`, then rerun the generated full-clear command from `dataset/validation_run_status/manifest.json` with the normal long budget.
