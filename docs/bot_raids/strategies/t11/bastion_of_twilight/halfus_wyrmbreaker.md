# Halfus Wyrmbreaker — Phase 0 research contract (Cataclysm Classic 4.4.2)

Scope: Bastion of Twilight, 10-player Normal/Heroic and 25-player Normal/Heroic. This is a sourced planning contract, not live-validation evidence. The current Wowhead page is labelled Patch 4.4.2, but the client build, hotfix cutoff, and local data hash are not frozen; guide values and local implementation values are therefore kept separate.

## Bot-safe encounter contract

- Read the weekly drake state before pull. Normal has three randomly selected active drake types and two Unresponsive types; Heroic has all five active. The active drakes continuously empower Halfus or Proto-Behemoth until released.
- Use at least two tanks: one on Halfus and one on released drakes. In 25-player, a third tank is a guide-reported option for splitting drake melee. If Slate Dragon is active, swap Halfus at a pre-agreed Malevolent Strikes threshold; do not encode an exact stack threshold as a universal rule.
- Release the drakes that make the current combination survivable, then kill every released dragon. A release makes the dragon hostile and applies its counter-debuff; a death applies Dragon's Vengeance. The eight-whelp pack contributes its Vengeance stack only after all eight whelps die in the local script.
- Storm Rider active: maintain a dedicated interrupt rotation for Shadow Nova. Releasing Storm Rider makes the cast interruptible according to both current guides; the local event starts after 7 seconds and repeats every 8 seconds. Shadow Nova frequency in 10-player was changed historically, but the current script does not branch by raid size.
- Time Warden active: spread and move from Proto-Behemoth fireball impact areas. The local target filter keeps one random eligible target for the barrage and only accepts Dancing Flames targets more than 40 and less than 100 yards from the caster.
- Orphaned Emerald Whelps active: use raid cooldowns for Scorching Breath and free the cage when the raid can handle the pack. Eight whelps are spawned in the repository setup; exact 4.4.2 spawn/health/damage tuning remains unverified.
- At 50% or lower, expect Furious Roar: three raid-wide knockdown casts. Plan mitigation before the sequence and a way to interrupt a Shadow Nova immediately afterwards. The local sequence uses 3-second internal spacing and a 25-second repeat after the third cast; current guides describe an approximately 30-second cycle, so no exact retail timer is a bot invariant.
- Treat the enrage as unresolved: current strategy sources report a 6-minute Berserk, while the local event schedules `SPELL_BERSERK` at 10 minutes. Do not certify a route against either value without live evidence.

Wowhead's guide composition is 2 tanks/2–3 healers/5–6 DPS for 10-player and 2–3 tanks/5–8 healers/14–18 DPS for 25-player. This is planning guidance, not an encounter invariant.

## Mode matrix

| Mode | Current guide health | Active drake types | Unresponsive types | Local heroic branch | Mode-specific delta |
|---|---:|---|---:|---|---|
| 10N | 32.5M | 3 of 5, random weekly rotation | 2 | false | normal active-drake rotation; 10-player Shadow Nova frequency change is not represented by a local branch |
| 10H | 51.5M | all 5 | 0 | true | all five drake types are active; guide-reported heroic damage/health values are not locally verified |
| 25N | 115.9M | 3 of 5, random weekly rotation | 2 | false | same normal script branch as 10N; no authoritative 25-player coefficient table audited |
| 25H | 184.7M | all 5 | 0 | true | all five drake types are active; guide-reported heroic damage/health values are not locally verified |

The health values are current Wowhead guide reports only. The local TDB/SQL has base and difficulty-entry rows (Halfus 44600 with historical variants 46209/46210/46211), but this task did not establish that those rows reproduce the live 4.4.2 client values. Do not interpolate missing spell, drake, or timer scaling between modes.

## Observable mechanics and targeting

### Active drakes and release

Five drake types surround Halfus: Nether Scion, Slate Dragon, Storm Rider, Time Warden, and the eight Orphaned Emerald Whelps. Current Wowhead and Icy Veins both describe three of five active in Normal and all five active in Heroic. The instance constructor implements the same rule: it randomly selects three flags when `map->IsHeroic()` is false and sets `DRAGON_FLAG_ALL_ACTIVE` in Heroic.

An active non-whelp drake starts as its encounter entry and is released by spell-click/event processing. The local AI removes the spell-click and auras, lifts the drake, waits 2.5 seconds before its counter-debuff, binds it to Halfus after another 2 seconds, then makes it aggressive after 1 second. Whelps use the cage game object, move out of the cage, and follow the same debuff/bind pipeline. These are repository timings, not 4.4.2 client timings.

| Active source | While imprisoned | On release | Repository spell identities |
|---|---|---|---|
| Slate Dragon | Malevolent Strikes on Halfus; current Wowhead reports 6% Normal/8% Heroic healing reduction per stack, up to 100%, 30-second duration; guide tank swaps are around 5–8 stacks | Stone Touch periodically casts Paralysis (Wowhead reports every 35 seconds) and current guides report a 12-second Halfus stun; Icy Veins calls the release effect Stone Grip and reports +100% damage taken | `39171` Malevolent Strikes; `83603` Stone Touch; `84030` Paralysis |
| Nether Scion | Frenzied Assault; current Wowhead reports +120% attack speed | Nether Blindness: -25% hit chance, attack speed, and physical damage in the current guide | `83693` Frenzied Assault; `83611` Nether Blindness |
| Storm Rider | Shadow Wrapped grants Shadow Nova; current Wowhead reports about 8 seconds and 25k Normal/50k Heroic damage; its ability table lists 47,500–52,500 Shadow within 50,000 yards | Cyclone Winds slows casting and makes Shadow Nova interruptible; current Wowhead reports 0.25s to 1.25s | `83952` Shadow Wrapped; `83703` Shadow Nova; `83612` Cyclone Winds |
| Time Warden | Dancing Flames grants Proto-Behemoth Fireball Barrage; current Wowhead reports about 20 seconds of fireballs over 10 seconds, 40k Normal/60k Heroic within 4 yards | Time Dilation slows fireball travel/casting by 50% in the current guide | `84106` Dancing Flames; `83706` Fireball Barrage; `83601` Time Dilation; `86058`/`83862` Fireball triggers |
| Orphaned Emerald Whelps | Superheated Breath grants Proto-Behemoth Scorching Breath; current Wowhead reports about 20 seconds, 8 seconds, 8k/12k per second (64k/96k total); its ability table lists 12,000 Fire | Atrophic Poison: current Wowhead reports 750 damage reduction per whelp (8 stacks, -6000 total); Icy Veins describes the resulting breath damage as roughly halved | `83956` Superheated Breath; `83707` Scorching Breath; `83609` Atrophic Poison; `86022` Unresponsive Whelp |

These numerical values are guide examples, not a complete four-mode spell table. The local C++ confirms the ability identities and state transitions but leaves base spell coefficients and the Stone Touch period to spell data.

### Dragon's Vengeance and drake damage race

Current Wowhead and Icy Veins report a 100% increase to Halfus damage taken per defeated drake. Blizzard's historical 4.0.6 notes explicitly changed the effect to apply on kill rather than release and increased the bonus while reducing drake health/damage. The local script applies `87683` on each non-whelp drake death and applies it once after all eight whelps have died. Exact aura stacking/coefficient behavior is not independently audited in the local Spell DB; retain the kill-trigger rule and mark numeric tuning fidelity-blocked.

### Halfus and Phase 2

- Above 50%, the local boss has ordinary melee plus buffs granted by active Slate, Nether, and Storm flags; it does not schedule a separate boss ability.
- When `DamageTaken` observes below 50%, the local script schedules Furious Roar immediately. Three casts are separated by 3 seconds; after the third, the event repeats after 25 seconds. Current Wowhead describes three casts within about 2 seconds, a 6-second sequence, about 8k per cast Normal/20k Heroic, and a roughly 30-second cycle; its ability table lists 19,000–21,000 Physical. Current Icy Veins reports about 60k total and 6 seconds. The local event and guide descriptions conflict.
- Shadow Nova can be queued after a roar. Keep the interrupter ready immediately after the raid stun; do not rely on a particular class or immunity.
- The local `EVENT_BERSERK` is scheduled at 10 minutes. Wowhead and Warcraft Tavern current-era strategy material report a 6-minute enrage. This is a material unresolved timer/build discrepancy.

### Proto-Behemoth fire

Proto-Behemoth is a passive flying encounter actor. The local script starts ordinary Fireball at 1 second and repeats every 2.5 seconds, or every 3.5 seconds while Time Dilation is present. The Fireball script converts the hit to the fast or slow barrage spell. The local barrage script randomly retains one eligible destination. Dancing Flames' target script excludes targets at or below 40 yards and at or above 100 yards, then randomly keeps one target. The current Wowhead/Icy guides describe random impact locations and a 4-yard danger area, but do not provide a complete 10N/10H/25N/25H target-count table.

When Time Warden is active, local Fireball Barrage starts at 13 seconds and repeats every 31 seconds; when Whelps are also active, local Scorching Breath starts at 24 seconds, otherwise at 13 seconds, and repeats every 31 seconds. The local event reschedules ordinary fireball 11 seconds after either special cast. Current guides describe both major Proto events at roughly 20-second cadence, so local schedules are diagnostic only.

## Bot roles and gates

- Tanks: establish Halfus and released-drake threat, stack released drakes for cleave when safe, swap the boss for Malevolent Strikes, and reserve cooldowns for the opening and Furious Roar.
- Interrupt team: assign a reliable rotation to Shadow Nova whenever Storm Rider is active; reserve an immediate post-Roar interrupt.
- Ranged/melee DPS: release and kill the chosen drakes, cleave the whelps, spread from fireball impact areas, and burn Halfus after enough Dragon's Vengeance stacks.
- Healers: front-load cooldowns for the opening drake/boss damage and cover Scorching Breath, Fireball Barrage overlap, Malevolent Strikes, and Furious Roar.

Required gates are active-drake state read, release interaction, released-drake threat, Shadow Nova interruption, Fireball/Barrage avoidance, Scorching Breath mitigation, Malevolent Strikes swap, drake-kill Vengeance credit, Furious Roar recovery, and enrage-time evidence. Heroic adds the all-five-drakes gate and unverified heroic damage/health scaling; it does not introduce a separate heroic-only actor in the local script.

## Reset, completion, and credit

- `JustAppeared` reads `DATA_ACTIVE_DRAGON_FLAGS`, applies the active Halfus buffs, and spawns setup group 462. The instance owns the random Normal/Heroic flag selection.
- On engage, the local boss engages the encounter frame, resets world state 5607 (`The Only Escape`), schedules Berserk, zones Proto-Behemoth into combat, updates released-drake encounter entries, opens the whelp cage if active, and starts Shadow Nova at 7 seconds when Storm Rider is active.
- On death, `_JustDied()` performs base boss-state completion, the encounter frame disengages, and setup spawn group 462 despawns. Instance `DONE` handling notifies Cho'gall for progression dialogue. This is repository credit/state behavior, not a retail loot or achievement assertion.
- On evade, the base evade path is called, summons are despawned, the encounter frame disengages, setup group 462 despawns, and `_DespawnAtEvade()` handles the boss despawn. The Halfus class does not explicitly reset all private flags/counters; whether the engine reconstructs the AI before a repull is unresolved.
- Instance mapping is `BOSS_HALFUS_WYRMBREAKER=44600` to `DATA_HALFUS_WYRMBREAKER=0`; entrance/exit doors are 205222/205223. The Eastern Kingdoms loader invokes `AddSC_boss_halfus_wyrmbreaker`.

## Repository and database audit

- `boss_halfus_wyrmbreaker.cpp` defines Halfus, Proto-Behemoth, enslaved-dragon, whelp-cage, and spell scripts. The enum block is the authoritative local spell-ID cross-reference used here.
- `bastion_of_twilight.h` defines actor entries: Halfus 44600; Proto-Behemoth 44687; base drakes 44645/44652/44650/44797 and whelps 44641; encounter variants 44828/44829/44826/44653; and Halfus difficulty entries 46209/46210/46211.
- `instance_bastion_of_twilight.cpp` defines map 671, Normal random-three/Heroic all-five flags, object/door mapping, spawn-group behavior, event forwarding, and DONE dialogue.
- `sql/updates/world/4.3.4/2023_12_19_00_world.sql` installs setup spawn group 462, whelp-cage objects, spell-script bindings for 86003/86022/86058/83862/83719, and spell-click entries. Historical 4.3.4 TDB/custom SQL rows provide difficulty-entry and encounter rows but are not proof of current 4.4.2 tuning.

## Source metadata

1. Wowhead, “Halfus Wyrmbreaker Strategy Guide - The Bastion of Twilight Raid Cataclysm Classic,” Beanna, updated 2024-06-04, page labelled Patch 4.4.2: <https://www.wowhead.com/cata/guide/raids/the-bastion-of-twilight/halfus-wyrmbreaker-strategy>. Used for current health reports, active-drake rotation, drake effects, guide timers/damage examples, 6-minute enrage, and role guidance.
2. Icy Veins, “Halfus Wyrmbreaker Encounter Guide: Strategy, Abilities, Loot - Cataclysm Classic,” Abide, updated 2024-07-29: <https://www.icy-veins.com/cataclysm-classic/halfus-wyrmbreaker-encounter-guide-strategy-abilities-loot>. Independent current-era source for active-drake/release model, debuff mapping, Dragon's Vengeance, Scorching Breath, interrupts, tank swaps, and Furious Roar.
3. Warcraft Tavern, “Halfus Wyrmbreaker Raid Guide - Cataclysm Classic,” retrieved 2026-08-12: <https://www.warcrafttavern.com/cataclysm/guides/halfus-wyrmbreaker-raid-guide/>. The page was access-restricted to the fetcher; its indexed result independently reports active drakes, release/kill order, Furious Roar, and a 6-minute enrage. It is not used to settle exact numeric tuning.
4. Blizzard Entertainment, “Patch 4.0.6 Official Notes,” historical Cataclysm notes: <https://worldofwarcraft.blizzard.com/en-us/news/2166872>. Used only for the historical change that Dragon's Vengeance applies on kill, drake health/damage were reduced, and Shadow Nova was less frequent in 10-player; Classic carryover is not independently proven.
5. Blizzard/Kaivax, “World of Warcraft: Cataclysm Classic—Patch 4.4.2 Notes,” 2025-02-18: <https://us.forums.blizzard.com/en/wow/t/world-of-warcraft-cataclysm-classic-patch-442-notes/2062030>. Establishes the Classic 4.4.2 Hour of Twilight context but contains no Halfus tuning note.
6. Local repository revision `8eb54f0160b3c3d986ed944f9d64ebf83922c0f8`: `src/server/scripts/EasternKingdoms/BastionOfTwilight/boss_halfus_wyrmbreaker.cpp`, `instance_bastion_of_twilight.cpp`, `bastion_of_twilight.h`, `eastern_kingdoms_script_loader.cpp`, and `sql/updates/world/4.3.4/2023_12_19_00_world.sql`. Used for implementation state, IDs, targets, timers, lifecycle, setup, and registrations; repository behavior is not retail proof.

## Material conflicts and unresolved fidelity blockers

- Exact 4.4.2 client build, hotfix cutoff, locale, and client-data hashes are not frozen; historical 4.0.6 changes cannot be silently promoted to Classic.
- Guide health values are not verified against the local TDB/DBC. No authoritative complete damage/health/spawn table for all four modes was found.
- Current guides report a 6-minute Berserk; the local AI schedules Berserk at 10 minutes. Exact live timer is blocked.
- Guide Shadow Nova/Furious Roar/Proto event approximations conflict with local schedules; 10-player Shadow Nova historical frequency change is not represented by a local branch.
- Exact Malevolent Strikes, Frenzied Assault, Shadow Nova, Furious Roar, Scorching Breath, Fireball/Barrage, Atrophic Poison, and Dragon's Vengeance spell coefficients, durations, target radii, and mode scaling require client spell data or live evidence.
- Whelp health/damage and whether all eight whelp deaths are required for one retail Vengeance stack are only repository-confirmed here; current Classic behavior is not live-validated.
- Normal weekly random selection and Heroic all-five selection are repository-confirmed, but the active rotation seed/weekly reset behavior is not audited.
- Private AI state and all GUID/event cleanup after evade are not explicitly reset in the Halfus class; repull behavior is unresolved.
- Retail loot, credit, achievement completion, and Cho'gall progression semantics are not asserted beyond repository `DONE`/`FAIL` handling.

Fidelity state: `fidelity_blocked`.
