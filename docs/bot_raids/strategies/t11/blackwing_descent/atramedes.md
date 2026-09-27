# Atramedes — research contract v3 and 10N bot strategy

Scope: Cataclysm Classic 4.4.2 behavior (client build 4.4.2.59185, hotfix
cutoff 2025-02-20 23:00 UTC) for 10N, 10H, 25N and 25H, with the 10N bot
strategy for the canonical composition. State: `fidelity_blocked`. Client data,
the native script and the database were audited on 2026-09-25 (repository
revision `a570b44369`). The report pages showed a human-verification interstitial that an agent could not
pass on 2026-09-25. On 2026-09-27 the Warcraft Logs (WCL) 10N kill MxFq7TRbvnjGY1hJ fight 32 was read. It was
opened through the user's running Chrome, after the headless and scratch-profile routes looped on
Cloudflare. That read resolved the boss melee DamageModifier (10.35, promoted to `sql/custom/world`), the 10N max health
(26,111,168, equal to native), the WCL DPS references and the Modulation repeat (16 s).
Only the "Round 1 live diagnosis" section reports live runs; it is diagnosis, not acceptance.

## WCL 10N kill (MxFq7TRbvnjGY1hJ fight 32, 2024-10-28, read 2026-09-27)

- 165.6 s kill, item level 359.9, raid DPS 157,669, no deaths. Two Blood DK
  tanks (Greysnout took every swing), one Restoration Druid and one Holy Paladin,
  two Survival Hunters, Retribution, Shadow, Combat and Elemental.
- **Melee and DamageModifier.** 22 landed swings, U 45,877–68,939, every 1.8 s
  (1.5 s base slowed by Frost Fever). Scarlet Fever covered 6.9–112.1 s and
  129.1–162.1 s. The registry bounds method gives 10.32–10.47, or
  10.22–10.36 after the native +1% auto-attack bonus, so 10.32–10.36 for both.
  The value is 10.35
  (`sql/custom/world/2026_09_27_21_atramedes_damage_modifier.sql` (promoted 2026-09-27; the DB updater applies it at worldserver startup),
  `atramedes_damage_calibration_registry_patch_v1.json`,
  `tests/test_atramedes_damage_modifier.py`). The 25N, 10H and 25H templates stay open.
- **Health.** `tools.raid_program.derive_encounter_health` on six consecutive
  resource rows gives 26,111,168. This equals native (85,892 x 304). Wowhead's 32.6M is not the
  4.4.2 10N value.
- **Timeline.**
  - Two pull gongs (Vertigo 11.8–21.8 s) held the queued first Modulation and Sonar Pulse, which both
    fired at 22.45 s. The native 13 s and 14.5 s first timers are consistent with that.
  - Sonic Breath came at 24.1 s, then 43.7 s later, and again about 21.5 s after landing.
  - Searing Flame came at 45.1 s and was gonged at 45.6 s.
  - Modulation repeated after 16.2 s and 16.8 s when nothing blocked it. The native repeat changed
    from 22–26 s to 16 s in `boss_atramedes.cpp`, which agrees with BigWigs.
  - Sonar Pulse repeated after 11.3 s once, then after 14.6–17.1 s. Native 11 s is kept until a
    second kill confirms the longer gaps.
  - Ground melee stopped at 89.8 s and resumed at 129.1 s. The air phase lasted about 38–39 s
    including travel.
  - Devastation hit one player, twice.
- **DPS references.**
  - Matched: fight 32. Blood DK 13,254 (the active tank), Survival Hunter 25,513
    (median of two), Retribution 19,930 and Elemental 24,949.
  - Round 2 (read 2026-09-27, same route, no check appeared) added five 10N
    kills of 2024-10 that field Balance, Assassination and Demonology:
    PpFW3bgy7m6Kxk1t fight 8, Bgcm6RavhWK7DLd1 fight 34, hxz7MH8gW9BYGNdr
    fight 41, jxNrbDtq9BdwAcam fight 30 and X7tWdbvxYn3MjACD fight 28
    (173.6–199.0 s, raid item level 354.2–357.9, full ground-air-ground
    cycles). They were found through the Balance rankings filtered to raids
    that also field the other two specs and were verified on each fight page.
  - All six kills are matched. Each spec's target is the median of one value
    per kill: Blood DK 13,293 (4), Balance 18,355 (5), Survival 20,413 (5),
    Fire 18,719 (3), Retribution 19,930 (3), Assassination 17,469 (5),
    Elemental 19,688 (2), Demonology 20,626 (5). No canonical spec uses the
    WoWSims fallback any more. The wanted specs' parses span 11–84, so the
    median is not a top-parse target.
  - xAhkN2y9YP3KRmnJ fight 17 (48.5 s, item level 401.4) ends before the first
    liftoff. It is throughput context only.
- Captures: `atramedes_wcl_dps_reference_v1.json`, `atramedes_wcl_cast_timelines_v1.json`
  (8 actors, 935 casts, boss events) and the ledger `wcl_10N_samples`.

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
  - Ground: Modulation 13 s, then every 16 s (22–26 s before 2026-09-27). Sonar Pulse 14.5 s, then every
    11 s. Sonic Breath 24 s, then every 42–43 s. Searing Flame 46 s (once).
    Liftoff 91 s.
  - Air: the land event comes 31 s after he reaches the liftoff point.
  - Ground after landing: Sonar 14 s, Modulation 13 s, Sonic Breath 22 s,
    Searing Flame 51 s, liftoff 93 s.
- **Addon bars (BigWigs Classic).** Modulation 11 s, then every 16 s. Sonar
  11.3 s. Breath 22 s, then every 42 s. Searing 45 s. Air 36 s from take-off,
  then 85 s of ground. The WCL 10N kill confirmed the 16 s Modulation, and the
  native timer was changed. The other native timers agree with that kill.

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
7. DB-side, promoted to the world updater (applied at worldserver start): `sql/custom/world/2026_09_25_40_atramedes_devastation_noisy_target.sql`
   restricts Devastation to Noisy! holders. Before, it hit the whole raid.
   Wowhead and Icy Veins both describe a hit on the 100-Sound player only.

## User raid experience (2026-09-25, authoritative)

The user, an experienced raider, gave these tactics. They are the plan;
where native data or earlier sources differ, the tactic stays and the
conflict is recorded (ledger `conflicts`, source
`user_raid_experience_20260925`).

1. "Atramedes should have a very large hitbox, and melee should stay at max
   melee range as much as possible to have the chance to dodge the rings."
   - TDB: creature_template 41442 uses model 34547 at scale 1, and
     creature_model_info 34547 has BoundingRadius 2 and CombatReach 20.
     Unit::GetMeleeRange is 1.5 + 20 + 4/3 = 22.83 yd (3D, centre to
     centre).
   - Melee hold slots at 21.58 yd behind the boss (as seen from the tank),
     20° apart.
   - A Sonar Pulse disk heading at a melee player in melee range is dodged by
     stepping around the boss at the same distance, until the lane is 8 yd
     to the side (about an 8 yd arc). The player stays in melee range.
2. "One designated ranged is on bell duty, usually a hunter": the gong owner
   is the hunter (unchanged; the canonical hunter is Survival since
   2026-09-26, user decision, and GongRank ranks every hunter spec first).
3. "In the air phase you can have 3 players assigned to gongs: the hunter,
   maybe the mage, and another very fast player."
   - The owner (hunter) and backup (mage) keep their relay stations.
   - The third gonger is the most mobile remaining player, ranked on
     capability: the yards its known mobility spells add over 8 s, melee
     first on ties.
   - In the canonical roster that is the balance druid (Dash and Stampeding
     Roar through Cat Form), then the rogue (Sprint).
   - It takes the shield farthest from the other two stations. A melee third
     may use any shield, since it cannot hit the flying boss anyway.
4. The mage Ice Block play (`BotAtramedesIceBlock.h`,
   `BotAtramedesAirActions.h`):
   - When the rescue is due (the kiter can no longer outrun the flame) and a
     mage with Ice Block ready stands in reach of a shield, the mage strikes
     (`air_ice_block_rescue`).
   - It then holds still, still casting at the boss (the survival Ice Block
     cast pre-empts the damage cast). Once the flame tracking it is
     within 8 yd, it casts Ice Block (45438) and stays for the whole 10 s.
   - On exit (Hypothermia, the flame still on it) it Blinks (1953) away,
     then kites.
   - A chased mage with Ice Block ready blocks by itself (`kiter_ice_block`),
     without a shield.
   - Readiness comes only from the published cooldown (300 s) and the
     absence of Hypothermia, so the play runs once per fight.
   - Nitro Boots is not modelled: bots have no engineering.
5. "If we don't have a mage we just kite as much as possible, then gong":
   the time-to-contact rescue remains the fallback, including after the
   Ice Block is spent.
6. Addendum: "People who have mobility spells are better at gongs in the air
   phase because they can outrun the laser longer, and maybe they can get
   2 gongs per phase, not 3." (`BotAtramedesMobility.h`)
   - The chased player spends its ready mobility before anyone strikes.
     - Speed buffs from 4 s before contact: Sprint, Dash, Stampeding Roar.
     - Leaps at contact: Blink, Disengage.
     - It picks whichever puts contact latest. The strike waits
       (`kiter_mobility_extension`).
   - Strikers are ranked by their ready mobility too, since the striker is
     the flame's next target.
   - Every speed, displacement, duration and cooldown is the 4.3.4 client
     row, pinned by `tests/test_atramedes_mobility_data.py`:

     | Spell | Effect | Duration | Cooldown |
     |---|---|---|---|
     | Sprint | +70% speed | 8 s | 60 s |
     | Dash | +70% speed, Cat Form | 15 s | 180 s |
     | Stampeding Roar | +60% speed, Cat Form | 8 s | 120 s |
     | Blink | 20 yd forward | — | 15 s |
     | Disengage | 15.55 yd back | — | 25 s |
     | Ice Block | immune to every school | 10 s | 300 s |

   - Ghost Wolf has a 2 s cast and is left out.
   - Aspect of the Cheetah (+30%, dazed when struck) is left out: it would
     fight the hunter's persistent Aspect of the Hawk self-buff
     (`BotPersistentSelfBuffContract.h`), which the runtime re-casts in
     combat.
   - Readiness includes the global cooldown of a GCD-bound spell, and a spell
     that needs Cat Form counts only while Cat Form is active or its
     shapeshift is ready too. A strike held back for an extension therefore
     never waits on a cast the server would reject.
   - Talents (Body and Soul, Speed of Light) are not assumed.
   - The target is 2 shields per air phase.
7. Readiness is a runtime fact: the snapshot must publish each bot's
   cooldowns for these spells as player MechanicTimers (patch request
   `player_spell_timers.patch`). Until then, no extension and no Ice Block
   play happen, and the strategy behaves as before.

**Native-data conflicts:**
- **Ice Block and the flame.**
  - In 4.3.4 Ice Block is immune to every school and has
    SPELL_ATTR1_DISPEL_AURAS_ON_IMMUNITY. It strips the physical Tracking
    aura (78092) and ends the flame's Tracking channel.
  - The flame AI keeps its MoveFollow and target and only re-acquires a
    dead or missing target, so the flame stays on the iced mage.
  - The breath hit (78353, fire) does no damage and adds no Sound while the
    mage is iced.
  - The flame does not "finish" on its own; it despawns at landing. After the
    block it still follows the mage, with no Tracking fact. The facts
    therefore follow it to the player under Ice Block or Hypothermia, and a
    second strike follows if more than about 2 s of the air phase remain.
- **Ghost Wolf.** It has a 2 s cast (left out).
- **Nitro Boots.** Not modelled.

## 10N bot strategy (canonical composition: 1 tank, 2 healers, 7 DPS)

Roster: Blood DK (tank); Balance, Survival Hunter, Fire Mage, Retribution,
Assassination, Elemental, Demonology; Holy Paladin and Discipline healers.
Duties come from capability on every snapshot (`BotAtramedesDutyPlan.h`), never
from roster slots.

- **Pull and tank.** Everyone targets the landed boss and the tank's threat
  takes him. On the ground the tank drags Atramedes to the anchor
  (150, -224.5), near the arena centre. From there every air relay station
  (below) is also in spell range of the grounded boss. He has 20 yd combat
  reach, so the tank stands 10 yd past the anchor. Melee hold slots at
  21.58 yd from his centre (melee range 22.83), behind him, and sidestep
  Sonar Pulse around him at that distance.
  - While he is still being dragged (grounded, on the living tank, more
    than 14 yd from the anchor: the pull and each landing), melee take no
    slot and native melee chase keeps contact. The slot "behind him as seen
    from the tank" is then his trailing side: in round 1 melee flipped to it
    at the pull and lost 6-15 s of swings while he walked about 58 yd at
    ~7.8 yd/s (`AnchorDragInProgress`, round 2). Hazard exits still apply.
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

- **Spirit packs** (route nodes `bwd.atramedes.north_spirits` and
  `south_spirits`, `BotAtramedesSpirits.h`). Each group of four aggroes
  together (creature_formations groupAI 3) and respawns 30 s after a reset.
  A dying spirit hands its ability to the others (Bestowal).
  - Kill order: the ability least harmful to hand on dies first.
    - North: Corehammer, Anvilrage, Moltenfist, Shadowforge. Icy Veins puts
      Corehammer first: Burden of the Crown, 80718, gives +100% damage done
      and no power cost to whoever carries it. Chain Lightning (Shadowforge)
      is never handed on.
    - South: Angerforge, Thaurissan, Burningeye, Ironstar. This order is
      provisional (no readable source yet). Execution Sentence (Ironstar) is
      never handed on.
  - Everyone, the tank included, damages the kill-order target once the
    pack is engaged. On a trash route the shared group focus
    (`FindValidationRouteGroupFocusTarget`) is the tank's own target, so the
    tank's target puts the raid on the kill order. The tank's position, and
    the melee's outside a Whirlwind, are left to native threat and melee
    range.
  - Radii: an area effect with TargetA SRC_CASTER and TargetB
    UNIT_SRC_AREA_ENEMY uses the TargetB radius (`SpellEffectInfo::CalcRadius`).
    It is tested as a 2D cylinder with no hitbox for these generic-family
    spells (`WorldObjectSpellAreaTargetCheck`). That makes Thunderclap
    (80649) 20 yd (radius index 9; round 3 logged a hit at 16 yd) and the
    Whirlwind pulse (80651) 4 yd (radius index 26; the tank at 4.37–4.56 yd
    took 0 of 13 ticks). `tests/test_atramedes_spirits.py` pins both against
    the client rows.
  - Ranged and healers stand on a ring 30 yd from the engaged pack, 30°
    (15.5 yd) apart, as near the bearing toward the arena centre as allowed.
    Every slot is:
    - outside every Thunderclap (20 yd), with a survival exit when inside
      21.5 yd;
    - within 40 yd (spell range) of every spirit;
    - at least 35 yd from every idle spirit (the other pack, even when the
      tank drags the engaged one toward it);
    - on the arena floor (48 yd from its centre) and off the pillar holes:
      all four navmesh cells around it are floor (`ArenaFloor::Solid`);
    - within heal range of the tank: 38 yd from the living main tank, or,
      with none in the snapshot, 33 yd from the pack centre, since the tank
      can stand about 5 yd beyond it. Heal range is about 43 yd with reaches.
  - When the tank drags the pack where the 30° ring does not fit everyone,
    the slots stay more than Chain Lightning's 12.5 yd jump apart:
    1. spread evenly over the widest valid arc of the 30 yd ring, down to
       26° (13.5 yd);
    2. else the rings at 30, 33 and 27 yd, packed 15.5 yd then 12.75 yd
       apart;
    3. else the valid points of a 1 yd grid around the pack, packed
       12.75 yd apart;
    4. with no valid point at all (two engaged spirits more than 80 yd
       apart), points on the 30 yd ring, preferring those on the floor and
       clear of the spirits, then those on the floor.
    The layout is computed once per snapshot. The last few layouts are
    cached per thread, keyed bit for bit on every input. In a cramped drag
    that cuts the cost from about 3.8 ms to 0.55 ms per decision round of
    seven bots.
    The review of round 6 had found the old fallback (the nearest valid
    point) stacking slots: some pair under 15 yd in 370 of 824 dragged
    positions, down to 0 yd. The drag sweep in
    `tests/test_atramedes_spirits.py` (each pack ±24 yd in 2 yd steps, the
    other idle, the tank dragging it or dead) now keeps every pair above
    12.5 yd (worst 12.81 yd) in the 787 positions per case with every
    engaged spirit in the room. Dragged into the walls (the other 463), the
    slots stay valid and at least 7 yd apart.
  - The route keeps the pull, threat pickup and completion.
  - Melee near Whirlwind (80652: 5 s, 80651 every second in 4 yd, 56.5k).
    A melee player (not the tank) within 4.75 yd of a whirlwinding spirit
    steps to a ring 5.4 yd from its target.
    - The ring point is the one nearest the player that is at least 5 yd
      from every whirlwinding spirit.
    - It lies outside the pulse and inside melee range (1.5 + spirit
      CombatReach 3.375 + 4/3 = 6.21 yd; creature_model_info 36437–36444),
      so the melee keep hitting and the native chase does not pull them
      back in.
    - The 4.75 yd trigger and the 5 yd clearance give hysteresis.
    - With no clear ring point (whirlwinding spirits around the target),
      they leave radially from the whirlwinding spirits' centroid until
      clear of all of them. They never ping-pong between two.
    - The round-4 version left to 10 yd, out of melee range, and flipped
      against the native chase.
  - Round 3 cleared both packs without a wipe.
    - North: Thunderclap hit players 19 times (125 in round 2), mostly the
      tank and melee. Chain Lightning was cast once, with no death.
    - The first kill of each pack followed the order. The second did not:
      Shadowforge in the north, Burningeye in the south. The tank's native
      area-threat target drives the melee and the remembered route focus
      (patch `spirit_kill_order_tank.patch`).
    - Burningeye's Whirlwind went to two spirits and killed the rogue and
      the retribution paladin.
    - Their 438 yd runback from the lower-wing elevator is longer than the
      server's 74-point path limit, so the route never advanced (request
      `lower_wing_runback_path_request.md`).
  - Round 2 wiped here: the shard was provisioned on the pack centre, the
    ranged never left melee range, and Moltenfist died first. About eight
    players took every Thunderclap, both healers died at 45 s and 53 s, and
    the raid wiped at 63 s.

**Round 4, the first live pull (2026-09-26).**
- Both spirit packs were cleared. The bell was rung, and Atramedes landed at
  (214.5, -223.9) and aggroed the raid, which was still on the bell gather
  point (231.6, -224.4), 17 yd away and inside his 20 yd reach.
- The plan never saw him. Both the intro and the 30 s post-wipe respawn are
  `instance->SummonCreature` TempSummons, which the blackboard files under
  Summons, while `FindBoss` looked only at Hostiles.
- The route therefore failed closed on the boss for the whole fight
  (`raid_mechanic_contract_fail_closed`, 762 decisions):
  - nobody moved or cast;
  - the 84k dealt to him came only from Lightning Shield, Eye for an Eye,
    Molten Armor and pets.
- Timeline:

  | Time | Event |
  |---|---|
  | 13 s | Modulation (25k each) |
  | 27.4–32.4 s | Sonic Breath, 6 ticks, on all ten stacked players; 5 ticks (+100 Sound) by 31.4 s |
  | 31.7 s | Devastation on all ten |
  | 32.7–35.1 s | Everyone died |

  Every player reached 100 Sound in the same breath, so this run cannot show
  whether the Devastation condition restricts it to the Noisy player.
- There was no Searing Flame (the first is at 46 s), no air phase and no
  gong.
- Fixes:
  - `FindBoss` looks in Summons and Hostiles.
  - The plan owns the node only while Atramedes is engaged, so the idle
    respawn is walked to and pulled by the route.
  - `TestRound4BellStack` replays the landing snapshot: tank drag, ranged
    arc, melee slots, the owner's standby and the breath split.
- After the wipe, the elevator recovery worked, but the walk back met the
  live central-hall north patrol at (-42.8, -164.8). The boss node refused
  it as undeclared, so the raid stood there for 10 minutes (round 5 requests
  A–C).

**Round 5: the first kill, not recorded (2026-09-26).**
- The plan owned the fight from the landing, and Atramedes died:
  26,110,798 damage, no death.
  - The Time Warp fallback came at 5.3 s.
  - The tank dragged him west.
  - Searing Flame came at 47–51 s, the air phase at about 91–131 s, and the
    kill at about 140 s.
- The native death callback rejected the kill (`gate=combined_rejected`,
  `engaged_guid_expected` empty). The adaptive owner skips the route
  adapter, and unlike Magmaw and Chimaeron nothing carried the route's
  engagement edge (`RememberValidationRouteBossEngagement`). The route never
  advanced and the plateau watchdog ended the run.
  - `BotWorldPopulationMgrAtramedesCandidates.cpp` adds the observer. It
    binds the engagement only while the plan owns the encounter node, the
    target is Atramedes (the route target entry), he is in combat, and
    native combat with him is observed.
  - `.git/round6_patches/atramedes/atramedes_route_observation.patch`
    declares it and submits it next to Chimaeron's.
- The Searing Flame went ungonged (three ticks on the raid). The gong owner
  never reached its shield: 311 of its standby moves were rejected
  (`route_destination_path_control_level_gap`).
  - The hall is a bowl: about 75.7 at the centre and 77–77.6 at the shield
    ring. The plan sent every destination at z 75.
  - The air kite's ring waypoints were rejected the same way.
  - Destinations now take the navmesh floor (`BotAtramedesArenaFloor.h`, a
    2 yd grid regenerated from `data/mmaps` by the test).
- `validation_route_future_encounter_contamination`: the tank dragged the
  north pack 14 yd south, and the fixed half circle toward the arena centre
  put both healers 26 yd from the idle south pack, which joined the fight.
  The standoff ring now keeps 35 yd from every idle spirit.

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

**Mobility and Ice Block replay** (`TestAirMobilityReplay`). This replay runs
the canonical roster with its mobility published. It covers every target,
spawn delays of 7 s and 3 s, the server stack cap, and three variants:
- Ice Block ready (the fight's first air phase);
- Ice Block and Dash on cooldown (a later air phase);
- no mage.

Each variant also runs as a second air phase, from the shields left after
its first one and a Searing Flame. That makes 116 runs.

Results:
- With the native 7 s spawn, every run (58) spends 1–2 shields and meets the
  exposure bounds. The first catch is within 3 s and 4 ticks, and no kiter is
  in the breath for more than 2 s at a time.
- With the 3 s stress spawn, 54 of 58 runs spend 2 shields and 4 spend 3.
  All 4 have the hunter as the first target before the relays reach their
  stations; since Aspect of the Cheetah was dropped, the hunter has only
  Disengage. One of them keeps a mage in the breath for 3.75 s after its
  Blink, before a relay is in reach.
- Sound stays below 90; in the first phases it peaks at 9.
- With Ice Block ready it is used at most once per run:
  - 17 of 20 runs by the rescue strike;
  - 2 by the chased mage itself;
  - 1 not at all (3 s spawn: the mage was never in reach in time).
  - With the 7 s spawn it is used in every run.
- The iced mage gains no Sound, and with the 7 s spawn it always blinks out
  of the block.
- Live acceptance is the exposure bound in the ledger, not the strike time:
  extensions and the Ice Block delay the strike by design.

Without mobility published, the older replay still spends 2–4 shields per
phase.

**Shields per air phase.** The historical guide reports one per air phase;
the user's target is 2. Round 2 counted air Resonating Clash (78168) casts in
six WCL 10N kills: 1, 1, 1, 2, 1, 1. The native replay's 1–2 with the 7 s
spawn matches that spend, which does not by itself isolate a Sound term in
the flame speed (`breath_speed_scaling_with_sound` stays open).

## Round 1 live diagnosis (blackwing_descent_10n-r01-553da85c98, read in round 2)

Three counted native clears, 131.6 ± 1.3 s, 0 boss-window deaths, boss melee
0.96x WCL. Against the six matched WCL kills every actor passes except the
Demonology Warlock (7,371 DPS, 0.36). Balance (1.43) and Assassination (1.17)
failed round 1 only against the patchwerk WoWSims fallback.

- **Phases (native, boss z from the combat log).** Liftoff starts at
  91.2–91.5 s after the first hit, he hovers at z 113.2 from 95–96 s and
  touches down at 127.8–128.5 s: 36.5 s airborne including travel. The WCL
  kill lifts off about 90 s and lands about 129 s. Round-1 kills end 2–4 s
  after the landing, so the air phase is 27% of the bot window against about
  23% in fight 32; melee get nothing in it (0.1–0.2M air damage each).
- **Melee at the pull.** The anchor drag moved him from about (215, -224) to
  (157, -222) in 12 s. Melee lost 6–15 s of swings (rogue gaps 10.7 s and
  8.0 s in two kills, Retribution 6.3–10.1 s in all three) chasing their slot
  on his trailing side. Round 2 leaves melee to native chase until he is
  within 14 yd of the anchor. Later ground gaps are 2.6–4.1 s (Sonar Pulse
  sidesteps).
- **Ranged.** The Fire Mage's first hit comes at 6.1–7.0 s: it walks its arc
  slot, which follows the dragged boss. Balance moves in 29–61% of its damage
  events and Elemental keeps casting; no gap over 2.5 s for Balance.
- **Demonology Warlock (class evidence, not an encounter change).** Only
  19–48 own damage events per kill and no Shadow Bolt. Its profile
  (`bot_rotation_profile` 287, `phase8_demonology_hellfire_survival_2026_07_27`)
  caps every enemy row at `max_range` 18 (Shadowflame 8). The resolver compares
  that cap with the centre-to-centre distance and intersects it with the native
  range, so with Atramedes' 20 yd combat reach no legal cast point exists
  outside his hitbox. On the 32 yd ranged arc Immolate, Incinerate, Hand of
  Gul'dan and Shadowflame were rejected `max_range_exceeded` 700–1,170 times
  per kill; the range recovery then fought the arc (`ranged_arc` 150–230
  movement receipts, `higher_priority_movement_active`,
  `movement_requires_instant_action` 72). In the same round the Magmaw shard's Demonology Warlock did 32.7k.
  The fix belongs to the class owner (raid-scoped, so accepted results stay
  put); moving the arc to 18 yd would put the warlock inside the boss.

## Unresolved (fidelity_blocked)

`ground_air_phase_timestamps` (10N now measured on both sides: native liftoff
91.2–91.5 s, touch-down 127.8–128.5 s; WCL first air Tracking 95.1–95.4 s in
six kills; resolving it for 10N needs the catalog and the BWD quantitative
audit updated together), `breath_initial_target_rule` (six WCL kills: the
ground breath never tracked a tank in 19 applications, the air breath tracked
a tank twice in 15; per-player Sound is not exposed),
`sonar_bomb_count_by_mode` (native 5 vs Wowhead 3; WCL shows impact groups
every 3 s with 1–3 players hit but no launch rows),
`breath_speed_scaling_with_sound` (air shields per phase 1–2 in WCL, as native),
`heroic_fiend_and_shield_destruction_cadence` (heroic only). The ledger's
unresolved entries now carry their modes.
Resolved on 2026-09-27 from WCL: `wcl_10n_kill_reference_pending`,
`boss_melee_damage_modifier_10n`, `boss_health_10n`, `modulation_repeat_interval`.

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
7. Warcraft Logs, Cataclysm Classic report MxFq7TRbvnjGY1hJ fight 32 (Atramedes 10N kill,
   2024-10-28): <https://classic.warcraftlogs.com/reports/MxFq7TRbvnjGY1hJ?fight=32>, and
   xAhkN2y9YP3KRmnJ fight 17 (10N kill, 2025-06-11): <https://classic.warcraftlogs.com/reports/xAhkN2y9YP3KRmnJ?fight=17>.
   Read 2026-09-27. Used for melee U, health, boss timeline, Devastation target, DPS and cast timelines.
8. Warcraft Logs, five further Atramedes 10N kills read 2026-09-27 (round 2):
   PpFW3bgy7m6Kxk1t fight 8, Bgcm6RavhWK7DLd1 fight 34, hxz7MH8gW9BYGNdr fight 41,
   jxNrbDtq9BdwAcam fight 30, X7tWdbvxYn3MjACD fight 28 (for example
   <https://classic.warcraftlogs.com/reports/PpFW3bgy7m6Kxk1t?fight=8>). Used for DPS
   references, Tracking targets, Sonar Bomb impacts and air shield counts.
