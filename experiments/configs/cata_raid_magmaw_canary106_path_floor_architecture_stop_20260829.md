# Magmaw Canary106 same-floor path architecture stop

## Immutable Canary106 identity

- Source commit: `052081b472abcf1706d863b3c9220f9d99101f9a`
- Worldserver SHA-256: `30794d8ceab5625428283cbed172d566fa9430cce33ce8e3756e7066edf9e8dd`
- Scenario: `blackwing_descent_10n_magmaw_diagnostic`
- Completion: `semantic_progress_plateau_watchdog` after 422 seconds
- Return code: `0`; timed out: `false`; worldserver absent after cleanup
- Report SHA-256: `8165bf57470d0aac82b9881bd1e881448f8ad479c4ec224da95e5938f8f3b437`
- Combat-analysis SHA-256: `121baddfc2d6b75c3661a38c1fdfcd6db86a7a3e02d60fcc4c02da5c1d140944`
- Combat-log SHA-256: `de15bbf1803f236daf2c33e39a404ff8b393c5d3829fbc66df369f1ed9e06bf6`
- Heartbeat SHA-256: `dd3337d69582f5bd7f2647533069e4c06bd3414c42177e40880b15dd51766af4`

## First causal edge

The raid killed the Chainwielder with no future-Drudge contamination. Nine
bots reached the declared terminal endpoint. Fire mage `Mgwdpsa` (`30006`)
remained 43.6772 yards away. Its progressive route movement request to
`(-333, -99, 214.154)` was rejected as
`route_destination_path_floor_gap`, even though the target-floor sample was
valid at `214.091` and the endpoint Z delta was only `0.0633392` yards.

The pack ledger correctly recorded one engaged member and one death. Route
completion then correctly required the full living cohort at the endpoint.
The planner rejection prevented the final mage from regrouping, so the route
could not advance to Drudges or Magmaw. This run did not exercise the parasite
lane. `magmaw_parasite_control_allows_player_infection` therefore remains at
nine occurrences.

## Combat receipt

The single Chainwielder encounter lasted 59.266 seconds, with 56 active damage
seconds. Party damage was `4,649,400`; active DPS was `83,025.000`; elapsed DPS
was `78,449.701`. Party healing was `74,656`; active HPS was `1,333.143`;
elapsed HPS was `1,259.677`. No bot died.

The Affliction warlock dealt `1,238,161` damage (`22,110.018` encounter DPS).
Its Felhunter dealt `199,106`, including six normal Shadow Bite events and
melee events. This capture contains no Fel Blood or Fel Intelligence cast
event and does not justify a PetAI special case.

## Recurrence audit

The exact runtime reason `route_destination_path_floor_gap` appears in 15
unique retained Magmaw reports. The last ten unique reports are the gate-bearing
architecture summary below. A token is counted at most once per run; intervening
successful route progress does not reset the count.

| Run | Completion | Seconds | Kills | Recorded owner or final witness |
| --- | --- | ---: | ---: | --- |
| `c1dafd4-autonomous.k0L7LY` | semantic plateau | 499 | 3 | 96 path-floor receipt contexts |
| `a66175a-autonomous.PJpg8H` | machine predicate | 345 | 3 | 3 path-floor receipt contexts |
| `5fed4889c4-autonomous.ZuqIk7` | process exit | 371 | 3 | hazard, tank `30002` |
| `31322fb541-canary97.boy3E8` | process exit | unavailable | 3 | combat-range mages and hazard hunter |
| `946f48e676-canary99.ADPeoJ` | process exit | unavailable | 3 | hazard, mage `30006` |
| `93fd8308b0-canary100.cIXN4o` | process exit | 402 | 3 | hazard, mages `30006` and `30007` |
| `gdb-canary101.5RrSiZ` | process exit | 361 | 3 | hazard, mages `30006` and `30007` |
| `a1fff71538-canary104.G772RN` | machine predicate | 714 | 3 | mechanic mage and hazard hunter |
| `902ff5545e-canary105.N6HWpF` | semantic plateau | 831 | 3 | 6 retained path-floor contexts |
| `052081b472-canary106.UHeDPn` | semantic plateau | 422 | 1 | route, mage `30006`, terminal cause |

## Read-only architecture review

The common hard gate is in `PlanMovementPath` in
`BotWorldPopulationMgrMovementPlanner.cpp`. It currently requires a complete
normal native path, a valid endpoint floor, and agreement from every
interpolated `GetHeight` sample. `DiagnoseNativePathFloors` in
`BotWorldPopulationMgrNativePathValidation.h` uses a 1.5-yard tolerance and
can resolve a different floor on multi-level geometry. That VMAP observation
then overrides an otherwise coherent native navmesh path.

The smallest owner-independent redesign is to separate native proof from floor
observation. Native proof must require the correct map/scope, a calculated
complete normal path, no forbidden path flags, an actual endpoint within a
bounded 3D tolerance of the request, and a valid endpoint floor. An
intermediate sampled-floor disagreement becomes a retained diagnostic conflict
when those native proofs pass, not an automatic rejection. Empty, incomplete,
shortcut, off-mesh, endpoint-mismatch, invalid-endpoint-floor, cross-map,
strict-descent, long-recovery, future-pack, and explicit actor/reference-floor
failures remain fail-closed.

The deterministic replay matrix must run that complete-path invariant for
`Route`, `CombatRange`, `Hazard`, and `Mechanic`; only validated incomplete-path
fallback may vary by owner. The Canary106 fixture is a 43.6772-yard progressive
Route path with a 0.0633392 endpoint Z delta and an intermediate sampled-floor
conflict. Telemetry must retain the actual native endpoint, endpoint distance,
path flags, target-floor result, first sample conflict, owner, route scope, and
an explicit `native_proof_admitted_floor_observation_conflict` verdict.

## Stop decision

This is not another encounter-policy work unit. The prior repair admitted only
short, same-floor `Mechanic` and `Hazard` movements of at most 20 yards. The
recurrence family also affects `Route` and `CombatRange` owners and longer
progressive movement. Continuing with owner- or distance-specific exceptions
would preserve the same architectural defect.

The occurrence limit is reached. Do not launch another Magmaw canary and do
not add another local movement exception. The next permitted work is a
read-only shared-planner architecture review that defines one owner-independent
same-floor proof, bounded progressive segmentation, deterministic replay
coverage across route/combat-range/hazard/mechanic owners, and explicit path
sample telemetry. Implementation requires a new approved bounded work unit
after that review.
