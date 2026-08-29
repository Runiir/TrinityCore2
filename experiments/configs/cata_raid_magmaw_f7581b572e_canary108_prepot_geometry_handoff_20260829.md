# Magmaw Canary108 prepull geometry handoff

## Identity and terminal result

- Run: `trinity-magmaw-f7581b572e-canary108.D8HVrb`
- Source commit: `f7581b572e8e971e121a78c8366dccbff79b6774`
- Worldserver SHA256: `7fa334732306c647a116d855071fef2fad43b012b680ff88854d0b26ea5da127`
- Scenario: `blackwing_descent_10n_magmaw_diagnostic`
- Completion: `machine_failure_predicate` after 376 seconds
- Failure: `bot_diagnosis_error`
- Route evidence: Chainwielder and both Drudges cleared; Magmaw generation 4 reached but not engaged
- Totals: 3 kills, 1 death, all 10 members alive again at closure, no boss kill

The prior native endpoint repair was exercised transiently: three native path
submissions were accepted and three leases were preserved with zero horizontal
delta and vertical deltas including `1.11812` and `0.446609`, both within the
1.5-yard floor-normalization bound. Earlier formation attempts also recorded
one partial-path and nine endpoint-mismatch rejections; they did not become the
terminal edge. Because the full route did not clear, the child signature is
still `not_exercised` for closure purposes even though its retained non-zero
normalization counterexample passed.

## First causal edge

The first run-blocking edge is a contradiction between encounter formation and
generic consumable geometry.

Magmaw deliberately assigns one fire mage and the marksmanship hunter as the
fixed mobile bait team. Their declared anchor is 30 yards behind the boss plus
24 yards laterally, or about 38.4 yards in two dimensions. The generic pre-pot
code required every member to be within 35 yards of the boss before using its
ordinary bag potion.

Eight members submitted and completed one native pre-pot use. The two declared
max-range baiters did not:

- `30006`, fire mage: submission count 0
- `30009`, marksmanship hunter: submission count 0

The first successful pre-pot aura was observed at `1787963964672`. The roster
continued waiting for the two geometrically ineligible members. At
`1787963989588`, the elemental shaman's aura expired and the shared setup was
terminalized as `raid_prepull_prepot_aura_expired_before_pull`. Nine final bot
diagnoses were errors and the boss never entered combat.

The bounded invariant is: durable flask and food setup may run during staging;
short-lived pre-pots begin only after the encounter reports full-health and
formation readiness; every admitted member uses its normal inventory item;
then the designated tank pulls. Boss distance is not a valid substitute for
encounter formation readiness and cannot exclude a declared max-range role.

## Combat signal

| Segment | Active DPS | Elapsed DPS | Active HPS | Elapsed HPS |
| --- | ---: | ---: | ---: | ---: |
| Chainwielder | 80,738.810 | 73,238.208 | 7,347.776 | 6,665.170 |
| Drudges | 108,970.312 | 66,746.102 | 35,414.469 | 21,691.943 |
| Magmaw prepull | 0 | 0 | 61,063.000 | 4,586.031 |

Affliction produced 19,978.155 active DPS on Chainwielder with 20.8% pet
damage, and 27,273.641 active DPS on Drudges with 15.8% pet damage. These trash
segments are diagnostic only and do not replace the exact 300-second isolated
self-provided-buff calibration.

## Artifact hashes

- `report.json`: `29cd0e4a27e144351528a6509f2ae639915f5a5bd2334df77439eece50bc3a37`
- `combat_analysis.json`: `daa81abe28c391ddc51ce60ba53a0c60f970a00e95dfa40c8716382f3415c5f9`
- `combat_log.json`: `3621f42214161dbf4ef4d34dc79083bdbc479a79418c2fbc36a9918f0235abf6`
- `heartbeat_events.jsonl`: `a671911b00ba9cf14b047dacbd2973157f31f95023cf0ff5ff189961100c4c8d`
- `worldserver_output.log`: `9ed5b2bde8d1480ea7c08fb873eb66d2e1b615414bb165aadf0bddb6f5edde34`
- `validation_route_manifest.json`: `f549cbb99bb1767f00c8a1697d249d2f4bec52b8df3b411b25adad94d94fc8f8`

This failed run is retained only until its compact handoff and hashes are
committed. It is not promotion evidence and must not be published as a pass.
