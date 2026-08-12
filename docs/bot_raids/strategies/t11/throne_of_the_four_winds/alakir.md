# Al'Akir — Throne of the Four Winds

Research dossier for the Cataclysm Classic 4.4.2 raid-program contract. This is an evidence record, not a live-ready bot strategy: the contract and ledger remain `fidelity_blocked`.

## Scope and identity

Al'Akir is encounter `DATA_ALAKIR` on map 754. The repository identifies the boss as entry 46753, at `(-49.64583, 815.0816, 191.1009)` in historical SQL, and registers `boss_alakir` from `src/server/scripts/Kalimdor/ThroneOfTheFourWinds/boss_alakir.cpp`. The central platform is gameobject 207737 and the center wind draft is 207922. Historical difficulty rows are 50203, 50217, and 50231; their 4.4.2 database meaning is not frozen here.

| Mode | Guide health | Historical local entry | Acid Rain aura / damage IDs |
| --- | ---: | ---: | ---: |
| 10N | 30.0M | 46753 | 88290 / 88301 |
| 10H | 48.1M | 50217 | 101452 / 93280 |
| 25N | 105.2M | 50203 | 101451 / 93279 |
| 25H | 168.3M | 50231 | 101453 / 93281 |

The health figures are current-guide reports, not client data. The SQL `difficulty_entry_1/2/3` order follows the repository's `RAID_MODE` order (10N, 25N, 10H, 25H); the table is rearranged for the requested mode order. Do not use this historical mapping as a current database assertion.

## Observable encounter model

The fight is ground-based through phase 2 and becomes a three-dimensional flying encounter at 25% health. On engage, the local source schedules Wind Burst, Lightning Strike, Ice Storm, Squall Line and a 10-minute Berserk; Static Shock is scheduled only on heroic maps. Electrocute is the local fallback attack when Al'Akir's victim is outside melee range and is removed when the victim returns to melee.

At 80% damage, the source changes to phase 2, starts Acid Rain and schedules Stormlings. At 25%, it enables `CanFly`, stops its ground attack, removes Acid Rain and the too-close knockback, destroys the central platform, opens the draft, starts Relentless Storm, despawns Squall Lines and heroic chain casters, and creates the phase-3 cloud/storm actors. These health gates are repository behavior; exact live damage-boundary semantics and 4.4.2 spell coefficients remain blocked.

## Phase 1 — platform hazards

- **Electrocute (88427):** the local fallback attack applies periodic Nature damage to a non-melee victim. Its script starts at 3,600 and adds 50% of that base for each subsequent tick (`3,600`, `5,400`, `7,200`, ... under the local formula), then removes the aura on melee return. Wowhead reports 4,000 Nature per second plus 4,000 per tick; the local formula/tick interval and retail coefficients are not reconciled.
- **Lightning Strike (91327):** the local targeting spell selects a primary target. Normal maps cast periodic cone spell 88238; heroic maps summon chain caster 93250. The local damage script halves non-primary damage, and the periodic script emits ten visual segments across a 60-degree cone to 75 yards. Wowhead reports a 15-second field, 4,000/20,000 initial Nature damage and 4,000/10,000 per second normal/heroic, with 10-yard bounces; exact target/bounce rules and mode values remain blocked.
- **Wind Burst (87770):** a cast/knockback aimed at platform occupants. The local first event is 23 seconds and repeats at 26 seconds. Current guides describe a roughly 25-second, four-second cast, 25,000/50,000 Nature damage and a 90-yard push; exact damage, knockback recovery, and return-to-platform behavior are unresolved.
- **Static Shock (87873, heroic local gate):** the local heroic event begins at 5 seconds and repeats every 6 seconds. Current guides describe a 5,000 Nature shock and cast interrupt within 45 yards; the current 4.4.2 mode gate and coefficients are not independently frozen.
- **Ice Storm (88239):** the local first target is random within 70 yards; the local summoned entry is 46973 and selects a position, emits a ping, moves/charges, then applies Ice Storm aura 87469 after 3.5 seconds. Historical SQL instead binds `npc_alakir_ice_storm` to 46734 and lists 46973 as the field entry, so the trigger identity is explicitly conflicted. The event begins at 5 seconds and repeats every 16 seconds. Guides report 2,000/7,000 Frost per 0.5 seconds normal/heroic, a 50% slow and 15-second patch melt; path, radius and mode scaling are unresolved.
- **Squall Line (88781/91104):** the local event begins at 10 seconds and repeats every 31 seconds, alternating left and right vehicle entries 47034/48852. Vehicle motion follows the local center and radius with an 11-second circle path; a random vehicle seat index 0–4 creates a two-seat gap, and the hit script gives six seconds of spell immunity. Guides report approximately 30-second summons/full rotations, five seconds of loss of control, and 10,000/40,000 Nature per second (50,000/200,000 total) normal/heroic; exact 4.4.2 geometry and coefficients are blocked.

## Phase 2 — Acid Rain and Stormlings

At the local 80% gate, the mode-selected Acid Rain aura starts and the instance changes weather to heavy rain. The local 80–25% phase schedules the first Stormling after a random 10–11 seconds, then every 20 seconds. Stormling pre-effect 47177 becomes add 47175 after 3.5 seconds; each add attacks platform occupants after 2.3 seconds, and its death casts Feedback 87904 before despawning after four seconds. Current guides describe five-yard proximity, 5,000 Nature per second, and Feedback increasing Al'Akir's damage taken by 10% per stack for 30 seconds normal/20 seconds heroic; count, health, target behavior and all mode scaling are not client-verified.

Current guides describe Acid Rain as 500/1,000 Nature per second normal/heroic, stacking every 15 seconds; Wowhead gives 2,500/5,000 per second at five stacks and 5,000/10,000 after two minutes. The local source confirms only the mode IDs, the phase-2 start, and removal at phase 3/evade/death. Do not hard-code guide tick rates, stack cap, or damage.

## Phase 3 — Relentless Storm, altitude, and flying

At 25%, the platform is destroyed and the center draft is opened. Players receive Eye of the Storm (82724) from the instance after a local seven-second event; the boss casts the initial Relentless Storm vehicle ride trigger (89528) and channel (88875). The initial ride script schedules a teleport seven seconds later to `(-126, 838, 316)` with independent random offsets of ±15 yards on x, y and z. Eight local Relentless Storm vehicles (47807) move on a 107.3-yard circle with an 11-second path parameter. The world trigger applies the storm visual and removes players within 110 yards 2D from the ride selector; the exact live wall/vehicle collision and knockback are unresolved.

The source sets Al'Akir `CanFly` before phase 3 and applies a periodic CanFly update to Wind Burst victims. Lightning Clouds are first scheduled locally at 26 seconds. A periodic targeting script chooses a random point within an 80-yard radius and randomizes altitude by ±10 yards; the cloud damage selector keeps hostile units within 10 yards vertical altitude, while Lightning Rod's ally selector keeps units within 5 yards vertical altitude. The cloud is armed five seconds after summon. Wowhead reports +300% Eye of the Storm movement, Wind Burst every 25 seconds for 30,000/60,000 Nature, Lightning every four seconds for 30,000/45,000, Rod after five seconds for 10,000/15,000 per second within 20 yards for five seconds, and Clouds after 15 seconds then every 10 seconds for 25,000/50,000 per second lasting 30 seconds (normal/heroic). The current source does not expose those DBC periods, duration, damage or horizontal radius as verified 4.4.2 data.

Phase-3 local events are: Wind Burst periodic at 6 seconds, Lightning Rod periodic at 6 seconds, Eye of the Storm at 7 seconds, clouds at 26 seconds, and heroic Lightning (89644) at 6 seconds. These event entries are not repeats in this C++ file; any actual periodic cadence comes from spell data and remains blocked. Current guides report random Lightning roughly every four seconds, Lightning Rod after a delay, and Clouds recurring while players change altitude. Treat those guide intervals as qualitative only.

## Reset, completion, and credit

On evade, the local AI removes Acid Rain from players, despawns summons, restores the platform and center draft, removes world-trigger auras, and despawns at evade. On `DATA_ALAKIR=FAIL`, the instance also clears tracked Relentless Storm vehicles, restores fine weather/default light, and despawns initial vehicles. On death, `_JustDied()` handles encounter state, Serenity 89750 is cast on players, chest 95386 is summoned, players lose Acid Rain, and the boss falls; world-trigger auras are removed. On `DATA_ALAKIR=DONE`, the instance sets fog/default light and removes remaining initial vehicles. Historical SQL has currency rows for 46753/50203/50217/50231 and sets creature lootid 0, but this is not current 4.4.2 loot/credit proof.

Al'Akir is immune to players until the instance receives `ACTION_CONCLAVE_DEFEATED`; that action removes the immunity and summons the four slipstreams (47066). This unlock relationship is confirmed by the repository instance script, while current retail encounter-credit semantics are unresolved.

## Source and repository notes

- Wowhead, “Al'Akir Strategy Guide — Throne of the Four Winds Raid Cataclysm Classic,” Beanna, updated 2024-06-04, page labelled Patch 4.4.2: https://www.wowhead.com/cata/guide/raids/throne-of-the-four-winds/alakir-strategy
- Icy Veins, “Al'Akir Encounter Guide: Strategy, Abilities, Loot,” updated 2024-07-29: https://www.icy-veins.com/cataclysm-classic/al-akir-encounter-guide-strategy-abilities-loot
- Warcraft Tavern, “Al'Akir Raid Guide — Cataclysm Classic,” direct retrieval was not available (403); no exact value is promoted from it: https://www.warcrafttavern.com/cataclysm/guides/alakir-raid-guide/
- Blizzard, “World of Warcraft: Cataclysm Classic Patch 4.4.2 Notes,” version context only, no Al'Akir tuning: https://us.forums.blizzard.com/en/wow/t/world-of-warcraft-cataclysm-classic-patch-442-notes/2062030
- Repository C++: `src/server/scripts/Kalimdor/ThroneOfTheFourWinds/boss_alakir.cpp`, `instance_throne_of_the_four_winds.cpp`, `throne_of_the_four_winds.h`, and `kalimdor_script_loader.cpp`, audited at revision `8eb54f0160b3c3d986ed944f9d64ebf83922c0f8`.
- Historical repository SQL: `sql/old/4.3.4/TDB04_to_TDB05_updates/world/023_throne_of_the_four_winds.sql`, `025_creature_template_addon.sql`, `066_instance_encounters.sql`, and `sql/old/custom/world/34_2020_02_21/custom_2018_12_21_00_world_updatepack.sql` (identities, difficulty rows, spell bindings, summon groups and historical reward/loot setup only).

## Material blockers

The endpoint remains `fidelity_blocked` pending frozen 4.4.2 client/DBC or equivalent live evidence for all mode health/damage coefficients; exact Electrocute, Lightning Strike, Wind Burst, Static Shock, Ice Storm and Squall Line values; Acid Rain stacking; Stormling/Feedback scaling; P3 spell periods, cloud/rod targeting and damage; flying/altitude/vehicle geometry; reset, Berserk, loot and encounter credit. No build, live validation, database/DVC operation, or commit was performed.
