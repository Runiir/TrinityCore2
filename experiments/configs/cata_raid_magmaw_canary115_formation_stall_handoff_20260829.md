# Magmaw Canary115 formation-stall handoff

Canary115 ran exact clean source `ed717e6cfbd2421edc41e4bfe5c43f952553a604`
with binary SHA-256
`acedc74d8ebf3118daef419e6d52c425b0d274fe92aa8d45012887595f44f3ed`.
Fresh deterministic provisioning and strict DB readback passed for the exact
ten-member `blackwing_descent_10n_magmaw_diagnostic` roster. The generated
config SHA-256 was
`e1dbdaae406473515007263f760429995fe4a760eda6afb69195865175ea3f00`.

## Result

The run was a fail-closed gameplay failure. Entrance regroup, Chainwielder,
and both Drudges completed with all ten bots alive and no contamination.
Magmaw never entered combat. The controller stopped after `301.254` seconds
without monotonic progress in generation 4.

All ten members consumed their native inventory flask and food successfully.
No member became pre-pot eligible and no pre-pot was submitted. The formation
owner repeated `raid_prepull_consumable` roughly 293–306 consecutive times per
bot while reporting the current decision as `ok`; therefore the repeated-
decision watchdog did not count the loop and the semantic-stall watchdog was
the terminal owner.

The first broken edge is a complete, floor-valid native formation path whose
horizontal endpoint matched exactly but whose MMAP-normalized endpoint Z was
`1.6441` yards below the request. The global vertical endpoint tolerance is
`1.5` yards, so at least GUIDs 30007 and 30010 repeatedly received
`route_destination_endpoint_mismatch`. The Magmaw formation producer submitted
each bot's current Z instead of the declared formation-anchor Z, even though
the latter was already bound to the route's walkable floor. This kept
`RangedGroupStaged` false and prevented pre-pot eligibility.

The forced final trace delta contained a gap, so `terminal_evidence_incomplete`
is true. This does not erase the earlier retained diagnoses, semantic-stall
status, or successful trash outcomes, but the run is not acceptance evidence.

## Throughput before the stall

| Stage | Raid DPS | Raid HPS | Affliction DPS |
| --- | ---: | ---: | ---: |
| Chainwielder | 78,803 | 7,361 | 24,208 |
| Drudges | 104,091 | 42,972 | 23,472 |

These are trash-stage diagnostics, not a 300-second single-target Affliction
score and not a Magmaw/WoWSims parity claim.

## Immutable hashes

- canonical report: `52b58694a3ec81bcb9b0cb9f36dfe21fe228b79b85e13a191f71193b5406862d`
- normalized JSONL: `4ad32dbeabf00a115c1700ad54d37e86599936cadb9595dedf47bf39c322fad5`
- worldserver log: `75871bdc57e8ca89bff4f825d4b234afe7c093867ba666a76714ca350469e8a9`
- provisioning verifier: `9b58c70d44e3174776721ab37712c420b518d82520ce3a85500aaa4026c8268f`
- provisioning readback: `869834d15ce0a79cd86a0bfe7a55c2113a0bf5f7f302df0dcbc437fff109eaa0`

Cleanup passed: the owned worldserver exited and bot/lease counts returned to
zero. Keep the raw bundle until the formation repair and independent review
are complete; then publish, remotely verify, and target-evict it.

## Required next action

Repair the producer, not the global path tolerance: Magmaw formation movement
must submit the declared formation-anchor Z and preserve the strict general
endpoint proof. Add an executable multi-tick replay proving that a walkable
MMAP endpoint normalized from the declared anchor advances formation to
pre-pot eligibility, and that repeated successful submissions without
formation progress are terminally visible. Run the full permanent regression
bank before authorizing another live canary.
