# Run 000080 Progress Summary

## Scope

Continued the Blackwing Descent full-clear validation lane from run 000079. No worker or reviewer Codex sessions were launched in this pass; the orchestrator handled the focused C++ route-executor change, build/test validation, and live Omnotron checks directly.

## Changes

- Split validation-route entries into activation/script entries and combat target entries so an Omnotron controller entry cannot become an authoritative combat focus when alternate golem entries exist.
- Tightened `routeUsableCombatTarget` so route focus references must be valid attack targets before they can drive tank/assist targeting.
- Added post-activation combat-ready handling for visible alternate boss route targets, preserving generic route targeting while avoiding fake completion evidence.
- Removed blocked/dead script-target teacher kill accounting; blocked and dead route targets now remain recovery/search evidence instead of producing `boss_killed` evidence.
- Updated static smoke coverage to assert the new combat-entry split and post-activation target-ready path rather than the removed fake-kill labels.

## Validation

- `cmake --build build --target worldserver -j2` passed after the final code state.
- Focused pytest passed:
  - `pixi run pytest tests/test_ml_pipeline.py::test_validation_scenario_manifests_link_routes_mechanics_and_provisioning tests/test_ml_pipeline.py::test_live_bot_validation_config_writes_alternate_route_targets tests/test_autonomy_pipeline_smoke.py::test_server_start_autonomy_enabled_by_default_contract tests/test_autonomy_pipeline_smoke.py::test_quest_first_portfolio_routing_surface -q`
- Focused Omnotron live validation:
  - `artifacts/live_validation_instances/run000080_omnotron_combat_focus/report.json`
  - Result: `boss_attempt_no_kill,no_progress_observed`.
  - Improvement over run 000079 best: no fake boss kills, no death loop, real evidence for pulls, tank positioning, target priority, and interrupts.
  - Evidence counts: `pulls=10`, `tank_positioning=11`, `target_priority=9`, `interrupts=4`, `boss_engagement_actions=10`, `boss_kill_evidence=0`, `teacher_assisted_kills=0`.
- Reverted-regression evidence:
  - `artifacts/live_validation_instances/run000080_omnotron_combat_focus_r2/report.json`
  - Result: `validation_route_activation_no_engagement,no_progress_observed`.
  - This documents that triggering the visible route target's default `DoAction(0)` after controller activation regressed engagement; that line was removed before the final build.

## Blockers

`full_blackwing_descent_clear` remains `needs_followup`. Omnotron now reaches real engagement evidence, target priority, tank positioning, and interrupts, but does not complete a boss kill. The likely next issue is active golem health/progress completion after the first engagement window, not route-target selection or evidence capture. Runtime ML control remains disabled.

## Next Handoff Prompt

Continue from run 000080 / commit from this pass. Full BWD still blocks at Omnotron. This pass fixed fake boss-kill evidence and separated controller activation from attackable golem focus; best focused evidence is `artifacts/live_validation_instances/run000080_omnotron_combat_focus/report.json`, which now has real Omnotron engagement (`boss_engagement_actions=10`, `pulls=10`, `tank_positioning=11`, `target_priority=9`, `interrupts=4`, no death loop, no teacher-assisted kills) but fails `boss_attempt_no_kill,no_progress_observed` with `boss_kill_evidence=0`. The attempted `DoAction(0)` target-activation nudge regressed to no engagement and was reverted; see `artifacts/live_validation_instances/run000080_omnotron_combat_focus_r2/report.json`. Next, debug why engaged Omnotron golems do not lose enough health or trigger the existing `boss_route_no_health_progress`/terminal path after real boss actions. Start in `src/server/game/Bots/BotWorldPopulationMgr.cpp` around `maybeValidationPrerequisiteNoProgressAssist`, `recordValidationRouteBossKill`, current-combat boss action handling, and validation target health/progress counters. Do not reintroduce fake blocked/dead target boss kills and do not relax required evidence. After a focused Omnotron segment passes with no failure labels and required evidence plus boss kill evidence, rerun the full BWD route sequence with the long budget.
