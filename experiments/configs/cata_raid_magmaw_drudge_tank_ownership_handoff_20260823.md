# Magmaw Drudge tank ownership handoff

## Closed run

- Scenario, runtime profile, and pool: `blackwing_descent_10n_magmaw_diagnostic`
- Build commit: `81c6986ec520240b6b2ba1577f345b3660c9cb31`
- Build tree: `3e952f7b15e89176f42c2eacae021bf2a113217c`
- Binary SHA-256: `65a23111b6b51580f4198dfee369f2fe1ec19a943ebc6569323489bf3c9e4af7`
- Build receipt: `/tmp/trinity-build-receipts-81c6986ec5/worldserver-build.json`
- Build receipt SHA-256: `81904c32318bd6b2b23c3b5377d21e77f29d370d86df9d5a5f325939af19fb1a`
- Report: `/tmp/trinity-magmaw-81c6986ec5/run2/report.json`
- Report file SHA-256: `1f9f7111923f1ab65b11c9808534e60be60c22ebe9c4de57a16ef1f000d44bd3`
- Canonical report SHA-256: `381361b372f1e6317de73df640c008b1fd5fbd72133180ea69162fc94ac453a3`
- Normalized trace SHA-256: `b4103d909a98fc2318c320b14ad892682ea009d940017b9664032cfe0e2dff0e`

The completion-watchdog run ended at 282.453 seconds with
`gameplay_failure / death_loop_watchdog`. The Chainwielder cleared and the
route advanced to `bwd.magmaw.drudges`, generation 3. Cleanup passed with the
worldserver absent, zero bots, zero leases, and no forbidden assistance.

## First broken edge

The Magmaw target-overwrite repair is confirmed. GUID 39 and
`future_encounter_target_forbidden` were absent after the route entered the
Drudge node. The live Drudges were GUIDs 59 and 60, entry 42362.

Both tanks selected their assigned Drudge and their normal taunt. The recorded
combat gates reported a live attackable target, known spell, sufficient power,
legal range, and line of sight. Native submission still returned `no_action`:

- tank 30001: spell 62124 on GUID 59;
- tank 30002: spell 56222 on GUID 60.

The trace kept `tank_owned_hostile_guids=[]`. Native Rush selected DPS 30007
and later DPS 30009. The threat seed closed with `failure=true` and
`complete=false`. Five bots died; the final three deaths triggered the
watchdog.

Source review explains the result. Adaptive encounter ownership returns
`adaptive_drudge_owns_live_pack` before `TryValidationRouteObjectiveGate()`
can call `ConfigureValidationRouteCombatAuthority()`. This can carry an
all-offense suppression flag from the preceding route node into adaptive
combat. Positive healing remains legal, but `TryCastCombatSpell()` and
`BotActionExecutor::ExecuteCombat()` reject taunts and attacks as `no_action`.

## Bounded implementation work unit

Owner: `raid-bot-runtime-implementation`.

Refresh current-route combat authority before an adaptive encounter owner
skips the legacy route action. Preserve terminal, recovery, contamination,
future-encounter, and native spell checks. Do not force threat, cast a spell
triggered, alter Drudge AI, teleport, revive, or manufacture an encounter
outcome.

Add a deterministic regression proving that an adaptive-owned live node clears
stale ordinary route suppression before the normal taunt/profile candidates
run, while terminal or recovery gates remain closed earlier in the update
lifecycle. Return a single matched live verification plan requiring both tanks
to submit native taunts or ordinary threat actions and obtain one assigned
Drudge victim each.

The live verifier remains completion-watchdog driven. It has no fixed success
timer and must terminate only on clear, semantic no-progress, repeated
decisions, excessive deaths, infrastructure loss, contamination, or explicit
interruption.

## Implemented repair

Commit `a4cde51ec11dabae0bf54f1085abd20987a38f80` refreshes current-route
combat authority before the decision kernel resolves an adaptive-owned node.
The refresh removes an inherited all-offense hold and keeps the declared next
encounter protected. Terminal and native-recovery holds return before this
candidate-submission boundary.

Changed runtime and regression files:

- `src/server/game/Bots/BotWorldPopulationMgrUpdateBotKernelFallback.cpp`
- `tests/test_bot_route_combat_target_policy.py`

The focused suite passed 34 tests:

```text
pixi run pytest -q tests/test_bot_route_combat_target_policy.py tests/test_bot_world_population_mgr_validation_authority_module.py tests/test_bot_action_arbitration.py tests/test_raid_workloop.py
```

The fallback module is 625 lines. No live build or shard has verified this
native change yet. The next owner is `raid-shard-architecture`: build the exact
clean commit through the queued coordinator, provision a fresh exact roster,
and run one completion-watchdog shard. Confirm both assigned tanks submit
normal native taunts or trained threat actions, each Drudge takes its assigned
tank as victim, the Drudges clear, and the route advances. If the run reaches a
later edge, route that new trace-backed edge rather than tuning this hypothesis
again.
