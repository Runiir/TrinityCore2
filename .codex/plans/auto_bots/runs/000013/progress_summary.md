# Run 000013 Progress Summary

## Scope

Continued from run 000012 / commit 8c748eac6f. Focused on the Stonecore 5N entrance validation blocker where the group killed one prerequisite pack and then looped in validation-route anchor/focus recovery.

No worker or reviewer Codex sessions were launched in this pass. The work was handled directly because the task was a focused route-state fix with local tests and long validation.

## Code Changes

- Tightened validation-route killed-focus cleanup in `src/server/game/Bots/BotWorldPopulationMgr.cpp`.
  - Confirmed route-progress kills now clear cohort target/focus memory as before.
  - Added cohort cleanup for `ValidationRouteAnchorOverrideValid`, `ValidationRouteAnchorOverrideUntilMs`, `ValidationRouteAnchorOverrideReason`, and `RecentDeathCount` so a confirmed route kill releases stale safe-memory/death-loop anchors.
- Added active-combat focus gating around validation-route safe-memory anchor selection.
  - If the bot, its victim, or the tank focus has a usable validation-route combat target, safe-anchor overrides are cleared.
  - `validation_route_safe_memory_after_danger` is only selected when there is no active route combat intent.
- Extended `tests/test_autonomy_pipeline_smoke.py` static smoke coverage for the new route cleanup and active-combat anchor guard.

## Validation

- `pixi run pytest tests/test_autonomy_pipeline_smoke.py -q`
  - Passed: 14 passed in 0.15s.
- `cmake --build build --target worldserver -j2`
  - Passed: `worldserver` built successfully.
- Long Stonecore entrance validation:
  - Command used `pixi run bot-live-validate --duration-policy completion-watchdog --observe-sec 300 --timeout-sec 900` with validation provisioning and bot-pool reset.
  - Artifact: `artifacts/live_validation_instances/stonecore_entrance_route_progress_reset_r1/report.json`
  - Result: failed with `failure_labels=["validation_route_stuck_loop"]`.
  - Evidence: kills=1, final-window trash_pulls=0, validation_route_actions=16, stuck_events=33, route_reason=`validation_route_safe_memory_after_danger`.
- Long Stonecore entrance validation after active-combat safe-anchor guard:
  - Artifact: `artifacts/live_validation_instances/stonecore_entrance_active_combat_anchor_guard_r1/report.json`
  - Result: failed with `failure_labels=["validation_route_stuck_loop"]`.
  - Evidence improved: kills=4, final-window trash_pulls=0, validation_route_actions=16, regrouping_evidence=10, stuck_events=17.
  - Final diagnosis: `repeated_decision_loop`, current_action=`move_to_validation_route_anchor`, blocker=`same_decision_fingerprint_repeating`.
  - Final route reason still returned to `validation_route_safe_memory_after_danger` after active targets were gone.

## DVC

Generated validation artifacts were checkpointed with DVC:

- `artifacts/live_validation_instances/stonecore_entrance_route_progress_reset_r1.dvc`
- `artifacts/live_validation_instances/stonecore_entrance_active_combat_anchor_guard_r1.dvc`

## Current Blocker

The route behavior improved from 1 recovered kill to 4 recovered kills, but the entrance segment still does not maintain final-window pull evidence. After clearing multiple prerequisite targets, the group falls back to safe-memory anchor regrouping with no focus:

- `validation_route_regroup`
- `follow_anchor_no_focus`
- `move_to_validation_route_anchor`
- `validation_route_safe_memory_after_danger`

This suggests the next fix should advance or terminate the entrance route after enough prerequisite kills, or make the tank reacquire the next route target/prerequisite instead of allowing no-focus safe-memory regrouping to dominate after combat targets disappear.

## Next Handoff Prompt

Continue from run 000013. The pass committed route-progress cleanup and active-combat safe-anchor suppression, then DVC-tracked two long Stonecore entrance validations. Key artifacts:

- `artifacts/live_validation_instances/stonecore_entrance_route_progress_reset_r1/report.json`: still failed `validation_route_stuck_loop`, kills=1, final-window trash_pulls=0, route_reason=`validation_route_safe_memory_after_danger`.
- `artifacts/live_validation_instances/stonecore_entrance_active_combat_anchor_guard_r1/report.json`: improved to kills=4 and stuck_events=17, but still failed `validation_route_stuck_loop`; final diagnosis is `repeated_decision_loop`, current_action=`move_to_validation_route_anchor`, route_reason=`validation_route_safe_memory_after_danger`, final trace is `follow_anchor_no_focus` / `move_to_validation_route_anchor`.

Inspect the active-combat-anchor report trace around target IDs 9, 14, 29 and route destination `920.382,963.89,316.865`. The likely next fix is to make Stonecore entrance route progression consume/complete a trash segment after enough prerequisite kills or after the source-entry route target is no longer reachable, then force tank route target search from the canonical route anchor instead of following safe-memory anchor with no focus. Rerun the same long Stonecore entrance validation after the fix before attempting segment/full-clear validation.
