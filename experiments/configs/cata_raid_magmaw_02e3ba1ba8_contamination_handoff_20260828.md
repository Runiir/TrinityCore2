# Magmaw 10N contamination ownership handoff

## Closed input canary

- Runtime commit: `02e3ba1ba81e2135d09cf18f0c8431be4bf314f3`
- Completion: `semantic_progress_plateau_watchdog` after 482 seconds
- Last owned node: `bwd.magmaw.chainwielder`, generation 2
- Result: 0 kills, 10 deaths, Magmaw not reached
- Party DPS/HPS during 84 active combat seconds: `44371.321` / `3070.631`
- Affliction DPS: `12449.274`; pet damage: `196023`

The first invalid edge was real future-node contact. Elemental Shaman `30010`
stood within the Drudge lane while Chainwielder was owned. Lightning Shield
hit Drudge `42362`, then heroic Cunning of the Cruel proc `109800` hit both
future Drudges. The contamination observer then wrote the cohort terminal
failure, globally suppressed offense, and prevented healing and recovery.
Before the observer terminalized gameplay, healers produced `251840`
effective healing. Afterwards they produced zero.

Artifact hashes:

- report: `de221bc91d1da4b94629490cd70f76bbd0f9afecaab65133e211c75abe577ea1`
- combat analysis: `ce0a60c7a2b7bd5d4707a2e492df3f47ab64fb8115bb853d688706225308d9fd`
- combat log: `106f4fd0a200800c159dc42c23ac0613d69e72f439293df6e9e5815b9dcf369f`
- heartbeat: `e367ffefadf54a187e0a70809ca2239779374918b5e4f609ae3d1eef02654f6d`

## Bounded repair

Source `dfe6da6e9741ea6c10fc861bd83bf436756aba0b` separates the two causes:

- `BotWorldPopulationMgrValidationPatrolFormation.cpp` keeps nonmelee,
  non-tank members at a named middle-room combat anchor outside the declared
  Drudge home/live clearance and rejects unsafe ranged movement candidates.
- `BotWorldPopulationMgrValidationRouteContamination.cpp` records the
  certification receipt and interrupts only direct/protected splash, melee,
  pet, or controlled-unit offense that can reach the future target. It cannot
  stop healing, current-pack combat, or native recovery.
- The completion watchdog ignores stale combat-health and damage snapshots
  while the exact cohort is all-dead/wiped, without immediately terminating a
  fresh recovery episode.

Focused validation: 106 tests passed, 1 unrelated pre-existing concatenated
source-view assertion deselected. All changed C/C++ files are below 1,000
lines. `BotWorldPopulationMgr.cpp` is 885 lines; the new modules are 160 and
124 lines.

## Exact next action

Build the exact source commit with the guarded eight-job policy. Freshly
provision one `blackwing_descent_10n_magmaw_diagnostic` completion-watchdog
canary. Accept no contamination receipt. Verify Chainwielder and both Drudges
clear without a death-loop, then continue through Magmaw. If contamination is
observed, the run must continue safely but final certification must remain
rejected.
