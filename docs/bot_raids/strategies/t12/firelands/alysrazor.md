# Alysrazor — Phase 0 research contract (Cataclysm Classic 4.4.2)

This dossier covers the four Firelands endpoints: `10N`, `10H`, `25N`, and `25H`. It is a sourced planning contract, not live-validation evidence. Blizzard announced a 30% health-and-damage reduction for every Firelands boss and other enemy at the 4.4.2 cutoff through `Power of Stormrage`; General Taldris Moonfall can deactivate it. The announcement does not publish the aura/NPC identity, default state, or persistence, so those fields remain `fidelity_blocked`.

## Observable encounter contract

Alysrazor is a four-phase flying/ground encounter. Current Cataclysm Classic guides describe a short opening Firestorm, then repeated Phase 1 flight cycles: Alysrazor circles the arena while ground teams handle Blazing Talon Initiates, Voracious Hatchlings, Plump Lava Worms, and the fire rings used by the flight team. Three Molten Feathers grant `Wings of Flame`; rings refresh flight and build `Blazing Power`. Phase 2 strips flight and creates a Fiery Vortex followed by Fiery Tornados. Alysrazor crashes into Burnout in Phase 3 while two Blazing Talon Clawshapers can restore her energy. At 50 Molten Power, Phase 4 is a grounded burn with Blazing Claw and Blazing Buffet. Guides report a permanent ground state after the third Phase 4 cycle.

The local checkout does not contain an Alysrazor boss AI. `boss_alysrazor.cpp` registers only trash/cosmetic scripts; the instance script maps the encounter slot and starts hatchling attacks, but contains no boss phases, energy, flight, reset, completion, or credit handler. Guide observations therefore cannot be promoted to executable invariants.

## Difficulty matrix and modifier state

| Mode | Current Cataclysm Classic guide health | Reported mode delta | 4.4.2 official modifier |
|---|---:|---|---|
| 10N | 51.5M | baseline guide observation | `Power of Stormrage`: announced −30% health and −30% damage to Firelands bosses/enemies; runtime aura/default unresolved |
| 10H | 77.3M | heroic Hatchling/Meteor and damage differences reported; exact table blocked | same official scope |
| 25N | 154.6M | 25-player health/add scaling; exact table blocked | same official scope |
| 25H | 231.9M | highest guide health; heroic add/meteor differences reported; exact table blocked | same official scope |

These health figures are guide observations and their modifier state is unspecified. Do not subtract 30% a second time. No current source audited here freezes all four mode coefficients, timer jitter, or whether the optional modifier is active in the guide values.

## Mechanics and targeting

### Opening and Phase 1 ground teams

On a fresh pull, guides report roleplay before Firestorm; Firestorm deals a large fire hit and knockback, followed by a ground strafe/Volcanic Fire effect. A ring blocks escape during the opening. Exact cast IDs, impact radius, target filter, roleplay duration, and reset behavior are not established by this checkout.

Blazing Talon Initiates are reported in alternating pairs roughly every 25 seconds, with four sets in a Phase 1 cycle. They use Brushfire and interruptible Fieroblast; `Fire It Up` stacks increase cast speed and damage. The exact spawn points, count in each mode, target filters, interrupt window, and damage table are unresolved.

Voracious Hatchlings hatch from two Molten Eggs about 10 seconds after each reported 35-second set. The nearest player is Imprinted and gains effectively unbounded threat plus a large damage increase for roughly three minutes or until death. After about 10 seconds they become Hungry; Tantrum is reported as a chance-based attack-speed/damage increase until fed. Satiated and feeding rules vary by source. Current guides report four Hatchlings in normal and six with reduced health in heroic; this is not repository-backed mode logic.

Plump Lava Worms are reported as four in normal and two in heroic. Their channel is a rotating cone; Gushing Wound is described as a periodic 60-degree cone and Lava Spew as a forward fire cone. The exact count, spawn locations, cone orientation, health, falloff, and mode coefficients remain blocked.

### Flight, rings, altitude, and energy

Players can take up to three Molten Feathers. Sources agree that the third grants `Wings of Flame` and approximately 30 seconds of flight; sources differ in whether the first two stacks are described as movement casting, movement speed, or both. During flight, rings are reported to open briefly, refresh flight, grant one `Blazing Power` stack, and restore 5% of a class resource. `Blazing Power` is reported as +8% haste per stack up to 25 stacks; 25 stacks grants `Alysra's Razor`, +75% critical strike chance for about 40 seconds. Ring geometry, spawn cadence, exact altitude and arena bounds, ring target eligibility, resource type, and spell implementation are unresolved.

### Phase 2 tornado

After the reported Phase 1 interval, Alysrazor strips Wings while retaining Feather/Power/Razor buffs. `Harsh Winds` creates a Fiery Vortex: guides report lethal periodic fire near the center and a lower but continuing fire loss outside its safe range. After about 10 seconds, five Fiery Tornados travel in a ring for about 20 seconds; current Classic guidance reports slower tornado behavior than legacy guides. Exact path, speed, height, collision, target eligibility, damage, and normal/heroic delta are blocked.

### Phase 3 crash and energy

After approximately 30 seconds of Phase 2, Alysrazor crashes and gains `Burnout`, reported as +50% damage taken. A Spark restores Molten Power; two Blazing Talon Clawshapers spawn about five seconds after the crash and periodically cast `Ignition`, restoring energy unless interrupted. Guides report a roughly 34-second phase window and differing Spark/energy descriptions. Exact resource name/DBC power type, starting and maximum values, Spark cadence, Clawshaper health, interrupt target, Ignition amount, and crash reset are fidelity-blocked.

### Phase 4 ground burn

At 50 Molten Power, Clawshapers leave and Alysrazor uses Blazing Claw about every 1.5 seconds in a frontal arc. Guides report a 10% stacking physical/fire vulnerability for 15 seconds. Ignited restores about two Molten Power per second; Blazing Buffet is reported every second for about 25 seconds, then Full Power deals a large fire hit and knocks players roughly 150 yards away. The third Phase 4 cycle is reported to leave her permanently grounded. Exact target/range, stack reset, damage coefficients, energy loop, knockback safeguards, soft-enrage, and mode deltas are unresolved.

Heroic guidance additionally reports Molten Meteors during Phase 1. Their roll, wall split, cover, timing, kill requirement, target/range, and exact spell identity are not verified in the local source or an authoritative four-mode table, so they are a heroic gate rather than an execution rule.

## Repository, DB, reset, unlock, and credit audit

The audited revision is `9e69ff681125b8ed5bfe67bba3cba5a9f94655e1`.

- `firelands.h` defines map 720, seven encounter slots, `DATA_ALYSRAZOR=3`, boss entry `52530`, and Alysrazor trash IDs: Blazing Monstrosity `53786`/`53791`, Egg Pile `53795`, Harbinger `53793`, Molten Egg `53914`, and Smouldering Hatchling `53794`.
- `kalimdor_script_loader.cpp` calls `AddSC_boss_alysrazor()`, but that function registers only `npc_harbinger_of_flame`, `npc_blazing_monstrosity`, `npc_molten_barrage`, `npc_egg_pile`, and cosmetic/utility spell scripts. There is no `boss_alysrazor` class or boss phase implementation.
- `instance_firelands.cpp` maps `BOSS_ALYSRAZOR` to `DATA_ALYSRAZOR` and delays Hatchling attack start by 500 ms. It has no Alysrazor-specific phase, energy, reset, death, loot, achievement, or player-credit logic.
- Historical SQL maps the base entry's difficulty slots to `54044`, `54045`, and `54046`, and sets HoverHeight 14, VehicleId 1673, and `mana_mod_extra=1.72414` on all four historical entries. The slot order is historical identity evidence, not proof of the current Classic 10/25 normal/heroic table. The spawn row places `52530` on map 720 at `(-41.9236,-275.299,48.29314)` with 7200-second respawn. Historical `instance_encounters` row `1206` names entry `52530` Alysrazor.
- Historical DB rows identify Fiery Vortex `53693` with aura `99793`, Fiery Tornado `53698` with aura `99817`, Plump Lava Worm `53520` with aura `99327`, and Blazing Talon Clawshaper `53734`. The local C++ additionally proves only trash/cosmetic spell identities and timings: Harbinger Fieroblast `100094` begins at 1 ms and is rescheduled at 500 ms; Fieroclast Barrage `100095` begins at 6 s and repeats randomly from 9–12 s; Blazing Monstrosity starts Molten Barrage at 6 s and continues at 9 s; Egg Pile summons a Hatchling at 1 ms, selects a live egg within 20 yards, hides it for 5 s, and repeats in a random 6–10 s window. These are trash mechanics, not boss timers.

No local Alysrazor `Reset`, `EnterEvadeMode`, `JustDied`, phase transition, door/unlock, loot, achievement, or credit handler exists. Encounter accessibility, wipe cleanup, lockout, completion credit, and difficulty selection must remain blocked until build-matched runtime evidence is available.

## Material blockers

1. Exact 4.4.2 client/DBC build and Firelands hotfix cutoff.
2. `Power of Stormrage` aura/NPC IDs, default state, persistence, and runtime toggle.
3. Whether the current guide health values already include the official modifier.
4. All four-mode health/damage coefficients and timer jitter.
5. Opening Firestorm/Volcanic Fire IDs, timing, target, range, and reset.
6. Phase 1 duration and the conflicting normal/heroic cycle reports.
7. Initiate spawn cadence, positions, counts, Brushfire/Fieroblast targeting, and scaling.
8. Hatchling counts, health, hatch timing, Imprint target and duration.
9. Hungry, Tantrum, Satiated, feeding, and worm interaction semantics.
10. Worm count, spawn geometry, cone/falloff rules, and scaling.
11. Feather stack behavior, flight duration, ring geometry, timing, altitude, and arena bounds.
12. Blazing Power/Razor resource, cap, restoration, duration, and target rules.
13. Phase 2 entry, Harsh Winds/Vortex filters, and damage/range values.
14. Fiery Tornado path, count, speed, altitude, collision, and damage.
15. Phase 3 Burnout, Spark, Molten Power, Clawshaper spawn, and Ignition implementation.
16. Clawshaper health, interrupt behavior, energy amount, and phase length.
17. Phase 4 Claw, vulnerability stacks, Buffet, Full Power, knockback, and energy loop.
18. Heroic Molten Meteor identity, timing, roll/split/cover mechanics, and scaling.
19. Number of cycles, third-cycle permanent-ground behavior, and soft-enrage state.
20. Local absence of boss AI means no executable phase/target/reset/add lifecycle.
21. Wipe reset, spawn/door state, unlock, lockout, loot, achievement, and player credit.
22. Historical difficulty-entry-to-mode mapping and modifier interaction are not current-build proof.

## Source metadata

1. [Wowhead Alysrazor strategy overview](https://www.wowhead.com/cata/guide/raids/firelands/alysrazor-strategy-overview), updated 2024-10-25, Cataclysm Classic. Used for four-mode guide health, phase flow, flight/ring observations, ground teams, add counts, tornado and ground-burn examples; approximate or conflicting values remain blocked.
2. [Icy Veins Alysrazor encounter guide](https://www.icy-veins.com/cataclysm-classic/alysrazor-encounter-guide-strategy-abilities-loot), updated 2024-10-08. Used as an independent cross-check for phase timing, feathers, Hatchlings/worms, Ignition, and Phase 4; conflicting phase durations and narrative values are retained as conflicts.
3. [Warcraft Tavern Alysrazor raid guide](https://www.warcrafttavern.com/cataclysm/guides/alysrazor-raid-guide-cataclysm-classic/), Cataclysm Classic guide. Used only to cross-check ring duration/Power/Razor and the reported heroic Molten Meteor mechanic; it does not supply a frozen 4.4.2 mode table.
4. [Blizzard: Firelands difficulty reduction with Hour of Twilight patch](https://us.forums.blizzard.com/en/wow/t/firelands-difficulty-reduction-with-hour-of-twilight-patch/2059756), Kaivax, 2025-02-13. Official 4.4.2 source for `Power of Stormrage`, the 30% health/damage reduction, and General Taldris Moonfall deactivation.
5. [Blizzard: Cataclysm Classic Patch 4.4.1 notes](https://us.forums.blizzard.com/en/wow/t/world-of-warcraft-cataclysm-classic-patch-441-notes/1996710), 2024-11-07. Used for Firelands release and seven-boss 10/25 normal/heroic scope.
6. [Blizzard: Cataclysm Classic Patch 4.4.2 notes](https://us.forums.blizzard.com/en/wow/t/world-of-warcraft-cataclysm-classic-patch-442-notes/2062030), 2025-02-18. Release context only; it does not publish an Alysrazor client/DBC hash or mode table.
7. [Wowhead Alysrazor NPC page](https://www.wowhead.com/cata/npc=52530/alysrazor), Cataclysm Classic identity/reference page. Used for boss identity and ability-name cross-checks; page-level tuning is not promoted over the guide conflicts.
8. Local repository audit at revision `9e69ff681125b8ed5bfe67bba3cba5a9f94655e1`: `src/server/scripts/Kalimdor/Firelands/boss_alysrazor.cpp`, `firelands.h`, `instance_firelands.cpp`, loader, and historical SQL under `sql/old/4.3.4`. Used for executable absence, IDs, historical templates/spawns, and trash-only timer evidence.
