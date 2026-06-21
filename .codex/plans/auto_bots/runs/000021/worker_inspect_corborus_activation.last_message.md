**Technical Report**

No files modified.

`advance_to_boss_route_no_focus` is emitted in [src/server/game/Bots/BotWorldPopulationMgr.cpp](/home/runiir/Games/trinity-cata/src/server/game/Bots/BotWorldPopulationMgr.cpp:6737), inside `BotWorldPopulationMgr::TryValidationRouteObjective`, on the non-tank follower path when:

- no group focus target is available,
- a dungeon anchor exists,
- the bot is close enough to the anchor,
- `_config.ValidationRouteKind == "boss"`,
- `routeDistance > 12.0f`.

The activation attempt is only made earlier in that same block if this guard passes:

[src/server/game/Bots/BotWorldPopulationMgr.cpp](/home/runiir/Games/trinity-cata/src/server/game/Bots/BotWorldPopulationMgr.cpp:6767)

```cpp
if (_config.ValidationRouteKind == "boss"
    && hasValidationRouteActivation
    && !_validationRouteActivationApplied)
```

So the code can record `advance_to_boss_route_no_focus` without recording either `validation_route_activation` or `boss_route_no_focus_activation_unavailable` when `_validationRouteActivationApplied` is already true. In that case the whole activation/unavailable block is skipped, and execution falls through to the route advance event at line 6783.

The confusing part is that diagnosis reports per-bot state fields:

[src/server/game/Bots/BotWorldPopulationMgr.cpp](/home/runiir/Games/trinity-cata/src/server/game/Bots/BotWorldPopulationMgr.cpp:11583)

```cpp
state.ValidationRouteActivationApplied
state.ValidationRouteActivationAttempts
```

Those fields are only synced inside `tryValidationRouteActivation`:

[src/server/game/Bots/BotWorldPopulationMgr.cpp](/home/runiir/Games/trinity-cata/src/server/game/Bots/BotWorldPopulationMgr.cpp:5966)

If the global `_validationRouteActivationApplied` latch is already true before this bot enters the no-focus branch, the guard prevents calling `tryValidationRouteActivation`, so this bot’s diagnosis can still show `validation_route_activation_applied=false` and `validation_route_activation_attempts=0` while the branch skips unavailable telemetry.

Config loading/generation is not the apparent source for this report. `LoadConfig` reads all activation fields in [src/server/game/Bots/BotWorldPopulationMgr.cpp](/home/runiir/Games/trinity-cata/src/server/game/Bots/BotWorldPopulationMgr.cpp:996). `write_validation_config` writes them from the route manifest in [tools/bot_ml/run_live_bot_validation.py](/home/runiir/Games/trinity-cata/tools/bot_ml/run_live_bot_validation.py:203). The generated report config contains Corborus:

- `BotWorld.ValidationRoute.TargetEntry = 43438`
- `BotWorld.ValidationRoute.ActivationDataId = 10`
- `BotWorld.ValidationRoute.ActivationDataValue = 1`

That means `hasValidationRouteActivation` should be true at [src/server/game/Bots/BotWorldPopulationMgr.cpp](/home/runiir/Games/trinity-cata/src/server/game/Bots/BotWorldPopulationMgr.cpp:6393).

**Smallest Useful Next Fix**

In the no-focus boss branch, sync/report the global activation latch before advancing. Minimal code fix:

- If `_validationRouteActivationApplied` is already true, copy `_validationRouteActivationApplied` and `_validationRouteActivationAttempts` into `state`.
- Record a recovery/target-search event such as `activation_applied_no_visible_target` before `advance_to_boss_route_no_focus`.

This will distinguish “activation already applied but no visible target/focus” from “activation unavailable” and make diagnosis counters match the actual global route state.

A smaller diagnostic-only fix would add global activation evidence to `BuildBotDiagnosisObjectJson`, but that would not explain the missing target/focus in trace as clearly.

**Tests To Run**

Use pixi per repo instructions:

```bash
pixi run pytest tests/test_autonomy_pipeline_smoke.py -k "validation_route"
pixi run pytest tests/test_ml_pipeline.py -k "validation_route_activation or validation_route_boss_attempt or route_directed_boss_no_focus"
```

For live validation after the fix, rerun the Corborus route with the long route-directed budget, not a 90s smoke:

```bash
--observe-sec 300 --timeout-sec 900
```