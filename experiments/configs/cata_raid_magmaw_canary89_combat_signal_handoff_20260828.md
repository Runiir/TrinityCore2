# Magmaw Canary89 combat-signal handoff

Canary89 used the clean exact gameplay build at commit
`7c13a3f89352c53b740820a1fe988a2796b2dc0c`. The current-standard 10N roster
cleared the entrance regroup, killed the Chainwielder, killed both Drudges,
rejoined, advanced to `bwd.magmaw.encounter`, pulled Magmaw, and fought for
more than 200 seconds. The completion watchdog stopped the run after three
observed death-loop edges. Cleanup passed with the worldserver absent and zero
bots and leases.

## First broken edge

The retained decision trace proves that role actions, healing attempts, ranged
formation movement, Pillar bait switches, and parasite-contact evasion were
submitted. It does not identify the native damage source that killed each bot,
effective damage and healing throughput, pet damage, or spell contribution.
Canary89 did not request the bounded native combat-log export. Therefore a
gameplay change cannot yet be attributed to the first fatal mechanic without
guessing.

## Bounded diagnostic repair

Commit `944b10579ec7bc5eea0840c7b15f297bc7cfea6d` makes the terminal evidence
bundle request `botauto combatlog`, verifies one cohort-bound contiguous chunk
sequence and completion marker, reconstructs the payload, and runs the existing
combat-log analyzer. New live captures fail closed when transport, decoding, or
analysis is incomplete. The report includes encounter and per-actor DPS/HPS,
pet contribution, ability breakdowns, positions, and incoming damage sources.

This tooling-only repair does not change gameplay, enemy values, routing,
movement, healing, class policy, or watchdog thresholds.

## Canary90 acceptance

- use the unchanged exact gameplay binary from commit
  `7c13a3f89352c53b740820a1fe988a2796b2dc0c`;
- freshly provision and read back the exact ten-character Magmaw roster;
- use the completion watchdog with no fixed success timer;
- require one complete cohort-bound combat-log export and successful analysis;
- report each encounter's party DPS and healing plus each actor's DPS, HPS,
  incoming damage sources, abilities, and pet damage;
- preserve native cleanup, zero leases, and worldserver exit;
- treat either a clear or a typed gameplay terminal as a measurement result,
  not as automatic gameplay acceptance.

## Immutable evidence

- Canary89 report:
  `/tmp/trinity-magmaw-7c13a3f893-canary89.UuuHBL/canary89-report.json`
- Capture report canonical SHA-256:
  `c567b00830e34383930241b0bc5b648e6b1a5412691cb99a0bf06ea1b19818e1`
- Capture report file SHA-256:
  `f230cae1570fce47b8e3259f7271cf83dff65e780e6b33bc8afa34f9e775fefa`
- Canary89 gameplay binary SHA-256:
  `c02a71618b616f6699b1504c66dc0d26fcd8efa14f33938afdaaf57da706cfba`
- Exact build receipt:
  `/tmp/trinity-magmaw-7c13a3f893-build.DM02YT/worldserver-build-receipt-v2.json`
- Build receipt file SHA-256:
  `10a4580edd2f5f07871f9c14fb0c3164768fadc73e58b07a6da87b96f97bb147`
- Build receipt semantic SHA-256:
  `a5b9c497d00d36b48cfc44f45d0ee6bdf2f0a552e05d3e9a91f2cf5421a6a56d`
- Forbidden assistance observed: false
- Fixed success timer: none; completion-watchdog policy only

This handoff authorizes one fresh measurement Canary90. It is not a clear and
must not be promoted as accepted raid evidence by itself.
