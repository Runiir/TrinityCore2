# Nefarian's End — research contract v2

Scope: Cataclysm Classic 4.4.2, 10-player normal/heroic and 25-player
normal/heroic. Planning only; this is not a live-fidelity claim. Every value
below is either guide-reported, repository-observed, or explicitly
`fidelity_blocked`. A blocked value must not become a fixed bot schedule.

## Bot contract

- Phase 1 starts on revived Onyxia. Keep Onyxia and Nefarian more than 50 yd
  apart, face both breaths away from the raid, and keep the Animated Bone
  Warriors away from breath cones. A third tank/kiter is needed when raid
  size permits; do not kill the warriors as a default plan.
- Track Onyxia's Electrical Energy and her lightning-facing cue. Stop or
  redirect Nefarian damage before an Electrocute would overcharge Onyxia, and
  rotate Onyxia so the Lightning Discharge side cones do not hit the raid.
  Trigger raid defensives on the observed Electrocute event, not a guessed
  damage value.
- Phase 2 has three platforms. Assign each a healer, an interrupt-capable
  player and damage; interrupt every Blast Nova. During heroic Explosive
  Cinders, the marked player leaves the platform and returns only after the
  aura expires. Nefarian's air damage continues during this phase.
- Phase 3 is a Nefarian burn with an Animated Bone Warrior kite. Keep breath
  and Shadowblaze Spark away from collapsed warriors; use slows/CC to buy kite
  time and never treat an add reanimation as a harmless reset. Continue the
  Electrocute defensive queue.
- Heroic Dominion is an observed control state: use Siphon Power to gain
  Stolen Power when safe, then Free Your Mind before reaching the portal. The
  local target cap conflicts with legacy guide counts, so target count is not a
  fixed contract.

## Common encounter shape

Wowhead and Icy Veins independently describe three phases: Onyxia first,
Nefarian lands about 30 seconds later, then Onyxia's death raises the lava and
leaves three platforms, followed by a Nefarian-only phase. The repository
confirms the same phases, three Chromatic Prototypes, transport/elevator
handling and the phase transition triggers.

The current guide reports these health values; they are not verified against a
4.4.2 DBC or combat log in this checkout:

| Mode | Onyxia | Nefarian | Each Chromatic Prototype |
|---|---:|---:|---:|
| 10N | 7.0M | 28.5M | 6.9M |
| 10H | 9.9M | 54.4M | 9.8M |
| 25N | 24.7M | 99.6M | 6.9M |
| 25H | 34.8M | 179.3M | 9.8M |

## Observable behavior and difficulty matrix

| Mode | Normal contract | Material delta / blocker |
|---|---|---|
| 10N | Onyxia → Nefarian landing; three platforms; three prototypes; bone kite; Electrocute every 10% | Guide-reported health above; exact 4.4.2 damage and local spell coefficients unresolved. |
| 10H | Normal contract plus Dominion in phases 1/3 and Explosive Cinders in phase 2 | Local Dominion cap is 5 targets in 10-player; legacy strategy reports 1. Treat target count as `fidelity_blocked`. |
| 25N | Same three phases and platform interrupt loop; allocate larger platform teams | Guide-reported health above; exact 25-player Hail, Barrage and Blast Nova target/damage scaling not fully exposed by the repository. |
| 25H | Normal contract plus Dominion and Explosive Cinders | Local Dominion cap is 2 targets in 25-player; legacy strategy reports 5. Cinders count/range and heroic coefficients remain blocked. |

### Phase 1: Onyxia, Nefarian and warriors

Onyxia gains Electrical Energy over time. Wowhead reports +1 energy every 2
seconds, a lethal Electrical Overload at 100 and approximately 1M Nature
damage; Icy Veins confirms the 100-energy wipe but does not expose the tick
rate. The local aura increments Onyxia's charge and warns at 50 and 80; its
maximum stack comes from spell data, which was not audited here. Nefarian's
health thresholds schedule Electrocute at 90, 80, … 10 percent. The local
machine event is delayed 5 seconds and adds 17 Onyxia-charge stacks; both
current guides report +25. Charge amount and exact spell coefficients are
therefore blocked.

The local Onyxia AI starts Tail Lash at 20s and Lightning Discharge at 22s,
then repeats them in 17–18s and 22s ranges; Shadowflame Breath starts in
11–12s and repeats in 13–17s. Wowhead instead describes roughly 15s Tail Lash
and roughly 25s wings cue followed five seconds later by Lightning Discharge.
Use cast/aura cues and not a timer-only facing policy. Children of Deathwing is
applied when the two dragons are within 50 yd in the local spell script and
raises attack speed by 100% in both strategy sources.

Hail of Bones is cast while Nefarian is airborne. Wowhead reports six random
impact locations in the first 30 seconds, two warriors per impact (12 total),
10 yd impact damage, and warriors whose energy drains by 2% per second and
collapses after about 50 seconds. The local AI confirms the warrior state
machine: full-power/animate a warrior, make it aggressive after 800ms, and at
energy ≤1 clear threat, become passive/not-selectable and feign death. Breath
or Shadowblaze reanimates a collapsed warrior and restores full energy. Exact
spawn count and tick period are not in the C++ and are guide-reported only.

### Phase 2: lava, platforms and interrupts

Onyxia's death moves Nefarian to the elevator center, raises him and lowers
the elevator; three prototypes jump to three fixed platforms. The local
prototype casts a readiness sequence, then Blast Nova initially at 3.5s and
every 13s. Wowhead reports approximately 8s; Icy Veins only says “constantly”.
The local timing and the guide timing conflict, so the bot must interrupt cast
events rather than predict them. Shadowflame Barrage is local-first at 2.5s
and repeats 2.5s; Wowhead reports random targets every 3s. Phase 2 ends after
all three prototypes die in normal; on heroic, the repository enters phase 3
when the first prototype dies. This is an implementation-level heroic delta
and should not be generalized beyond this checkout without a verified source.

Heroic Explosive Cinders is local-first at 2s and repeats 15s during phase 2.
Icy Veins reports a random player, periodic damage every 2s and an 8s
explosion/knockback; an older Icy guide reports one 10-player or three
25-player targets every 20s. Count and cadence are `fidelity_blocked`.

### Phase 3: Shadowblaze and add control

After the prototype condition is met, the local controller raises the
elevator, disengages surviving prototypes and lands Nefarian. Nefarian starts
the Shadowblaze pre-start aura, then breath at 9s and Tail Lash at 1s. Local
breath repeats in 17–22s and Tail Lash in 15–22s ranges. The current Wowhead
guide reports Shadowblaze Spark at about 25s initially, accelerating to a
10s minimum; fire spreads toward the nearest player and dissipates after about
50s. The local pre-start aura uses tick counters (first trigger after one
tick, then six, then decreasing to two) without exposing the aura tick period.
Use observed sparks/patches; do not schedule the local counter as seconds.

## Repository lifecycle and audit

- `npc_nefarians_end_onyxia::JustEngagedWith` sets the instance
  `IN_PROGRESS`, removes the pre-fight aura, adds the charge aura and starts
  Onyxia events (`boss_nefarians_end.cpp:925-951`). Onyxia cannot die until
  Nefarian has landed (`:1015-1020`).
- Nefarian's `DamageTaken` prevents death outside phase 3, detects each 10%
  threshold, and schedules the machine event after 5 seconds
  (`boss_nefarians_end.cpp:534-549`).
- Nefarian `JustDied` calls `_JustDied`, disengages its encounter frame and
  removes Dominion/Cinders (`:453-460`). Onyxia death informs Nefarian and
  despawns after 19s (`:960-967`).
- Nefarian evade restores/raises the elevator as needed, disengages live
  Onyxia/prototypes, despawns summons, sets `FAIL`, removes heroic auras and
  despawns the boss (`:419-445`). Onyxia evade delegates to Nefarian
  (`:953-958`).
- The instance maps boss 41376 and related actors, forwards Dominion stalkers,
  respawns Nefarian 30s after `FAIL`, and only spawns the Nefarian group after
  the other five Blackwing Descent bosses are done
  (`instance_blackwing_descent.cpp:31-57,197-200,276-290,462-464,520-529`).
- The loader declares and calls `AddSC_boss_nefarians_end`
  (`eastern_kingdoms_script_loader.cpp:75-83,307-315`). Historical SQL has
  creature templates/difficulty entries and encounter row 1026/41376, but no
  searched current or historical `ScriptName='boss_nefarians_end'` binding.
  The AI is registered through the C++ loader/factory; do not infer a SQL
  binding that is not present.

## Target and control rules

- `Children of Deathwing` checks sibling distance ≤50 yd; separate the dragons
  beyond that boundary (`boss_nefarians_end.cpp:1515-1535`).
- Nefarian's Electrocute trigger is deterministic by his health threshold, not
  a random target. The lightning machine casts the visual and damage spell,
  then modifies Onyxia's charge (`:791-801`).
- Dominion summons four portal stalkers for each controlled player; the local
  script keeps only the farthest portal for that player, moves the player at
  3.5 velocity and instakills if the Dominion aura remains on arrival
  (`:1845-1987`).
- Shadowblaze chooses a nearby/location-valid spark through controller stalker
  position and local ±5-yard candidate offsets; the spread direction is toward
  the nearest player in the local implementation (`:1292-1387`). Do not treat
  it as a raid-player random-target spell.
- `Free Your Mind` removes the control aura and stops movement; Cinders
  detonates only when its periodic aura expires (`:1990-2003,2023-2040`).

## Source metadata

1. **Wowhead — “Nefarian Strategy Guide - Blackwing Descent Raid Cataclysm
   Classic”.** Author Beanna; Patch 4.4.2; updated 2024-06-10; URL
   <https://www.wowhead.com/cata/guide/raids/blackwing-descent/nefarian-strategy>;
   accessed 2026-08-11. Supplies mode health, energy, 50-yard separation,
   Hail/Bone, platform, Barrage, Electrocute, Shadowblaze and heroic summary
   values. It does not expose a reliable client build or hotfix cutoff.
2. **Icy Veins — “Nefarian Encounter Guide: Strategy, Abilities, Loot”.**
   Author Abide; last updated 2024-07-29; URL
   <https://www.icy-veins.com/cataclysm-classic/nefarian-encounter-guide-strategy-abilities-loot>;
   accessed 2026-08-11. Independent Cataclysm Classic guide covering energy,
   Electrocute charge, Dominion, Cinders, platform interrupts, Bone behavior
   and Shadowblaze. Exact 4.4.2 build metadata is not stated.
3. **Icy Veins — “Nefarian DPS Strategy Guide (Heroic Mode included)”.**
   Legacy Cataclysm strategy page, page metadata approximately 14 years old;
   URL <https://www.icy-veins.com/wow/nefarian-dps-strategy>;
   accessed 2026-08-11. Used only for independent historical Dominion/Cinders
   target counts and platform team guidance; not treated as Classic 4.4.2
   tuning.
4. **Warcraft Tavern — “Nefarian Raid Guide - Cataclysm Classic”.** Publisher
   Warcraft Tavern; publication metadata not exposed; URL
   <https://www.warcrafttavern.com/cataclysm/guides/nefarian-raid-guide/>;
   accessed 2026-08-11. Used as an additional qualitative heroic Cinders/
   Dominion reference; exact target count was not relied upon.
5. **Repository C++ — Nefarian's End.** Revision
   `889d38cc9451c2b8104db142ce069593b4647a41`; path
   `src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent/boss_nefarians_end.cpp`;
   accessed 2026-08-11. Relevant ranges: `374-910`, `912-1073`,
   `1139-1286`, `1288-1388`, `1390-1622`, `1724-2040`.
6. **Repository instance/header/loader.** Revision
   `889d38cc9451c2b8104db142ce069593b4647a41`; paths
   `blackwing_descent.h:25-38,76-84,145-154,225-235`,
   `instance_blackwing_descent.cpp:31-57,197-200,276-290,350-380,462-464,490-529`,
   `eastern_kingdoms_script_loader.cpp:75-83,307-315`; accessed 2026-08-11.
7. **Historical DB evidence.** `sql/old/4.3.4/TDB00_to_TDB01_updates/world/004_creature_template.sql:3930-3932,12924,12933-12945`
   (base/difficulty templates),
   `sql/old/4.3.4/world/12_2016_09_28/2016_09_02_00_world.sql:12`
   (Nefarian difficulty entries), and
   `sql/old/4.3.4/TDB04_to_TDB05_updates/world/066_instance_encounters.sql:462`
   (encounter 1026); accessed 2026-08-11. No ScriptName binding was found in
   the searched SQL.

## Unresolved fidelity blockers

- Exact 4.4.2 client/build/hotfix cutoff and spell coefficients.
- Onyxia charge tick period/max-stack representation, local +17 versus guide
  +25 Electrocute charge, and exact Electrical Overload damage.
- Local Nefarian landing/phase timers versus guide 30 seconds; Blast Nova
  3.5/13s local versus approximately 8s guide; Barrage and Cinders cadence.
- Mode-specific Hail/Bone/Barrage/Blast Nova target counts and damage.
- Dominion target count (local cap 5/2 versus legacy report 1/5), whether local
  Dominion repeats in phase 3, and Cinders target count/radius.
- Shadowblaze aura tick period, exact spark target-selection spell behavior,
  room-coverage timing and any current berserk interaction.
- Reliable 4.4.2 SQL/DBC confirmation of every health, energy and damage value.
