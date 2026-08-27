# Canary92 Magma Spit outcome handoff

## Scope

- Scenario: `blackwing_descent_10n_magmaw_diagnostic`
- Route node: `bwd.magmaw.encounter`, generation 4
- Runtime commit: `5fb925eca7f4e49378edb6e70f7d81db951a7178`
- Binary SHA-256: `6e9114f491d3dbe596b3bdd8a13cb7e70ae1e1b26d9ab1c3ca551a402456ef46`
- Gate-bearing build receipt SHA-256: `c98f82f0d4e159a2fc4f54624731f4af3d4166306b8b26fa73c0c76691e04716`
- Build receipt semantic SHA-256: `36cbb8e32d24c357fdf98995bd94be4e1f23e432342da2d5c4345032e4fe6dda`

## Accepted observations

Canary92 cleared the entrance regroup, Chainwielder, and Drudge nodes, then
engaged Magmaw. It stopped fail-closed on the death-loop watchdog after four
ranged damage dealers died together. Cleanup, identity, telemetry
demultiplexing, trace completeness, and combat-log transport all passed. No
forbidden assistance was observed.

The Magmaw segment recorded 5,006,046 party damage, 294,473.294 party DPS,
238,170 party healing, and 14,010 party HPS. The Affliction actor recorded
920,319 damage, 54,136.412 DPS, 5,600 healing, 329.412 HPS, and 215,037 pet
damage for a 23.3655 percent pet share. These are short encounter values, not
300-second training-dummy reference values.

## First broken edge

Spell 95280 correctly reduces the 10-player targeting set to three players.
For each selected player it triggers Magma Spit missile 78359. The missile has
an explicit unit target and a four-yard `TARGET_UNIT_DEST_AREA_ENEMY` damage
effect. Because the ranged group is correctly stacked, each of the three
missiles damages the whole stack. The first volley therefore produced 24
landed damage events against eight non-tanks instead of three landed hits.
The second volley repeated the multiplication and killed GUIDs 30007, 30008,
30009, and 30010 together.

No Pillar of Flame was cast during this short boss segment, so Canary92 neither
accepts nor rejects the pending Pillar movement repair.

## Bounded repair contract

Owner skill: `raid-encounter-implementation`.

Preserve spell 95280's native 10-player/25-player selection of three/eight
players and preserve spell 78359's native damage. Constrain effect 0 of spell
78359 to its explicit selected unit so one selected missile produces one
damage outcome. Keep the new implementation in a separate C++ module below
1,000 lines instead of growing the existing 1,349-line `boss_magmaw.cpp`.
Register the module in the Eastern Kingdoms loader and bind the spell script
through a custom world SQL migration. Add focused regression coverage for the
explicit-target filter, loader registration, SQL binding, and preserved
three/eight target selection.

Forbidden shortcuts include changing damage values, reducing the targeting
count, spreading the ranged strategy to mask the defect, adding healer power,
forcing survival or completion, suppressing the watchdog, or special-casing
recorded GUIDs and coordinates.

## Evidence locations

- Report: `/tmp/trinity-magmaw-5fb925-canary92.AvoEMJ/canary92-report.json`
  (`a2c7dd5d92c5713fb179b34d9946d96bec5e1117b7469e992977446afa7963ad`)
- Normalized telemetry: `/tmp/trinity-magmaw-5fb925-canary92.AvoEMJ/canary92-raw.jsonl`
  (`31156b85b928361d2493e2025492cad43cd6b6fa1e5db6630cad02a34d9ce7bc`)
- Worldserver log: `/tmp/trinity-magmaw-5fb925-canary92.AvoEMJ/canary92-worldserver.log`
  (`ab52d9f6ee751a6d2d6e2bb2f0e4467b6d7f89da448257a4c221c79601b176bd`)

The next live check must use a fresh provisioned state and the completion
watchdog. It must demonstrate exactly three landed Magma Spit outcomes per
10-player volley before any later failure is classified.
