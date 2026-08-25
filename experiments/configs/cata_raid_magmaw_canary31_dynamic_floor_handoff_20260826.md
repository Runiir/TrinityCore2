# Magmaw Canary31 dynamic floor handoff

Canary31 ran the exact clean `8f916f9792e9c937204d5e09e93294c98957ae10` tree with the coordinator-built binary. It cleared the entrance regroup and Chainwielder, then failed closed on the Drudge node after 470.324 seconds. The worldserver exited normally and cleanup proved zero bots and leases. No teleport, forced threat, forced resurrection, encounter-state mutation, or other forbidden assistance was observed.

## What the prior repair proved

The positive self-target range repair worked. Holy paladin `30004` used Divine Favor (`31842`) as a positive self action. The retained trace has no `native_self_centered_range` or `native_self_centered_path_rejected` event. Do not reopen that hypothesis. The route also retained the prior safe-member offense behavior, and native Rush sequences 1 through 4 each recorded exact ten-player reseparation.

## First broken edge

`dynamic_drudge_recovery_candidates_are_rejected_when_map_height_selects_a_remote_collision_layer_even_though_the_candidate_is_group_safe_and_the_native_path_has_not_been_tested_at_the_declared_floor`

Rush sequence 5 was the first observation without exact-roster reseparation. Fire mage `30007` repeatedly produced group-safe candidates whose two-dimensional source, lane, and peer-spacing predicates all passed, but `ResolveDynamicCandidateZ()` resolved their floor around `-133` to `-145` while the encounter floor and declared anchor were around `214`. Those candidates were immediately rejected as `drudge_anchor_floor_rejected` before their native path could be evaluated at the declared floor.

The first concrete example is at `1787700121348`. Candidate 1 was `(-282.846, -68.2321)`, with every group predicate true, but its resolved Z was `-138.287`; candidates 2 and 3 failed the same way at `-133.363` and `-141.592`. The only candidates left on the encounter floor were source-unsafe or peer-spacing-unsafe. The same pattern repeated at `1787700142364`, where three group-safe candidates resolved to `-139.981` through `-145.309` and were rejected before path admission.

`30007` then cycled through `drudge_anchor_lane_unsafe`, `drudge_anchor_spacing_unsafe`, `drudge_tank_recovery_anchor_strict_path_rejected`, and repeated reseparation movement. It died at `1787700162083`. Restoration druid `30003` and fire mage `30006` later died, so the completion watchdog stopped the run at three deaths with seven survivors. The Drudges remained alive and Magmaw was not reached.

## Source diagnosis

`BotRaidDrudgeNativeAnchor::ResolveFloorZ()` asks `Map::GetHeight()` for a floor near the declared encounter Z, but the returned static collision height can still be a remote lower layer. `ResolveDynamicCandidateZ()` correctly rejects the large delta, yet that rejection also prevents `StrictNativePath()` from testing the same two-dimensional candidate at the known encounter-floor Z. `StrictNativePath()` repeats the same height lookup before its stronger complete-path, floor-continuity, source-union, and exact-end checks.

The receipt proves the two-dimensional candidate was safe. It does not authorize accepting a missing floor or bypassing native path validation. The repair must preserve the known encounter-floor reference as a bounded fallback only when native path validation independently proves the endpoint and full path on that floor.

## Bounded repair contract

Implement one shared native-floor hypothesis:

- Keep a near-declared native height result when it is finite and within the existing tolerance.
- When height lookup returns a remote stacked-collision layer, allow the declared/reference Z to proceed only through the existing complete native-path, path-floor, source-union, and exact-end gates.
- Reject the candidate if the native path cannot prove the declared/reference endpoint. Do not clamp an arbitrary Z, skip path validation, or accept an incomplete route.
- Use one shared floor-admission contract from dynamic candidate materialization and strict path validation so the two call sites cannot disagree.
- Add deterministic coverage for a near-declared floor, a remote lower layer with a valid declared-floor native path, and a remote layer whose declared-floor path is invalid.
- Keep every C and C++ source/header below 1,000 lines. Split by concern if needed.

Do not hard-code Magmaw coordinates, reduce source or lane distances, weaken peer spacing, teleport, force movement or threat, revive bots, manufacture damage, or alter native encounter state.

## Immutable Canary31 evidence

- Source commit: `8f916f9792e9c937204d5e09e93294c98957ae10`
- Source tree: `080a4adc5cef55f15c366fbbe56d962dff9d6bb3`
- Binary SHA-256: `377f237c62fab767c5c7cb0ac8ec2ff2415aea57bbe2a36673f2335dad2d41e9`
- Build receipt: `/tmp/trinity-magmaw-8f916f9792-build.0niEdV/worldserver-build-receipt.json`
- Build receipt canonical SHA-256: `d8c151b2b3b7454523db7874197e4f378338f08a04c32de1b10c404976102067`
- Build receipt file SHA-256: `c20258e95584c1a0a3f622ec3db2f1be4a63daf53d0ade0f90712c79f07c11ee`
- Config SHA-256: `4214c5f8c1385ca34ef4fd877c04367a7e07c083db4fa6359853d9059799bd06`
- Report: `/tmp/trinity-magmaw-8f916f9792-canary31.GR4fFT/canary31-run/capture/report.json`
- Report canonical SHA-256: `af656af00a77166776e1800a9faaa6e7a3120f4b128506db9426d2998f110508`
- Report file SHA-256: `7ac7eaf942d9aefd0efd24a4ec03a81709750b31a1cedad1caaf535472c594e5`
- Raw trace SHA-256: `914a850dce9d339d17ab3feedb60a5ee1ce5ef3ca2d107b43f29243334a25617`
- Server log SHA-256: `fc0215dd8a2006105d2d2222dbdbaad7991508704a65dc7c91afa0e8ec73b1de`
- Server epoch: `5566588161289347`
- Attempt: `2`
- Route scope: generation `3`, node `bwd.magmaw.drudges`
- Terminal: `gameplay_failure`, `death_loop_watchdog`, three deaths, seven survivors
- Native Rushes: 20 delivered, sequences 1 through 4 with exact-roster reseparation, sequence 5 first missing
- First death: GUID `30007` at `1787700162083`
- Later deaths: GUID `30003` at `1787700301162`, GUID `30006` at `1787700302168`
- Evidence demultiplexing: passed, 166 retained and bound rows, zero rejected rows
- Forbidden-assistance gate: passed
- Cleanup: passed, worldserver exit code 0

The next owner is `raid-bot-runtime-implementation`. It may implement this one floor-admission edge and run focused tests only. A separate coordinator must review the patch, obtain an exact queued build receipt, provision a fresh roster, and run Canary32 under the completion watchdog.
