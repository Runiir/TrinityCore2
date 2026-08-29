# Magmaw Canary118 parasite recurrence handoff

## Immutable identity

- Run: `trinity-magmaw-2fdaa927b3-canary118.GOOMkp`
- Source: `2fdaa927b3683e72d9a32e4b62e75a7a172872c2`
- Worldserver SHA-256: `fb4bde35bd3662c7a55fb05d5f2e54fa8939e573650991d81a842d3c8b5322ef`
- Regression-suite receipt SHA-256: `0a0570aa29349c44363eaaa38ca0985db29d7c072fd73d4255d4cc52a1b2ffa9`
- Report SHA-256: `c559b26a2391bb0e281d93a217df5a42235a20307ceb37ed0d38556b60661387`
- Normalized JSONL SHA-256: `419bc586afbda1048424a03cb97d1e7b282c5fad622be432ef8efeb15a847cf9`
- Worldserver log SHA-256: `3f7149a7fe8d45919dc52f96fd42d186a359575eb83d68324b1188fc77f45a59`

The exact immutable fixture bank passed before this build. Its admitted
parasite fixture revisions were lane paths revision 3, lane-transition replay
revision 2, and full-runtime replay revision 2. This live recurrence therefore
invalidates those passing boundaries.

## Route result

Entrance regroup, the Chainwielder, and both Drudges completed with all ten
bots alive. Magmaw was engaged. The run ended at 539.477 seconds under the
death-loop watchdog after all ten bots died; no boss-death evidence exists.
The capture shut down and cleaned up normally.

Magmaw combat produced 20,124,716 party damage, 82,141.698 active DPS,
4,686,512 healing, and 19,128.620 active HPS. Affliction contributed
6,608,862 damage and 26,974.947 DPS. Its Felhunter contributed 1,434,992
damage, or 21.7131% of the warlock total. Throughput is diagnostic only because
the encounter did not clear.

## Reproduced blocker

The combat log contains 53 direct `Parasitic Infection` hits and 27
`Infectious Vomit` hits. Direct infections were distributed across the fire
mage (13), discipline priest (16), holy paladin (11), restoration druid (11),
and Affliction warlock (2). The first direct infection occurred on the assigned
fire-mage baiter at the fixed left endpoint `(-340.855, -30.165)`, with the
parasite at `(-340.773, -30.348)`: 0.2 yards apart.

The assigned mage and hunter did submit both fixed endpoints, so the failure is
not absence of the lane. The first broken state-machine edge is narrower:
after both baiters become `IsArrived()` for a still-living parasite generation,
`EnsureLaneTransition()` returns no destination. `Propose()` guards its
unsafe-endpoint handling with `if (destination && ...)`, so it cannot redirect
the arrived cohort even when parasites occupy that endpoint. The mage remains
at the endpoint, becomes infected repeatedly, and later spreads the failure
into the support stack. Live trace samples also contain fallback radial
destinations, confirming that fixed-lane ownership was not continuous.

This was the earliest reproduced safety-policy failure, but the first lethal
event was separate: off-tank `30002` took three Mangle hits immediately before
dying, with no successful tank-swap or mitigation transition in the retained
trace. The later raid deaths followed that tank loss. Keep Mangle ownership as
a separate open work unit; do not mislabel it as parasite-lane recovery.

## Fail-closed disposition

This is occurrence 14 of
`magmaw_parasite_control_allows_player_infection`, with the prior architecture
review covering occurrence 13. Revision 3 is quarantined. Do not build or run
another canary from the same fixture boundary.

The next admissible work is one compiled revision-4 replay that sets both
baiters arrived while the same living wave makes the endpoint unsafe. It must
fail before the runtime edit, then prove that both baiters receive one shared
opposite fixed endpoint and transition identity, without a local radial/no-op
escape. Only the smallest trace-backed state repair may follow. A live clear is
provisional; closure still requires two consecutive independent current-
standard clears.
