# Atramedes — research contract v3 and 10N bot strategy

Scope: Cataclysm Classic 4.4.2 behavior (client build 4.4.2.59185, hotfix
cutoff 2025-02-20 23:00 UTC) for 10N, 10H, 25N and 25H, with the 10N bot
strategy for the canonical composition. State: `fidelity_blocked`. Client data,
the native script and the database were audited on 2026-09-25 (repository
revision `a570b44369`). Warcraft Logs (WCL) values are still unresolved: the
report pages showed a human-verification interstitial that an agent may not
pass. Nothing here is a live-validation result.

Machine-readable sources: the contract `atramedes_v1.json` and the ledger
`atramedes_ledger_v1.json` (client values, native audit, completion rows,
unresolved list), next to them `atramedes_wcl_dps_reference_v1.json` and
`atramedes_wcl_cast_timelines_v1.json` (pending extraction plans). The raid
target is `experiments/configs/raid_targets/blackwing_descent_10n_atramedes.json`.

## Access: the shard and its native prerequisites

- Instance: boss index 3 (`DATA_ATRAMEDES`), encounter 1022, map 669. The shard
  is seeded with Magmaw and Omnotron done. The intro is not seeded.
- Dwarven spirits: spawn groups 435 (left: Moltenfist, Anvilrage, Shadowforge,
  Corehammer) and 436 (right: Angerforge, Ironstar, Thaurissan, Burningeye).
  A dying spirit empowers the survivors of its group (Bestowal). A group that
  evades resets and respawns after 30 s. In a seeded instance `ReadSaveDataMore`
  spawns the shields and both spirit groups, because the intro byte is NUL.
- When all 8 spirits are dead, the intro is saved DONE. The Column of Light
  appears and the Ancient Bell (204276, spawn 235153) becomes selectable 4.5 s
  later. Its `GossipHello` summons Atramedes at (288.3, -222.4, 96.6). He flies
  to (249.4, -223.6), casts Roaring Breath, and lands at (214.5, -223.9, 74.8)
  as `REACT_AGGRESSIVE`.
- A wipe sets FAIL, despawns the shields, and respawns shields and boss after
  30 s at (220.0, -224.3). The kill sets DONE and despawns the shields.
- Route order (requested from the scenario owner): north spirits, south spirits,
  regroup at (150, -224.5), bell ready, bell (the raid gathers at the bell),
  intro wait, encounter.
  - The regroup must come before the bell. An arrival node completes only when
    no bot is in combat, and the landing pulls the raid standing at the bell.
  - `intro_wait` completes on "grounded and aggressive, or engaged", so the
    encounter node takes over as soon as he lands.

## Mechanics (4.4.2 client rows; the 4.3.4 DBC holds the same values)

The Sound Bar (89683, then 88824 on every player) is alternate power
(UnitPowerBar 23, 0–100). At 100 Sound the player gets Noisy! (30 s).
Devastation Trigger then fires Devastation (78868) every 500 ms: 24,375–25,625
Fire (heroic 29,250–30,750).

| Source (10N) | Damage | Sound | Area |
|---|---|---|---|
| Sonar Pulse disk (4 per cast, 41546) | none (heroic 2,924 Shadow) | +3 per 0.5 s (heroic +7) | 5 yd, moving from the boss toward its player |
| Modulation (77612) | 31,200–32,800 Shadow, raid | none (heroic +10) | raid |
| Sonic Breath (78098 at Tracking Flames 41879) | 19,500–20,500 Fire per 1 s tick (heroic 29,250) | +20 per tick (heroic +30) | 15° cone, unlimited range, 2 s cast + 6 s channel |
| Searing Flame (77840, 6 s channel) | 19,500–20,500 Fire raid every 2 s, +50% Fire taken per tick | none | raid, plus 41807 fire patches within 35 yd |
| Roaring Flame patch (41807 / 42001) | 9,750 + 7,800/s for 4 s | +5 | 3 yd |
| Roaring Flame Breath (air, 41962) | 15,600–16,400 Fire per 0.5 s (heroic 29,250) | +3 (heroic +10) | 5 yd around the flame |
| Roaring Flame spawn (78555) | 14,625–15,375 Fire | +10 | 8 yd |
| Sonar Bomb (air, 5 markers every 3 s) | 20,000 Arcane (heroic 30,000) | +20 (heroic +30) | 6 yd |

- **Ancient Dwarven Shields** (spawn group 400: 10 creatures of 8 entries).
  The spellclick casts 77709 from the shield: everyone goes to 0 Sound and
  Noisy! is removed.
  - Ground: the shield interrupts Atramedes and applies Vertigo (5 s stun,
    +50% damage taken). Atramedes then destroys that shield.
  - Air: the Reverberating Flame waits 2 s, flies to the shield, destroys it,
    then tracks the striker.
  - Heroic: Nefarius destroys one more shield after each ground gong.
- **Air breath speed.** The Reverberating Flame gains +20% speed every second
  (78217 → 78218). Both guides say a gong restarts the breath at its initial
  speed; the native script now does this.
  - The stack cap is a conflict. The client rows (4.3.4 DBC and 4.4.2.59185
    SpellAuraOptions) allow 99 stacks in 10N, 25N and 10H, and 10 in 25H.
  - The server's `SpellMgrCorrectionsPart04.cpp` sets 10 for all four
    variants, so the running server caps at 10.
- **Phases (native).**
  - Ground: Modulation 13 s, then every 22–26 s. Sonar Pulse 14.5 s, then every
    11 s. Sonic Breath 24 s, then every 42–43 s. Searing Flame 46 s (once).
    Liftoff 91 s.
  - Air: the land event comes 31 s after he reaches the liftoff point.
  - Ground after landing: Sonar 14 s, Modulation 13 s, Sonic Breath 22 s,
    Searing Flame 51 s, liftoff 93 s.
- **Addon bars (BigWigs Classic).** Modulation 11 s, then every 16 s. Sonar
  11.3 s. Breath 22 s, then every 42 s. Searing 45 s. Air 36 s from take-off,
  then 85 s of ground. The difference is recorded as a conflict. Native timers
  change only with WCL evidence.

## Native audit (fixed 2026-09-25)

1. `boss_atramedes.cpp` (1,141 lines) is split into the AIs, `boss_atramedes_spells.cpp`
   and `boss_atramedes_shared.h`. Registration and DB bindings are unchanged.
2. The player Sound Bar and Noisy! are removed on evade and on death. Before,
   survivors carried their Sound into the next pull.
3. A Vertigo during the intro flight now resumes the landing. Before, the script
   asked the instance for an AI data id and always got 0. The intro flight is an
   explicit flag, set at the bell summon and cleared at the intro landing:
   `IsInPhase(PHASE_INTRO)` matches every phase, and `REACT_PASSIVE` also holds
   in the air and for 800 ms after each landing.
4. The landing removes the air Sonar Bomb trigger (92519), not the disk aura.
5. A redirected Reverberating Flame restarts at its initial speed.
6. `GetTimeUntilEncounterMechanic` publishes the native time to Searing Flame,
   Sonic Breath and liftoff. It covers the ground phase only.
7. Staged, DB-side: `sql/custom/staged/world/2026_09_25_40_atramedes_devastation_noisy_target.sql`
   restricts Devastation to Noisy! holders. Before, it hit the whole raid.
   Wowhead and Icy Veins both describe a hit on the 100-Sound player only.

## 10N bot strategy (canonical composition: 1 tank, 2 healers, 7 DPS)

Roster: Blood DK (tank); Balance, BM Hunter, Fire Mage, Retribution,
Assassination, Elemental, Demonology; Holy Paladin and Discipline healers.
Duties come from capability on every snapshot (`BotAtramedesDutyPlan.h`), never
from roster slots.

- **Pull and tank.** Everyone targets the landed boss and the tank's threat
  takes him. On the ground the tank drags Atramedes to the anchor
  (150, -224.5), near the arena centre. From there every air relay station
  (below) is also in spell range of the grounded boss. He has 20 yd combat
  reach, so the tank stands 10 yd past the anchor. Melee keep native maximum
  range (about 22 yd from his centre).
- **Gongs** (native spellclick only, `BotAtramedesGongPolicy.h`):
  - The owner is the best ranged DPS (hunter, then mage, …) and the backup is
    the next.
  - Owner standby, in two stages:
    - Until this ground phase's Searing Flame is spent (or while the schedule
      is unknown), it waits beside the shield nearest the anchor that is not a
      relay shield (250130), still inside spell reach of the boss.
    - After that, while the boss stays in spell range of it, it waits at the
      first air relay station (`gong_owner_air_standby`). The next air phase's
      first catch then has a relay in place from the flame's spawn.
  - A ground strike by a player in reach of a non-relay shield uses that one:
    the relay shields are the air phases' first catches. With only a relay
    shield in reach, Searing Flame still strikes it.
  - The owner strikes as soon as Searing Flame starts, when anyone reaches
    90 Sound, or at 80 Sound unless Searing Flame is due within 15 s.
  - The backup acts when the owner is dead or kiting. No strike happens while
    Atramedes is already stunned.
  - **Budget.** Shields for the Searing Flames still expected stay in reserve.
    That is this ground phase's Searing Flame (from the published timer;
    unknown counts as pending), plus the next ground phase's while the boss is
    above 50% health (on the ground) or 30% (in the air).
    - Searing Flame may always use a shield.
    - A 90-Sound emergency spends down to this phase's Searing Flame, since a
      Devastation death now outranks a Searing Flame 51–82 s away.
    - An air rescue also keeps the next phase's shield.
    - An 80-Sound gong keeps one more spare.
    - Why 50% and 30%: the next Searing Flame is at least 82 s (ground) or 51 s
      (air) away. At a 150k raid-DPS floor that removes 47% or 29% of the native
      10N health, so a boss below the threshold dies first.
  - **Air rescue.** The Reverberating Flame runs 5 yd/s and gains 1 yd/s every
    second (Building Speed, server cap 10); an unbuffed kiter runs 7 yd/s.
    - Time to contact solves the separation d(t) = d0 + c·t − t²/2.
      - A target summoned within 3 yd never gets out of the 5 yd breath
        (peak 3 + 2 = 5 yd), so it is in contact at once.
      - One summoned farther out gets out and is caught again later.
    - A rescue fires when contact is within 1 s.
    - A lone kiter also strikes at a shield ahead when the flame would catch
      it before the next shield; the west side has none for 105 yd. When the
      owner or backup is in reach of its own station's shield, that relay
      strikes at contact instead, so no shield is spent early. A passer-by
      beside a shield does not count as a relay.
    - The strike goes to whoever stands beside a shield in reach. A non-relay
      shield comes first, then the shield farthest from the flame. The tank
      counts too when it is the kiter, since Atramedes has no victim in the
      air.
      - The kiter itself only strikes shields ahead of it.
      - Once the flame is on top of the kiter, any shield will do: a faster
        flame's predictive follow overshoots, so "behind" means nothing.
    - With nobody in reach, the kiter runs for the nearest shield ahead
      (`gong_approach`).
    - A 90-Sound emergency still strikes when contact is true but the rescue
      budget is spent.
    - **Relays.** In the air, the gong owner and the backup wait at relay
      stations within reach of a shield and in spell range of the hovering
      boss.
      - Range: Spell::CheckRange is 3D, 40 + 1.5 + 20 = 61.5 yd from the hover
        point (130.7, -226.6, 113.2), less a 0.25 yd margin.
      - Reach: the native spellclick reach is 12.5 yd in 3D (INTERACTION_DISTANCE
        5 + player reach 1.5 + shield CombatReach 6, model 32469). The bots
        use 11.5 yd.
      - Stations stand 10 yd from their shield toward the hover point
        (10.15 yd in 3D) and are held within 1 yd, so the whole hold area is
        inside both limits. 10.5 yd plus the hold would leave the reach.
      - Five native spawns have a station in range: 250128 (57.5 yd),
        250126 (59.1), 250125 (59.5), 250122 (59.7) and 250129 (60.0).
        250124 (60.5 + 1) misses the margin.
      - The owner takes the station nearest the hover point. The backup takes
        the in-range one farthest from the owner's (250129 while 250128
        stands), so a strike far from the flame is at hand on either side.
      - A kiting or redirect-running relay leaves its station empty. Only when
        a single station is left does the other relay take it over.
      - With 3 or fewer shields left, none with a station in range, and more
        shields than the Searing Flame reserve, the owner guards the shield
        nearest the hover point anyway (out of range). There, the rescue
        outweighs its damage.
      - Every station, in range or not, is held within the same 1 yd.
    - The striker keeps the air Resonating Clash aura (78168). Until the flame
      re-tracks it (2 s wait plus the flight to the shield) it already runs on
      along the ring (`air_redirect_run`). If two players still carry the 15 s
      aura, the one whose aura expires last struck last and is the one that
      runs.
    - During the redirect the flame is interrupted and nobody is the kiter, so
      a second shield is never spent on the same catch.
- **Sonic Breath.**
  - The tracked player circles the boss 28–42 yd out while the breath is cast
    or channelled. It runs away from the Tracking Flames marker.
    - The marker chases it in a straight line, so the marker's bearing around
      the boss always trails and the direction holds for the whole breath.
    - Only on the summon snapshot, when the marker sits on the kiter, does the
      raid side choose (away from the raid centroid).
    - A breath simulation at 7 yd/s against the 5 yd/s marker never reverses,
      and at every channel tick the beam is at least 12.6° from the kiter (the
      cone's half-angle is 7.5°).
  - Others leave the beam backward, or run ahead of the sweep when the beam will
    reach them within its 8 s.
- **Sound.** Everyone sidesteps Sonar Pulse lanes (5 yd, plus 1.5 yd at
  60+ Sound). They also leave fire patches, Sonar Bomb markers and the
  Reverberating Flame.
- **Formation.**
  - Ground: ranged stand on an arc 32 yd from the boss and healers 26 yd,
    facing the arena centre.
  - Air: one slot per player on a 10 yd-spaced ring around (145, -225), at
    17 yd or 25 yd. The outer slot is the alternate when a bomb marker is placed.
- **Air.**
  - The tracked player runs the ring, away from the flame (the same
    trailing-chaser rule, around the arena centre).
    - Each ring waypoint is 4 yd inside a shield and 3 yd onward, so it lies
      inside spellclick reach and past the shield.
    - Every waypoint is reached before the next is taken, so the kiter passes
      every shield in reach. Before this fix, a 12 yd skip meant it never came
      within reach.
  - Melee and the tank cannot reach the flying boss. They hold their slot and
    ask for offense suppression.
  - Ranged keep casting within about 48 yd horizontally of him.

Acceptance observations are in the ledger, `acceptance_observations`:
- a native clear after the spirits and bell;
- every Searing Flame gonged within 2 s;
- no Searing Flame without a shield and no emergency withheld;
- nobody reaches 100 Sound;
- 0 boss-window deaths.

**Air-phase replay.** `tests/test_atramedes_strategy.py` replays successive
31 s air phases for every target, the tank included. Model:
- each air phase follows a ground Searing Flame gonged by the strategy;
- it starts from the ground formation at liftoff, after that Searing Flame;
- the flame spawns on the target, as 78213 does, after the native takeoff
  (7 s) or after 3 s, while the backup is still walking;
- every bot follows its own plan at 7 yd/s, in 0.25 s steps;
- strikes run their native effects;
- the flame relaunches a predictive follow every 400 ms, and its breath ticks
  every 0.5 s.

The phases:
- Phase 1: ten shields less one Searing Flame, boss at 100%.
- Phase 2: the shields left after phase 1, less one Searing Flame, boss at 60%.
- Phase 3: three shields left, boss at 25% (no reserve). Covered by the three
  shields farthest from the hover point (no station in range) for every
  target, and by all 120 three-shield sets with the target rotating over the
  roster.

Bounds for every phase: the first catch is struck within 3 s of contact, with
at most 2 s (4 ticks) of breath before it, and one click at a time. In phases
1–2, every later catch is also within 3 s, the kiter is never in the breath
for more than 2 s at a time, and nobody nears 90 Sound.

Results, at both the server cap of 10 stacks and an uncapped 99:

| Phase | First catch (worst) | Later catches (worst) | Strikes | Shields left | Max Sound |
|---|---|---|---|---|---|
| 1 | at once, 0 ticks | 0 s | 2–3 | 6–7 | 9 |
| 2 | at once, 0 ticks | 0.25 s, 0 ticks | 2–4 | 1–4 | 6 |
| 3, farthest three | 1.5 s, 3 ticks (3 s spawn); at once (7 s) | — | 2–3 | 0–1 | 9 |
| 3, all 120 sets | 1.5 s, 3 ticks (3 s spawn); at once (7 s) | — | ≤ 3 | — | — |

Phases 2 and 3 only meet the bound because the ground Searing Flame and the
air strikes prefer non-relay shields, and because the owner waits at its air
station once the ground Searing Flame is spent. Without that, phase 2 started
with no relay in place (first catch 5–6 s, 10–12 ticks).

Solo runs (no living relay): the first catch takes up to 3.5 s (7 ticks,
bound 6 s), later catches up to 2.25 s.

An offline sweep, not part of the test, ran one- and two-shield sets at 25%
for every target. With the native 7 s spawn every first catch met the bound.
With the 3 s spawn, 20 of 550 runs took 5 ticks.

**Open question: shields per air phase.** The historical guide reports one per
air phase. A WCL count of Resonating Clash (78168) per air phase would tell
whether the native flame speed is too high.

## Unresolved (fidelity_blocked)

`wcl_10n_kill_reference_pending`, `boss_melee_damage_modifier_10n` (native
roll at modifier 1: 4,553–6,764 per 1.5 s swing), `boss_health_10n`
(native 26,111,168 vs Wowhead 32.6M), `ground_air_phase_timestamps`,
`modulation_repeat_interval`, `breath_initial_target_rule`,
`sonar_bomb_count_by_mode` (native 5 vs Wowhead 3),
`breath_speed_scaling_with_sound` (which includes shields per air phase against the native flame speed), `heroic_fiend_and_shield_destruction_cadence`.

## Sources

1. Wowhead, "Atramedes Strategy Guide - Blackwing Descent Raid Cataclysm Classic",
   updated 2024-06-04, 4.4.2 label: <https://www.wowhead.com/cata/guide/raids/blackwing-descent/atramedes-strategy>.
   Used for health, Sound, shields, 85/40 phases, Devastation target, kiting and composition (1 tank, 2 healers).
2. Icy Veins, "Atramedes Encounter Guide: Strategy, Abilities, Loot - Cataclysm Classic",
   Abide, 2024-07-29: <https://www.icy-veins.com/cataclysm-classic/atramedes-encounter-guide-strategy-abilities-loot>.
   Used for the Devastation target, gong use, and breath speed rising over time and with Sound.
3. Icy Veins, "Atramedes Detailed Strategy Guide (Heroic Mode included)", Damien,
   2012-10-08 (historical): <https://www.icy-veins.com/wow/atramedes-strategy-guide-normal-heroic>.
   Used for the breath reset to initial speed after a gong, 5 Sonar Bomb markers in 10-player,
   Modulation adding no Sound, and the relay kite.
4. wago.tools 4.4.2.59185 DB2 rows (SpellEffect, SpellMisc, SpellTargetRestrictions, …),
   extracted with `tools.raid_program.extract_442_client_spell_rows --follow-triggers`
   (hashes in the ledger).
5. BigWigs_Cataclysm `Blackwing/Atramedes.lua` (commit a5a9f7dea7, 2026-09-24) and
   DBM-Cataclysm `BlackwingDescent/Atramedes.lua` (commit 721d0f3e15, 2026-05-23).
6. Repository: `boss_atramedes*.{cpp,h}`, `instance_blackwing_descent.cpp`,
   `blackwing_descent.cpp`, `SpellMgrCorrectionsPart04.cpp`, the 4.3.4 DBC in `data/dbc/enUS`,
   and the TDB 434.22011 dump (templates, conditions, spellclicks, spawn groups 400/435/436).
