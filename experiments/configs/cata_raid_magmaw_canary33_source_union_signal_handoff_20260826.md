# Magmaw Canary33 source-union signal handoff

Canary33 ran the exact clean source commit `8e86e3761f8fb970b9b6f1d4682ebd6b35ad362d` with the coordinator-built binary. It cleared the entrance regroup and Chainwielder, reached `bwd.magmaw.drudges`, and failed closed on `semantic_stall` after 482 seconds. The semantic stall itself covered 301.598 seconds and 101 unchanged samples. Two bots died, eight remained alive, the worldserver exited normally, and cleanup proved zero bots and leases. No forbidden assistance was observed.

## What the prior repair proved

The declared/reference-floor repair was partially effective. Canary33 delivered repeated native Rushes, emitted five deduplicated `drudge_native_charge_reseparation_complete` traces, and reduced the observed Drudge pair to approximately 59.5% and 57.0% health before progress stopped. The old endpoint-height rejection remained absent. Do not reopen declared endpoint height admission or weaken the four-yard reference-floor envelope.

Canary33 still emitted three generic `route_destination_path_floor_gap` traces and retained floor-gap geometry receipts, so the prior repair is not evidence that every movement path is floor-valid. Those events remain separate from the work unit below.

## First actionable signal edge

`drudge_source_union_rejection_conflates_an_unsafe_navmesh_projected_endpoint_with_an_unsafe_intermediate_path`

Canary33 exported 143 deduplicated `drudge_anchor_source_union_path_unsafe` traces. The first was fire mage `30007`, trace sequence `260`, timestamp `1787704169706`. It occurred in route generation `3` at `bwd.magmaw.drudges`. Candidate receipts prove that the requested endpoints passed both live-source predicates, lane membership, peer spacing, and group-position safety before native path validation rejected them.

The label is not precise enough to select a gameplay repair. In `StrictNativePath`, `SourceUnionPathSafe(path)` runs before the exact native endpoint tolerance check. `SourceUnionPathSafe` checks `path.GetActualEndPosition()` as well as intermediate samples. A path projected away from the requested endpoint can therefore be reported as source-union unsafe even when no intermediate sample is the first failed predicate. The current evidence cannot safely distinguish an endpoint projection problem from a real path crossing.

The earlier `drudge_lane_native_path_rejected` trace at timestamp `1787704163586` is not the actionable edge. Its receipt says `movement_lease_preserved` and `higher_priority_movement_active`, which is expected arbitration rather than a path-safety failure.

## Bounded diagnostic repair contract

- Keep the complete native path and floor checks first.
- When exact endpoint matching is required, evaluate and report the existing exact-end tolerance before source-union path safety.
- Preserve the existing exact-end tolerances: at most 0.25 yards in two dimensions and at most 1.0 yard vertically.
- Preserve the full source-union invariant. Every admitted endpoint and path sample must remain at least 15 yards from both live Drudges and both home anchors. A recovery starting inside a radius may only exit without moving materially closer than the existing `startDistance - 0.25` tolerance.
- Preserve native path completeness, lane membership, peer spacing, the four-yard declared-floor envelope, and normal movement arbitration.
- Add deterministic coverage proving that an endpoint projection miss reports exact-end rejection before source-union rejection, while an exact endpoint with an unsafe intermediate sample still reports source-union rejection.
- Retain coverage that native incomplete path types remain rejected.
- Keep every C and C++ source and header below 1,000 lines.

Do not reduce the 15-yard source distance, admit incomplete native paths, route through the source midpoint, bypass path samples, force movement, teleport, revive bots, change damage or healing, or manufacture an encounter outcome. This work unit fixes diagnostic ordering only. The next canary must route exactly one newly disambiguated gameplay edge and then continue to a real fix.

## Immutable Canary33 evidence

- Source commit: `8e86e3761f8fb970b9b6f1d4682ebd6b35ad362d`
- Source tree: `78a06b5621844be7692c0a8ef20360dac396b003`
- Binary SHA-256: `5443408411b0cd01a6fbe59fb92dc8c781e46cd2cb812d4b28cabb74c0a886e2`
- Build receipt: `/tmp/trinity-magmaw-8e86e3761f-build.zSAuid/worldserver-build-receipt.json`
- Build receipt canonical SHA-256: `828b16a6d19b760a366158149cf45745c842acd75d4e1fd9b77ad108c3aa8986`
- Build receipt file SHA-256: `6548abec96a58f8a9a930d33ddf9c25e966bcb69eaa8a317385a5bb9b88a9e66`
- Report: `/tmp/trinity-magmaw-8e86e3761f-canary33.AY2cmq/canary33-run/capture/report.json`
- Report canonical SHA-256: `7ab3db0d1f33329b4d6d1cc814e1fa1964b5123df977bd86563c7b4091ec1542`
- Report file SHA-256: `bb8c67cf095872fa4c56fac18b0d49e981106bb4d8a453064ddbd886bb3bcc5d`
- Raw trace SHA-256: `31af2850e43586efb119052cc35e7f0c9247f793dfd7a761dc200ce12c5fce19`
- Server log SHA-256: `1a344563427d0e5964d51ccf0d18776b6a83adb970b131f561c4066bb63295a9`
- Server epoch: `4726084351523090`
- Attempt: `2`
- Route scope: generation `3`, node `bwd.magmaw.drudges`
- Terminal: `gameplay_failure`, `semantic_stall`, eight survivors, two deaths, one trash kill, zero boss kills
- Deduplicated source-union traces: `143`
- Deduplicated native path type 8 rejections: `31`
- Deduplicated native path type 132 rejections: `2`
- Deduplicated reseparation-complete traces: `5`
- Evidence demultiplexing: passed
- Final forced diagnosis and trace: passed
- Forbidden-assistance gate: passed
- Cleanup: passed, worldserver exit code `0`

The next owner is `raid-bot-runtime-implementation`. It may implement this one fail-closed diagnostic-ordering edge and run focused tests only. A separate coordinator must review the patch, obtain a new exact queued build receipt, provision a fresh roster, and run Canary34 under the completion watchdog.
