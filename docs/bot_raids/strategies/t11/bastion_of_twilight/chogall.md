# Cho'gall — Phase 0 research contract (Cataclysm Classic 4.4.2)

This is a sourced planning dossier for Bastion of Twilight's Cho'gall encounter in 10-player normal/heroic and 25-player normal/heroic. It is not live-validation evidence. Guide-reported values are kept separate from this checkout's C++/SQL baseline; neither is silently promoted to a 4.4.2 bot invariant when build or hotfix provenance is missing.

## Bot-safe encounter contract

- Use two tanks. Exchange the boss after Fury of Cho'gall and keep the off-tank available for Corrupting Adherents; the exact safe number of Fury stacks is tuning- and group-dependent.
- In phase one, interrupt Conversion/Worshipping immediately, avoid Corrupting Crash and Depravity, kill each Adherent before Fester Blood where possible, and keep its death pool away from the raid. Kill or control Blood of the Old God before it reaches players.
- Handle Flame's Orders and Shadow's Orders as separate raid-damage calls. Damage the summoned elemental before Cho'gall absorbs it, but do not assume a retail health-to-stack coefficient from this dossier.
- Keep Corrupted Blood low. Dispel Corruption: Accelerated, turn Corruption: Sickness away from allies, separate Corruption: Malformation from the raid, and treat Corruption: Absolute as an unhealable end state.
- At 25% health, stop relying on phase-one add cleanup: Cho'gall consumes remaining Adherent/pool state, then the raid burns through Corruption of the Old God while killing Darkened Creations and interrupting/avoiding their beams. In heroic, also move away from Spiked Tentacles; exact knockback/melee behavior is not frozen here.

## Difficulty matrix

| Mode | Current guide health | Local Adherent summon rule | Local heroic delta |
|---|---:|---|---|
| 10N | 33.5M | one random left/right portal | no heroic elemental, spiked-tentacle, or heroic-death path |
| 10H | 56.7M | one random left/right portal | heroic spell data; P2 Spiked Tentacles; heroic elemental power hooks |
| 25N | 101.4M | one random left/right portal | 25-player target cadence; no heroic elemental, spiked-tentacle, or heroic-death path |
| 25H | 175.2M | both left and right portals simultaneously | two Adherents, heroic elemental power hooks, P2 Spiked Tentacles |

Wowhead's current Cataclysm Classic page reports 33.5M/56.7M/101.4M/175.2M for 10N/10H/25N/25H. It is not corroborated by a current four-mode TDB/DBC snapshot, and Blizzard's historical 4.2 notes document a later 20% Cho'gall health/damage reduction without exposing the 4.4.2 client/hotfix lineage. Health remains `fidelity_blocked`.

## Observable mechanics and targeting

### Corruption and worship

The local encounter initializes Corrupted Blood (93104) on engage and uses alternate power 0–100. Thresholds are 25 (Corruption: Accelerated, 81836), 50 (Sickness, 81829), 75 (Malformation, 82125), and 100 (Absolute, 82170 plus 82193). Local `AddCorruption` caps at 100, applies Corrupted Blood Damage Increase (93187) with stacks equal to the increment, and marks world state 5659 once any player exceeds 30 corruption. The local script registers increments of 10 for Corrupting Crash (81685) and Depravity, 5 for Spilled Blood (81757), 5 for Sickness/Sprayed Corruption, 1 for Corruption of the Old God, and 2 for Accelerated/Corrupted Bite.

Current guides describe Accelerated as +2 corruption per second if not dispelled, Sickness as a periodic forward vomit that adds 5 to hit allies, Malformation as a back tentacle casting at a nearby ally, and Absolute as double damage/instant spells but no healing. Icy Veins and current Wowhead list Crash/Depravity as +10, while Blizzard's historical 4.2 notes say Crash/Depravity were reduced to 5 and Corruption-of-the-Old-God damage per corruption was reduced from 3% to 2%. These values are conflicting historical/current reports, not a resolved 4.4.2 spell table.

Conversion (91303) selects two targets in a non-25-player map and four in a 25-player map in the local script, then applies Worshipping (91317), its linked channel (92314), and a root. Local target filtering is random resize; Conversion stops the target's cast and restores movement when removed. Current guide prose says two targets in 10-player and five in 25-player, and that Worshipping grants Cho'gall Twisted Devotion every three seconds. The target count, channel break window, and Twisted Devotion spell values remain blocked where local and guide evidence differ.

### Phase one

- **Fury of Cho'gall (82524):** local initial cast at 33s, then every 47s, on the current victim in both phases. Guides describe a tank hit and +20% Physical/Shadow damage taken for one minute; exact spell coefficients and stacking are data-dependent.
- **Flame's Orders (81171) / Shadow's Orders (81556):** local self casts at 6.1s and 20.8s, each repeating every 40s. Portal spells are 81186 (Fire) and 81558 (Shadow). Elementals begin with ten Fire Power (93245) or Shadow Power (93301) stacks, cannot die normally in the local AI, and become passengers after an absorb attempt beginning at 10.5s. The local periodic elemental-power script only lowers stacks, clamping them to `ceil(healthPct / 10)`; the boss records the remaining stacks. Local heroic aura scripts scale Flaming Destruction by 10% per recorded stack and Empowered Shadows by 5% per stack; exact retail aura spell values are unresolved.
- **Corrupting Adherent (81628):** local first summon at 39s and repeat every 92.3s. The local spell script chooses one left/right summon except in 25H, where it casts both (81611 and 81618). Adherents become aggressive after 2s; Corrupting Crash (81685) starts at 6s in 25-player maps or 10s otherwise, then repeats every 6s at a random valid target. Depravity uses mode IDs 81713/93175/93176/93177 (10N/25N/10H/25H), starts at a random 8–9s, and repeats 5–6s in 25-player maps or 11–12s otherwise. Current guides say two Adherents on heroic, which conflicts with the local 10H/25N rule.
- **Fester Blood (82299):** local schedules +39s after every Adherent summon. Its script separates alive and dead Adherents; the local summon helper creates four blood entities per dead-pool hit. An Adherent death casts Spilled Blood visual/trigger 81771 and schedules 81757 after 5.1s. Blood entities engage after 2.2s, select one random valid target, add a very large threat value (the source labels it “sniffed”), and melee; exact health, movement, corruption, and mode scaling are not in C++.
- **Conversion (91303):** local first cast at 11s and random-repeat 21–25s. See the corruption section for target and interruption handling.
- The local 10-minute Berserk is generic spell 26662. Current guides do not provide a conflicting exact enrage value, but no live run was authorized.

### Phase two and heroic death path

`DamageTaken` changes to phase two when damage crosses below 25% and queues Consume Blood of the Old God (82630) after 1ms. The boss checks for triggered Blood aura 82659 after 5.1s and supplies it if absent, then casts Darkened Creations (82414) after 6s. Darkened Creations repeat every 30s in normal and 40s in heroic. Heroic mode queues Spiked Tentacle trigger 93315 after 16.8s and repeats every 20s. The consume script transfers the relevant effect to the boss and applies Corrupted Cho'gall (95821); remaining Adherents are made passive and despawn after 6.75s when hit by Consume.

Each Darkened Creation starts with visual 82452, transforms to an eye tentacle with 82451 and void visual 82397 after 3.5s, then becomes selectable and casts Debilitating Beam (82411) toward its summoner every 1.5s. The local C++ confirms the target relationship and cadence but not spell radius, interruptibility, damage, healing/damage reduction, or mode coefficients. Current guides describe four creations in 10-player and ten in 25-player; the local AOE summon spell does not expose that count.

The source contains a heroic-only lethal-damage RP path: if `DATA_FULL_HEROIC_ID` is true, lethal damage is held at one health, Cho'gall walks to the trapdoor, opens it after 3s, falls, and teleports after 4s before suicide spell 3617. The current instance implementation always returns false for `DATA_FULL_HEROIC_ID`; therefore this path is not an active local 10H/25H behavior and must not be treated as a Classic invariant.

## Reset, completion, credit, and repository identity

- `Reset()` calls the BossAI reset, reinitializes elemental-stack/first-Darkened/allow-death fields, and reapplies Boss Hittin' Ya (73878). Engage sends encounter-frame state, resets world state 5659, casts Corrupted Blood, and schedules phase-one events. Evade disengages, despawns summons, removes the corruption creature's auras, and calls `_DespawnAtEvade()`.
- `JustDied()` calls generic `_JustDied()`, disengages the encounter frame, and removes corruption auras. The normal death line is conditional on `DATA_FULL_HEROIC_ID`/heroic. The instance maps DONE/FAIL through generic boss state; retail lockout, loot, achievement persistence, and exact credit recipients are not established by this audit.
- Bastion of Twilight is map 671; `DATA_CHOGALL` is encounter index 3, with five boss slots only in heroic because Sinestra occupies the fifth slot. Header identities are boss 43324, event/introduction Cho'gall 46965, Fire Portal 43393, Fire Elemental 43406, Corruption 43999, Malformation 43888, and Spiked Tentacle trigger 50265. The 4.3.4 TDB row identifies level 88, base health 2,500,000, and `boss_chogall`; this is not four-mode 4.4.2 tuning. Historical map-671 SQL has difficulty-6 spawns and Boss Hittin' Ya aura 73878; the 2023 model update records model 34576 for 43324 and 35367 for 46965, verified build 15595.

## Material conflicts and fidelity blockers

- Exact 4.4.2 client/DBC build, locale, hotfix cutoff, and whether historical 4.2 Cho'gall nerfs are reflected in the Classic spell rows.
- Four-mode health, melee, elemental, Adherent, Crash, Depravity, Flaming Destruction, Empowered Shadows, Corruption-of-the-Old-God, Darkened Creation, and Beam scaling.
- Current guide health versus historical 4.2 20% reduction; current guide/local +10 Crash/Depravity versus Blizzard's 4.2 reduction to 5; 2% versus 3% Corruption-of-the-Old-God scaling.
- Conversion target count (local 2/4 by map versus guide 2/5), Worshipping break timing, Twisted Devotion magnitude/duration, and exact target eligibility.
- Orders alternation/portal cadence, elemental health-to-stack conversion, absorb timing, and heroic-only aura coefficients.
- Adherent count in 10H, 25N, and 25H; random left/right selection; Crash/Depravity exact radii, damage, corruption, and interrupt timing.
- Fester Blood's living/dead target effects, number/health/movement of Blood entities, pool lifetime, and corruption values.
- Phase-two creation count, spawn geometry, Beam target/interrupt behavior, Spiked Tentacle health/knockback, and all phase-two timers beyond local event scheduling.
- Heroic trapdoor death RP is gated off by the local `DATA_FULL_HEROIC_ID` implementation; retail heroic behavior and Sinestra-unlock credit are not proven.
- Post-evade helper state, retail reset/lockout, loot, achievement, and player-credit semantics.

## Source metadata

1. [Wowhead, “Cho'gall Strategy Guide — The Bastion of Twilight Raid Cataclysm Classic”](https://www.wowhead.com/cata/guide/raids/the-bastion-of-twilight/chogall-strategy), Beanna, updated 2024-06-04, page labelled Patch 4.4.2; accessed 2026-08-12. Used for current four-mode health, corruption descriptions, heroic 25-player Adherent note, phase descriptions, and ability summaries.
2. [Icy Veins, “Cho'gall Encounter Guide: Strategy, Abilities, Loot”](https://www.icy-veins.com/cataclysm-classic/chogall-encounter-guide-strategy-abilities-loot), Abide, updated 2024-07-29; accessed 2026-08-12. Used independently for corruption amounts/threshold behavior, orders, heroic elemental handling, Adherent/Fester sequence, phase-two race, reset/role guidance, and achievement wording.
3. [Warcraft Tavern, “Cho'gall Raid Guide”](https://www.warcrafttavern.com/cataclysm/guides/chogall-raid-guide/), Passion, current page retrieved 2026-08-12. Used as an independent qualitative check for Conversion, orders, Adherent timing/placement, Fester Blood, Blood fixate, 25% transition, and Darkened Creations; its page does not establish a four-mode tuning table.
4. [Blizzard, “Rage of the Firelands Patch 4.2 Notes”](https://worldofwarcraft.blizzard.com/en-us/news/2993743/rage-of-the-firelands-patch-42-notes-updated-628), June 28 historical patch notes; accessed 2026-08-12. Used only to document the official historical Cho'gall 20% reductions, Crash/Depravity corruption reduction from 10 to 5, Corruption-of-the-Old-God scaling reduction from 3% to 2%, and shorter Twisted Devotion; not treated as a 4.4.2 hash/cutoff.
5. [Blizzard, “World of Warcraft: Cataclysm Classic Patch 4.4.2 Notes”](https://us.forums.blizzard.com/en/wow/t/world-of-warcraft-cataclysm-classic-patch-442-notes/2062030), Kaivax, 2025-02-18; accessed 2026-08-12. Used to anchor the Classic 4.4.2 release context; no Cho'gall-specific tuning or client/DBC hash is published there.
6. Local repository: `src/server/scripts/EasternKingdoms/BastionOfTwilight/boss_chogall.cpp` (lines 70-246, 286-546, 553-804, 806-945, 947-1105, 1124-1424); `bastion_of_twilight.h` (lines 23-198); `instance_bastion_of_twilight.cpp` (lines 30-50, 82-218, 267-299); and `eastern_kingdoms_script_loader.cpp` (lines 32, 264). Used for spell IDs, event offsets/random ranges, target filters, phase transitions, corruption/worship scripts, summon/absorb behavior, reset/evade/death, boss-state mapping, and loader registration.
7. Local DB/SQL: `data/TDB_full_434.22011_2022_01_09/TDB_full_world_434.22011_2022_01_09.sql` (creature-template row 43324); `sql/old/4.3.4/world/28_2018_04_15/2018_04_14_00_world.sql` (map-671 difficulty-6 spawns and addon auras); `sql/old/4.3.4/TDB01_to_TDB02_updates/world/131_misc.sql` and `189_creature_template.sql` (historical movement/flags); `sql/updates/world/4.3.4/2023_09_15_00_world.sql` (model rows verified 15595); and historical Cho'gall loot SQL. Used for repository identity/spawn/model provenance only, not current 4.4.2 tuning.
8. [Wowhead, “Cho'gall — NPC — Cataclysm Classic”](https://www.wowhead.com/cata/npc=43324/chogall), legacy NPC/comments page; accessed 2026-08-12. Used only as a historical cross-check for Darkened Creation count claims; not treated as current 4.4.2 authority.
