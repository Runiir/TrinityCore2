You are a worker Codex agent in /home/runiir/Games/trinity-cata. Use pixi for Python tasks. Do not commit.

Context:
- Run 000027 completed Stonecore route-sequence evidence in artifacts/live_validation_instances/stonecore_route_sequence_r8, but it is rejected as full clear because it is segmented/debug evidence.
- In run 000028, the orchestrator ran:
  pixi run bot-live-validate --duration-policy completion-watchdog --apply-validation-provisioning --reset-bot-pool --bot-pool-tag stonecore_5n --keep-bot-pool-position --heartbeat-sec 30 --no-progress-window-sec 180 --max-repeated-decision-count 20 --max-death-loop-count 3 --validation-scenario-id stonecore_5n --output-dir artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r1 --observe-sec 300 --timeout-sec 900
- That failed with completion_reason=machine_failure_predicate, failure_labels=["bot_diagnosis_error"], diagnosis_code=bot_loaded_not_in_world, and only generic questing actions: accept_hub_quests, move_to_quest_hub, search_collect_mob. No validation_route_actions were emitted because no route config was active.

Task:
1. Inspect src/server/game/Bots/BotWorldPopulationMgr.*, tools/bot_ml/run_live_bot_validation.py, build_live_scenario_reports.py, build_validation_run_status.py, and relevant tests.
2. Determine the least invasive implementation path for a real uninterrupted Stonecore full-clear validation that uses the route manifest in one worldserver process and is not rejected as route_segment_context/route_sequence_context.
3. If feasible within one pass, implement a scoped first step with focused tests. Prefer a runtime route advancement mechanism or a validation harness mode that keeps one worldserver process alive while advancing route nodes with machine-readable evidence. Avoid falsifying full-clear evidence by relabeling segmented runs.
4. If implementation is too broad, produce a concrete design note and next-step patch target.

Constraints:
- Do not commit.
- Do not run long live validation; the orchestrator will run long validation.
- Keep any edits narrow and aligned with existing patterns.
- Use pixi for Python tests.

Write your final answer to the configured last-message path with: summary, files changed, tests run, blockers, and exact next command(s).
