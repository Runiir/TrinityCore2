# Sinestra — Phase 0 research contract v1

Scope is Cataclysm Classic 4.4.2-labelled Bastion of Twilight heroic behavior in **10H and 25H only**. Sinestra is a bonus, heroic-only encounter after Cho'gall Heroic. `10N` and `25N` are deliberately rejected endpoints: this dossier does not model a normal-mode Sinestra fight or copy normal-mode health into a heroic plan.

This is research, not a live-validation result. The official 4.4.2 notes do not freeze a client/DBC build or a Sinestra hotfix cutoff. Current Wowhead and Icy Veins agree on the encounter shape, but several numeric values and timers are presented as approximate, historical, or contradictory. Those fields remain `fidelity_blocked`.

## Observable heroic contract

- Unlock is conditional: clear Cho'gall on Heroic, then access the bonus encounter. The local instance has `DATA_SINESTRA=4` and a fifth boss slot only on heroic instances, but no local Sinestra AI, loader entry, unlock event, or credit handler exists. Do not infer that the endpoint is playable from the header alone.
- Sinestra begins at 60% health with `Drained`, which reduces damage dealt by 40%, and Phase 1 ends at 30%. `10H` current guide health is 42.9M and `25H` is 128.8M. These are current-guide observations, not frozen bot invariants.
- Phase 1 repeats Flame Breath, Wrack, two chasing Shadow Orbs/Twilight Slicer, and five Twilight Whelps. The current guide reports Breath about every 20s, Wrack at 15s then every 70s, orbs every 30s for 15s, and whelps after 30s then every 50s. The Icy Veins guide confirms the mechanics but not all of those numbers; exact retail schedules are blocked.
- Keep the tank in melee range: otherwise Twilight Blast is used. Flame Breath is unavoidable arena-wide in the current strategy, despite its frontal visual. Wrack starts on a random non-tank, ramps every 2s, and on dispel bounces to two nearby allies while resetting its ramp but not its duration.
- Each Shadow Orb follows its random target; the two orbs connect with Twilight Slicer. Current Wowhead reports a 30k/s pulse within 5 yards and a 50k/s beam, while the ability pages expose 27–33k Twilight Pulse and a different radius/value presentation. Keep the relationship and target behavior, not one disputed coefficient.
- Whelps cast Twilight Spit (about 4k Shadow and +10% Shadow damage taken for one minute). Their death creates a growing Twilight Essence pool and can revive a whelp once. Icy Veins says whelps should be held rather than killed in Phase 1; revived whelps do not create another pool. Pool damage and growth are not mode-verified.

## Phase 2 and Phase 3

- At 30%, Sinestra uses Mana Barrier and casts Twilight Extinction after the Calen rescue sequence begins. Current Wowhead describes an 8s lead-in and about 500k raid Shadow damage; Fiery Barrier from Calen negates the extinction for players under it. Calen must be kept alive while Fiery Resolve/Pyrrhic Focus sustains the duel.
- When Sinestra's mana reaches 40%, Twilight Carapace drops from two Pulsing Twilight Eggs for 30s. Current Wowhead reports 4.1M health per egg and recommends splitting ranged damage. If the window fails, the barrier must be reduced again. Exact 10H/25H egg health, exposure reset, and failure behavior are not represented locally.
- Twilight Spitecallers spawn during Phase 2. Current Wowhead reports about 2.9M health, roughly every 30s, and Unleash Essence every 8s for 10% of maximum health each second over 10s. Regular interrupts/stuns are unsafe because of Indomitable; soft control is described. Twilight Drakes must face away because of Twilight Breath. Spawn count, target selection, and mode scaling are blocked.
- After both eggs die and Calen dies, Phase 3 starts with Sinestra restored to full health, no Drained reduction, and Essence of the Red on the raid. The current guide reports +100% melee/ranged/spell haste and +5% maximum mana per second for 3m. Phase 1 mechanics repeat at full damage; whelp pools become the soft-enrage. Whelp cadence, stack swap policy, and exact Essence duration require validation.

## Repository and DB cross-reference

The audited revision is `8eb54f0160b3c3d986ed944f9d64ebf83922c0f8`.

- `src/server/scripts/EasternKingdoms/BastionOfTwilight/bastion_of_twilight.h` defines map 671, `EncounterCountNormal=4`, `EncounterCountHeroic=5`, `DATA_SINESTRA=4`, and boss entry 45213. It has no Sinestra spell enum or AI contract.
- `instance_bastion_of_twilight.cpp` maps 45213 to `DATA_SINESTRA` and selects five boss states for heroic maps. It has no Sinestra `SetBossState`, reset, unlock, summon, loot, or credit branch.
- The Bastion directory contains no `boss_sinestra.cpp`; the Eastern Kingdoms loader registers Halfus, Theralion/Valiona, Ascendant Council, and Cho'gall, but no Sinestra script. Therefore no local reset, evade, phase, target, summon, achievement, or completion behavior is executable evidence.
- Historical 4.3.4 SQL identifies Sinestra 45213 and variant 49744 in `instance_encounters`, Sinestra Controller 46834, Channel Target 46835, Pulsing Twilight Egg 46842 (variant 49989), Calen 46277 (historical map spawn; variant 49970), Twilight Spitecaller 48415 (variant 49969), Twilight Drake 48436, Whelp Spawner 48052, Twilight Whelp 48049 (variants 49990–49992), Egg Cosmetic Stalker 51609, and historical Drained aura 89350. These are identity references only; the snapshot is not a 4.4.2 runtime guarantee.
- Wowhead spell identities cross-reference Drained 89350, Twilight Blast 89280, Flame Breath 90125, Wrack 89421, Twilight Pulse 92958, Twilight Slicer 92852, Twilight Spit 89299, Twilight Essence 88146, Mana Barrier 87299, Twilight Extinction 86226, Fiery Barrier 87231, Fiery Resolve 87221, Pyrrhic Focus 87323, Twilight Carapace 87654, Unleash Essence 90028, and Essence of the Red 87946. Spell pages provide useful identities and some ranges, but not a verified mode/hotfix table.
- The user’s “calter/pulsar” terms are normalized here to Calen and Pulsing Twilight Egg; no separate Calter or Pulsar endpoint was found in the repository/DB audit.

## Reset, completion, and difficulty delta

No Sinestra AI means no local reset or completion path can be asserted. Historical spawn auras do not establish runtime phase transitions. The only repository difficulty delta is the heroic boss-count slot; normal endpoints are rejected, and exact Heroic 10/25 scaling is unresolved. Retail unlock persistence, encounter credit, loot, achievements, wipe reset, egg/whelp cleanup, and Calen/Spitecaller cleanup all remain blocked.

## Material blockers

- Exact Blizzard 4.4.2 client/DBC build, hotfix cutoff, and Sinestra mode-health/scaling table.
- Executable Sinestra AI/loader/unlock/credit/reset behavior is absent locally.
- 10H versus 25H health for eggs, Spitecallers, Drakes, Whelps, Calen, and all spells.
- Exact Flame Breath, Wrack, Orb/Pulse/Slicer, Whelp/Spit/Essence, Twilight Extinction, Calen duel, egg exposure, Spitecaller, Drake, and Essence of Red timings/targets/radii.
- Phase transition/reset semantics, mana-barrier failure loop, pool growth/revival, whelp cadence, and all wipe/loot/achievement/credit behavior.

## Source metadata

1. [Wowhead Sinestra Strategy Guide](https://www.wowhead.com/cata/guide/raids/the-bastion-of-twilight/sinestra-strategy), Beanna, updated 2024-07-09, page labelled Patch 4.4.2. Used for current Heroic health, unlock, phase descriptions, numeric examples, approximate timers, target rules, and add behavior.
2. [Icy Veins Sinestra Encounter Guide](https://www.icy-veins.com/cataclysm-classic/sinestra-encounter-guide-strategy-abilities-loot), Abide, updated 2024-07-29. Used independently for heroic-only status, Wrack/orb/whelp handling, Calen/egg/Spitecaller flow, Phase 3, and loot/achievement scope.
3. [Wowpedia Sinestra tactics](https://wowpedia.fandom.com/wiki/Sinestra_%28tactics%29), historical reference. Used only to cross-check legacy spell identity/range presentation; it is not used to override current 4.4.2 values.
4. [Dark Wolves Bastion guide](https://www.darkwolves.eu/gwiki/index.php?gid=180473&page_name=bastion_of_twilight), historical independent strategy reference. Used only for qualitative orb, Calen, egg, and whelp flow.
5. [Blizzard Cataclysm Classic Patch 4.4.2 notes](https://us.forums.blizzard.com/en/wow/t/world-of-warcraft-cataclysm-classic-patch-442-notes/2062030), 2025-02-18. Confirms release context but does not freeze Sinestra data/hotfixes.
6. Local repository sources listed above plus historical SQL paths under `sql/old/4.3.4`; local evidence is implementation/identity evidence, not proof of retail 4.4.2 behavior.
