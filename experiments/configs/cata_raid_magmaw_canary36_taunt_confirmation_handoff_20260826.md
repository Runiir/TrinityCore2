# Magmaw Canary36 native taunt confirmation handoff

Canary36 ran exact clean source `c0c013e6d911c9c88b7c761869fb37d4531f700a` under the completion watchdog. It cleared the entrance and Chainwielder, then failed closed on the Drudge death-loop watchdog after 368.523 seconds. Drudges remained incomplete and Magmaw was not reached. The worldserver exited normally, evidence demultiplexing bound all 132 retained rows, final forced diagnosis and trace passed, forbidden assistance was absent, and cleanup proved zero bots and leases.

## What Canary36 proved

The 35-yard configured-seed combat envelope repaired the Canary35 failure. Affliction no longer remained 58 to 68 yards from its assigned Drudge. The new trace rejected remote recovery candidates before movement and later observed Affliction about 15 yards from its source with native line of sight and range. Do not reopen generic floor validation, reference-floor movement, endpoint ordering, source-union admission, the 35-yard envelope, spell ranges, or line of sight.

## First actionable runtime edge

`drudge_native_taunt_submission_is_recorded_before_assigned_tank_victim_ownership_is_observed`

At timestamp `1787713065130`, Drudge spawn `250141` targeted bot `30006`. Its assigned tank was bot `30002`. `TryCastCombatSpell()` accepted native spell `56222`, but the same native transition recorded:

- `taunt_submitted = true`
- `taunt_outcome_observed = false`
- `native_victim_owned = false`
- `victim_changed = false`
- current victim still `30006`

The action path records `drudge_lane_native_taunt` and adds the tank to `ValidationRouteDrudgeTauntRosterGuids` as soon as the cast helper accepts the request. Request submission is not proof that the source changed victim. Subsequent Rush observations targeted healers while complete native threat candidates were absent. Three members then died and the watchdog terminated the run.

## Bounded repair contract

- Separate native taunt request submission from confirmed source ownership.
- Bind pending confirmation to the exact attempt, wipe generation, route generation, map, instance, source spawn/GUID, and assigned tank GUID.
- After submission, keep the source ownership guard closed until a later native observation proves `source->GetVictim() == assigned tank`.
- Emit distinct typed states for submitted-pending, confirmed, and bounded-unconfirmed retry. Do not label submission as success.
- Retry through the existing native action candidate, cooldown, range, line-of-sight, and target-legality gates. Use a bounded backoff so the tank cannot spam the same taunt every decision tick.
- If the tank is out of range, retain the existing native taunt-approach path. Confirmation may not bypass movement or native spell legality.
- Do not release group offense or formation progression based only on the submission receipt.
- Keep all C and C++ sources and headers below 1,000 lines. `BotWorldPopulationMgrValidationRouteDrudgeActions.cpp` is 998 lines, so extract the taunt-confirmation concern into a focused module rather than growing it.

Do not force threat, assign a victim, modify enemy damage, widen spell range, grant line of sight, teleport, resurrect, alter Drudge AI, or manufacture a clear. Do not mix healer throughput, safe-member offense policy, or another movement hypothesis into this repair.

## Deterministic acceptance

1. A submitted taunt with an unchanged DPS victim remains pending and cannot produce confirmed ownership or a duplicate immediate taunt.
2. A later exact native observation of the assigned tank as victim confirms ownership and prevents another taunt.
3. An unconfirmed request becomes retryable only after bounded backoff and must pass the normal action candidate gates again.
4. An out-of-range assigned tank uses the existing native approach path and does not bypass range or line of sight.
5. Pending state cannot survive attempt, wipe, route, map, instance, source, or assigned-tank identity changes.
6. Focused Drudge action, telemetry, threat-seed, and workloop tests pass, `git diff --check` passes, and every touched C/C++ file remains below 1,000 lines.

## Immutable Canary36 evidence

- Source commit: `c0c013e6d911c9c88b7c761869fb37d4531f700a`
- Source tree: `4db06bb0cb636fccaee70d43b2c891577d11b1bc`
- Binary SHA-256: `d0b8fc020c8d47fd0a87644bc4b1633395127f80dbeb6d4c319614b5b8128080`
- Build receipt: `/tmp/trinity-magmaw-c0c013e6d9-build.q2EIT8/worldserver-build-retry1-receipt.json`
- Build receipt file SHA-256: `78405755e517749c9243e18a46739069a59e9f753d6b40c5cd0dc4e474d32f53`
- Build receipt canonical SHA-256: `0c8c40d0661ede172066cc0d192aa3fb39f14531e78fc023fd2d25cb60d8ba71`
- Report: `/tmp/trinity-magmaw-c0c013e6d9-canary36.dmDyB7/canary36-run/capture/report.json`
- Report canonical SHA-256: `113b74254d3a2fe44a2cba8db81f074b2dfb3b735106c55301c34c7164688ac9`
- Report file SHA-256: `6dcec59459a63eaab17a49016674093d68e8058d1454c28fe95014ef066e9f27`
- Raw trace SHA-256: `febd8713abba5a41f1902c7e66cef7fc138dab426b98fa5b8a4493ac568041a4`
- Server log SHA-256: `45df6d5c585f9f6d1f03c9e53b7e2d1e24430833a57691701ffd3b89b56b5cb2`
- Route scope: generation `3`, node `bwd.magmaw.drudges`, manifest index `2/4`
- Terminal: `gameplay_failure`, `death_loop_watchdog`, entrance and Chainwielder clear, Drudges incomplete, Magmaw not reached
- Deaths: `30008`, `30006`, `30007`
- Evidence demultiplexing: 132/132 retained rows bound, zero rejected or unchecked
- Final forced diagnosis and trace: passed
- Forbidden-assistance gate: passed
- Cleanup: passed, worldserver exit code `0`

The next owner is `raid-bot-runtime-implementation`. It may implement this one trace-backed taunt-confirmation repair and run focused tests only. A separate coordinator must review and commit it, obtain a new exact queued build receipt, provision a fresh ten-player roster, and run Canary37 under the completion watchdog.
