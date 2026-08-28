# Magmaw Canary105 parasite recurrence handoff

## Immutable identity

- Source commit: `902ff5545e4a`
- Worldserver SHA-256: `f258dd862791dc8805f8a241a7f574af1657008fe501bb5bfaf1319de581d6f1`
- Scenario: `blackwing_descent_10n_magmaw_diagnostic`
- Final completion: `semantic_progress_plateau_watchdog`, not timed out
- Report SHA-256: `a0bd929d3ef033b5acb4d1c914a6f83816533612fa27d17ae79c42b416ad3b7d`
- Combat-analysis SHA-256: `19d51d6fdca6fe3874b5a91c40692bd092e34939395628044a474123f4bc15ad`
- Combat-log SHA-256: `29eaf8b57a8f6cfb1e50cc1ea9f900dbc363b13b15b7c8d1c0c1128db5f98963`

## Route result

Chainwielder and both Drudges cleared for three trash kills with no future-pack
contamination. Two bots died during Drudges and recovered before Magmaw. The
raid reached Magmaw, dealt `14,762,649` damage, and wiped. Magmaw active-window
throughput was `79,798.103` DPS and `11,841.059` HPS. The final report records
12 cumulative deaths and no boss kill.

The Canary104 same-level path rejection also recurred. Final forced traces
contain 92 rejected requested-intent receipts: 63 partial-path and 29 floor-gap
rejections. This is occurrence 2 of
`same_level_encounter_hazard_path_rejection`, not closure evidence.

## First recurring encounter edge

Player parasite control failed again. Fire mage `Mgwdpsa` first received
Parasitic Infection at `1787957617758`; `Mgwdpsb` followed 242 ms later.
Ultimately nine of ten players took Parasitic Infection or Infectious Vomit:
all five DPS, all three healers, and the Blood DK. The deduplicated
damage-taken aggregates contain 50 Parasitic Infection events for `362,857`
damage and 15 Infectious Vomit events for `204,796`, totaling `567,653`.

This is occurrence 9 of the stable causal signature
`magmaw_parasite_control_allows_player_infection` in
`cata_raid_magmaw_blocker_recurrence_v1.json`. The accepted Canary95 repair
did not close this edge: Canary95 itself recorded infection, followed by later
closed runs including Canary104 and Canary105.

## Bounded repair contract

Replace reactive pack-anchor recomputation for the fixed mobile team with one
persistent encounter lane state. The hunter and one fire mage own the rear
left/right endpoints. On Pillar or parasite release they commit to the opposite
endpoint, do not reverse or re-enter the pack until the destination is safe and
the lane transition completes, and retain mobile parasite targeting while
moving. Other ranged and healers remain boss-side unless directly endangered.
Movement survival outranks damage submission.

Do not add another distance-only escape, move the whole ranged group, alter the
native encounter, weaken path or route guards, or special-case a bot GUID. If
the next exact autonomous canary records any player Parasitic Infection, the
recurrence count becomes 10 and implementation/canaries stop for the required
ten-occurrence architecture summary.

Felhunter Fel Blood spam was reported from the same current binary but is a
separate pet-autocast work unit. It must not be folded into the Magmaw lane
patch.
