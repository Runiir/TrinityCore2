# Magmaw Chainwielder melee future-pack guard handoff

## Identity

- Source and binary: commit `946f48e676d2db47469c96e72563e1baffea3ead`, SHA-256 `6d10bd97d44626581b683862196c53943fc955f56b61d5a125b1aa965c0962e5`.
- Scenario: `blackwing_descent_10n_magmaw_diagnostic`.
- Closed diagnostic replay: `/tmp/trinity-magmaw-map-at-trace.EejW3N/run`.
- Report SHA-256: `9e7c8cc1600d031e967ea7a398668f3c19c4ea806108ef58e60e749d9f6f7d81`.
- Combat-log SHA-256: `3be2217cbd9506bdabd69e65c69c0a255cb9fa9c4e5be84043fe039b753908ea`.

## First broken edge

During route generation 2, the Chainwielder node, tank `30001` reached `(-308.208,-64.122,212.863)`. Drudge `60` then landed the first future-pack melee hit at timestamp `1787949231950`. Both Drudges subsequently entered the Chainwielder fight and four bots died.

`MoveBotToProfileRange` currently applies `IsValidationRoutePatrolCombatPointSafe` to null-action and ranged destinations, but explicitly bypasses it for `action->AutoAttackMode == "melee"`. The recorded tank position proves that the melee bypass can carry a bot into the future-Drudge envelope.

## Bounded repair contract

Repair the patrol movement admission rule so explicit melee range movement cannot enter a future route pack during the Chainwielder node. Preserve ordinary melee closing inside the current pack's safe combat region and leave hazard escape, class rotations, encounter mechanics, route coordinates, and watchdog policy unchanged.

Add one focused counterexample for the recorded tank destination and one admissible current-pack melee destination. Do not build, run a shard, modify databases, publish evidence, or commit. Keep every C/C++ file below 1,000 physical lines.

## Matched verification

After root review and an exact build, rerun the complete Magmaw route with the completion watchdog. The route must show no Drudge damage at generation 2, then advance through both Drudges to Magmaw. A diagnostic exception interposer may be used only if the earlier `map::at` abort recurs; such a run is not acceptance evidence.
