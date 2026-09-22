# Magmaw cleanup handoff, 2026-09-22

The user stopped work for cleanup. No second validation was launched. The other
Magmaw thread remains paused and both review workers are finished or interrupted.

## Proven result

Commit `6bad2af351` restores fresh-instance route admission. A later node cannot
be selected without its prerequisites. Use the scenario-level full manifest on
one worldserver. The same native binary as the failed boss-only run cleared
entrance, Chainwielder, Drudges and Magmaw with zero recorded deaths. Binary SHA256:
`529ebcc542a0cde1f399b6de4e5f3e23ba8f97b7bd12c5750ae2fea83f542bca`.
Native build source is `f57f3eba37ea295ba8e07d4d2035c7d7a908a4e3`.

Native counters reported 229,238.661 DPS and 19,336.944 HPS over 124 combat seconds.
These are not exact pull-to-death results. No performance, actor or parent
requirement was accepted. The per-actor review is retained at
`artifacts/cata_raid_program/magmaw_route_prerequisites_actor_review_20260922.json`.
Its short trace windows include post-kill activity and cannot establish
whole-fight idle fractions.

## Pending controller repair

The watchdog failed to terminate after an uncertified diagnostic native clear:
it waited for certification acceptance, delaying the terminal combat-log export.
The coordinator preserved the clear snapshot, verified the owned server epoch,
issued native stop, verified zero bots/leases, then shut down the server. This
manual cleanup bypassed the deferred combat-log export. The missing exact event
stream is explicit; aggregate counters cannot replace it.

The saved Python patch factors the existing strict node/generation/death check
into `observed_native_manifest_clear` and lets both watchdog transports stop on
that result without granting certification. Eight focused tests passed, along
with 13 existing controller tests and 23 terminal/liveness tests. Independent
review was interrupted by the user's stop. **Do not treat this patch as reviewed
or live-validated.** No C++ gameplay code was changed in this task.

On explicit resume, review that patch and
`tests/test_diagnostic_clear_termination.py`, then use the committed recipe
`experiments/configs/cata_magmaw_route_prerequisites_autostop_20260922.json` once.
Verify automatic clear termination, combat-log export before stop, exact damage
accounting and cleanup. Do not repeat native target repairs on the invalid
boss-only setup. Keep the existing class and WCL requirements open.

## Retained evidence

The run, pre-cleanup snapshot, operator cleanup responses, DVCLive metrics,
dry-run manifest and test logs are archived through
`artifacts/cata_raid_program/magmaw_route_prerequisites_evidence_20260922.tar.gz.dvc`.
The compact publication receipt records direct remote verification and exact
local eviction. SQL telemetry run 254 has its own verified DVC pointer.

The first launch-test pass initially failed on a missing new-test argument and
an existing opt-in asset mock/stale context expectation. These were corrected;
the final launch suite passed 32 tests. No failed checks were discarded.
