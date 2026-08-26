# Magmaw Canary34 reference-floor intent handoff

Canary34 ran the exact clean source commit `8d421ad45b495e7e52e0ef68e9fb359f63ce4fdf` with the coordinator-built binary. It cleared the entrance regroup and Chainwielder, reached `bwd.magmaw.drudges`, and failed closed on the death-loop watchdog after 458.964 seconds. Three bots died, seven remained alive, the worldserver exited normally, and cleanup proved zero bots and leases. No forbidden assistance was observed.

## What the prior repair proved

The reordered endpoint diagnostic produced the intended disambiguation. Candidate selection now distinguishes projected endpoint failures from source-union failures. The live trace also proves that the Drudge brain can select and submit complete native movement paths: all ten bots received selected paths, the charge sequence reached generation 24, and generation 23 landed.

Do not reopen exact endpoint ordering, lower source-union distance, weaken the four-yard declared/reference-floor envelope, or loosen generic movement admission.

## First actionable runtime edge

`drudge_reference_floor_path_proof_is_discarded_by_generic_movement_planner`

The Drudge brain validates candidate paths with `NativePathFloorsValid(Bot, path, z, true)`. That proof permits native path samples on the explicitly supplied Drudge reference floor while retaining the existing four-yard actor/reference and sample/reference envelopes. After selection, the brain submits only the endpoint through `MoveBotToPoint`. The independent movement planner reconstructs the same path but calls the ordinary two-argument `NativePathFloorsValid(bot, candidatePath)`, which has no reference floor and is intentionally strict.

The resulting `route_destination_path_floor_gap` events occur after `native_complete_path` and `native_movement_submitted` traces. Fire mage `30007` produced that exact sequence immediately before dying. Affliction warlock `30008` and restoration druid `30003` died during the same repeated recovery cycle. This is a policy-to-executor handoff defect, not evidence that generic floor validation should be relaxed.

## Bounded repair contract

- Extend the typed movement intent with an optional, explicit reference-floor contract. Absence of that contract must retain the current strict generic behavior.
- Let the independent planner call the existing reference-floor overload only when the caller supplied that contract. Preserve the existing four-yard actor/reference and per-sample/reference envelope.
- Supply the reference floor only from a Drudge path that already passed complete native path, exact endpoint, source-union, lane, peer-spacing, and reference-floor checks.
- Keep encounter policy out of the movement executor. The brain supplies a mechanical constraint; the executor only validates and executes it.
- Preserve normal movement arbitration, rejection reporting, native path completeness, endpoint validation, recent-failure handling, and movement ownership.
- Add deterministic coverage proving that a scoped reference floor admits only paths inside the existing envelope, actor or sample values outside the envelope reject, and ordinary movement still uses strict floor validation.
- Keep every C and C++ source and header below 1,000 lines. `BotWorldPopulationMgrValidationRouteDrudgeActions.cpp` is already 999 lines and `BotWorldPopulationMgrValidationRouteDrudgeGeometry.cpp` is 990 lines, so do not add new logic to either without extracting a separate concern.

Do not add an encounter-name lookup to the planner, cache an unverified endpoint, globally loosen floor validation, bypass native path generation, force movement, teleport, revive bots, change damage or healing, or manufacture an encounter outcome.

## Deterministic acceptance

1. A movement intent without a reference floor follows the existing strict planner path and rejects a stacked-floor mismatch.
2. A movement intent with a valid Drudge reference floor uses the existing reference-floor path validation and can admit the already-proven path.
3. A reference floor more than four yards from the actor rejects.
4. Any path sample more than four yards from the supplied reference floor rejects.
5. Only the Drudge scoped submission sets the optional contract; unrelated movement callers remain unchanged.
6. Focused movement and Drudge regression tests pass, `git diff --check` passes, and all touched C/C++ files remain below 1,000 lines.

## Immutable Canary34 evidence

- Source commit: `8d421ad45b495e7e52e0ef68e9fb359f63ce4fdf`
- Source tree: `f632f463cfcfd318a2aca1423b6e6250eb659b52`
- Binary SHA-256: `30388f55bb1466096ba31bcbe8c90be9e74b766b55876d46990ee1fcc45bc94d`
- Build receipt: `/tmp/trinity-magmaw-8d421ad45b-build.a9PEpd/worldserver-build-receipt.json`
- Build receipt canonical SHA-256: `cb107ab15b019763f54169a22544f4cd4432b21102159f1d364a5fc566794474`
- Report: `/tmp/trinity-magmaw-8d421ad45b-canary34.SSZkC0/canary34-run/capture/report.json`
- Report canonical inventory SHA-256: `764ab239bdbb131a5d8dca4a3b07171d76e893df8501b687b14f963a419e3dd5`
- Raw trace SHA-256: `dadea3a54960f66d3292ecc9cefe6d599475876bb96ea28f0ba8f2f7bf1c1db3`
- Server log SHA-256: `5e3f39540e2b5bb14a31c7b6b44cb307b7e1a23428c8f3959744ee477876aff0`
- Route scope: generation `3`, node `bwd.magmaw.drudges`
- Terminal: `gameplay_failure`, `death_loop_watchdog`, seven survivors, three deaths, one trash kill, zero boss kills
- Drudge charge generation: `24`; prepared: `24`; delivered: `24`; landed: `23`
- Deduplicated exact-end rejections: `127`
- Deduplicated source-union rejections: `59`
- Evidence demultiplexing: `164/164` bound, zero rejected
- Final forced diagnosis and trace: passed
- Forbidden-assistance gate: passed
- Cleanup: passed, worldserver exit code `0`

The next owner is `raid-bot-runtime-implementation`. It may implement this one typed handoff repair and run focused tests only. A separate coordinator must review the patch, obtain a new exact queued build receipt, provision a fresh roster, and run Canary35 under the completion watchdog.
