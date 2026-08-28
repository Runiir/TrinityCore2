# Magmaw Canary 96 Chainwielder movement handoff

## Immutable input

- Runtime commit: `841512d64422e3ef310e3c4df3bfe7cfd30573eb`
- Scenario: `blackwing_descent_10n_magmaw_diagnostic`
- Report SHA-256: `6a77f7686589f73e1b7df0802cfc0a82dc4b726ad655067d3fe3086e899461f1`
- Heartbeat stream SHA-256: `0ac31afc6808fbc6914839e985bb0f742a8895ccf5cb45be9d02eeae3f2f7743`
- Historical attributable trace: Canary 02e worldserver output line 745

## Route result

The Chainwielder died, but the route remained on its Chainwielder node when a
Drakonid Drudge entered combat. The accidental Drudge pull wiped all ten bots.
The interrupted controller retained the report and heartbeat stream but did not
finalize a combat log, so this evidence is diagnostic and cannot certify a run.
The Magmaw parasite repair was not exercised.

## First broken edge

The attributable Canary 02e trace shows Elemental Shaman `30010` submitting a
`combat_range` point move to `(-310.569, -97.0254, 214.091)`. The native planner
accepted the move even though that point was 7.788 yards from a future Drudge.
`MoveBotToProfileRange` skipped `IsValidationRoutePatrolCombatPointSafe` when
the resolved action pointer was null. Canary 96 reproduced the same
Chainwielder-to-Drudge contamination under the current route identity.

## Accepted bounded repair

Commit `1f676f8d70` removes the null-action patrol-safety bypass. Explicit melee
actions retain their existing behavior. The recorded unsafe point is inside the
50-yard future-Drudge envelope, while the declared patrol combat anchor remains
outside it. Focused and adjacent validation passed: 20 tests.

## One-run verification contract

Build the exact clean authorized commit, freshly provision the same 10-player
Magmaw shard, and run one completion-watchdog canary. Verify that `30010` cannot
submit the recorded unsafe combat-range destination, the Chainwielder and
Drudges clear in order without future-encounter contamination, and ordinary
healing, offense, and lethal-hazard movement remain active. If the route reaches
Magmaw, also evaluate the already-authorized parasite policy. Return the first
new trace-backed edge if the run does not clear. Do not tune class damage from
this raid run.
