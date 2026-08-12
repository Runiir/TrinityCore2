# Conclave of Wind — Throne of the Four Winds

Research dossier for the Cataclysm Classic 4.4.2 raid-program contract. This is an evidence record, not a live-ready bot strategy: the contract and ledger are intentionally `fidelity_blocked`.

## Scope and identity

The encounter is three separate djinns on map 754:

| Platform | Boss | Base entry | Local spawn | Main role |
| --- | --- | ---: | --- | --- |
| West | Anshal | 45870 | `(-47.9531, 1053.44, 200.0943)` | Life/nature; tank and add control |
| North | Nezir | 45871 | `(189.394, 812.569, 200.0943)` | Frost tank platform and Sleet Storm soak |
| East | Rohash | 45872 | `(-51.4635, 576.25, 200.0943)` | Wind hazards; no conventional tank |

The three bosses do not share a health pool. Current Wowhead guidance says all three must die inside a 60-second window or they return at full health. The local script instead prevents a single lethal death below 1%, records a “gathering strength” state, and kills all three only after the other two are also gathering. That is a useful repository identity, not proof that the current Classic reset path is identical.

Normal and heroic are separate 10/25 modes. The local historical difficulty rows are:

| Mode | Anshal | Nezir | Rohash | Explicit local mode spell variants |
| --- | ---: | ---: | ---: | --- |
| 10N | 45870 | 45871 | 45872 | Withering 85576; Chilling 85578; Deafening 85573; Gather 86307; Wind Chill 84645 |
| 10H | 50113 | 50108 | 50105 | 93182; 93148; 93191; 101445; 93124 |
| 25N | 50103 | 50098 | 50095 | 93181; 93147; 93190; 101444; 93123 |
| 25H | 50123 | 50118 | 50115 | 93183; 93149; 93192; 101446; 93125 |

The rows and IDs come from the repository’s historical SQL/header. They are not a current 4.4.2 database snapshot. Wowhead’s current table reports approximately 4.3M/6.9M/14.6M/23.4M health per djinn for 10N/10H/25N/25H; no complete independent mode matrix or frozen client data was found, so those numbers remain guide-only.

## Observable encounter model

Keep the raid split across all three platforms. The guides agree on intentional cross-platform travel through the wind launchers/air lifts, while the local source requires a victim to be within 65 yards (2D) of that boss’s home position and excludes vehicle targets. The local check stops attacks outside the platform. If no valid player remains, Anshal and Nezir escalate a platform-wide out-of-range aura and teleport toward center; Rohash escalates its aura but has no corresponding center teleport in that local branch.

The energy model is not safe to hard-code as retail truth. Icy Veins reports starting at zero, gaining one per second, and using the ultimate at 90. Wowhead’s ability narrative says 100 and roughly 1.5 minutes. The local instance schedules a one-second power-gain loop, an 80-second warning, all three full-strength actions at 90 seconds, a 23.5-second delay before resuming gain, and a nominal 113.5-second repeat; it also schedules an eight-minute Berserk. Threshold, reset, cycle, and Berserk status are unresolved for the target build.

At full strength the three platform ultimates occur together:

- Anshal teleports to the West center and channels Zephyr (84638), healing allies and empowering surviving Ravenous Creepers. The local re-engage is 15 seconds after the cast.
- Nezir teleports to the North center and channels Sleet Storm (84644) for the same local 15-second re-engage interval. The SpellScript splits hit damage by the selected target count. Guides recommend gathering players on North, but the exact 4.4.2 target list and damage are not verified.
- Rohash channels Hurricane (84643), applying the hurricane ride-vehicle spell (86481) to caught players. Guides report a 15-second lift, periodic Nature damage, and fall damage; vehicle/fall details are blocked.

## Platform mechanics

### Anshal — West

- Soothing Breeze (86205) targets a friendly unit and creates a ground field. Guides describe a 10-yard, 30-second field that heals allies and silences/pacifies enemies inside; Wowhead reports 40k HP/s normal and 80k heroic. The local first event is 15.5 seconds and repeats randomly in the 31–33 second range. Exact 4.4.2 radius, aura and cadence remain blocked.
- Nurture (85422) summons five Ravenous Creepers (45812). The local first event is 27 seconds, and after each ultimate re-engage it schedules the next at 35 seconds. A trigger uses 85428/85429; the add count/health are not client-verified.
- Toxic Spores (86290) is applied through the Creeper pipeline. Local scheduling starts 20.5 seconds after Nurture and repeats every 20 seconds. Current guidance treats the adds as a proximity/stacking poison hazard and recommends killing or kiting them away from the raid. Exact stacks, target filters, and heroic proximity damage conflict across guide prose and spell data.
- Zephyr’s guide-reported healing and Creeper empowerment are recorded in the ledger, but no coefficient is promoted. A tank must keep Anshal and adds outside Soothing Breeze.

### Nezir — North

- Wind Chill (84645 normal 10-player; 93123/93124/93125 for 25N/10H/25H) is a local AOE event scheduled first at 11 seconds and every 11 seconds. Current guidance describes a roughly 10-second stack, Frost damage and 10% increased Frost damage taken per stack for about 35 seconds. The local mode IDs are confirmed; coefficient, duration and 25-player values are not.
- Permafrost (86082) uses the current victim and a forward cone. The local first/repeat timer is 12 seconds; guides describe a roughly three-second cone and higher heroic Frost damage. Keep the tank facing away from other players.
- Ice Patch (86122) locally selects a random in-range target and repeats from 14 seconds. Guides describe a 10-yard patch, stacking 10% slow and periodic Frost damage; exact radius, duration, target selector and scaling are blocked.
- Sleet Storm (84644) is the full-strength ultimate. Its local SpellScript divides damage by the selected target count, while current guidance gives only a broad split-damage description and mode examples. Do not encode a fixed soak count or coefficient without build evidence.

### Rohash — East

- Rohash has no conventional auto-attack/tank loop in the local source. Slicing Gale (86182) selects a random hostile target in range. The local first event is one second and repeats every 2.1 seconds; Wowhead’s table gives a 28,500–31,500 Nature range, while current prose says roughly 3–5 seconds. Timer and coefficient are blocked.
- Tornadoes (86192) summon three moving hazards. Their path is random/DB-driven and contact knocks players from the platform; exact movement and collision data are unresolved.
- Wind Blast (86193, triggered effect 85480) redirects to a world trigger and copies cone targets. The local first event is 32.5 seconds, repeats every 60 seconds, and restores aggression after an 11-second finish event; guides describe roughly 30 seconds and a six-second rotating wind wall. Direction, periodicity and damage are blocked.
- Heroic only: Storm Shield (93059) is scheduled at 30.1 seconds and after re-engage at 37.5 seconds when Rohash has at least 30 mana. Wowhead reports a 450k absorb and nearby Nature damage. The local heroic gate is confirmed; values are not.
- Hurricane (84643 → 86481) catches platform occupants at full strength. Guides describe 15 seconds of lift and Nature damage followed by fall damage. Vehicle allocation and fall behavior are unresolved.

## Synchronization, reset, and credit

The local health gate triggers below 1% and clamps lethal damage to health minus one. If two other djinns already report `DATA_IS_GATHERING_STRENGTH`, `KillConclaveIfAllowed` kills Anshal, Nezir and Rohash; otherwise the current djinn becomes passive, casts its mode-specific Gather Strength spell, and waits. The local controller does not implement an explicit 60-second full-health respawn timer, so the current guide rule stays unresolved.

Setting `DATA_CONCLAVE_OF_WIND` to `IN_PROGRESS` zones all three bosses into combat and starts global events. On failure, the instance cancels energy/warning/full-strength/Berserk events, resets Skywall effect gameobjects and despawns hurricane vehicles. On completion, Nezir’s death invokes 88835, the instance sets the Conclave state to `DONE`, removes Al’Akir’s PC immunity and sends `ACTION_CONCLAVE_DEFEATED`. Exact retail loot, encounter credit, and reset semantics are not established.

Icy Veins describes Stay Chill as defeating the encounter with at least seven Wind Chill stacks on every raid member. The source declares 94119 (`SPELL_STAY_CHILL_ACHIEVEMENT_CREDIT`) but does not cast it in this encounter file. Achievement credit is therefore blocked.

## Source and repository notes

- Wowhead, “Conclave of Wind Strategy Guide — Throne of the Four Winds Raid Cataclysm Classic,” Beanna, updated 2024-06-04, page labelled Patch 4.4.2: https://www.wowhead.com/cata/guide/raids/throne-of-the-four-winds/conclave-of-wind-strategy
- Icy Veins, “Conclave of Wind Encounter Guide: Strategy, Abilities, Loot,” Abide, updated 2024-07-29: https://www.icy-veins.com/cataclysm-classic/conclave-of-wind-encounter-guide-strategy-abilities-loot
- Warcraft Tavern, “The Conclave of Wind Raid Guide — Cataclysm Classic,” retrieved 2026-08-12; direct fetch returned 403, so only qualitative indexed text was used: https://www.warcrafttavern.com/cataclysm/guides/conclave-of-wind-raid-guide/
- Blizzard, “World of Warcraft: Cataclysm Classic Patch 4.4.2 Notes,” retrieved 2026-08-12; version context only, no Conclave tuning: https://us.forums.blizzard.com/en/wow/t/world-of-warcraft-cataclysm-classic-patch-442-notes/2062030
- Repository C++: `src/server/scripts/Kalimdor/ThroneOfTheFourWinds/boss_conclave_of_wind.cpp`, `instance_throne_of_the_four_winds.cpp`, and `throne_of_the_four_winds.h`, audited at revision `8eb54f0160b3c3d986ed944f9d64ebf83922c0f8`.
- Historical repository SQL: `sql/old/4.3.4/TDB04_to_TDB05_updates/world/023_throne_of_the_four_winds.sql` (map 754 spawns, coordinates, difficulty-entry context and prefight auras), `025_creature_template_addon.sql`, and `066_instance_encounters.sql` (encounter identity 88835). Historical SQL is provenance, not a current 4.4.2 database.

## Material blockers

The endpoint remains blocked pending a frozen 4.4.2 client/DBC or equivalent live evidence for the energy threshold/cycle, all four-mode health and coefficients, every recurring timer/random range, target counts and split rules, platform/vehicle movement, heroic Storm Shield, synchronized-death reset window, Berserk, loot/credit, and Stay Chill achievement credit. No live validation, database mutation, build, DVC operation, or commit was performed.
