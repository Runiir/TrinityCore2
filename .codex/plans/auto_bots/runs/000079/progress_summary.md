# Run 000079 Progress Summary

## Scope

Continued the Blackwing Descent full-clear validation lane. Launched one large worker (`worker_omnotron_blocker`) with model `gpt-5.5` and high reasoning because the blocker spanned route data, C++ validation-route execution, and live raid evidence. The worker was terminated after partial results once it entered repeated long Omnotron validation/debug cycles; the orchestrator reviewed and retained the useful code/config/test changes.

## Changes

- Added data-driven alternate validation-route target entries so council-style bosses can expose attackable members separately from activation/controller NPCs.
- Extended validation config/manifest generation and C++ route config loading/diagnostics for `BotWorld.ValidationRoute.AlternateTargetEntries`.
- Adjusted validation-route activation focus handling so a boss activation target is only remembered as the active focus when it is alive and attackable.
- Updated Omnotron route metadata to target an attackable golem entry with alternate golem entries while preserving controller `activation_action_entry=42186` / `activation_action_id=1`.
- Added focused pytest/static coverage for alternate route targets and the route-focus contract.

## Validation

- Full BWD route sequence `r4`: `artifacts/live_validation_instances/blackwing_descent_uninterrupted_full_clear_r4/report.json`.
  - Entry trash and Magmaw completed.
  - Omnotron failed; aggregate labels: `validation_route_death_loop`, `route_sequence_child_failed`.
- Focused Omnotron diagnostics:
  - `artifacts/live_validation_instances/run000079_omnotron_alt_targets/report.json`: no death loop, but emergency timeout; `boss_kill_evidence=161`, `pulls=161`, `interrupts=0`.
  - `artifacts/live_validation_instances/run000079_omnotron_activation_focus_fix/report.json`: no failure labels and no death loop; `boss_kill_evidence=30`, `pulls=30`, but `tank_positioning=0`, `target_priority=0`, `interrupts=0`.
  - `artifacts/live_validation_instances/run000079_omnotron_golem_route_focus_fix/report.json`: regressed to `validation_route_activation_no_engagement,no_progress_observed` with the golem route metadata.
- Focused tests passed:
  - `pixi run pytest tests/test_ml_pipeline.py::test_validation_scenario_manifests_link_routes_mechanics_and_provisioning tests/test_ml_pipeline.py::test_live_bot_validation_config_writes_alternate_route_targets tests/test_autonomy_pipeline_smoke.py::test_server_start_autonomy_enabled_by_default_contract tests/test_autonomy_pipeline_smoke.py::test_quest_first_portfolio_routing_surface -q`
- `cmake --build build --target worldserver -j2` passed after the C++ validation-route focus change.

## Blockers

`full_blackwing_descent_clear` remains `needs_followup`. The death-loop symptom is improved in focused Omnotron runs, but Omnotron still does not produce required live evidence for interrupts, target priority, and tank positioning. Runtime ML control remains disabled.

## Next Handoff Prompt

Continue from run 000079 / commit from this pass. Full BWD route sequence `artifacts/live_validation_instances/blackwing_descent_uninterrupted_full_clear_r4/report.json` now proves entry trash and Magmaw complete, then blocks at Omnotron. This pass added alternate route target support and Omnotron route metadata/focus fixes; focused evidence shows no death loop in `artifacts/live_validation_instances/run000079_omnotron_activation_focus_fix/report.json`, but it still lacks `tank_positioning`, `target_priority`, and `interrupts`. Next, debug Omnotron’s generic validation-route executor so it selects an actually attackable active golem after controller activation and records real tank/target/interrupt actions. Start with `src/server/game/Bots/BotWorldPopulationMgr.cpp` around `tryValidationRouteActivation`, `findAuthoritativeRouteFocusTarget`, and target-search results `target_seen_not_attackable` / `search_after_activation_no_focus`. Do not relax `validation_route_death_loop` or required evidence. After a focused Omnotron segment passes with no failure labels and required evidence, rerun the full BWD route sequence with the long budget.
