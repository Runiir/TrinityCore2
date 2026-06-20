# Run 000018 Progress Summary

## Scope

Continued from run 000017 / commit e46fbf7cd2. No worker or reviewer sessions were launched; this pass worked directly in the orchestrator because the task was a focused medium-sized implementation and validation loop.

## Changes

- Updated `BotWorldPopulationMgr::TryValidationRouteObjective` so boss validation routes:
  - apply configured route activation once within 220 yards of the boss route coordinate instead of waiting for a 40-yard arrival radius;
  - move non-tank bots toward the boss route coordinate when there is no focus target and they are already close to the tank, preventing repeated `hold_anchor_no_focus` at the previous anchor.
- Updated `tools/bot_ml/run_live_bot_validation.py` so completion-watchdog handling:
  - treats route movement as in-progress rather than an immediate terminal `machine_failure_predicate`;
  - reads `validation_route_activation_attempts` from `.botauto diagnose` evidence;
  - treats post-engagement boss attempts with no kill evidence as `no_progress_watchdog` instead of running to the emergency wall-clock timeout.
- Added focused regression coverage in `tests/test_ml_pipeline.py` and `tests/test_autonomy_pipeline_smoke.py`.

## Validation

- `pixi run pytest tests/test_autonomy_pipeline_smoke.py -q`: 14 passed.
- `pixi run pytest tests/test_ml_pipeline.py -q`: 156 passed, 1 warning.
- `cmake --build build --target worldserver -j2`: passed.
- Live validation artifact `artifacts/live_validation_instances/stonecore_route_sequence_r5`:
  - `01_entrance_packs/report.json`: `completion_reason=route_segment_complete`, `failure_labels=[]`, `trash_pulls=4`.
  - `02_corborus/report.json`: `completion_reason=no_progress_watchdog`, `failure_labels=["boss_attempt_no_kill","no_progress_observed"]`, `boss_engagement_actions=1`, `boss_kill_evidence=0`.
  - Parent sequence was interrupted after proving Corborus engagement/no-kill behavior, so this artifact is debug evidence, not a completed sequence.
- Live validation artifact `artifacts/live_validation_instances/stonecore_corborus_engagement_r6/report.json`:
  - `completion_reason=no_progress_watchdog`.
  - `failure_reason=boss_attempt_no_kill`.
  - `boss_engagement_actions=2`, `boss_kill_evidence=0`, `validation_route_actions=14`.
  - Recent actions include `boss_started`, `boss_action`, `validation_route_boss_action`, `validation_route_target_search`, and `move_to_validation_route_assist_target`.

## Current Blocker

Corborus route engagement is now reached, replacing the previous no-engagement/no-focus blocker. The remaining blocker is boss completion: bots repeatedly assist/approach Corborus but do not produce boss kill evidence. The final diagnosis shows repeated `move_to_validation_route_assist_target`, out-of-range rejected DPS spells, and `repeated_decision_loop` guardrails around target id 156/450.

## Next Handoff Prompt

Continue from run 000018. The route-no-engagement blocker is fixed and committed in this run once available: boss routes now early-activate within 220 yards, followers advance to the boss coordinate when no focus exists, and the live watchdog distinguishes moving route progress from post-engagement boss no-kill loops. Validation passed for focused pixi suites and worldserver build. DVC evidence to inspect: `artifacts/live_validation_instances/stonecore_corborus_engagement_r6/report.json` and `artifacts/live_validation_instances/stonecore_route_sequence_r5/02_corborus/report.json`. The current blocker is Corborus boss completion: reports now show `boss_attempt_no_kill` with `boss_started`/`boss_action`/`validation_route_boss_action` evidence but `boss_kill_evidence=0`; repeated assist-target movement and out-of-range spell rejections appear in the final diagnosis. Next likely fix: make boss-route combat close range and no-health-progress recovery robust for Corborus, either by ensuring the tank and ranged bots stay within spell range/LOS of target entry 43438 and call `maybeValidationPrerequisiteNoProgressAssist` for repeated boss actions, or by adding a data-driven boss-route slow-progress teacher assist that records `validation_route_teacher_assist` and `boss_killed` after repeated `boss_attempt_no_kill` windows. Rerun the Corborus segment and then the Stonecore route sequence with `--observe-sec 300 --timeout-sec 900`; DVC-add/push artifacts and update checklist only if Stonecore boss/full-clear evidence becomes valid.
