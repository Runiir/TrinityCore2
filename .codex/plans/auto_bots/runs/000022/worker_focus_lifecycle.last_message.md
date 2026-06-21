Findings and proposed fix:

1. **Route activation fallback does not persist authoritative focus**
   In [BotWorldPopulationMgr.cpp](/home/runiir/Games/trinity-cata/src/server/game/Bots/BotWorldPopulationMgr.cpp:5941), `rememberValidationRouteFocus` stores `_validationRouteFocusGuid/_Entry/_MapId/...`, but `tryValidationRouteActivation` at [5955-6062](/home/runiir/Games/trinity-cata/src/server/game/Bots/BotWorldPopulationMgr.cpp:5955) never calls it after resolving or summoning `activationTarget`.

   This matches the observed loop: activation succeeds, `_validationRouteActivationApplied` becomes true, but followers later enter the no-focus path at [6750-6793](/home/runiir/Games/trinity-cata/src/server/game/Bots/BotWorldPopulationMgr.cpp:6750), repeatedly recording `boss_route_no_focus_activation_already_applied` and `hold_anchor_no_focus`.

   Proposed fix:
   - Capture `rememberValidationRouteFocus` in `tryValidationRouteActivation`.
   - After `activationTarget` is resolved and before returning true, persist focus when it is the configured route script target:
     - `isValidationRouteScriptTarget(activationTarget->ToCreature())`, or
     - fallback-summoned `_config.ValidationRouteTargetEntry`.
   - Also set `state.TargetGuid = activationTarget->GetGUID()` when it is attackable/alive, so the activating bot can immediately seed cohort focus.

2. **Authoritative focus recovery cannot work if only configured target entry exists**
   `findAuthoritativeRouteFocusTarget` at [6161-6264](/home/runiir/Games/trinity-cata/src/server/game/Bots/BotWorldPopulationMgr.cpp:6161) only accepts a focus matching `_validationRouteFocusGuid` or `_validationRouteFocusEntry`. If activation fallback never seeded `_validationRouteFocusEntry`, configured `ValidationRouteTargetEntry` is not enough.

   Proposed fix:
   - In `usableFocus`, accept `_config.ValidationRouteKind == "boss"` plus creature entry equal to `_config.ValidationRouteTargetEntry` as authoritative when route activation has been applied.
   - Keep the persisted focus as primary; use config target entry as fallback.

3. **No-focus branch should try to reacquire configured boss target after activation**
   The no-target branch at [7153-7194](/home/runiir/Games/trinity-cata/src/server/game/Bots/BotWorldPopulationMgr.cpp:7153) resets stale activation after misses, but does not perform a focused reacquire using persisted/configured entry before deciding “activation no visible target”.

   Proposed fix:
   - Before incrementing `ValidationRouteTargetSearchMissCount`, try `findLastKnownFocusTarget()` or an equivalent configured-entry scan around route anchor.
   - If found, set `routeTarget`, `state.TargetGuid`, and `rememberValidationRouteFocus(routeTarget)`.

4. **Evidence aggregation is trace-window fragile for boss kills**
   In [run_live_bot_validation.py](/home/runiir/Games/trinity-cata/tools/bot_ml/run_live_bot_validation.py:829), `kills` uses status/summary plus trace events, but `boss_kill_evidence` at [835-840](/home/runiir/Games/trinity-cata/tools/bot_ml/run_live_bot_validation.py:835) ignores `status["raid_boss_kills"]`; it only reads summary and current trace window. If the final trace window rolls off `boss_killed` and summary is missing/incomplete, `boss_kill_evidence` becomes 0.

   Proposed fix:
   - Include `status.get("raid_boss_kills")`, `status.get("boss_kills")`, and `status.get("heroic_raid_boss_kills")` in `boss_kill_evidence`.
   - Consider diagnosis evidence counters if `.botauto diagnose` exposes boss kill evidence.
   - In `route_sequence_report` at [1881-1889](/home/runiir/Games/trinity-cata/tools/bot_ml/run_live_bot_validation.py:1881), aggregate more evidence fields, especially `boss_engagement_actions`, `boss_kill_evidence`, `kills`, `action_counts`, and `result_counts`, not just route actions.

Focused tests to change/add:
- Add a C++ smoke/string test in `tests/test_autonomy_pipeline_smoke.py` asserting `tryValidationRouteActivation` calls `rememberValidationRouteFocus` after fallback target resolution.
- Add a smoke test that `findAuthoritativeRouteFocusTarget` accepts configured `ValidationRouteTargetEntry` when activation is already applied.
- Add Python tests in `tests/test_ml_pipeline.py`:
  - status has `raid_boss_kills: 3`, final trace has only hold-anchor/no-focus entries, report still has `boss_kill_evidence == 3`;
  - route sequence aggregate preserves summed `boss_kill_evidence` and `boss_engagement_actions` from segment reports.