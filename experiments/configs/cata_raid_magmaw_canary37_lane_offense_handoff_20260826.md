# Magmaw Canary37 lane-local offense handoff

Canary37 ran exact clean source `4277a2b6eebe0cf1e526bc97e3643622b70de6d5` under the completion watchdog. It cleared the entrance and Chainwielder, then failed closed on the Drudge death-loop watchdog after 337.934 seconds. Drudges remained incomplete and Magmaw was not reached. The worldserver exited normally. Final diagnosis and trace, evidence demultiplexing, forbidden-assistance checks, and cleanup all passed.

## What Canary37 proved

The native taunt-confirmation repair worked. A submitted taunt was later confirmed from native victim ownership. Both Drudges remained assigned-tank owned, and all ten native Rushes landed. The prior movement, reference-floor, path, combat-envelope, and taunt-confirmation repairs must remain closed.

## First actionable runtime edge

`post_rush_cross_lane_threat_gate_suppresses_eligible_lane_offense`

Before the first death, the trace contained 1,615 waits, 273 offensive-cooldown events, 126 DoT events, and only six `drudge_lane_single_target_action` records. The Drudges still had 96.1% and 96.6% health. The global `nativeRushAuthorityReady` conjunction required both lanes to retain 2.5x live threat headroom after the first landed Rush. A deficient lane therefore called `HoldOffense()` for every member, including members whose own Drudge still had the assigned tank as its native victim.

The three deaths were downstream. The route deliberately uses `native_full_wipe_only`; resurrection or partial-death recovery is not an admissible repair.

## Bounded repair contract

- Before the first landed Rush in the exact attempt, wipe, and route scope, retain both-lane assigned-tank ownership, 2.5x threat headroom, the unique intended farthest seed, and every existing formation and native-action gate.
- After that landed proof, evaluate ownership and offense admission per lane.
- A non-tank in an exact assigned-tank-owned lane may resume its normal profile action even when its local headroom is below 2.5x or the other lane is not ready.
- An assigned tank below local 2.5x headroom must continue normal native threat-building actions.
- A wrong local victim keeps that lane closed.
- Preserve formation, reseparation, health sync, target selection, movement, range, line of sight, spell legality, native threat, encounter behavior, and full-wipe-only recovery.

Do not inject threat, force a victim, modify enemy damage or health, widen ranges, grant line of sight, teleport, resurrect, alter Drudge AI, or manufacture a clear.

## Accepted implementation checkpoint

Luna max implemented and reviewed the bounded repair at commit `bc755ada8410798c8319e168bdaaff09fc0847f4`, tree `403bc4198f8bbcfc1f55095e5605e054c9e23b4d`.

- The exact Rush observation scan now requires `candidate.Landed` plus matching attempt, wipe, and route identity.
- Pre-Rush authority remains both-lane and retains the original headroom and seed proof.
- Post-Rush ownership and authority are lane-local.
- Assigned tanks remain on the native threat-build path until their local headroom reaches 2.5x.
- Wrong local ownership remains fail-closed.
- `pixi run python -m pytest tests/test_drudge_*.py tests/test_bot_world_population_mgr_validation_route_drudge_module.py tests/test_cata_raid_runtime_foundation.py tests/test_raid_workloop.py -q` passed 153 tests.
- `git diff --check` passed.
- The touched C/C++ files are 99 and 942 lines, both below 1,000.

## Runtime verification plan

Run one fresh exact 10-player Canary38 through the completion watchdog. The repair counts as confirmed only if:

1. The first post-Rush authority transition is bound to a landed observation in the exact attempt, wipe, and route scope.
2. Eligible non-tanks emit `drudge_lane_single_target_action` after the first landed Rush while a deficient local tank may still emit `drudge_native_tank_threat_build`.
3. A wrong local victim still emits the ownership hold and does not release that lane.
4. The route preserves the ten native Rushes, lane ownership, reseparation, health-sync, and forbidden-assistance gates.
5. The completion watchdog, rather than a fixed success timer, terminates on clear or a typed failure.

## Immutable Canary37 evidence

- Source commit: `4277a2b6eebe0cf1e526bc97e3643622b70de6d5`
- Source tree: `71c8935e9ec33a824fca902c1a0a5f340a6050dc`
- Binary SHA-256: `0ee99c5222b9eeddc5d9278d1b6c4c33530c35b6dc76854208b7d9fb2487958c`
- Build receipt: `/tmp/trinity-magmaw-4277a2b6ee-build.NSarGJ/worldserver-build-receipt.json`
- Build receipt file SHA-256: `8a542121c9621637fd81cd1074cf67266eeabe39901ef7d5bfcab6cef35ed090`
- Build receipt canonical SHA-256: `68f90098aca3de6148d0de3d4c3b1c0b5ba1ef10aff8447e70df603ea8679a6a`
- Report: `/tmp/trinity-magmaw-4277a2b6ee-canary37.ThMtua/canary37-run/capture/report.json`
- Report canonical SHA-256: `8880ba49164ccef12148cd907a0df9722fd31a25461c1ee6773b7cacdd8b15d3`
- Report file SHA-256: `e53f3b4d6187de61df13557f99d415b77312eba3700881ee597c9966f497fd95`
- Raw trace SHA-256: `22b7e4e302048214db625a47e16758ddc7451078379c88ffb09bbe9b55291f45`
- Server log SHA-256: `5b1373bc65536ed1597d208af8d851f4745b7ada5cc122183a894d3b42fbba41`
- Terminal result: `gameplay_failure`, `death_loop_watchdog`
- Route result: entrance clear, Chainwielder clear, Drudges incomplete, Magmaw not reached
- Deaths: `30006`, `30008`, `30004`
- Native Rushes: 10 landed, five per source
- Native ownership roster: `30001`, `30002`
- Final Drudge health: approximately 96.1% and 96.6%
- Final forced diagnosis and trace: passed
- Forbidden-assistance gate: passed
- Evidence demultiplexing: 123/123 retained rows bound, zero rejected or unchecked
- Cleanup: passed, worldserver exit code `0`, zero bots and leases

The next owner is `raid-shard-architecture`. It must obtain a new exact queued build receipt for `bc755ada8410798c8319e168bdaaff09fc0847f4`, provision and read back a fresh exact ten-player roster, and run Canary38 under the completion watchdog. Only the live trace can confirm the repair.
