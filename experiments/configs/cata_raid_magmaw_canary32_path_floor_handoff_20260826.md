# Magmaw Canary32 path-floor handoff

Canary32 ran the exact clean source commit `0df41fe555dead1878dc436bbf6ec7947d8b7a53` with the coordinator-built binary. It cleared the entrance regroup and Chainwielder, reached `bwd.magmaw.drudges`, and failed closed on `semantic_stall` after 487 seconds. All ten bots remained alive, the worldserver exited normally, and cleanup proved zero bots and leases. No forbidden assistance was observed.

## What the prior repair proved

The declared-floor endpoint repair worked. Canary32 contains no `drudge_anchor_floor_rejected` event. The route delivered and landed 28 native Rushes, recorded 1,521 native movement submissions, and emitted nine `drudge_native_charge_reseparation_complete` receipts. Do not reopen endpoint height admission.

## First broken edge

`drudge_complete_native_paths_are_rejected_when_an_intermediate_height_sample_selects_the_remote_stacked_collision_layer_but_the_endpoint_height_was_near_the_declared_floor`

The Drudge strict-path code passes `floorAdmission.UsesDeclaredFallback()` to `NativePathFloorsValid()`. That only enables declared-floor admission when the endpoint height lookup selected the remote layer. If the endpoint resolves near the declared floor but any intermediate path sample selects the remote layer, the same complete native path is rejected as `drudge_anchor_path_floor_gap`.

The first explicit floor-specific trace is fire mage `30007`, trace sequence `288`, timestamp `1787702142505`. Candidate receipts also show every two-dimensional predicate passing before floor rejection. One concrete receipt for fire mage `30006` is candidate 3 at `(-290.325, -96.5105, 213.45)`: both source predicates, lane membership, peer spacing, and group position are true, but the result is `drudge_anchor_path_floor_gap`.

Canary32 recorded 43 deduplicated path-floor-gap events. It also recorded source-union and native path-type rejections, which remain separate fail-closed gates. Do not weaken them in this work unit. Removing the incorrect path-floor rejection may expose an already complete, source-safe candidate; if the next canary still fails, route its first newly proven edge separately.

## Bounded repair contract

- Keep the generic movement planner strict.
- For the specialized Drudge strict path only, admit remote height samples against the declared/reference floor for the whole complete native path, independent of the endpoint lookup result.
- Preserve the existing safeguards: the actor start and every path point must remain within the four-yard reference-floor envelope when native height evidence is remote; the path must be complete; source-union safety must pass; and the actual endpoint must match.
- Add deterministic coverage proving that a near-resolved endpoint can still use declared-floor admission for remote intermediate samples, while an actor or point outside the reference-floor envelope remains rejected.
- Keep every C and C++ file below 1,000 lines.

Do not change source distances, lane or peer spacing, native path completeness, source-union safety, encounter state, damage, threat, healing, movement speed, or watchdog policy. Do not teleport, force movement, revive bots, or manufacture an outcome.

## Immutable Canary32 evidence

- Source commit: `0df41fe555dead1878dc436bbf6ec7947d8b7a53`
- Source tree: `847f9ad150ae74a12faf1f61c34f27bebe029e85`
- Binary SHA-256: `61d9260660d49c040a25883167e7a2967fc772cd5e8096a4555d6c51fb351256`
- Build receipt: `/tmp/trinity-magmaw-0df41fe555-build.L5Jej3/worldserver-build-receipt-v2.json`
- Build receipt canonical SHA-256: `c828158151a46e366eddeb931f63484011d19024e6082e8d567a1bc37574e6c6`
- Report: `/tmp/trinity-magmaw-0df41fe555-canary32.C5C9fE/canary32-run/capture/report.json`
- Report canonical SHA-256: `be0debeb72cfb87516e07457a64c2af41277d4036a1ec698f23ff159940d6b39`
- Report file SHA-256: `a4d39e7fc95436931b1c66f4c43b37a8dc79c02d10bd06fb914835ff7f37ccdc`
- Raw trace SHA-256: `f97fadce16efb4cb0431dbde452b763c057c57bb002a188ef6ee76290dacd20d`
- Server log SHA-256: `0e4cd49854aa6b0736fa520c749eab00b7b824a003d4c79868572480f6a8731b`
- Server epoch: `4580487178309574`
- Attempt: `2`
- Route scope: generation `3`, node `bwd.magmaw.drudges`
- Terminal: `gameplay_failure`, `semantic_stall`, ten survivors, one trash kill, zero boss kills
- Evidence demultiplexing: passed
- Forbidden-assistance gate: passed
- Cleanup: passed, worldserver exit code `0`

The next owner is `raid-bot-runtime-implementation`. It may implement this one Drudge-only admission edge and run focused tests only. A separate coordinator must review the patch, obtain a new exact queued build receipt, provision a fresh roster, and run Canary33 under the completion watchdog.
