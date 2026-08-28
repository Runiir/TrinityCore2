# Magmaw Chainwielder central future-pack movement guard handoff

## Identity

- Source commit: `e06bccb086c9808669f753e25e84ca0c91cfc3d0`.
- Worldserver SHA-256: `1e88714baf69fc01c191b8003733d29008b58be230916aa65c18d244f5f5404f`.
- Scenario: `blackwing_descent_10n_magmaw_diagnostic`.
- Closed clean canary: `/tmp/trinity-magmaw-e06bccb086-canary102.XMMon8/run`.
- Report SHA-256: `6b3a7e0aa8d8a3369e7dfd3bfc73ebf4a913f483d36e2749c0515a1541fd6fde`.
- Combat-log SHA-256: `fdbc7a09c842fa750e592ab24c6fac257512d6ea13416a7032dfa0ac29f17856`.
- Worldserver-log SHA-256: `c979a759491653a402d84c752049d70cc65b1978237dfe84d15dd88cb8d3fbe4`.

## First broken edge

Generation 2 still owned `bwd.magmaw.chainwielder`, and the Chainwielder was
alive at `(-331.532,-71.326)`. The tanks and most of the raid settled around
`(-334.058,-65.336)`. Future Drudges 59 and 60 were already at approximately
`(-327.9,-63.0)`, only 6.5 to 7.8 yards away.

Drudge 60 landed the first future-pack melee hit on tank 30001 at timestamp
`1787952753550`. The Chainwielder continued receiving damage for more than 16
seconds afterward. This rules out a route-transition or post-kill ordering
race. Drudge engagement was caused by an unsafe live combat destination during
the Chainwielder node.

The previous repair guards `MoveBotToProfileRange` and the explicit patrol
combat anchor. Canary102 proves that another movement owner can still bypass
those caller-local checks. The route therefore remains nondeterministic: clean
canaries have cleared both trash packs, but this exact run admitted the future
pack and wiped all ten bots.

## Bounded repair contract

Move the existing future-trash destination admission rule to the shared
movement executor boundary for the active `ranged_patrol_to_anchor` contract.
All ordinary movement owners must reject destinations inside a later trash
pack's declared live/home clearance. Preserve safe destinations, native
recovery semantics, class rotations, encounter mechanics, route coordinates,
and completion-watchdog policy.

Prefer one low-complexity hard mask over additional caller-specific branches.
Add focused counterexamples for the recorded unsafe destination and a safe
Chainwielder combat point. Do not build, run a shard, modify databases, publish
evidence, or commit inside the specialist work unit. Keep every C/C++ file
below 1,000 physical lines.

## Matched verification

After root review, build the exact implementation commit under the guarded
fast4 resource policy and run a fresh completion-watchdog canary. Generation 2
must contain no entry-42362 damage. The route must then clear both Drudges and
reach Magmaw. The pending Bloodlust stale-cohort repair remains unverified
until a clean run reaches the boss.
