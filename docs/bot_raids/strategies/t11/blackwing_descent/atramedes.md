# Atramedes — Phase 0 research contract v2

Scope: Cataclysm Classic 4.4.2-labelled behavior for 10-player Normal (10N), 10-player Heroic (10H), 25-player Normal (25N), and 25-player Heroic (25H). This is a researched planning contract, not a live-validation result. Exact client/DBC coefficients and movement timing are not inferred where sources disagree.

## Contract

- Track every player’s Sound from 0 to 100. At 100, treat the player as a hard-fail target for Devastation. Keep Sound low enough that gongs are reserved for Searing Flame and air-breath rescue.
- Assign one gong owner and a second emergency owner. A gong resets raid Sound and applies Vertigo; normal has ten shield spawns, while Heroic Nefarius destroys another available shield after each ground gong, leaving a guide-reported effective budget of seven.
- Ground: keep melee at maximum range, spread or use stable groups to make Sonar Pulse paths predictable, and move the Sonic Breath target around the boss without crossing the raid. Gong Searing Flame immediately when its cast begins.
- Air: move continuously to dodge Sonar Bomb and fire patches. Kite Roaring Flame Breath around the outside, never through the center. Gong only when the current breath is about to catch its target; the gong becomes the next breath target and is then destroyed.
- Heroic: interrupt and kill Obnoxious Fiends immediately. Their approach is phase-shifted/immune in the local AI; after attachment, interrupt Obnoxious and remove the Fiend before it forces an early gong.

## Mode matrix

| Mode | Current guide health | Guide shield budget | Local/guide phase model | Heroic delta |
|---|---:|---:|---|---|
| 10N | 32.6M | 10 | local first liftoff at 91s, air land event 31s; guides report 85/40 or 80/40 | none |
| 25N | 97.9M | 10 | same local timer path; exact movement duration unresolved | none |
| 10H | 34.8M | 7 effective | same local timer path; guides report 85/40 or 90/30 | Nefarius destroys extra ground-gong shields; Fiends; higher damage/Sound |
| 25H | 103M | 7 effective | same local timer path; exact movement duration unresolved | Nefarius destroys extra ground-gong shields; Fiends; higher damage/Sound |

Current Wowhead reports 32.6M/34.8M/97.9M/103M for 10N/10H/25N/25H. The historical Icy Veins page reports 26.1M/34.8M/78.3M/103M; normal health provenance is unresolved and must not become a bot invariant.

## Observable mechanics and targeting

### Sound and gongs

- The Sound Bar starts at zero. Current guides agree that 100 Sound triggers Devastation and kills the player; the local Sound Bar script adds the Noisy state at alternate power equal to max and the Devastation trigger runs only while a noisy player exists.
- The local script updates the Silence is Golden world state when any player reaches at least 50 Sound. This is achievement state, not a combat threshold.
- A shield click in ground uses Resonating Clash Ground, manually interrupts Atramedes, and applies Vertigo. Current guides report five seconds of stun and 50% increased damage; the local script confirms the manual interrupt and shield tracking, but spell duration/coefficient remains DBC data.
- A shield click in air records both the used shield and clicker. The Reverberating Flame stops, waits two seconds, travels to the shield, casts Sonic Flames, then tracks the clicker (or nearest player within 100 yards if the clicker is unavailable). The local spell script removes the relevant Vertigo/air aura and the breath redirection is therefore an observable local rule.

### Ground phase

- Local first ground events are Modulation 13s, Sonar Pulse 14.5s, Sonic Breath 24s, Searing Flame 46s, and liftoff 91s. Sonar repeats every 11s; Modulation repeats randomly 22–26s; Sonic Breath repeats randomly 42–43s. After landing, local events are Sonar14s, Modulation13s, Searing51s, Sonic22s, then liftoff after 93s. The Searing cast reschedules Modulation six seconds later.
- Current Wowhead reports an 85-second ground phase, Modulation every 15s, Sonar Pulse every 10s with four disks, Sonic Breath every 20s, and Searing Flame after 40s. Current Icy Veins reports 90s ground and Sonic Breath every 40s; the historical page reports 80s ground and two Sonic Breaths per phase. These are retained as conflicts against the local schedule.
- Modulation is unavoidable raid damage and adds Sound in current strategy guidance. The local spell script increases each hit by the target’s current alternate-power percentage; no numeric DBC base damage is encoded in C++.
- Sonic Breath local target filtering removes Atramedes’s current victim, then randomly keeps one eligible area target. Current Wowhead calls the target random; historical Icy Veins says highest Sound and not the tank. Exact 4.4.2 target selection/range is unresolved.
- Searing Flame is once per ground phase in strategy sources. Wowhead reports 20k normal/40k Heroic every two seconds for six seconds, stacking +50% Fire damage per tick; it also reports Roaring Flame patches lasting 45s, 10k/20k initial damage, 8k/10k periodic damage, and +5/+10 Sound. The local C++ schedules the cast but leaves these coefficients to spell data.
- Sonar Pulse disks are local summons: the pulse aura starts after 400ms, movement begins after another 800ms, and each disk travels to first collision within 100 yards before despawning at spline duration. The exact disk target and spell coefficients are DBC/guide data.

### Air phase

- On reaching the liftoff point, local Atramedes disables gravity, starts the Sonar Pulse trigger and Roaring Flame Breath, and schedules the land event after 31s. Landing movement then returns him to ground, re-engages players after 800ms, and starts the next ground schedule. Current Wowhead reports 40s air; current Icy Veins reports 30s; the historical page reports 40s. Movement duration is unmeasured.
- Roaring Flame Breath tracks a moving flame entity. Local tracking follows the summoner, and a gong redirects the flame to the shield before tracking the gong user. Current Wowhead describes a random initial player and a breath that accelerates until gonged; historical Icy Veins says the highest-Sound player is initially selected. Do not encode the disputed initial target as exact.
- Current Wowhead reports three Sonar Bomb locations every three seconds in Normal and six in Heroic, with 20k/30k Arcane damage within six yards and +20/+30 Sound when hit. Historical Icy Veins reports five 10-player or eight 25-player locations, three-second telegraphs, +20 Sound, and Sound-scaled air damage. Local C++ starts the trigger and handles each bomb summon but does not encode the mode target count.
- Air fire trails/patches are movement hazards. Keep kites on the outside and place each gong far from the current breath target so the redirect takes longer.

## Heroic mechanics

- Heroic summons Lord Victor Nefarius at engage. Local Nefarius schedules an initial Fiend at 30s, repeats every 35s, stops at liftoff, and restarts 30s after landing. Current Wowhead describes a Fiend every 30s during ground; historical Icy Veins describes twice per ground phase, sometimes once or three times. Treat count/cadence as a conflict.
- The local Fiend chooses a random eligible player within 100 yards, excluding players already carrying Pestered, focuses/chases after one-second steps, and casts Obnoxious one second after attachment then every 2.5s. Current Wowhead reports +10 Sound every 1.5s; historical Icy Veins reports roughly 10k melee and +10 Sound, so exact period and damage are unresolved.
- Nefarius’s Destroy Shield spell locally filters to selectable shields and randomly removes one. It is triggered after Vertigo ends, confirming the extra Heroic shield loss, but exact spell target-area behavior is DBC-dependent.
- Current Icy Veins says Heroic raises damage and Sound scaling for all listed abilities except Roaring Flame Breath and makes Sonar Bombs fall faster. Wowhead supplies individual examples. These claims are recorded as guide-reported deltas; exact per-mode coefficients remain unresolved.

## Reset, completion, and credit

- `Reset()` calls `_Reset()` and sets the event phase to intro but does not explicitly clear `_noisyPlayerGUIDs`, shield GUIDs, or the Reverberating Flame GUID. Engage reinitializes the Sound Bar and achievement world state. Whether the engine reconstructs the AI object before a repull is unresolved.
- Evade despawns tracked summons, disengages the encounter, sets `DATA_ATRAMEDES` to FAIL, removes the Nefarius vehicle aura from players, reopens the Athenaeum door, and despawns Atramedes. The instance schedules shield/boss respawn after 30s.
- Death calls `_JustDied()`, disengages the frame, removes the vehicle aura, reopens the door, and speaks the death line. Instance `SetBossState(DATA_ATRAMEDES, DONE)` despawns the shield spawn group and notifies generic Nefarius; this is the expected boss credit path.
- The instance creates/spawns Ancient Dwarven Shield group 400, maps creature 41442 to `DATA_ATRAMEDES`, and forwards Atramedes summons (Sonar Pulse, Tracking Flames, Sonar Bomb, Reverberating Flame, Obnoxious Fiend) to the boss AI. Loader registration invokes `AddSC_boss_atramedes`.

## Repository audit

- `boss_atramedes.cpp` defines Sound/Noisy/Devastation, gong ground/air handling, target filters, movement, all local timers, Nefarius/Fiend behavior, cleanup, and spell scripts.
- `blackwing_descent.h` defines Atramedes 41442, Sonar Pulse 41546, Sonar Bomb 49623, Tracking Flames 41879, Reverberating Flame 41962, Nefarius 49580, and Obnoxious Fiend 49740, plus `DATA_ATRAMEDES=3`.
- `instance_blackwing_descent.cpp` maps 41442 to `DATA_ATRAMEDES`, spawns shield group 400, forwards summons, sets FAIL/DONE handling, and respawns shields/boss after 30s on failure.
- The current TDB row for 41442 has difficulty entries 49583/49584/49585 and ScriptName `boss_atramedes`; local TDB rows exist for the Heroic Nefarius and Fiend variants. `sql/updates/world/4.3.4/2022_01_09_01_world.sql` binds Reverberating Flame 41962. The historical custom update explicitly binds the boss, shields, Nefarius, Fiend, spell scripts, vehicle accessory, spellclicks, conditions, and movement. Whether that historical custom pack is applied is outside this audit.
- Historical map-669 spawn SQL lists ten Ancient Dwarven Shield creature spawns and the Atramedes encounter area. This is DB history, not proof of the live 4.4.2 hotfix state.

## Source metadata

1. Wowhead, “Atramedes Strategy Guide - Blackwing Descent Raid Cataclysm Classic,” Beanna, updated 2024-06-04, page labelled Patch 4.4.2: <https://www.wowhead.com/cata/guide/raids/blackwing-descent/atramedes-strategy>. Used for current health, Sound/gong behavior, current ground/air timing, damage examples, target descriptions, Sonar Bomb counts, and Heroic Fiend/shield behavior.
2. Icy Veins, “Atramedes Encounter Guide: Strategy, Abilities, Loot - Cataclysm Classic,” Abide, updated 2024-07-29: <https://www.icy-veins.com/cataclysm-classic/atramedes-encounter-guide-strategy-abilities-loot>. Independent current-era source for Sound, ten/seven shields, ground/air execution, gong use, air kiting, and Heroic Fiends.
3. Icy Veins, “Atramedes Detailed Strategy Guide (Heroic Mode included),” Damien, last updated 2012-10-08, explicitly marked WoD 6.1.2: <https://www.icy-veins.com/wow/atramedes-strategy-guide-normal-heroic>. Historical independent source used only for alternate phase/timer/target counts, Sound scaling, Heroic deltas, and health values; not treated as 4.4.2 authority.
4. Local repository: `src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent/boss_atramedes.cpp` (lines 37–1141), `blackwing_descent.h` (lines 25–145), `instance_blackwing_descent.cpp` (lines 31–505), and `eastern_kingdoms_script_loader.cpp` (lines 76–83, 308–315).
5. Local DB/SQL: `data/TDB_full_434.22011_2022_01_09/TDB_full_world_434.22011_2022_01_09.sql` creature-template rows; `sql/updates/world/4.3.4/2022_01_09_01_world.sql` (Reverberating Flame binding); `sql/updates/world/4.3.4/2023_09_15_00_world.sql` (creature addon rows); `sql/old/custom/world/34_2020_02_21/custom_2019_08_20_00_world_updatepack.sql` (lines 166876–167027); and `sql/old/4.3.4/world/10_2016_03_12/2015_10_02_00_world.sql` (lines 132–141, map 669 shield spawns).

## Material conflicts

- Current Wowhead: 85s ground/40s air; current Icy Veins: 90s/30s; historical Icy Veins: 80s/40s; local: 91s first liftoff, 31s air event, 93s later liftoff plus movement.
- Sonic Breath cadence/target: current Wowhead random every20s; current Icy Veins every40s; historical Icy Veins highest Sound, twice per ground phase, not tank; local random eligible target excluding current victim.
- Sonar Bomb: current Wowhead 3 Normal/6 Heroic locations; historical Icy Veins 5 10-player/8 25-player; local trigger has no C++ count.
- Sound/damage coefficients differ between current Wowhead examples and historical Icy Veins’s Sound-scaling descriptions; exact DBC values are unresolved.
- Heroic Fiend timing differs (current Wowhead every30s, local 30s then35s, historical Icy twice per ground); Fiend Obnoxious period differs (current guide1.5s, local2.5s).
- Normal health differs between current Wowhead and historical Icy Veins; no reliable exact build/hotfix evidence resolves it.

## Unresolved fidelity blockers

- Exact Blizzard 4.4.2 client/build/hotfix cutoff and whether the local TDB/SQL snapshot matches it.
- Live ground/air movement duration and actual event timestamps in all four modes.
- Exact 4.4.2 Sound gain, DBC coefficients, spell target radii, and mode-specific Sonar/Sonic target counts.
- Initial Sonic Breath and Roaring Flame Breath target-selection rule (random versus highest Sound) and Heroic timing.
- Heroic Fiend spawn count/period, Obnoxious period/damage, and whether all ability Sound/damage deltas match the current guide.
- AI object reconstruction and explicit reset behavior for custom GUID sets after evade.
- Whether the historical custom SQL pack is applied to the current database.
