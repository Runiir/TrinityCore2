# Magmaw Canary40 future-encounter handoff

Canary40 ran exact source `8d6a453e4ed473cf0db496c45d73fd489785a34c` under the uncapped completion watchdog. It cleared the entrance regroup and Chainwielder, then failed closed after 426.296 seconds because Magmaw entered combat while the route still owned the Drudge pair. The worldserver exited normally, final forced diagnosis and trace passed, telemetry identity remained stable, forbidden assistance was absent, and cleanup removed every bot and lease.

## What Canary40 proved

The Canary39 movement-before-support repair materially improved the live result. All ten bots remained alive, both Drudges remained tank-owned, sixteen native Rushes were delivered, and the Drudges reached `21.4466%` and `22.3511%` health. Canary39 had already lost its first healer while both Drudges were above `42%`. The new result closes the death-loop symptom, but it is not an accepted Drudge or route clear because the next encounter contaminated generation 3 before terminal evidence.

## First actionable runtime edge

`drudge_recovery_path_enters_next_boss_activation_envelope`

At `1787733364325` and `1787733364729`, the two tanks submitted native complete paths to the declared recovery anchors. Their final forced positions were exactly `(-321.5, -30.0, 211.283429)` and `(-288.8, -43.0, 212.301)`. At `1787733365853`, while the route was still `bwd.magmaw.drudges`, generation 3, the first and only `validation_route_future_encounter_contamination` event recorded future target GUID `76`. The next node is the Magmaw encounter, whose target entries are `41570`, `42347`, `41806`, and `42321`. The next status changed Magmaw's boss-state slot from `0` to `1` while both Drudges were alive.

The recovery endpoints are only `17.7271` and `19.1097` yards from Magmaw's declared center `(-302.467, -31.7101)`. By contrast, the combat tank positions used safely during the same run are `26.2785` to `29.1912` yards away. The existing tank member anchors `(-295.0, -68.0, 213.05)` and `(-329.0, -60.0, 212.35)` are `37.0501` and `38.7855` yards from Magmaw and remain more than 15 yards from the declared Drudge homes.

The exact damage or proximity callback that first engaged Magmaw was not serialized, so do not claim a specific spell. The causal boundary is sufficient: the native recovery movement reached the only newly introduced positions, then the next boss entered combat within about 1.5 seconds.

## Bounded repair contract

- Reuse safe declared route geometry where possible. Prefer the existing tank member anchors over inventing new coordinates if the native Detour probe and full Drudge invariants accept them as recovery endpoints.
- Extend the deterministic navmesh parity probe so both replacement recovery paths must be complete, endpoint-exact, and floor-valid.
- Add a deterministic next-encounter exclusion check derived from the current node and immediate next node. Recovery endpoints and paths must remain no closer to the next encounter than the already live-proven safe combat geometry.
- Preserve two-tank separation, source-union safety, native Rush ownership, exact-roster reseparation, health sync, kill sync, same-tick healing, and independent set-and-forget movement.
- Update the source scenario and regenerate the canonical route dataset through the repository generator. Do not hand-edit generated identity or hashes.

Do not change Magmaw's aggro behavior, suppress native boss combat, reduce Drudge ranges or damage, force threat or victims, teleport, grant pathing or line of sight, reset an encounter synthetically, or manufacture a clear.

## Required implementation evidence

Focused tests must replay the Canary40 transition and reject the old recovery endpoints because they are closer to Magmaw than the known-safe combat boundary. They must accept the replacement endpoints only after the native Detour path, source-union, separation, and future-encounter checks all pass. Every touched C or C++ source/header must remain below 1,000 lines.

After root review and focused tests, commit the bounded repair, build that exact commit only through the coordinator, verify the frozen 10N roster and runtime identity, then run Canary41 under the completion watchdog. There is no fixed raid success timer. A full clear must be repeated once from fresh state before promotion.

## Immutable Canary40 evidence

- Source commit: `8d6a453e4ed473cf0db496c45d73fd489785a34c`
- Binary SHA-256: `619d44a5a8a4d8fff6a79ad9febd07b2e428f7dba56a608607c0db3dbd26590d`
- Build receipt: `/tmp/trinity-magmaw-8d6a453e4e-canary40-build.pE0Sko/worldserver-build-receipt.json`
- Build receipt canonical SHA-256: `7ec46a9e4f4dfeaaae4db0031e813aaffd46a8499320657f2ef7fac8112b8b90`
- Report: `/tmp/trinity-magmaw-8d6a453e4e-canary40.fNd0yX/canary40-run/capture/report.json`
- Report canonical SHA-256: `e71603d1714a4dd2c7c5661fb90504f207014c25bafdf9e6611b72f1da683133`
- Report file SHA-256: `13a8d5ea4776dc16db5a9a14dce0f417333d6f1de0520b24b33fe6c0a904b6ad`
- Raw trace SHA-256: `4a963ff4dae2d2fe7dbaabe3352cba09494aa0de83efe1bb7865ceecc62af8cb`
- Server log SHA-256: `7b4add0dc649da8a24431762aec73a6188b4f76f0623d7094db85f63563535d4`
- Scenario: `blackwing_descent_10n_magmaw_diagnostic`, difficulty `10N`, attempt `2`, route generation `3`
- Terminal result: `gameplay_failure`, `validation_route_future_encounter_contamination`
- Route result: entrance clear, Chainwielder clear, Drudges incomplete, Magmaw prematurely engaged
- Final alive roster: `10/10`
- Final Drudge health: `21.4466%`, `22.3511%`
- Delivered native Rushes: `16`
- First contamination timestamp: `1787733365853`
- Future target runtime GUID: `76`
- Final forced diagnosis and trace: passed
- Forbidden-assistance gate: passed
- Cleanup: passed, worldserver exit code `0`, zero bots and leases

This failed canary is diagnostic evidence only. Do not promote it as an accepted clear.
