# Atramedes — research contract v3 and 10N bot strategy

Scope: Cataclysm Classic 4.4.2 behavior (client build 4.4.2.59185, hotfix
cutoff 2025-02-20 23:00 UTC) for 10N, 10H, 25N and 25H, with the 10N bot
strategy for the canonical composition. State: `fidelity_blocked`; per mode, 10N is `accepted` (user
decision 2026-09-30, see Unresolved) and 10H, 25N and 25H stay `fidelity_blocked`. Client data,
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
    liftoff. It was throughput context only and was dropped in round 3 (outside
    the tier-11 band; see "Round 3").
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
| Sonar Bomb (air, 3 markers every 3 s in 10N; 5 in 10H, 12 in 25-player) | 20,000 Arcane (heroic 30,000) | +20 (heroic +30) | 6 yd |

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
     cast pre-empts the damage cast). It starts no new cast once the flame
     could reach 8 yd within one global cooldown, because Ice Block is on the
     global cooldown. Once the flame tracking it is within 8 yd and Ice Block
     is castable, it casts Ice Block (45438) and stays for the whole 10 s.
   - On exit (Hypothermia, the flame still on it) it Blinks (1953) away,
     then kites.
   - A chased mage with Ice Block ready blocks by itself (`kiter_ice_block`),
     without a shield.
   - Readiness comes only from the published cooldown (300 s) and the
     absence of Hypothermia, so the play runs once per fight. A global
     cooldown still running delays the cast but does not cancel the play.
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
    above 40.8% health (on the ground) or 25.4% (in the air).
    - Searing Flame may always use a shield.
    - A 90-Sound emergency spends down to this phase's Searing Flame, since a
      Devastation death now outranks a Searing Flame 51–82 s away.
    - An air rescue also keeps the next phase's shield.
    - An 80-Sound gong keeps one more spare.
    - Why 40.8% and 25.4%: the next Searing Flame is at least 82 s (ground) or
      51 s (air) away. At a 130k raid-DPS floor that removes 40.8% or 25.4% of
      the native 10N health (26,111,168), so a boss below the threshold dies
      first. The floor is the slowest matched tier-11 kill (131,217 raid DPS,
      hxz7MH8gW9BYGNdr fight 41; median of the seven 145,174), since round 3
      (it was 150k from ~409-gear Magmaw runs, 50% and 30%).
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
the flame speed (`breath_speed_scaling_with_sound` is bounded for 10N by a user
decision, not measured: see "Round 3 fix: the kiter Sound bound" below).

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

The per-mode gate (`fidelity_state_by_mode`) accepts 10N since 2026-09-30 and keeps
10H, 25N and 25H blocked. No unresolved claim covers 10N any more: two were closed
for 10N by user decisions, `sonar_bomb_count_by_mode` and
`breath_speed_scaling_with_sound`.

- **User decision 2026-09-30 (`sonar_bomb_count_10n`).** Question: can 10N be
  accepted with the native Sonar Bomb count of 5, although no source can confirm 3 or
  5 for 4.4.2? The user answered: "Switch to 3". Source
  `user_decision_20260930_atramedes_sonar_bomb_10n` (supporting source: Wowhead 4.4.2,
  3 bombs per wave in normal). The SpellMgr correction now gives 10N Sonar Bomb 92526
  three targets (`SpellMgrCorrectionsPart04.cpp`; it was 5). 92532 (10H) stays 5 and
  92531/92533 (25-player) stay 12. The change is syntax-checked only; it needs a
  worldserver build before a live run. The bots dodge every bomb marker whatever the
  count.
- `sonar_bomb_count_by_mode` (10H, 25N, 25H). Wowhead 4.4.2 says 6 in heroic and 3 in
  25N, the historical guide 5 in 10-player and 8 in 25-player; native keeps 5 for
  10H and 12 for 25-player. No same-mode log or count. Why no log settled 10N
  either: WCL logs no Sonar Bomb launch. In 9Rdhq6BkMXKNw3CP fight 13 every filter
  on the bomb spell IDs, the names and the summons over 1:25–2:15 is empty. Only
  the impacts (92553) appear. Impact waves hit 1–2 distinct players in three
  kills (round 2: 1–3), which fits both 3 and 5. The 4.4.2 client has no
  MaxTargets row for 92526/92532, so the count is set on the server.
- **User decision 2026-09-30 (`breath_speed_scaling_with_sound`, 10N).** The review
  rejected the earlier 10N closure "with bounds": every measured WCL chase had its
  kiter at 0–10 Sound, so an extra Sound term above 10 was never measured, and
  nothing kept a 10N kiter in that range. The user answered: "Bound kiter Sound
  (Recommended): keep the time-only ramp and add a 10N acceptance rule: the tracked
  kiter stays at 10 Sound or less during the chase". Source
  `user_decision_20260930_atramedes_kiter_sound_bound`. The native ramp is unchanged;
  a 10N kill is accepted only with the acceptance observation below.
- `ground_air_phase_timestamps` and `breath_initial_target_rule` are resolved for
  10N, and `breath_speed_scaling_with_sound` is bounded for 10N. All three stay open
  for 10H, 25N and 25H, which have no log.
- `heroic_fiend_and_shield_destruction_cadence` (heroic only).

Resolved on 2026-09-27 from WCL: `wcl_10n_kill_reference_pending`,
`boss_melee_damage_modifier_10n`, `boss_health_10n`, `modulation_repeat_interval`.

## Round 3: tier-11 references and the 10N air phase (read 2026-09-30)

The route was `codex exec -m gpt-6.1-sol` in one tab of the user's Chrome (profile
Runiir). No check appeared. The first read lost the plugin connection after 12
pages, and two further reads (41 and 46 pages) finished it. Source
`wcl_atramedes_10n_air_20260930`.

- **References at tier-11 gear.** The roster now wears T11 phase gear (about
  359, user decision 2026-09-30), so the references are kills at raid item
  level 352–366.
  - The six matched kills (354.2–359.9) stay.
  - 9Rdhq6BkMXKNw3CP fight 13 (356.7, 180 s, full air phase) adds a third
    Elemental kill and two more Survival hunters.
  - xAhkN2y9YP3KRmnJ fight 17 (401.4) is dropped.
  - Two targets change: Elemental 19,688 → 24,949 (3 kills) and Survival
    20,413 → 21,610 (6 kills). The other six specs are unchanged.
- **Air-phase timestamps (10N resolved).** Seven kills:
  - The last ground swing is at 87.9–90.4 s.
  - The first air Tracking is at 95.1–95.4 s, and the first breath tick about
    0.5 s later.
  - Melee resumes at 127.5–133.0 s (median 129.1).
  - This matches native: liftoff at 91 s, the flame at about 95 s, landing
    31 s later, touch-down at 127.8–128.5 s and re-engage 0.8 s after it.
  - The second ground phase's first Tracking comes at 150.3–152.0 s, which
    is native's landing + 22 s.
- **Breath target (10N resolved: random).**
  - Sound at each Tracking was summed from the WCL Alternate Power gains since
    the last shield strike.
  - In the 18 applications where the gains show who was loudest, the target
    was the loudest player only twice. Examples: Jonson 0 vs Andremus 90, and
    Rubælia 0 vs Worgnfreeman 73.
  - Sonic Breath never tracked a tank in 22 ground applications. The air
    flame tracked a tank twice (round 2).
  - After its target dies, the flame takes another player: Vahan died at
    1:58.8 and Zuuri was tracked at 1:59.5.
  - A hunter's Feign Death also dropped the flame (Rubælia, fight 30). Native
    re-targets only a dead or missing target. No canonical bot uses Feign
    Death, so the gap is recorded, not fixed.
- **Flame speed (10N: bounded by the user decision, not measured above 10 Sound).**
  - WCL logs no Building Speed rows, so the speed comes from catch timing.
  - The flame spawns on its target (first tick at +0.5 s). The target breaks
    free and is caught again after 12.0 s (Vahan, Nitro Boosts), 12.0 s
    (Rubælia, Nitro), 8.5 s (Aduktai, Darkflight), 4.5 s (Jonson, no speed)
    and 20.0 s (Aiada, from a redirect head start with Nitro and Sprint).
  - The native ramp (5 yd/s + 1 yd/s per second) in a straight chase predicts
    12.8–13.2, 12.8–13.2, 7.8–8.8, 4.0 and 16–17 s. Kites that curve around
    the ring are caught sooner.
  - Every target had 0–10 Sound, so a flame whose speed depends on Sound alone
    is ruled out. Two things stay unmeasured: an extra Sound term above that
    range, and the stack cap (10 on the server, 99 in the client; 0.3 s apart
    in these chases). The review rejected closing the claim on that alone; the
    user's bound (below) keeps every accepted 10N chase inside the measured
    range.
  - A redirected flame tracks the striker 7.2–7.6 s after the strike. Air
    strikes per phase in seven kills: 1, 1, 1, 2, 1, 1, 1.
- **Strategy fix: the Ice Block play survives a global cooldown.**
  - Ice Block is on the global cooldown (SpellCooldowns 3200:
    StartRecoveryTime 1500), and the published readiness includes it. A mage
    casting at the boss therefore read "not ready" for up to 1.5 s after
    every cast start.
  - Before the fix, the bait flickered off during each cast start. The mage
    then ran as the redirect runner, and the air gong decision handed the
    catch to a second shield.
  - Now Ice Block counts as available with at most one global cooldown left
    (`IceBlockAvailable`) and is cast only when ready.
  - The bait starts no new cast once the flame could reach the trigger
    distance within one global cooldown (`IceBaitQuietYards`).
  - A chased mage whose Ice Block waits on the global cooldown keeps kiting
    without casting, and no shield is spent (`atramedes_ice_block_pending`).
  - The other air paths were reviewed against the user's tactics: the hunter
    owns the gong, up to three gongers, the mage's Ice Block once per fight
    then Blink, and melee at maximum range on the ground and held in the air.
    No other defect was found.

## Round 3 fix: the kiter Sound bound (user decision 2026-09-30)

**Rule.** In every air-phase Roaring Flame chase the tracked kiter stays at 10 Sound
or less, the range the WCL chases measured. The native flame keeps its time-only
ramp. A 10N kill that breaks the rule, or cannot prove it, is not accepted.

**What a chase is.** It starts in the first snapshot in which the Reverberating
Flame follows a player: its Tracking target, or the iced mage it keeps following
without one (`BuildFacts` `AirKiter`). It ends when the flame follows another
player, follows nobody (a gong redirect: the flame waits and flies to the shield),
or the air phase ends. A redirect back to the same player starts a new chase.

**Server evidence.** `BotAtramedesObservationCounters.h` and
`BotAtramedesObservationStore.h` keep per-attempt counters:
- air phases, chases and chase samples;
- the loudest kiter sample (`max_kiter_sound`) and the samples above 10
  (`samples_above_10`);
- the largest sampling gap next to an engagement (`max_sample_gap_ms`).

Every bot decision offers the cohort's encounter snapshot (republished every
100 ms), and each snapshot is sampled once. The counters are scoped like
Nefarian's: per cohort, start lifecycle, attempt id and map instance.

`complete` is true only after a sample of the attempt, and only while sampling
covered it:
- no gap over 1 s next to the air phase (a breath tick adds 3 Sound every
  0.5 s);
- no gap over 5 s inside one ground engagement (an air phase lasts 31 s, so
  none can pass unseen);
- no instance change and no clock that went back.

The export is `.botauto status` `raid_runtime.encounter_observations.atramedes`,
in the same object as Nefarian's block. A cohort that never ran Atramedes, or a
reused one (Stonecore, calibration, legacy Magmaw), exports byte-identical status.

**Acceptance check.** `tools/raid_program/run_sanity.py`
(`acceptance_observation`) reads the block of the judged attempt's final status.
It uses the same attempt and final-window rules as Nefarian. For a counted kill it
blocks when:
- any sample is above 10;
- the evidence is missing or malformed, or its counts contradict each other;
- `complete` is anything but true;
- there is no chase although the kill had an air phase (the counters saw one, or
  the boss window reached 110 s: liftoff is at 91 s and the first chase at about
  95 s).

The round-2 records predate the counters, so they now block as unproven.

**Strategy (round 3, built after the report-only check).** Before this change the air
strategy did not keep the bound: the first chase took a random player with whatever Sound it
carried from the ground (a Sonic Breath tick is +20), a kiter the time-to-contact model expected
to outrun the flame took breath ticks without a rescue, and the air kite outranked the Sonar Bomb
(+20) and fire-patch (+5 per second) exits. A shield strike sets every bar to 0 (77709), so the
bound is kept with native strikes and lawful movement only (`BotAtramedesSoundBound.h`,
`BotAtramedesKitePath.h`):
- *Pre-liftoff reset* (`pre_liftoff_sound_reset`). In the last 4 s before the published liftoff,
  while anyone (the tank included: the air flame may take it) is above 7 Sound, whoever stands
  nearest a shield strikes the nearest one, a non-relay shield when in reach. Vertigo holds the
  liftoff for its 5 s and the flame spawns about 4 s after the liftoff, so nothing but the last
  Sonar Pulse disks can add Sound before the first chase. A chase that starts above 10 cannot be
  repaired, which is why the reset comes before the flame and not at its spawn.
- *Chase Sound reset* (`air_kiter_sound_reset`). While the chased player, or during a redirect the
  striker the flame will track next, is above 7 Sound (one breath tick would pass 10), a strike
  is due at once. Its mobility and its own Ice Block lower no Sound, so they do not hold the strike
  back, and a chased player named to strike strikes before casting.
- *Sound-bound contact* (`air_kiter_sound_bound`). The hits the chased player is about to take
  count as contact: the next breath tick (within a tick of contact, or still inside the breath
  while the model expects it to escape) and every fire patch in reach, when they would pass 10.
- *Shield budget* (`ShieldBudget`). The rest of the fight needs one Searing Flame interrupt per
  ground phase still to come (this one while pending, the next while the boss lives to reach it:
  above 40.8% on the ground, 25.4% in the air, since the round-3 dodge fix; 50% and 30% before). Air strikes (rescues, Sound resets, the pre-liftoff
  reset) spend every other shield; a 90-Sound emergency may spend the next phase's interrupt; an
  80-Sound gong keeps one more spare. A forbidden strike is withheld and logged
  (`air_kiter_sound_reset_at_reserve`, `air_kiter_sound_bound_at_reserve`,
  `pre_liftoff_sound_reset_at_reserve`). Expected spend: 1 per ground phase, 1-2 air catches, plus
  the pre-liftoff reset when someone is loud.
- *Gong team.* The Ice Block rescue stays the mage's play once per fight (readiness only from its
  300 s cooldown and Hypothermia); the pre-liftoff reset is a ground strike and never uses it. The
  mage waiting for the flame is never chosen to strike again.
- *Kite path.* The chased player, the redirect runner and leaps (Blink, Disengage) keep the next
  ring waypoint unless that run crosses a Sonar Bomb zone or a fire patch. Then they take, among
  the ring waypoints of the next two shields on the rescue lane (4 yd inside the shield) and an
  inner lane (9 yd, still in click reach, on the hall floor), the one with the least expected
  Sound: +20 per bomb zone crossed, +5 per second in each patch, and +3 per breath tick the flame
  would land on that heading before arrival, so leaving a hazard never hands the kiter to the
  flame. Earlier chases leave their trails on the ring (patches outlast the air phase).
- *Relays.* The redirected flame flies to the struck shield across the relay station and lays its
  trail there, and bombs mark relays: a relay holds the clear point in click reach of its own
  shield nearest its station (`AirStationFor`) and steps there instead of away from the shield
  (`air_relay_hazard_step`); the Ice Block bait steps out of a bomb zone or patch instead of
  holding in it.

**Replay** (`tests/test_atramedes_kiter_sound_bound.py`, the strategy test's native replay with the
production chase counter; kiter samples above 10 per air phase, before -> after this change):

| Scenario | Phases | Above 10 before | Above 10 after | Worst after |
|---|---|---|---|---|
| Canonical, phases 1-3 (no mobility published) | 120 | 0 | 0 | 9 |
| Mobility, native 7 s spawn (first, next) | 58 | 2 | 0 | 9 |
| Mobility, 3 s stress spawn | 58 | 1 | 1 | 18 |
| Ground Sound carried (+20 on the target, +6 on two), 7 s spawn | 58 | 58 | 0 | 6 |
| Ground Sound carried, 3 s spawn | 58 | 58 | 16 | 24 |
| Sonar Bombs and fire patches, 7 s spawn (3 seeds) | 174 | 97 | 30 | 50 |
| Sonar Bombs and fire patches, 3 s spawn (3 seeds) | 174 | 111 | 25 | 78 |

Each run also meets the older bounds (one click at a time, the mage's Ice Block at most once per
fight). The solo runs (no relay alive) still reach 21: the lone kiter is away from every shield
when the flame spawns on it. The remaining misses are stress cases: with the 3 s spawn in the
second air phase the pre-liftoff reset has used the one in-range relay shield left and no relay is
in reach of the spawn catch; with bombs and fire, a bomb landing on a player just re-tracked (+20
from any Sound, which no strike can undo), a catch on the west side (105 yd without a shield) after
the kiter spent its mobility, and phases whose shields run out (withheld with the reserve reason).
The replay's flame spawns on its target (0.5 yd) and patches tick +5 each, both worst cases; the
spawn burst 78555 is not modelled. Live 10N kills are still judged by the server counters, not by
this replay.

## Round 3 fix: everyone dodges everything (user raid experience 2026-09-30)

The user, from raid experience (source `user raid experience 2026-09-30`, ledger
`user_raid_experience_20260930_atramedes_dodge`, authoritative):

> "For atramedes ideally everyone is as close to 0 sound as possible, meaning the bots dodge
> everything."

In 10N every Sound source can be avoided: Modulation adds no Sound (client rows; only heroic adds
+10), the ground Searing Flame adds none and is interrupted by the gong. The kiter Sound bound
above still gates only the tracked kiter; this section is about every bot, in both phases.

**Audit** (before this fix; "sees" = the snapshot carries it and a rule reads it).

| Source | Who is exposed | Sees it | Moves out | How early | Cost / gap |
|---|---|---|---|---|---|
| Sonar Pulse disk, +3/0.5 s, 5 yd | everyone on a lane from the boss; the tank beside him | once the disk leaves the boss (1.2 s after it spawns; heading unknown before) | ranged step sideways 8.5 yd; melee around the boss at their distance | ~0.5 s after it moves; a melee at 21.6 yd has ~2.4 s | the tank stood on the boss (no time; reached 100 Sound); a step out of one lane often entered the next of the four; melee cut through the boss centre when the tank moved |
| Sonic Breath, +20/s, 15° cone | the kiter; anyone the beam sweeps | yes (boss cast + Tracking Flames) | the kiter circles; others step behind the beam or run ahead | from the cast (2 s before the first tick) | run-ahead and the kite crossed disk lanes; melee walking through the centre took ticks |
| Fire patch, +5/s per patch, 3 yd | everyone near a Searing Flame patch or a Roaring Flame trail | yes | radial exit from the nearest patch | next decision; first tick 1 s after spawn | a trail is a band of overlapping patches: the radial exit went along it (ping-pong); slots and walks back to them crossed trails |
| Sonar Bomb, +20, 6 yd | whoever stands at the marker 2.5 s after it appears | yes (marker 49623) | radial exit from the nearest marker | next decision (~1 s to leave) | three markers per wave land near each other: the exit stepped into the next zone |
| Roaring Flame Breath, +3/0.5 s, 5 yd | the kiter; bystanders on its path | yes | bystanders keep 9 yd from the flame | at 9 yd | at 10 stacks the flame runs 15 yd/s: a step straight away from it is along its path |
| Redirected flame (to the struck shield) | relays and spread players on its line | yes | as above | as above | same; the runner (next kiter) ran into old trails on the ring |

Per role: the **tank** had no dodge room on the ground; **melee** stayed in range but crossed
lanes and the centre; **ranged/healers** ping-ponged between hazards; the **gong relays** walked
through trails to their stations and the redirect runner through trails on the ring; the **kiter**
is the kite path of the section above; the **Ice Block mage** waits for the flame on purpose.

**Fix** (`BotAtramedesDodge.h`, lawful native movement only):
- *One hazard field per bot and snapshot:* bomb zones (7.5 yd), fire patches (4.5 yd), every moving
  Sonar Pulse lane (7.5 yd, from behind the disk to 60 yd ahead), an unmoved disk's footprint, the
  Reverberating Flame and 2.5 s of its path (toward the player it chases, or during a redirect toward
  the struck shield), and the Sonic Breath band (the cone plus 10°).
- *Shortest safe step:* an exit keeps its own point when that point clears the whole field (all
  single-hazard behaviour is unchanged); otherwise it takes the nearest clear point on the hall
  floor, pricing fire crossed on the way (12 yd per second in fire), bomb zones crossed (15 yd) and a
  walk that meets a moving disk (30 yd, disks at 7 yd/s). Melee and the tank dodge on the ring
  17.6–21.6 yd from the boss (still in melee range, user raid experience 2026-09-25), air relays
  within click reach of their own shield.
- *Tank at maximum melee range:* once Atramedes stands at the anchor, the tank backs out to the melee
  slot radius (21.6 yd) along its bearing from him; he stays put.
- *Melee walk around the boss* to their slot (steps of at most 40° on the slot circle), never
  through his centre where the lanes and the beam start.
- *Fire-free ground slots:* melee slots, the ranged arc and the tank's spot move along their circle
  off Searing Flame patches.
- *Detours:* formation walks (air spread, relay stations, ground slots) go around fire trails and
  bomb zones, gaining at least 1.5 yd a step (no back and forth); with no detour a bot standing
  clear holds. The gong approach and the chased kiter's walk to a shield take the least-cost step.
- *Redirect runner:* detours around trails; when none exists it waits clear of fire, never closer
  to the flame; standing in fire, the least-cost step out.
- *Sonic Breath:* the kite and the run-ahead keep their direction but bend their radius and stride
  around disk lanes (time-aware) and patches; a run-ahead still far from the sweep may wait out a
  disk. The beam exit resolves against lanes and fire too.
- *Flame:* bystanders leave the flame's path, not only its position.

**Replay metric** (`tests/test_atramedes_raid_sound.py`, production strategy; before = the same
program compiled against the headers before this fix). Ground: 12 whole first ground phases
(seeds 1–12, native disks every 11 s from 14.5 s, Sonic Breaths at 24 and 66 s, Searing Flame at
46 s with its patches until the gong). Air: 60 first and 60 second air phases (seeds 1–3, every
first target, flame spawn 7 s or 3 s after liftoff, Sonar Bombs and fire trails, mobility
published). Sound gained from hazards per player per phase (the kiter's Sound while chased counts
under "kiter"), mean / max:

| Phase | Tank | Melee | Ranged | Healers | Gong relays | Ice Block mage | Kiter | All roles |
|---|---|---|---|---|---|---|---|---|
| Ground, before | 15.1 / 106 | 6.1 / 35 | 2.1 / 12 | 4.3 / 15 | 2.6 / 26 | 1.8 / 6 | 0.2 / 6 | 4.7 / 106 |
| Ground, after | 1.7 / 12 | 0.6 / 3 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0.3 / 6 | 0.3 / 12 |
| Air 1 (7 s), before | 7.8 / 65 | 10.8 / 70 | 14.1 / 81 | 12.0 / 48 | 2.1 / 45 | 12.6 / 40 | 4.5 / 23 | 9.8 / 81 |
| Air 1 (7 s), after | 0.3 / 3 | 0.2 / 3 | 0.3 / 3 | 0.3 / 3 | 0.7 / 20 | 2.4 / 6 | 5.0 / 31 | 0.6 / 20 |
| Air 1 (3 s), before | 5.0 / 23 | 8.6 / 65 | 9.6 / 105 | 10.0 / 65 | 7.7 / 35 | 4.6 / 25 | 2.7 / 25 | 8.2 / 105 |
| Air 1 (3 s), after | 0.3 / 3 | 0.2 / 3 | 0.3 / 3 | 0.3 / 3 | 0.2 / 3 | 1.4 / 5 | 2.8 / 25 | 0.4 / 5 |
| Air 2 (7 s), before | 5.1 / 23 | 10.9 / 71 | 12.1 / 87 | 11.0 / 63 | 13.0 / 55 | 18.3 / 65 | 5.2 / 35 | 11.7 / 87 |
| Air 2 (7 s), after | 0.3 / 3 | 0.3 / 3 | 0.3 / 3 | 0.3 / 3 | 1.1 / 25 | 1.3 / 10 | 3.1 / 20 | 0.6 / 25 |
| Air 2 (3 s), before | 4.7 / 23 | 7.8 / 73 | 8.4 / 65 | 9.5 / 60 | 16.5 / 76 | 11.6 / 55 | 8.9 / 68 | 10.1 / 76 |
| Air 2 (3 s), after | 0.7 / 12 | 0.2 / 3 | 0.3 / 3 | 0.5 / 3 | 1.8 / 23 | 1.2 / 10 | 8.4 / 55 | 0.7 / 23 |

By source per phase (all players): ground Sonar Pulse 33.5 → 4.3, Sonic Breath 13.3 → 0, fire
2.5 → 1.3; air bystanders: bombs 21–53 → 0–1.3, fire 52–59 → 0–2.8, breath 5.7–10.6 → 2.1–4.2.

*Cost:* seconds moved per player per phase: ground melee 29.8 → 34.0 (dodging around the boss;
out of melee range 1.7% → 1.8% of the phase), ranged 18.0 → 17.3, healers 19.7 → 18.3, tank 11.5 →
11.4; air everyone moves less (ranged 16.7–18.5 → 10.5–13.9 s, healers 13.1–15.1 → 9.2–10.0 s),
because no exit steps into the next hazard.

*Negative control:* the same ground phases with the bots' exits ignored give 42.5 Sound per
player (disks 387 Sound per phase), so the harness bites; the rule tests each have a no-hazard or
single-hazard control that keeps the old exit.

**Kiter Sound bound replay** (`tests/test_atramedes_kiter_sound_bound.py`, phases above 10 of 29 or
87; before -> after): mobility with the 3 s spawn, second phase 1 -> 0; ground Sound carried, 3 s,
second phase 16 -> 13; bombs and fire, 7 s spawn 14 -> 10 (first) and 16 -> 3 (second); 3 s spawn
6 -> 5 and 19 -> 16. Over twelve seeds (348 phases each) 41/59/60/53 -> 38/48/44/18. Every
zero-bound scenario stays at zero. The ratchets in the test now hold these values.

**Shield reserve floor.** The next-Searing-Flame reserve assumed a 150k raid DPS measured on
Magmaw at ~409 gear. The roster now wears tier-11 gear (~359): the seven matched 10N references
(`atramedes_wcl_dps_reference_v1.json`, raid item level 354–360) have whole-fight raid DPS
131,217–157,669 (median 145,174), and the actor targets sum to about 155k (the 0.95 pass line about
147k). The floor is now 130,000, the slowest matched kill rounded down, so a slower T11 raid does
not release the reserve too early; the thresholds follow (82 s: 40.8%, 51 s: 25.4%;
`ReserveRaidDpsFloor` in `BotAtramedesGongPolicy.h`). A lower floor only keeps the reserve longer.
It is one composition-independent constant: every BWD 10N scenario uses the one canonical T11
composition, and `tests/test_atramedes_raid_sound.py` fails when a matched reference drops below it.

**Still open.** A disk's heading is unknown for its first 1.2 s at the boss, so melee and the tank
still take an occasional tick (tank mean 1.7 per ground phase). Bystanders still take a breath tick
now and then from a 15 yd/s flame. The kiter's own Sound is the bound's business (the stress cases
above). The replay's flame patches tick +5 each and the spawn burst 78555 is not modelled. Live
evidence per role is not yet exported by the server (only the kiter's chase counters are).

## Round 3 review fixes (2026-09-30)

- A pre-liftoff Sound reset that the air-strike budget allows now outranks a refused
  elective high-Sound gong (`pre_liftoff_sound_reset`), so the first kiter starts within the bound.
- The redirected-flame prediction resolves the struck shield through its runtime identity (GUID in
  the snapshot, else its entry, excluding shields still standing), never by comparing a GUID counter
  with a database spawn id.
- Observation coverage: a gap leaving an engaged phase is checked whatever follows (boss absent,
  another route); over 5 s after a ground sample or 1 s after an air sample the attempt exports
  `complete:false`. `max_sample_gap_ms` includes that gap.
- Ice Block is strictly once per fight: an attempt-scoped guard (cohort, attempt id; not the
  combat-log lifecycle, so `.botexp start` on an engaged cohort keeps it; `BotAtramedesIceBlockGuard.h`)
  records the first Ice Block while Atramedes is engaged; later plays (rescue strike, bait, the chased
  mage's own block) are refused even after the 300 s cooldown. A wipe (Atramedes out of combat, or the
  wipe generation moving) or a new attempt id clears it. The chased mage relies on its block only if it
  is castable now or ready before the predicted flame contact (0.25 s margin); otherwise the gong rescue
  goes ahead.
- Ground circling and the Sonic Breath run-ahead use one safe-segment predicate (clear end, arena
  floor, no disk met, no fire or bomb crossed).
- Observation blocks export `first_observed_at_ms`/`last_observed_at_ms`; the harness requires them
  to cover the judged boss window within the observer's gap bound.

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
