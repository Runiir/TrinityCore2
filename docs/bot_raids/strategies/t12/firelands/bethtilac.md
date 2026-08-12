# Beth'tilac — Phase 0 research contract (Cataclysm Classic 4.4.2)

This dossier covers the four Firelands endpoints: `10N`, `10H`, `25N`, and `25H`. It is a sourced planning contract, not live-validation evidence. The official 4.4.2 Firelands modifier is recorded separately from encounter tuning: Blizzard announced a 30% health-and-damage reduction for all Firelands bosses and other enemies, implemented by `Power of Stormrage`, with an in-instance option to deactivate it. The announcement does not publish the aura/NPC identity or a client/DBC hash, so those fields remain `fidelity_blocked`.

## Observable encounter contract

- Beth'tilac starts on the upper fiery web. The raid is divided between a web group (boss tank, healers, and damage) and a ground group (add tank, healers, and damage). Clicking a descending Spinner's filament moves a player to the web; the web group must leave before `Smoldering Devastation` completes.
- While Beth is on the web, `Venom Rain` damages the ground every roughly 3 seconds. Players on the web suppress the ground effect; the current guides describe this as a web/ground realm interaction, but the local checkout has no encounter AI to establish the exact aura or eligibility test.
- Beth's Fire Energy drains over time. Current strategy guidance reports a natural 90-second drain, with a Drone reaching zero energy able to climb and siphon Beth's energy. At zero Beth casts an 8-second `Smoldering Devastation`; three such casts lead to her descent and Phase 2. Exact server event ordering and Drone contribution are blocked.
- In Phase 1, Spinners descend on filaments, Spiderlings run from ground spawn lanes, and a Cinderweb Drone appears about every 45 seconds. The ground group must prevent Spiderlings from reaching Beth or a Drone; Consume heals the recipient and grants a permanent damage/movement increase per Spiderling eaten.
- A `Meteor Burn` on a web player damages nearby players and burns a hole in the web. Move the web group away from the impact and use a hole to jump down before the next devastation. The current guide presents a roughly 25-second interval and a 7-yard/40,000-damage example, but not a frozen mode table.
- Phase 2 begins after the third devastation. No new adds are expected in current guides; existing adds remain a cleanup liability. Beth gains `Frenzy`, and `Widow's Kiss` requires tank swaps while the raid burns through a soft-enrage window. Exact Phase 2 ramp and reset behavior are not executable locally.

## Difficulty matrix and modifier state

| Mode | Current Cataclysm Classic guide health | Heroic delta | 4.4.2 official modifier |
|---|---:|---|---|
| 10N | 20.9M | baseline endpoint | `Power of Stormrage` announced as 30% health/damage reduction to all Firelands enemies; aura state is not locally executable |
| 10H | 32.8M | higher health/damage; heroic Drone Fixate and Engorged Broodlings are reported | same official modifier scope |
| 25N | 62.6M | 25-player scaling; normal add rules | same official modifier scope |
| 25H | 98.5M | highest health/damage; heroic add rules | same official modifier scope |

The four health figures are current-guide observations, not runtime invariants. The guide does not state whether its numbers include the optional modifier. Do not subtract 30% from them again. The official modifier announcement is authoritative for the cutoff state but does not freeze the underlying 10/25 or normal/heroic DBC values. Historical original-Cataclysm hotfixes that reduced Beth'tilac by 15% are retained only as a conflict; they must not be stacked with `Power of Stormrage`.

## Mechanics and targeting

### Web, ground, and energy

The web and floor are distinct encounter regions. A web player can be selected by web-level effects; ground players carry the add-control burden and are the affected population for `Venom Rain`. Filaments are a movement/realm gate, not a damage target. A precise range, click cooldown, player-count assignment, and server aura implementation are unresolved.

Fire Energy is the phase clock. The sources report a 1% per second natural drain, approximately 90 seconds from full to empty, and a faster drain when a Drone reaches zero and siphons Beth. At zero, `Smoldering Devastation` (`99052`) has an 8-second cast and is lethal to players remaining on the web; the spell page reports 380,000–420,000 Fire damage. The number of casts before descent and the exact energy reset are guide observations only.

### Beth'tilac's ground pressure

`Venom Rain` (`99333`) is an unlimited-range Fire hit reported every about 3 seconds while the raid is on the ground. The ability page gives 22,874–26,583 Fire damage and legacy per-difficulty values, while guide prose gives approximately 15,000 normal and 25,000 heroic; retain the identity and relationship, not one coefficient. `Ember Flare` (`98934`) hits web-level players roughly every 5–7 seconds; current narrative examples are about 18,000 normal and 28,000 heroic, while the table exposes a different range. These are not a mode-verified runtime table.

`Meteor Burn` (`99076`) targets a random web player approximately every 25 seconds. The current guide reports about 40,000 Fire damage within 7 yards and a hole in the web. The target filter, impact geometry, and whether the timer is a cooldown or event range are unresolved.

### Cinderweb Spinners

At the pull and after each devastation, roughly 4–9 Spinners descend on filaments after about 1.5 minutes. While hanging they cast `Burning Acid` (`98471`) at random players about every 2 seconds; the page identifies a 2-second cooldown and 30,914–34,862 Fire damage, while the guide reports lower normal/heroic examples. Taunt or otherwise bring them down so they can be killed; clicking a filament carries a player to the web. Historical heroic references add a hanging stun (`Fiery Web Spin`), but the current guide does not confirm its 4.4.2 presence, so it remains a heroic conflict rather than a contract rule.

### Ground adds

- **Cinderweb Drone** (`52581`): one roughly every 45 seconds. The off-tank keeps its frontal `Boiling Spatter` (`99463`) away from the raid; the spell page reports 76,658–89,089 Fire in a forward cone. Drone `Burning Acid` (`99934`) selects a random player; guide prose gives roughly an 8-second cadence and 20,000/28,000 examples, but the current page and narrative values conflict. The Drone's energy is reported to drain at 1% per second; at zero it climbs and siphons Beth. If a Spiderling is within about 10 yards, Drone `Consume` (`99304`) heals it for 20% maximum health and permanently adds 20% damage and movement speed per Spiderling. Heroic guides report `Fixate` on a random ground player for 10 seconds with 75% reduced Drone damage; exact spell identity and target exclusion are unresolved.
- **Cinderweb Spiderling** (`52447`): current guidance reports a wave of three from three lanes about every 12 seconds, generally rushing the highest-threat player (often a healer). On reaching a target it leaps within 6 yards and applies `Seeping Venom` (`97079`), 6,937–8,062 Nature every 2 seconds for 10 seconds. Icy Veins reports four spawn locations, while other current and historical guides report three; lane count and mode distribution are blocked. Spiderlings reaching Beth trigger a heal; exact target, range, and whether the heal is 10% or another current value are not locally implemented.
- **Engorged Broodling** (`53745`, heroic): current guides report these only in heroic, following Spiderling waves. They fixate a player and detonate on contact with `Volatile Burst`; sources disagree on whether they are killed, intercepted, or only soaked and on the exact damage/pool behavior. Their spawn count, lane mapping, target filter, and mode scaling remain blocked. Historical DB variants (`53746`–`53748`) are identity references, not mode assignments.

### Phase 2

After three devastations Beth descends, no new adds are expected, and surviving ground entities still matter. `Frenzy` (`99497`) is reported as +5% damage per stack about every 5 seconds. `Widow's Kiss` (`99476`) is a tank debuff: current guide prose describes a 10% healing reduction every 2 seconds for 20 seconds and a nearby-ally consequence; the ability page presents malformed/conflicting text. `Consume` heals Beth when a Spiderling is consumed. The exact stack cap, tank-swap window, aura targets, and whether Ember Flare ramps with Frenzy are all fidelity-blocked.

## Repository, DB, reset, unlock, and credit audit

The audited revision is `8eb54f0160b3c3d986ed944f9d64ebf83922c0f8`.

- `src/server/scripts/Kalimdor/Firelands/firelands.h` defines map 720, seven encounter slots, `DATA_BETHTILAC=0`, boss entry `52498`, and door `208877`. `instance_firelands.cpp` maps the boss and door only; it contains no Beth-specific events, phases, summons, reset, loot, credit, or achievement handling.
- `src/server/scripts/Kalimdor/Firelands/` has implementations for the other Firelands bosses but no `boss_bethtilac.cpp`. The Kalimdor loader has no Beth declaration or `AddSC_boss_bethtilac` call. Therefore there is no executable local evidence for web/ground state, add cadence, energy, phase changes, wipe cleanup, or completion.
- Historical TDB rows identify Beth variants `52498`, `52675`, `53576`–`53578`, and `54089`; Spiderling `52447`, Spinner `52524`, Drone `52581`, and Broodling `53745` plus variants. Historical `instance_encounters` row `1197` maps entry `52498` to Beth'tilac. These rows are identity evidence only and do not establish current Classic mode tuning.
- Firelands was released as a seven-boss 10/25-player normal/heroic raid in the official 4.4.1 notes. No Beth-specific unlock prerequisite is published; local instance code does not implement an unlock event. Treat accessibility, door behavior, encounter state, retail lockout, loot, achievement, and player credit as blocked until runtime evidence exists.

## Material blockers

- Exact Cataclysm Classic 4.4.2 client/DBC build, Beth/add mode table, and whether current-guide health/damage examples are before or after `Power of Stormrage`.
- Official modifier aura/NPC IDs and default/toggle persistence; do not invent IDs from the announcement.
- Beth's web/ground aura and filament rules; Fire Energy implementation; exact Smoldering count, reset, and descent sequence.
- All four-mode health/damage coefficients and timer jitter for Venom Rain, Ember Flare, Meteor Burn, Spinners, Drones, Spiderlings, Broodlings, Frenzy, and Widow's Kiss.
- Spiderling lane count (three versus four), Broodling kill/soak semantics, heroic Spinner ability, target filters, add cleanup, phase transition, wipe reset, door/unlock, loot, achievement, and credit.

## Source metadata

1. [Wowhead Beth'tilac strategy guide](https://www.wowhead.com/cata/guide/raids/firelands/bethtilac-strategy-overview), updated 2024-10-25, Cataclysm Classic. Used for four-mode boss health, web/ground flow, current timers/examples, add behavior, Phase 2, and ability values; approximate or conflicting values stay blocked.
2. [Icy Veins Beth'tilac encounter guide](https://www.icy-veins.com/cataclysm-classic/bethtilac-encounter-guide-strategy-abilities-loot), Abide, updated 2024-10-08. Used independently for role/target flow, heroic Fixate/Broodling behavior, four-lane conflict, and Phase 2 description.
3. [Blizzard: Firelands difficulty reduction with Hour of Twilight patch](https://us.forums.blizzard.com/en/wow/t/firelands-difficulty-reduction-with-hour-of-twilight-patch/2059756), Kaivax, 2025-02-13. Official 4.4.2 cutoff source for 30% health/damage reduction, `Power of Stormrage`, and General Taldris Moonfall deactivation.
4. [Blizzard: Cataclysm Classic Patch 4.4.1 notes](https://us.forums.blizzard.com/en/wow/t/world-of-warcraft-cataclysm-classic-patch-441-notes/1996710), 2024-11-07. Used for Firelands release, seven bosses, and 10/25 normal/heroic endpoint scope.
5. [Blizzard: Cataclysm Classic Patch 4.4.2 notes](https://us.forums.blizzard.com/en/wow/t/world-of-warcraft-cataclysm-classic-patch-442-notes/2062030), 2025-02-18. Release context only; it does not publish a Beth client/DBC hash or mode table.
6. [Blizzard: original Cataclysm 4.2 hotfixes](https://worldofwarcraft.blizzard.com/en-us/news/3019413), historical reference. Used only to record the old 15% Beth reduction as a non-applicable conflict; it is not stacked with the 4.4.2 modifier.
7. [Wowhead Beth'tilac NPC page](https://www.wowhead.com/cata/npc=52498/bethtilac) and linked [spell pages](https://www.wowhead.com/cata/spell=99333/venom-rain). Used for spell/NPC identity and page-level ranges; malformed or legacy mode presentations are explicitly not promoted.
8. Local repository audit at revision `8eb54f0160b3c3d986ed944f9d64ebf83922c0f8`: `src/server/scripts/Kalimdor/Firelands/firelands.h`, `instance_firelands.cpp`, `kalimdor_script_loader.cpp`, and historical SQL under `sql/old/4.3.4` for Beth/add/encounter identities. No Beth AI is present.
