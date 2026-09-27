# Maloriak — research contract v3 (2026-09-25)

Scope: Cataclysm Classic 4.4.2-labelled behavior for 10-player Normal (10N), 10-player
Heroic (10H), 25-player Normal (25N) and 25-player Heroic (25H). The bot program runs the
4.3.4 client and server with 4.4.2 reference tuning
(`experiments/configs/cata_raid_acceptance_policy_v1.json`). State: `fidelity_blocked`. Nothing
here is live-validated. Where the native script and a source disagree, both are kept and the
bot does not treat the disputed value as exact.

Machine-readable packet: `experiments/configs/cata_raid_encounters/blackwing_descent/maloriak_v1.json`
(contract) and `maloriak_ledger_v1.json` (values, sources, research completion). WCL references
(fight 34 extracted): `maloriak_wcl_dps_reference_v1.json`, `maloriak_wcl_cast_timelines_v1.json`. Finish line:
`experiments/configs/raid_targets/blackwing_descent_10n_maloriak.json`.

## Contract

- Interrupt every Arcane Storm.
- Tactic source: the user's first-hand raid tactic (2026-09-26) is authoritative and replaces
  the guides where they differ (ledger `user_raid_experience_20260926`, conflicts
  `release_aberrations_interrupts` and `remedy_during_add_switch`).
- Remedy: above 30%, and again once the chambers are empty and every Aberration is dead, remove
  it at once (Spellsteal, then Purge, Tranquilizing Shot, priest Dispel Magic). From 30% until
  then nobody removes it: his self-heal offsets the tank's damage and keeps him above 25%.
- Release Aberrations: never interrupted. Every release goes through (10N holds 18 in the
  chambers); kill each Aberration as it comes, one at a time, with no wait for Green (a pack in
  the slime window simply dies faster). The guides differ: current guidance interrupts when
  about nine are up, the historical guide interrupts the first release of a cycle. Human raids
  usually reach Green before 30%; bot damage reaches 30% sooner, with the reserve still full.
- Threat on adds: the hunter's Misdirection and the rogue's Tricks of the Trade go on the Feral
  off-tank while their own target is a loose Aberration (armed during the release cast, they
  would carry boss attacks and boss threat to the Feral). The shaman Frost Shocks a loose
  Aberration (nearest Maloriak first), else one of the kited pack; never a frozen one. No slow
  totem (Earthbind would replace the earth buff totem). The hunter lays traps at its feet (their
  range is self; no Trap Launcher): Freeze Trap for an Aberration running at it that nobody is
  hitting (not the burn target, not the off-tank's pickup, no player DoT on it; damage breaks
  it), Ice Trap otherwise, and Ice Trap at the kite loop's far corner for the kited pack
  (outside Red). A frozen Aberration is left asleep until nothing else is left.
- The Feral kites: holding Aberrations in phase one it walks a small loop on the flank away
  from Maloriak, one waypoint at a time and only when the mobile pack on it is within 8 yards,
  so it stays one controlled group. Every path it walks (joining, each leg, the diagonal left by
  a dropped corner) stays 20 yards or more from Maloriak and clear of Absolute Zero, jet fire
  and Flash Freeze blocks; a loop with fewer than three usable waypoints is not used. When no
  clear path exists, while the pack catches up, or while a rooted Aberration stands beside it,
  it holds explicitly where it stands (a renewed hold keeps the kite's movement); a rooted one
  farther behind is left to rejoin. It keeps Nature's Grasp up when the druid knows it.
- While Aberrations are up in phase one the ranged and healers' back fan leans to the kite's
  side (20 to 100 degrees off the rear, 20 yards out, 5.6 yards apart): every fan slot reaches
  every kite waypoint within 40 yards, and the shaman takes the flank end, within Frost Shock's
  25 yards of the loop; Frost Shock goes only to an Aberration in its range. The fan follows the
  loop the Feral is actually on (or can join on a clear path); when it holds elsewhere, the fan
  follows where it holds. Kite paths also keep clear of the cauldron (its 9.5-yard radius plus a
  margin, so native path smoothing cannot cut into it). The hunter walks to a corner of that
  loop for the pack's Ice Trap (the farthest from Maloriak that keeps 5 yards from every other
  player, the Feral and its pack included, and 8 yards from a Biting Chill target) and holds
  that post only while the spot it actually stands on keeps the same clearances (otherwise it
  steps onto the corner); with no such corner the post is suspended. A chilled hunter keeps its isolation.
- Vial order. Normal: random Red or Blue, then the other color, then Green. Heroic: Black first
  and again after each Green. Two independent sources say so verbatim: "On normal difficulty, he
  will either start with Red Vial or Blue Vial, followed by whichever of those he did not use
  first; after those two he will use Green Vial." (Icy Veins, 2024) and "The Red and Blue phases
  can come in any order" (Icy Veins, 2012).
- Red: stand in front of the boss, inside the Scorching Blast cone, which splits its damage among
  everyone hit. A Consuming Flames target leaves the cone. Positioning does not follow the
  offensive target: ranged damage dealers and healers keep the cone stack, the Consuming Flames
  exit and the Blue spread while they burn Aberrations. Melee damage dealers on an Aberration
  fight it at the off-tank, so the cone is shared by the main tank, the healers and the ranged.
- Blue: spread at least 5 yards apart. Ranged damage dealers break Flash Freeze blocks; everyone
  else stays out of the 5-yard shatter; a Biting Chill target steps away from allies.
- Green: Debilitating Slime doubles damage taken for 15 s.
- Aberrations are tanked away from Maloriak, a controlled kite rather than a spread. Growth
  Catalyst reaches 10 yards and buffs Maloriak too.
- At 30%, if Aberrations are left (in the chambers, counted natively from the sleeping,
  unselectable chamber creatures, or loose): every damage dealer (and healer) stops damaging
  Maloriak and the damage dealers kill the Aberrations one at a time, the Feral holding the rest,
  until the chambers are empty and every released one is dead, so phase two starts with only
  the two Prime Subjects. With nothing left at 30% there is no pause. The Blood DK main tank
  keeps full damage (Death Strike keeps him healthy). The switch is a cohort latch: Remedy heals
  him back above 30% without ending it; it ends when the adds are gone, at phase two, after
  180 s (logged once with his health, the reserve and the loose count) or on a wipe. No DoT is
  started or refreshed on the boss; DoTs already ticking and projectiles already in flight land,
  with whatever aura they carry (a player cannot recall either). For every bot but the main tank the boss is restricted at
  the native edge every tick: no cast, DoT or area spell on him, and the bot's pet, guardians
  and totems turn to the adds (the totem-owned Greater Fire Elemental skips Fire Nova and Fire
  Shield while he is in their radius). A cast still running that would reach him (aimed at him,
  or a Blizzard, Hurricane or Hellfire over him) is stopped, the pet is sent back, and offensive
  cooldowns, guardian summons, combat potions and raid haste wait for phase two. One Arcane Storm
  interrupt or taunt on him stays allowed per cast. Between releases the damage dealers wait off
  the boss.
- Phase two (25%–0%): burn the boss. The off-tank holds the Prime Subjects (and any Aberration
  left if the switch could not empty the chambers). The raid stays out of the front. The tank
  steps out of Magma Jets. Everyone
  avoids Absolute Zero spheres and jet fire. Use raid haste here: the nuke phase is a DPS race.

## Mode matrix

| Mode | Vial order | Adds and roles | Phase two and deltas |
|---|---|---|---|
| 10N | Random Red/Blue, other, Green | 3 Aberrations per successful Release, 18 in reserve; one off-tank | 25%; two Prime Subjects; no Black |
| 25N | same | same reserve; two off-tanks are easier | same |
| 10H | Black, random Red/Blue, other, Green | five Vile Swills in Black; stronger adds | Black repeats after each Green; Prime Subject Fixate reported |
| 25H | same as 10H | two off-tanks recommended | same as 10H |

Native health (`gt_npc_total_hp_exp3[88]` 85,892 × HealthModifier):

| Creature | 10N | 25N | 10H | 25H |
|---|---|---|---|---|
| Maloriak | 19,755,160 | 68,713,600 | 34,631,654 | 121,210,790 |
| Aberration | 240,498 | 858,920 | 584,066 | 2,128,570 |
| Prime Subject | 8,589,200 | 30,062,200 | 12,024,880 | 42,087,080 |

The heroic values match both guides. The normal values match the 2012 Icy Veins page (19.8M and
69.3M), not the 4.4.2 Wowhead page (24.7M and 86.6M). This conflict stays unresolved until a WCL
health derivation is available.

## Client values (4.4.2.59185, difficulty rows)

Extract: ledger `source_catalog.client_442_59185_maloriak_rows_20260925`. The ledger records the
command and the upstream table hashes.

| Spell | Values |
|---|---|
| Arcane Storm 77896 → 77908 | 0.5 s cast, 6 s channel, 1 s ticks in 80 yd: 11,309 (normal), 47,124 (heroic) |
| Remedy 77912 | 10 s self heal 25,000 / 75,000 / 50,000 / 150,000 per second (10N/25N/10H/25H) plus mana |
| Release Aberrations 77569 | 1.5 s cast; Release All Minions 77991 1.5 s |
| Scorching Blast 77679 | 60 yd, 70-degree cone, 400k / 1M / 850k / 2.7M split among targets (`spell_custom_attr` 0x8) |
| Consuming Flames 77786 | 10 s, 4,500 / 9,000 / 7,500 / 13,500 per second; the native aura script adds 50% of magic damage taken |
| Biting Chill 77760 → 77763 | 10 s, 5,000 (normal) / 10,000 (heroic) per second to allies within 3 yd |
| Flash Freeze 77699 | 30 s stun and 56,549 / 56,549 / 84,824 / 117,811 frost to enemies within 5 yd of the target; the block has 64,387 HP (10N) |
| Shatter 77715 | 45,239 (normal) / 84,824 (heroic) within 5 yd |
| Debilitating Slime 77615 | +100% damage taken, 15 s, the whole room; the cauldron knocks back within 30 yd |
| Growth Catalyst 77987 | area aura 10 yd: +10% (normal) / +20% (heroic) damage dealt, −20% damage taken |
| Magma Jets 78194 | 2 s cast; a line of Magma Jet 41901 every 3 yd along the boss facing: 37,999 (10N) / 70,686 (heroic) and a knockback, then 18,849 / 37,699 every 0.5 s in 3 yd for 20 s |
| Acid Nova 78225 | 10 s, 7,500 (normal) / 15,000 (heroic) per second on everyone |
| Absolute Zero 78223 | sphere 41961 arms in 3 s, triggers within 3 yd, 47,124 / 94,249 frost within 5 yd and a knockback |
| Engulfing Darkness 92754 | heroic: 3 s cast, 8 s channel, 20-degree cone, 15,000 / 25,000 per tick, −100% healing |

Player interrupts (client): Kick, Rebuke, Pummel and Mind Freeze 5 yd / 10 s; Wind Shear 25 yd / 15 s;
Counterspell 40 yd / 24 s; Skull Bash 13 yd / 60 s base. Dispels: Spellsteal 40 yd, Purge 30 yd, Dispel
Magic 30 yd, Tranquilizing Shot 35 yd.

The runtime 4.3.4 DBC matches these rows. Of 102 difficulty-0 SpellEffect rows, the only
Maloriak differences are radius indices: the 50,000-yd self radii of the vial throws and imbues,
and Growth Catalyst's second radius (both builds keep its 10-yd first radius). Difficulty
variants from SpellDifficulty.dbc: Remedy 77912 becomes 92965 / 92966 / 92967 (25N / 10H / 25H),
Scorching Blast 92968-92970, Consuming Flames 92971-92973, Flash Freeze 92978-92980. Arcane Storm
77896, Release Aberrations 77569 and Magma Jets 78194 have none.

## Native script audit (repository)

Files: `boss_maloriak.cpp` (creature AIs), `boss_maloriak_spells.cpp` (spell scripts, split out of
the 1,293-line file), `boss_maloriak_shared.h` (identifiers and the vial-order helper).
`AddSC_boss_maloriak` registers the spell scripts, so the Eastern Kingdoms loader is unchanged.
Classification: `source_present_ready_for_diagnostic_shard`, still `fidelity_blocked`.

Repaired:

1. **The first normal vial was always Blue.** The constructor started from Red, and the
   transition from Red is Blue. It now starts at the cycle start, so the first vial is the random
   Red/Blue branch both guides describe. `SelectNextVial` and `AdvanceUsedVials` reproduce the
   original transitions exactly and are replay-tested. The counters could not survive a wipe on
   this spawn: Maloriak (250112) has no spawn_group row, so it is in the Default Group without
   compatibility mode, and `_DespawnAtEvade` respawns a new Creature with a new AI. `Reset()`
   restarts the cycle and the release reserve anyway, for a compatibility-mode spawn, where
   `Creature::Respawn` only calls `Reset()` on the same AI.
2. **Phase two leaked vial events.** The walk, drink, imbue, green slime and attack events carry no
   phase mask. A 25% crossing during a cauldron visit could still re-apply a colored imbue after
   Drink All Bottles, or slime the room in the nuke phase. Phase two now cancels those events at
   the 25% crossing, stops a cauldron walk already in progress and ignores late cauldron arrivals.
3. **Observation.** `GetTimeUntilEncounterMechanic` publishes the native EventMap time to Arcane
   Storm, Release Aberrations, Remedy, the Red and Blue abilities, the phase-two abilities and the
   next vial. It returns 0 while the cast runs. It is read-only (the shared
   `TimeUntilScheduledEvent` helper, replayed against the production EventMap). Wiring it into the
   blackboard is a coordinator patch.

Applied in c0efb93a61: `SpellMgrCorrectionsPart04.cpp` used to assign Biting Chill EFFECT_0 `TargetA`
twice. The second assignment now writes `TargetB`, as intended.

Open native fidelity items (recorded, not changed):

- **Biting Chill targets.** The script picks a random target within 60 yd, but the spell's cast
  range is 10 yd, so a ranged pick fails and only melee-range picks land. The 2012 guide says one
  melee-range target in 10-man and two in 25-man. Wowhead says three random raid members. Count
  the live targets before changing the filter.
- **Shadow Imbued and taunts (heroic).** Icy Veins says "Maloriak will gain Shadow Imbued, making
  him immune to taunts." The native aura (92716, mechanic mask 1614) grants no taunt immunity. The
  bot follows the guide and never taunts under it.

Left unchanged (unresolved; no authoritative value):

- the Remedy heal ramp;
- the berserk timer (6 min current wording, 7 min normal and 12 min heroic historically);
- the Prime Subject Rend;
- Debilitating Slime removing Growth Catalyst (claimed by both Icy Veins pages; no client effect expresses it);
- heroic Fixate;
- Release Aberrations continuing to be cast after the reserve is empty.

## Laboratory route and the round-1 plateau

The round-1 shard started on Drakeadon Mongrel 250119. That point was also the regroup and the
lab-trash anchor. The Mongrel follows the patrol of Drakonid Slayer 250117 (formation with
250118/250119).

The patrol was engaged at the regroup. The future-encounter guard then forbade attacking entry
42803, the next node's target, and the regroup could never complete. The cohort killed the
unlisted Slayer, then stayed in combat with the guarded Mongrels until the 180 s plateau
(evidence: `round1_two_shard_proof_20260925`).

A second blocker waited behind it. Adaptive owners suppress the generic route objective, and only
adaptive Magmaw records native boss engagement. A native Maloriak kill would therefore be rejected
by the route (`ValidationRouteEngagedBossGuid` empty).

Proposed rows, checked on the pinned 669 navmesh:

- regroup and start at the laboratory junction (-110.0, -335.0, 67.73). It is 64 yd from the patrol
  anchor, 42 yd from Maimgor and on the natural path from the lower-wing elevator;
- lab trash anchored on the patrol leader (-55.97, -299.45, 63.66), pack entries 42802 and 42803,
  cluster radius 40 yd (the southern half of the patrol, away from Ivoroc);
- the boss row unchanged.

Maimgor 250109 hovers 34-37 yd from both approach paths and is not pulled. M applied the rows
(2def03047e). The kill-credit observer is a Maloriak candidate
(`world.validation_route_maloriak_observation`, reasons `maloriak_route_observation_*`) submitted
by `SubmitMaloriakKernelCandidates`, so adaptive Magmaw's observer stays untouched.

## Bot tactic (`Encounters/Maloriak/BotAdaptiveMaloriakStrategy.h`)

Duties are chosen by capability from the observed roster, never by roster slot.

| Duty | Canonical 10N owner | Rule |
|---|---|---|
| Main tank | Blood DK | lease, else Blood DK > Prot Paladin > Prot Warrior > Feral; taunts back an aggressive boss, not under Shadow Imbued; in phase one holds him at the tank spot (-105.8, -449.0), 36 yd north of the cauldron |
| Off-tank | Feral (bear) | picks up and taunts loose Aberrations, Prime Subjects and Vile Swills; holds them at an add spot ≥ 20 yd from the boss |
| Arcane Storm | Retribution (lowest-GUID melee 10 s interrupt) | the owner at the cast; the second short interrupter after 0.8 s of channel; everyone capable after 2 s |
| Release Aberrations | Rogue and Elemental Shaman | interrupt only when six or more are loose (heroic Dark: while Vile Swills live); never the Arcane Storm owner (with one short interrupter the long pool takes it); the dispatch recounts the Aberrations natively before interrupting. An admitted release is published as an interrupt veto, keyed by map, instance and boss GUID, that the kernel profile resolver honours (in round 3 rotation interrupts cut every release); the legacy SelectCombatSpell and BotController paths do not check it |
| Remedy | Mage (Spellsteal) | Shaman Purge after 1.5 s, Hunter and Priest after 3 s; an assigned purger or interrupter stops its own hard cast first, only when the duty spell passes every other cast gate (sight, range, cooldown, power, control), and a healer keeps a heal while anyone is below 50% |
| Raid haste | Elemental Shaman (else a Mage) | in phase two |
| Flash Freeze | ranged damage dealers | break the nearest block; others leave the 5-yard shatter |

Formations are logical anchors for native pathing, computed from the boss and main-tank frame and
clamped to the room floor. Maloriak drinks at the cauldron's north rim at every vial; the cauldron
blocks line of sight across the back half of the room (round 4: both healers healed nothing for
60 s from behind it), so the main tank leads him back to the tank spot, and holds it while he is
passive or out of melee reach instead of chasing him to the rim (but never while he is aggressive on
someone else: the tank taunts first, Dark Command reaches 30 yd). Every slot, and every ranged place
a player keeps, must see him past the cauldron (9.5 yd line-of-sight radius around -105.75,
-485.39, 0.5 yd over the model's half-extent; applied while he is outside it). Shifted ranged slots
are resolved in group order (40-degree shift, then the whole back arc, then a last-resort point in
sight 2.5 yd from those already placed) so they keep the 5-yard spread. The cauldron shifts melee
slots but never holds melee offense; only hazards do.

A raider who dies during the fight stays dead (battle-res eligible) until the encounter resets or
the raid wipes: the boss row declares `boss_recovery_policy: native_full_wipe_only`. Released
mid-fight, a ghost would reach the portal while the encounter is in progress and be resurrected
outside the raid (round 4, `validation_active_instance_drift`).

- pre-pull: the entrance line about 28 yd from the boss, with offense held until the pull tank
  engages. The pull tank waits for the play-mode pull timer, for nobody dead, for everyone at 70%
  health or more, and for every non-tank within 15 yd of its slot. Every holder reports that
  gate's reason, and only a satisfied gate reports `prepull_pull_owner_wait`, so the shared
  25-second pre-pot waits for the pull gate (round 3). A move that starts outside the laboratory
  (the corridor, the lower-wing elevator landing after a runback) is travel on the route lane,
  not a same-level mechanic step;
- Red: rows in front inside the cone, melee at ±25° beside the tank, Consuming Flames targets
  behind;
- Blue, Dark and phase two: a fan behind the boss at 18 yd, 40° apart, and melee behind at ±50°
  (a third melee straight behind at 8 yd). A chilled player keeps its isolation position;
- Green and the vial transitions: no formation.

Hazards preempt formations: Absolute Zero (7 yd) and jet fire (4.5 yd), each exiting from the
nearest source and rotating the exit until it clears every other sphere and fire; the tank's
Magma Jets sidestep (8 yd perpendicular); shatter clearance; and Biting Chill isolation (not for
tanks, who hold the boss and the adds).

The Magma Jets sidestep point comes from the boss facing, the tank's projection on the jet line
and the side it already stands on. None of these change while the tank sidesteps, so every tick of
one cast proposes the same point.

A formation slot never sits inside a hazard. Each hazard gets a clearance of its trigger radius
plus 2 yd: Absolute Zero 9 yd, jet fire 6.5 yd, an ice block 9 yd. A slot inside a clearance
shifts along its arc to the nearest clear point:

- the Red cone within ±30° of the front; the back arc outside the front ±70°;
- ranged may also move 5 or 10 yd out or 5 yd in, and keep 5 yd from the other ranged slots.

When no ring point is clear, a melee damage dealer holds offense (`melee_ring_hazard_hold`)
rather than chasing back into the hazard. So a bot that just evaded is never sent back.

The add spot stays on the side the off-tank holds until the boss comes within 15 yd of it
(20 yd to pick a side).

One spot healer, the lowest-GUID healer, focuses frozen, Consuming Flames and Biting Chill players
below 85%. It yields to the ordinary lowest-health scan while a tank is under 50%, or when another
player is more than 10 points lower.

Damage dealers burn Aberrations during the slime window, when six are loose (nine while the native
timer shows Green within 15 s), or below 30% boss health. In phase two they stay on the boss.

## Encounter damage fidelity

Every creature template runs at DamageModifier 1 (upstream reset
`sql/updates/world/4.3.4/2025_06_18_06_world.sql`). Native melee rolls at modifier 1:

- Maloriak 10N (1.5 s swing): 4,553-6,764;
- Maloriak 25N/10H/25H (2.0 s swing): 6,071-9,019;
- Aberration: 5,954-8,902;
- Prime Subject: 5,966-8,914;
- Vile Swill: 6,027-8,975.

Historically the 10N melee was about 25k per boss hit and 5k per Aberration hit, and about 20k
per Prime Subject hit. The boss 10N value is now calibrated (DamageModifier 9.5, promoted to `sql/custom/world`; see finding
7 below). The other boss modes and the adds stay `open`, and the non-melee helpers are
`not_applicable`.

## Sources

1. Wowhead, "Maloriak Strategy Guide — Blackwing Descent Raid Cataclysm Classic", Beanna, updated
   2024-06-04, Patch 4.4.2: <https://www.wowhead.com/cata/guide/raids/blackwing-descent/maloriak-strategy>.
   Accessed 2026-08-11; not re-read on 2026-09-25 (HTTP 403).
2. Icy Veins, "Maloriak Encounter Guide: Strategy, Abilities, Loot — Cataclysm Classic", Abide,
   published 2024-05-17, updated 2024-07-29:
   <https://www.icy-veins.com/cataclysm-classic/maloriak-encounter-guide-strategy-abilities-loot>.
   Re-read 2026-09-25.
3. Icy Veins, "Maloriak Detailed Strategy Guide (Heroic Mode included)", Damien, published
   2011-08-26, updated 2012-10-08: <https://www.icy-veins.com/wow/maloriak-strategy-guide-normal-heroic>.
   Historical; re-read 2026-09-25.
4. Client rows 4.4.2.59185 (wago.tools DB2 exports), extracted 2026-09-25.
5. Repository sources:
   - `boss_maloriak*.{cpp,h}`, `blackwing_descent.h`, `instance_blackwing_descent.cpp` and
     `SpellMgrCorrectionsPart04.cpp`;
   - the TDB 434.22011 dump, the gt tables in `sql/updates/world/4.3.4/2025_06_07_0{0,1}_world.sql`
     and the historical script bindings;
   - the pinned 669 navmesh and the round-1 proof archive.
6. Warcraft Logs was behind a human-verification gate on 2026-09-25 and on agent-browser retries on
   2026-09-27. It was then read through GPT-6 Astra in the user's verified Chrome session:
   report MxFq7TRbvnjGY1hJ fight 34 (Maloriak 10N kill, 2024-10-28, 125.1 s). That gave the boss
   melee sample, per-spec DPS (`maloriak_wcl_dps_reference_v1.json`), 818 player casts
   (`maloriak_wcl_cast_timelines_v1.json`) and the Red/Blue/phase-two boss timeline (ledger
   `wcl_10N_boss_timeline_fight34`). The kill has no Green phase. A second kill, VL3fW9wNm2PRJDYt
   fight 13 (2024-10-21, 209.6 s), adds a Guardian tank (who tanked Maloriak, so it is not a matched reference for the
   add-tanking bot Feral, which stays no_reference), two Demonology Warlocks and a Green phase
   (ledger `wcl_10N_boss_timeline_fight13`). Its phase two repeats Magma Jets about every 11.8 s,
   Acid Nova 30.7 s and Absolute Zero 11.3 s. The native script used 6, 20 and 7 s; it now uses the
   WCL values on 10N only (first Absolute Zero 11.3 s). 25N, 10H and 25H keep 6, 20 and 7 s
   and the 8.4 s first Absolute Zero, because only 10N was observed. Remedy keeps being cast in phase two in the log,
   but not natively (open).
7. Maloriak 10N melee: 29 landed swings with U 40,559-63,630 (Scarlet Fever on the boss for all but
   3 of them). Against the native roll 4,553.3-6,764.2 the bounds are 9.41-9.71 with the +1%
   auto-attack bonus. DamageModifier 9.5 is in
   `sql/custom/world/2026_09_27_22_maloriak_damage_modifier.sql` (promoted 2026-09-27; the DB updater applies it at worldserver startup). Aberration and Prime Subject
   stay open because the log does not show their Growth Catalyst stacks.
8. Full-route run r11 (2026-09-27) killed Maloriak natively, but it recorded no Maloriak melee swings
   and was not the Maloriak shard.

## Unresolved (fidelity blockers)

- Maloriak-specific hotfix carryover to the 2025-02-20 cutoff.
- Live vial and ability cadence in all modes; WCL cadence beyond the one 10N kill (Green phase,
  heroic, 25-player).
- Biting Chill target counts (native 60 yd pick vs 10 yd range; guides disagree). The SpellMgr
  target correction is applied (c0efb93a61).
- The Green-phase length: 21 s plus a 15 s transition (2012 guide), the next vial 30 s after the
  15 s slime (2024 guide), or 40 s after the Green imbue (native).
- Normal health (native vs Wowhead 4.4.2) and the enrage timer.
- Heroic Prime Subject Fixate, and Rend (seen in the 10N log; spell id and cadence unknown).
- A live observation of a random first vial, including after a wipe and re-pull.
- A live read-back of the historical script bindings and `spell_custom_attr`.
- Melee calibration of Aberration and Prime Subject (Growth Catalyst stacks unknown) and of every
  25N/10H/25H template. Maloriak 10N: 9.5 staged, awaiting a live +-10% check.
