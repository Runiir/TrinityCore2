# Hagara the Stormbinder — Phase 0 research contract (Cataclysm Classic 4.4.2)

This dossier covers Dragon Soul's fourth endpoint in `10N`, `10H`, `25N`, and `25H` for build `59185`, locale `enUS`, and the official global raid-unlock cutoff `2025-02-20T23:00:00Z`. It is sourced planning evidence, not a live observation. Later hotfixes and the March `Presence of the Dragon Soul` modifier are excluded.

## Observable encounter contract

Current Cataclysm Classic sources describe a repeating main phase followed by alternating Ice and Lightning intermissions. The first intermission is selected by the glow on Hagara's weapons before the pull; later intermissions alternate and never repeat the same element. Intermissions make Hagara immune until their crystals/conductors are handled, then `Feedback` stuns her and exposes a 100% damage-taken window for 15 seconds. Guides report an approximately 30-second first main phase and approximately 50-second later main phases, but another current guide describes a 50-second main phase without the first-phase exception. These are observations, not frozen scheduler values.

Main-phase observations are `Focused Assault`, `Ice Lance`, `Shattered Ice`, and—after the first main phase—`Ice Tomb`. `Focused Assault` targets the current tank, channels for five seconds, strikes for 50% normal weapon damage every 0.5 seconds, cannot be blocked/dodged/parried, and has a five-yard range. Normal guides say a stationary Hagara can be outranged; heroic guidance says she follows the tank, but exact movement/cancellation state is not build-backed. `Ice Lance` fires toward a random player near Hagara, with a three-yard Frost impact. One Cataclysm Classic guide reports 15,000 Frost, 25% attack-speed reduction in normal, and 25% Frost-damage-taken per hit in heroic; another describes 10% per stack in heroic. The exact missile spell, debuff stacking, cast cadence, crystal count, and exclusion rules remain fidelity-blocked even though historical spell identities are available.

`Ice Tomb` selects random players and stuns until the tomb is destroyed; the guide table reports two in 10-player and five in 25-player, while the Encounter Journal text reports six in 25-player heroic. Tombs do not splash to nearby players, break line of sight, and are not reported in the first main phase. `Shattered Ice` is a random-player Frost hit with a four-second movement reduction; the spell reference exposes 92,500–107,500 damage and a 1.4-second cast, but those rows are not a build-matched four-mode table.

## Intermissions

### Ice

`Frozen Tempest` makes Hagara immune and creates four `Frozen Binding Crystal` creatures. Destroying all four ends the Ice intermission. Four equidistant Ice Waves travel clockwise from the cardinal directions; the spell reference reports 190,000–210,000 Frost in a three-yard area and +50% Frost damage taken for 2.5 seconds. Hagara's bubble applies `Watery Entrenchment`: current guide tables report 12% maximum health per second and 50% movement reduction, while one heroic strategy paragraph reports 12.5%; the percentage-health nature is corroborated, but the exact 4.4.2 value is not frozen. `Icicle` impacts random outer-edge locations and is reported to knock back within seven yards; its damage, cadence, count, and area-trigger identity are unresolved.

Heroic Ice adds `Frostflake`: 10% movement reduction, increasing by 10% every second for 15 seconds in the guide narrative. On expiry it deals 25% maximum health and leaves a ten-yard Frostflake Snare area with 50% slow; the spell reference confirms the 15-second/10%-per-stack aura but not all encounter-side behavior. `Feedback` after all four crystals stuns Hagara and increases her damage taken by 100% for 15 seconds.

### Lightning

In the Lightning intermission Hagara is protected by `Water Shield`/the lightning phase immunity and applies constant raid-wide `Lightning Storm`; every tick is reported to add 5% Nature damage taken, acting as a soft enrage. A `Bound Lightning Elemental` spawns at phase start. Killing it turns a nearby conductor into the first link; `Lightning Conduit` then damages the nearest target for 20,000 Nature every second and connects to another player or conductor within ten yards. Players must chain the link through every `Crystal Conductor` to overload them and remove the shield. Current sources conflict on mode layout: one current guide reports eight conductors in 10-player and four in 25-player; the Encounter Journal reports four by default and eight in 10-player heroic; Icy Veins reports four without a mode qualifier. The per-mode count is therefore not promoted.

The same sources report two intermediate players for a 10-player chain and five for a 25-player chain, while the NPC text only establishes approximately 5–10-yard player spacing. Heroic guidance adds `Storm Pillars`, which explode after three seconds for 35,000 damage; count, target filter, spell identity, and raid-size scaling remain unresolved. Overloading all conductors applies `Feedback` and returns the fight to the main phase. The selected intermission alternates after each completed main phase.

## Difficulty and raid-size observations

| Mode | Current-guide health observation | Ice Tomb observation | Conductor observations | Reported delta |
|---|---:|---|---|---|
| 10N | 31,000,000 | 2 | current guide: 8 by raid size; EJ: 4 default | normal Ice Lance attack-speed effect; no Frostflake/Storm Pillar reported |
| 10H | 52,000,000 | 2 | current guide: 8 by raid size; EJ: 8 in 10H | heroic Ice Lance Frost vulnerability; Frostflake and Storm Pillars |
| 25N | 95,000,000 | 5 | current guide: 4 by raid size; EJ: 4 normal | normal Ice Lance attack-speed effect |
| 25H | 155,000,000 | guide: 5; EJ: 6 | current guide: 4 by raid size; EJ text does not freeze 25H | heroic Ice Lance Frost vulnerability; Frostflake and Storm Pillars |

Health values are current-guide observations with unspecified modifier state and are not asserted as cutoff runtime values. The Ice Tomb and conductor entries intentionally retain source conflicts. No damage coefficient, mode-specific health multiplier, or raid-size modifier is inferred from the guide prose.

## Official modifier state

Blizzard's 4.4.2 notes announce Dragon Soul as an eight-boss, 10/25-player raid with normal and heroic modes; the official live announcement freezes the global opening at this dossier's cutoff. A later official Classic announcement names `Presence of the Dragon Soul`: from the March 18 weekly reset, all Dragon Soul enemies receive 5% health and damage reduction, increasing by 5% every two weeks to 30% by the end of May; Lord Devrestrasz can remove it. The announcement supplies no aura/NPC IDs or persistence/default-state details. This post-cutoff schedule is recorded for future toggles but not applied to Hagara's cutoff observations. Historical retail `Power of the Aspects`/Lord Afrasastrasz is not a Classic identity.

## Repository, DB, reset, prerequisite, and credit audit

The audited revision is `de7578ab0d812999a3096e95363b91b8db19a603`.

- `dragon_soul.h` defines map `967`, `EncounterCount = 8`, `DATA_HAGARA_THE_STORMBINDER = 3`, and the `DS` data header, but no current Hagara boss constant.
- `instance_dragon_soul.cpp` maps only Madness of Deathwing actors; its door/gameobject tables are empty. The loader registers the Dragon Soul instance and Madness script, not `boss_hagara`; no current Hagara AI, spawn mapping, phase, reset, spell, or credit path exists in the checkout.
- Historical SQL records encounter `1296` as entry `55689` (`Hagara`), with model/equipment rows for the primary entry. Historical helper entries include `56136` Frozen Binding Crystal, `56165` Crystal Conductor, `56700` Bound Lightning Elemental, `56104` Ice Wave, and `57929` Hagara Facing Stalker. Variant rows include `57462`, `57955`, and `57956` for Hagara, but their mode mapping is unresolved. Historical access rows label map 967 difficulties 0/1 as 10N/25N and 2/3 as 10H/25H with quest `6177` on heroic; current Classic entry/lockout semantics are not established.
- Historical loot rows attach loot identity `55689`, but no current four-mode loot, achievement, encounter-state, player-credit, or reset implementation is present. Icy Veins names `Holding Hands` as a Normal/Heroic achievement requiring all raid members in the final Lightning Conduit, but current achievement and credit wiring remain unverified.

No spawn coordinates, current health tables, exact scheduler, precise random ranges, enrage spell, reset cleanup, prerequisite, or completion-credit behavior is promoted. A runtime implementation must resolve the blockers below before scheduling any source-only value.

## Material blockers

1. Exact 4.4.2 build/DBC/hotfix state at the requested cutoff.
2. Cutoff raid availability and default modifier state before the February 20 opening.
3. Classic `Presence of the Dragon Soul` aura/NPC IDs, default state, toggle, and persistence.
4. Retail `Power of the Aspects` versus Classic `Presence` identity separation.
5. Four-mode health, damage, and modifier-interaction tables.
6. Current Hagara AI/loader/spawn/object/lifecycle absence and the identity path needed for a bot endpoint.
7. Historical variant-entry mapping for 57462, 57955, and 57956.
8. Focused Assault heroic movement/cancellation, target filter, damage implementation, and repeat timer.
9. Ice Lance exact cast cadence, unattackable crystal count, target filter, and missile spell linkage.
10. Conflicting heroic Ice Lance vulnerability: 25% per hit versus 10% per stack.
11. Ice Lance normal attack-speed aura target, duration, stacking, and reset.
12. Ice Tomb four-mode target counts and the first-main exclusion/runtime cadence.
13. Shattered Ice exact target cone/random rule, cast cadence, damage, and slow enforcement.
14. First-main duration: approximately 30 seconds versus the 50-second generic strategy statement.
15. Weapon-glow first-intermission selection, transition grace, and later phase timing.
16. Frozen Tempest/Water Shield immunity spell linkage and removal conditions.
17. Frozen Binding Crystal entries, positions, health, damage, and four-crystal completion event.
18. Ice Wave spawn geometry, clockwise motion, cadence, damage, and lethal collision behavior.
19. Watery Entrenchment conflict (12% versus 12.5%), tick interval, radius, and slow rule.
20. Icicle spell/area-trigger identity, damage range, cadence, count, knockback, and target exclusions.
21. Heroic Frostflake/Frostflake Snare stack, expiry, dispel, damage, radius, and reset behavior.
22. Feedback spell linkage, stun event, +100% damage window, and phase resume timing.
23. Lightning Storm spell identity, tick interval/damage, random target rule, and 5% Nature stack reset.
24. Crystal Conductor count/layout: guide 8/4 by raid size, EJ 4 default plus 8 in 10H, Icy 4 unqualified.
25. Bound Lightning Elemental entry/count/health/targeting, death-to-conductor selection, and reset.
26. Lightning Conduit damage tick, nearest-target tie-break, ten-yard link, chain completion, and overload order.
27. Heroic Storm Pillar count, three-second warning, 35,000 damage identity, target/radius, and raid-size scaling.
28. Main/intermission loop, enrage/berserk duration, and combat-leash/evade transitions.
29. Wipe reset cleanup for Hagara, crystals, waves, conductors, elemental, auras, and area triggers.
30. Current prerequisite, lockout, loot, achievement, encounter completion, and player-credit behavior.

## Source metadata

1. [Wowhead Hagara strategy overview](https://www.wowhead.com/cata/guide/raids/dragon-soul/hagara-the-stormbinder-strategy-overview), updated 2025-02-19. Current Cataclysm Classic guide for health observations, phase flow, spell values, timers, raid-size observations, and heroic deltas; post-cutoff and internally inconsistent on conductor count and some values.
2. [Icy Veins Hagara encounter guide](https://www.icy-veins.com/cataclysm-classic/hagara-the-stormbinder-encounter-guide-strategy-abilities-loot), published/updated 2025-02-15. Before-cutoff Cataclysm Classic corroboration for phase alternation, first-phase timing, Ice Lance cadence, 12% Watery Entrenchment, Lightning chaining, heroic Frostflake/Storm Pillar, and achievement semantics; it reports four conductors without a complete mode table.
3. [Warcraft Tavern Hagara raid guide](https://www.warcrafttavern.com/cataclysm/guides/hagara-the-stormbinder-raid-guide/). Secondary corroboration for ability/phase headings; direct page access was unavailable during this audit, so no unique numeric value is promoted from it.
4. [Wowhead Hagara NPC/Encounter Journal](https://www.wowhead.com/cata/npc=55689/hagara-the-stormbinder). Historical/current reference for entry `55689`, spell identity rows, mode text (including 25H six Ice Tombs and 10H eight conductors), phase IDs, and the eight-minute community-reported berserk; generic/legacy fields and comments are not treated as current runtime proof.
5. [Wowhead Focused Assault](https://www.wowhead.com/cata/spell=107851/focused-assault), [Ice Lance](https://www.wowhead.com/cata/spell=105313/ice-lance), [Shattered Ice](https://www.wowhead.com/cata/spell=105289/shattered-ice), [Frozen Tempest](https://www.wowhead.com/cata/spell=105256/frozen-tempest), [Ice Wave](https://www.wowhead.com/cata/spell=105314/ice-wave), [Watery Entrenchment](https://www.wowhead.com/cata/spell=105259/watery-entrenchment), [Frostflake](https://www.wowhead.com/cata/spell=109325/frostflake), [Feedback](https://www.wowhead.com/cata/spell=108934/feedback), [Lightning Conduit](https://www.wowhead.com/cata/spell=105367/lightning-conduit), and [Ice Tomb reference](https://www.wowhead.com/cata/spell=70157/ice-tomb). Used for spell identities/effects only; legacy rows do not establish a complete 4.4.2 mode table.
6. [Blizzard Cataclysm Classic 4.4.2 notes](https://www.bluetracker.gg/wow/topic/us-en/2062030-world-of-warcraft-cataclysm-classic-patch-442-notes/), Kaivax, 2025-02-18. Official raid scope, fourth-boss/rogue quest context, and February 20 opening.
7. [Presence of the Dragon Soul begins March 18](https://us.forums.blizzard.com/en/wow/t/presence-of-the-dragon-soul-begins-march-18/2074792), Kaivax, 2025-03-12. Official post-cutoff 5%/biweekly/30% modifier schedule and Lord Devrestrasz toggle; not applied to cutoff values.
8. Local audit at revision `de7578ab0d812999a3096e95363b91b8db19a603`: `src/server/scripts/Kalimdor/CavernsOfTime/DragonSoul/dragon_soul.h`, `instance_dragon_soul.cpp`, `boss_madness_of_deathwing.cpp`, and `kalimdor_script_loader.cpp`. Used for map/data slot and absence of current Hagara lifecycle code.
9. Historical TrinityCore SQL at the same revision: `sql/old/4.3.4/TDB04_to_TDB05_updates/world/066_instance_encounters.sql`, `TDB00_to_TDB01_updates/world/004_creature_template.sql`, `TDB00_to_TDB01_updates/world/005_quest_template.sql`, `TDB01_to_TDB02_updates/world/128_creature_template.sql`, `TDB01_to_TDB02_updates/world/192_access_requirement.sql`, `TDB02_to_TDB03_updates/world/029_wdb_templates_updates.sql`, `035_wdb_templates_updates.sql`, `sql/old/4.3.4/world/13_2016_11_06/2016_10_09_02_world.sql`. Used for historical entry/helper/NPC/loot/access identities only.
10. [Original Dragon Soul difficulty changes](https://worldofwarcraft.blizzard.com/en-us/news/4326384/dragon-soul-difficulty-changes), Blizzard, 2012-01-19. Historical retail `Power of the Aspects`/Lord Afrasastrasz comparison only; it is not substituted for Classic `Presence of the Dragon Soul`.
