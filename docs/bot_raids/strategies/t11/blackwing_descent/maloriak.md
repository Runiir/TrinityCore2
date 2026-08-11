# Maloriak — Phase 0 research contract v2

Scope: Cataclysm Classic 4.4.2-labelled behavior for 10-player Normal (10N), 10-player Heroic (10H), 25-player Normal (25N), and 25-player Heroic (25H). This is a researched planning contract, not a live-validation result. Where the current server implementation and a guide disagree, the disagreement is retained and the bot must not schedule the disputed value as exact.

## Contract

- Interrupt every Arcane Storm. Keep a second interrupt lane for Release Aberrations, but deliberately allow only a controlled number of successful casts; never interrupt a Release cast by reflex if the add quota for the current green window is not met.
- Remove Remedy immediately by purge/dispel or spellsteal. Treat it as possible in every main-phase color and be ready for a guide-reported occasional cast in phase two, even though the local phase-two event map schedules no new Remedy.
- Normal vial order is `Red or Blue -> the other color -> Green`; the first color is random per cycle. Heroic order is `Black -> Red or Blue -> the other color -> Green`, repeating after Green. Do not infer the first Red/Blue color from the previous cycle.
- Red: face Maloriak toward the raid for Scorching Blast; Consuming Flames targets leave the cone. Blue: spread at least 5 yards, move Biting Chill away, and free Flash Freeze without chain-shattering the raid. Green: bring released Aberrations near the boss only for the 15-second Debilitating Slime burst, then return them to a safe kite lane.
- At 25% health, stop treating the color as active: Maloriak releases every remaining Aberration and two Prime Subjects, then uses the phase-two mix. Burn the boss while off-tanks kite the adds away from Maloriak; avoid Magma Jets, Absolute Zero, and Acid Nova. Heroic additionally requires Black-phase Vile Swill control and Engulfing Darkness survival.

## Mode matrix

| Mode | Main-phase vial order | Main-phase add/role model | Phase two / material delta |
|---|---|---|---|
| 10N | Random Red/Blue, other, Green | 3 Aberrations per successful Release cast; one off-tank is normally sufficient | 25% threshold; two Prime Subjects; no Black phase |
| 25N | Random Red/Blue, other, Green | Same 3-per-cast reserve; two off-tanks make Growth Catalyst separation safer | 25% threshold; two Prime Subjects; no Black phase |
| 10H | Black, random Red/Blue, other, Green | Five Vile Swills in Black; one off-tank normally handles them; heroic add damage/health is higher | 25% threshold; Black repeats after each Green; Prime Subject Fixate is guide-reported |
| 25H | Black, random Red/Blue, other, Green | Five Vile Swills in Black; two off-tanks are recommended; heroic add damage/health is higher | 25% threshold; Black repeats after each Green; Prime Subject Fixate is guide-reported |

Current Wowhead 4.4.2 guide health values are 24.7M (10N), 34.6M (10H), 86.6M (25N), and 121.2M (25H). An older Icy Veins encounter page reports 19.8M and 69.3M for the two normal modes; exact normal-mode health/hotfix provenance is therefore recorded as unresolved rather than treated as a bot invariant.

## Observable mechanics and targeting

### Shared main phase

- Arcane Storm is an area raid hit (guide: within 80 yards), channels for about 6 seconds, and must be interrupted. The local AI makes Maloriak interruptible for the channel and closes that window after 6.5 seconds.
- Remedy is a 10-second self-heal/mana buff. The current 4.4.2 guide reports 150,000 health per tick with the amount increasing by 150,000 each tick; the local AI repeats its cast every 24 seconds after its color-specific first cast.
- Release Aberrations releases three sleeping Aberrations from growth chambers. Each successful local cast selects up to three non-drowned chamber creatures at random and increments a six-cast counter (18 reserve creatures total). An interrupted cast does not increment the counter. The local event is scheduled in Red, Blue, and Green; current strategy pages describe the intended operational casts differently (Red/Green on Icy Veins, throughout phase one on Wowhead), so color-specific Release scheduling is a fidelity blocker.
- Growth Catalyst increases nearby Aberration damage and reduces incoming damage. Wowhead reports 10% damage dealt in normal and 20% in heroic, with 20% damage reduction per nearby stack. Keep them away from Maloriak except during Green. The 10-player guide model uses one off-tank; 25-player uses two when possible.

### Vials

- Red grants Scorching Blast (a cone split among targets) and Consuming Flames (random player, 10-second fire DoT that amplifies subsequent magic damage taken by 50%). Stack for the cone, excluding the Consuming Flames target. The current guide describes 2 Scorching Blasts and roughly 3–4 Consuming Flames per Red; local schedules are 19s then every 17s for Scorching and 7s then every 14.5s for Consuming.
- Blue grants Flash Freeze and Biting Chill. Spread at least 5 yards; local Flash Freeze target filtering excludes Maloriak's victim and players currently being attacked by an Aberration, then randomly keeps one eligible target. Current guides describe ranged targeting, while exact mode target counts are not represented by the C++ filter. Free the ice block promptly and do not break adjacent blocks.
- Green applies Debilitating Slime to Maloriak, players, and Aberrations, removes Growth Catalyst, and increases damage taken by 100% for 15 seconds. The cauldron knockback moves Maloriak toward the entrance. Bring the planned add pack into that burst window, then kite away before the buff expires.
- Black is Heroic-only. Maloriak gains Shadow/Imbued Shadow and cannot be taunted; five Vile Swills are spawned. Kill or control the Swills while moving out of Dark Sludge pools. Face the boss away from the raid for Engulfing Darkness and rotate tank cooldowns during its 8-second healing lockout.

### Phase two (25%–0%)

The local `DamageTaken` hook enters phase two on the damage event crossing 25% in all four modes. It immediately stops the old event phase, releases all remaining minions, drinks all bottles, and applies Unstable Mix. The local nominal follow-up is Magma Jets at 3.5s, Acid Nova and Absolute Zero at 8.4s; repeats are 6s, 20s, and 7s respectively. Guides describe approximately 6s, 30s, and 10s instead, so these are server-baseline observations and not a cross-client schedule.

Release All Minions targets every remaining chamber creature through two spell effects; it is not the three-target random Release path. It also summons two Prime Subjects. Keep Aberrations and Prime Subjects away from Maloriak because of Growth Catalyst. Icy Veins reports Heroic Prime Subjects gaining a few-seconds-after-spawn Fixate that persists until the target dies; no explicit Fixate logic exists in this local AI, so target persistence is unresolved.

## Reset, completion, and credit

- `Reset()` calls the base reset and closes interruptibility, but does not explicitly zero `_currentVial`, `_usedVialsCount`, or `_releasedAberrationsCount`. Evade despawns/cleans up the encounter and the Heroic Nefarius summon; whether the engine reconstructs the AI before a re-pull must be tested before relying on a clean vial counter.
- Evade cleanup removes player Flash Freeze/Biting Chill/Consuming Flames, despawns the growth-chamber spawn group, and despawns tracked summons. Creature creation forwards Flash Freeze and Vile Swill to Maloriak's summon tracker.
- Death cleanup removes the same encounter state and calls the base boss death path. The instance maps creature 41378 to `DATA_MALORIAK`; the base `BossAI` path is therefore the expected IN_PROGRESS/DONE credit mechanism. The instance sends DONE to the generic Nefarius scene. Heroic Lord Victor Nefarius separately awards title ID 188 through spell 89798 after the death scene; this is presentation/title credit, not a replacement for boss DONE state.

## Repository audit

- `boss_maloriak.cpp` defines the state machine, vial order, local event timings, target filters, add release selection, cleanup, Heroic Nefarius, Vile Swill, and phase-two transition.
- `blackwing_descent.h` maps Maloriak (41378), Cauldron Trigger (41505), Aberration (41440), Prime Subject (41841), Flash Freeze (41576), Absolute Zero (41961), Heroic Nefarius (49799), and Vile Swill (49811).
- `instance_blackwing_descent.cpp` maps 41378 to `DATA_MALORIAK` and forwards Flash Freeze/Vile Swill summons to the boss. `eastern_kingdoms_script_loader.cpp` declares and invokes `AddSC_boss_maloriak`.
- The current TDB 4.3.4 dump row for 41378 contains difficulty entries 49974/49980/49986 and `boss_maloriak`; corresponding rows exist for Aberration, Prime Subject, Flash Freeze, Lord Victor Nefarius, and Vile Swill. `sql/updates/world/4.3.4/2025_06_17_01_world.sql` groups Maloriak `DamageModifier` values by these difficulty rows. The historical custom update `sql/old/custom/world/34_2020_02_21/custom_2019_08_20_00_world_updatepack.sql` explicitly binds the creature and spell scripts; the earlier draft's “no historical SQL binding” statement was false. Current script registration is loader-based, while whether that historical custom pack is applied is outside this research scope.
- Spawn/instance data in `sql/old/4.3.4/world/10_2016_03_12/2015_10_02_00_world.sql` places Maloriak in map 669 and includes two sleeping Prime Subjects. This is historical DB evidence, not proof of the live 4.4.2 client state.

## Source metadata and conflicts

1. Wowhead, “Maloriak Strategy Guide — Blackwing Descent Raid Cataclysm Classic,” Beanna, updated 2024-06-04, page labelled Patch 4.4.2: <https://www.wowhead.com/cata/guide/raids/blackwing-descent/maloriak-strategy>. Used for current health, vial cadence/order, ability targets/damage examples, Heroic Black, Green window, phase-two behavior, and role guidance.
2. Icy Veins, “Maloriak Encounter Guide: Strategy, Abilities, Loot — Cataclysm Classic,” Abide, updated 2024-07-29: <https://www.icy-veins.com/cataclysm-classic/maloriak-encounter-guide-strategy-abilities-loot>. Independent current-era strategy source for order, five Vile Swills, Black behavior, Red/Blue/Green positioning, 18-add reserve, two Prime Subjects, and 25% transition.
3. Icy Veins, “Maloriak Detailed Strategy Guide (Heroic Mode included),” Damien, last updated 2012-10-08 (explicitly marked WoD 6.1.2): <https://www.icy-veins.com/wow/maloriak-strategy-guide-normal-heroic>. Historical independent source used only for phase-duration ranges, 10/25 target counts, enrage/difficulty deltas, Dark duration, and Heroic Fixate. It is not a 4.4.2 hotfix authority.
4. Local repository evidence: `src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent/boss_maloriak.cpp` (lines 37–1292), `blackwing_descent.h` (lines 30–183), `instance_blackwing_descent.cpp` (lines 31–58, 145–196, 224–261), `eastern_kingdoms_script_loader.cpp` (lines 76–83, 308–315), `data/TDB_full_434.22011_2022_01_09/TDB_full_world_434.22011_2022_01_09.sql` (creature-template rows), `sql/updates/world/4.3.4/2025_06_17_01_world.sql` (lines 8–15, 37–39), `sql/old/custom/world/34_2020_02_21/custom_2019_08_20_00_world_updatepack.sql` (lines 168762–168821), and `sql/old/4.3.4/world/10_2016_03_12/2015_10_02_00_world.sql` (lines 122–125).

Material conflicts retained in the ledger: 15.5s local face event versus roughly 20s guide vial, 90s local Black return versus roughly 95s historical Dark duration, local phase-two repeats versus guide approximations, Wowhead’s three Biting Chill targets versus Icy Veins’ 10/25 one/two targets, Wowhead’s Heroic damage examples versus historical “same damage” statements for several spells, current Icy Veins’ six-minute enrage wording versus historical 7m/12m, and differing descriptions of which color phases cast Release Aberrations.

## Unresolved fidelity blockers

- Exact Blizzard 4.4.2 build/hotfix cutoff and whether the current TDB/Trinity data matches that cutoff.
- Live timer and movement-duration confirmation in all four modes; no live validation was run.
- Exact per-mode spell coefficients and target counts (especially Biting Chill, Flash Freeze, Arcane Storm, Magma Jets, Absolute Zero, and Heroic/Normal deltas); C++ selects spell IDs but does not encode DBC coefficients.
- Heroic Prime Subject Fixate target persistence in this repository build.
- Whether a Maloriak AI object is reconstructed on evade; `Reset()` does not reset custom counters.
- Enrage duration and normal health values due current-versus-historical guide conflict.
