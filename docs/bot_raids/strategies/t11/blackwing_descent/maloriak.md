# Maloriak — research contract v4 (2026-09-30)

Scope: Cataclysm Classic 4.4.2-labelled behavior for 10-player Normal (10N), 10-player
Heroic (10H), 25-player Normal (25N) and 25-player Heroic (25H). The bot program runs the
4.3.4 client and server with 4.4.2 reference tuning
(`experiments/configs/cata_raid_acceptance_policy_v1.json`). State: `fidelity_blocked` at contract
level; per mode (`fidelity_state_by_mode`) 10N is `accepted` (round 3; the round-3 fix of 2026-09-30
added target-era evidence and a native draw for the Green timers, see "Round-3 fix" below) and 10H,
25N and 25H are `fidelity_blocked`. Nothing here is live-validated; the 10N acceptance observations are in
the ledger. Where the native script and a source disagree, both are kept and the
bot does not treat the disputed value as exact.

Machine-readable packet: `experiments/configs/cata_raid_encounters/blackwing_descent/maloriak_v1.json`
(contract) and `maloriak_ledger_v1.json` (values, sources, research completion). WCL references
(the tier-11 set, round 3): `maloriak_wcl_dps_reference_v1.json`; cast timelines (fight 34):
`maloriak_wcl_cast_timelines_v1.json`. Finish line:
`experiments/configs/raid_targets/blackwing_descent_10n_maloriak.json`.

## Contract

- Interrupt every Arcane Storm.
- Tactic source: the user's first-hand raid tactic (2026-09-26) is authoritative and replaces
  the guides where they differ (ledger `user_raid_experience_20260926`, conflicts
  `release_aberrations_interrupts` and `remedy_during_add_switch`).
- Remedy: above 50%, and again once the chambers are empty and every Aberration is dead, remove
  it at once (Spellsteal, then Purge, Tranquilizing Shot, priest Dispel Magic). From 50% until
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
- At 50% (30% until the user's decision of 2026-09-27, below), if Aberrations are left (in the chambers, counted natively from the sleeping,
  unselectable chamber creatures, or loose): every damage dealer (and healer) stops damaging
  Maloriak and the damage dealers kill the Aberrations one at a time, the Feral holding the rest,
  until the chambers are empty and every released one is dead, so phase two starts with only
  the two Prime Subjects. With nothing left at 50% there is no pause. The Blood DK main tank
  keeps full damage (Death Strike keeps him healthy). The switch is a cohort latch: Remedy heals
  him back above 50% without ending it; it ends when the adds are gone, at phase two, after
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
- User decision (user raid experience 2026-09-27): "Mage should not dispell remedy. If it does
  maybe thats why it gets over. If not stop dps at 50%". Round 1 removed no Remedy during the 30%
  hold: his health samples show one full 250,000 Remedy at 94-104 s inside each hold, and the only
  removal was the Mage's Spellsteal at 46 s, before it. He still reached 25% in 26-32 s because he
  took 38-48k DPS there (Blood DK 23-31k plus DoT and proc tails). So the hold now starts at 50%.
  From 50%, 25 points (4.94M) last about 235 s at the Blood DK's damage less Remedy's 10.4k
  average, and about 130 s even if the tails continued, against a hold of about two minutes.
- Growth Catalyst reaches 10 yards and buffs Maloriak too, so the off-tank never fetches an add
  at his side: an add within 12 yards of him is taunted from a post 15 yards out on the add-spot
  side, and the pack stays there (`BotMaloriakPullPost.h`). In r01 kill 6bf522 eight or nine adds
  stood within 10 yards of him for 25 s of phase two while the Feral fetched adds off the Blood
  DK, and melee hits on him fell to about a fifth.
- A sphere wanders within 10 yards of where it spawned and despawns only when someone triggers
  it. When spheres block every melee ring point (3.5 yards, or the 5-yard outer ring melee also
  use), the main tank walks Maloriak 12 yards away from them and he follows
  (`BotMaloriakSphereDrag.h`). In r01 kill 6bf522 the rogue and the Retribution Paladin landed
  nothing on him for the last 38 and 25 s, from the second sphere on, and no sphere exploded
  (the log has no sphere positions, so the ring block is inferred).

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

- **Biting Chill targets.** The script picked a random target within 60 yd, but the spell's cast
  range is 10 yd, so a ranged pick failed. Fixed on 10N in round 3 (25 WCL casts, all on
  melee-range players): the pick is within 10 yd. 25N/10H/25H keep the 60-yd pick (the 2012 guide
  gives two targets in 25-man).
- **Shadow Imbued and taunts (heroic).** Icy Veins says "Maloriak will gain Shadow Imbued, making
  him immune to taunts." The native aura (92716, mechanic mask 1614) grants no taunt immunity. The
  bot follows the guide and never taunts under it.

Changed in round 3 from 10N WCL evidence (see "Round 3" below): the Remedy heal ramp (10N),
Debilitating Slime removing Growth Catalyst (10N), the berserk timer (10N, 7 min), the Prime
Subject Rend (10N) and the pre-vial opening (10N).

Left unchanged (unresolved; no authoritative value):

- the berserk timer on 25N/10H/25H (7 min normal and 12 min heroic historically, 6 min current wording);
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
| Release Aberrations | nobody | never interrupted (user tactic 2026-09-26). Every phase-one release is published as an interrupt veto, keyed by map, instance and boss GUID, that the kernel profile resolver honours (in an earlier round rotation interrupts cut every release); the legacy SelectCombatSpell and BotController paths do not check it |
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

Damage dealers kill every loose Aberration as it comes, one at a time (the weakest first, a trapped
one last), with no wait for the slime window (user tactic). From the 50% switch until the chambers
are empty only the Blood DK stays on Maloriak. In phase two they stay on the boss.

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
   and the 8.4 s first Absolute Zero, because only 10N was observed. Remedy in phase two: see
   source 9.
7. Maloriak 10N melee: 29 landed swings with U 40,559-63,630 (Scarlet Fever on the boss for all but
   3 of them). Against the native roll 4,553.3-6,764.2 the bounds are 9.41-9.71 with the +1%
   auto-attack bonus. DamageModifier 9.5 is in
   `sql/custom/world/2026_09_27_22_maloriak_damage_modifier.sql` (promoted 2026-09-27; the DB updater applies it at worldserver startup). Aberration and Prime Subject
   stay open because the log does not show their Growth Catalyst stacks.
8. Full-route run r11 (2026-09-27) killed Maloriak natively, but it recorded no Maloriak melee swings
   and was not the Maloriak shard.
9. Round 2 (2026-09-27, same Astra route): six more 10N kills, each picked for one Fire Mage or
   Assassination Rogue with a middle parse (Fire 52/50/50, Assassination 49/57/48). Their
   all-target DPS (View Unfiltered Damage) gives Fire a median of 18,244.2 and Assassination
   20,150.2 (`maloriak_wcl_dps_reference_v1.json`; each kill's `actor_dps` holds only that player,
   so the other specs keep their targets). Their Maloriak cast rows
   (`maloriak_wcl_boss_timelines_round2_v1.json`) with fights 34 and 13: an Arcane Storm before
   the first vial in all eight kills (median 14.3 s); Remedy 17.8-21.0 s (median 19.4) after
   Unstable Mix in all five kills whose phase two lasted that long. Both are now native on 10N
   (Arcane Storm 14.3 s after engage; phase-two Remedy 19.4 s after Unstable Mix, then every 24 s).
   A Release Aberrations (two kills) or Remedy (three kills) before the first vial came only on
   Red openings, with no rule that fits all eight; it stays open.

## Round 3 (2026-09-30): tier-11 references and the 10N claims

Route: GPT-6.1 Sol through the Codex Chrome plugin in the user's Chrome (profile Runiir), one own
tab per task, no verification check. Chrome exited during the first parallel batch (about 10:45
UTC); it was relaunched with the same profile and the rest ran sequentially (ledger source
`wcl_r3_sol_20260930`, which lists the reports).

References. The roster now wears tier-11 phase gear (about 359). The matched set is nine 10N kills
at raid item level 355.6-361.0 (the eight round-2 kills plus QfJR9AZw13G6kzXP fight 14, whose Blood
DK tanked Maloriak: 56 of 57 boss swings). Every reference now carries each gated roster spec it
fields. Targets (median, kills; all View Unfiltered Damage since the round-3 fix): Blood DK 15,364
(6), Survival 22,933 (9), Fire 18,702 (4), Retribution 20,071 (4), Assassination 20,706 (4), Elemental
22,266 (8), Demonology 20,472 (3). The Feral add tank stays exempt.

10N findings (ledger values `*_10N`) and native changes:

- Opening (19 kills; first vial Red 12, Blue 7): an Arcane Storm 10.9-14.9 s after the pull, then
  one action about 3.2 s after the storm begins. Slots at 14.1-16.4 s were Release Aberrations or
  Remedy (4 and 4, never before 15.7 s); slots at 17.4-18.1 s were the vial (7 of 11), Remedy (3) or
  Release (1). Blue openings carry them too, so "Red openings only" is withdrawn. Native 10N: the
  storm time is drawn from the 19 observed values and the same slot rule decides
  (`boss_maloriak_shared.h` `PRE_VIAL_*`). After a Release the throw waits for the 1.5 s cast
  (2.8 s after its begin, 1.6-1.7 s live).
- Vial offsets (six kills): after a Red or Blue imbue Arcane Storm and Release Aberrations come in a
  random order, the first at 11.3 s, then Release at 14.6 s or the storm at 16.2 s; Remedy at
  17.8-21.0 s (Red) or 16.2-19.4 s (Blue); the Green storm begin at 3.6-4.4 s (3.1-6.1 s with the
  post-cutoff kills, see "Round-3 fix"). Native 10N now follows this (the Blue storm came at 6 s).
- Biting Chill (25 casts in nine kills): one pick per cast, always a player in melee range (10
  tanks, 16 melee damage dealers); one cast also caught the player beside the tank (the aura's
  3-yd area). Native 10N now picks within 10 yd, the spell's range (it picked within 60 yd and
  failed on ranged picks). This settles the guide conflict for 10N in favour of the 2012 guide.
- Flash Freeze (16 casts in ten kills, 17 players frozen): always a ranged damage dealer or a
  healer, never a tank or melee, as both guides say. Native 10N now prefers players beyond 10 yd
  of Maloriak (the old pick allowed melee players beside him).
- Health: damage taken minus Remedy healing is 19.76M in two kills (24.92M - 5.16M, 21.26M -
  1.50M). The native 19,755,160 is right; the Wowhead 24.7M is not.
- Remedy ramps: tick n heals 25,000 x n (x 0.9 under a healing debuff), 1.25-1.32M per full cast
  against the flat 250,000 of the client row. Native: `spell_maloriak_remedy` scales every tick; it
  is bound to the 10N id 77912 only (the 25N/10H/25H ids stay flat) by
  `sql/custom/world/2026_09_30_21_maloriak_remedy_ramp.sql` (promoted 2026-09-30). An undispelled Remedy in the
  50% hold now heals about 1.3M.
- Green: Slime Imbued 7.2 s after the throw; the slime lasts 15 s; Arcane Storm 4.0-4.5 s,
  Remedy 7.3-10.9 s and the first Release begin 7.3-10.5 s after the imbue (native 5 / 7.5 / 9 s). The slime
  stripped every Growth Catalyst, the Aberrations' own included; a survivor had it again 5.2 s
  later. Native (10N; the guides say it for every mode, but only 10N was observed):
  `StripGrowthCatalystForSlime` removes it and survivors recast after 5.2 s. The round-3 fix draws
  the 10N storm over 3.1-6.1 s, Remedy over 7.3-14.2 s and the Release begin over 6.415-10.505 s (below).
- Fourth vial: two long kills threw the next vial 41.65 and 41.67 s after Slime Imbued (native 40 s
  + 1.3 s throw). The Green-duration conflict is settled for 10N.
- Enrage: Berserk 64238 at 7:02.6 of a 7:06 kill (cDQCyb4B71Wj9dV8 fight 15; the 2012 guide says 7
  min on normal). Native 10N now casts it 7 min after the pull.
- Prime Subjects cast Rend 78034 on their tank 14.1-14.6 s after landing, then 9.7-16.2 s apart
  (client 1,000 per 3 s per stack, 18 s). Native 10N now does (`boss_maloriak_minions.cpp`); the
  early removals seen live (2.8-4.9 s) are not modelled.
- Spell values (U): Consuming Flames 4,500, Biting Chill 5,000, Scorching Blast 400,000 split
  44,444 over nine players, Arcane Storm 11.8-12.4k (client 11,309), Acid Nova 9,075 (7,500 x
  1.1^2: Growth Catalyst on Maloriak), Magma Jet 38-41k (client 37,999). The client values hold.
- Adds: Aberration 0.802 <= m <= 0.824 (30 rows, Growth Catalyst auras counted per swing, own
  included), set to 0.81; Prime Subject 3.394 <= m <= 3.627 (16 rows), set to 3.5
  (`sql/custom/world/2026_09_30_20_maloriak_add_damage_modifier.sql`, promoted 2026-09-30). The boss's 9.5 read
  1.02x WCL in the round-2 shard kills.
- The live world DB has the historical custom SQL (share-damage attribute on all four Scorching
  Blast ids, every spell script bound).

The helper creature AIs moved to `boss_maloriak_minions.cpp` (the boss file stays well under
1,000 lines); `AddSC_boss_maloriak` registers them, so the loader is unchanged, but CMake must be
reconfigured to pick up the new file.

## Round-3 fix (2026-09-30): unfiltered references and target-era corroboration

Two review findings (GPT-6.1 Sol, round 3) were fixed with a new capture by the same route (ledger
sources `wcl_maloriak_10n_post_cutoff_20260930` and `official_hotfix_audit_20250113_20250220`;
archive `artifacts/cata_raid_program/wcl_round3_maloriak_bwd10n_20260930.tar.gz`).

References (finding 6). Fights 34 and 13 had been read in the default damage-done view, which drops
add damage in phase two, while the bots are scored on all targets. Both were re-read with View
Unfiltered Damage (options=8192), every player row in both views. Fight 34 is unchanged for every DPS
player (only the Blood DKs differ: Greysnout 11,793.0 unfiltered, 11,681.9 default). Fight 13 is
higher unfiltered: Survival 20,488.7 (16,145.0), Retribution 20,432.7 (20,230.9), Demonology 22,112.5
and 18,830.5 (19,314.1 and 17,145.5). All nine references now use the unfiltered view; the default
values stay beside them (`dps_default_view`). The Retribution target moves from 19,969.85 to
20,070.75 and Demonology from 20,060.4 to 20,471.5; the other targets are unchanged, and every gated
spec keeps at least three kills. The add-tanking Blood DK Orageux (fight 13) stays excluded.

Target era (finding 4). The 10N values came from kills dated 2024-10-01 to 2025-01-13, but the
fidelity target is the live game on 2025-02-20. Two checks close that gap:

- Official audit: no Cataclysm Classic hotfix or patch-note entry dated 2025-01-13 to 2025-02-20
  mentions Blackwing Descent, Maloriak, a tier-11 raid, raid boss tuning or a global encounter change.
  The hotfix thread list jumps from 2024-12-11 to 2025-02-21, the hotfix news article has no Cataclysm
  Classic section in that interval, and the 4.4.2 patch notes (2025-02-18) have no tier-11 entry. A
  document audit cannot exclude an unannounced change, so the kills below were compared as well.
- Five 10N kills after the cutoff (2025-03-02 to 2025-05-13, raid item level 383-400, 150-213 s),
  compared only on gear-independent mechanics (timers, target counts, base values):
  - Agree: the opening (storm, then one action about 3.2 s later, or 4.7-4.9 s later as in three
    pre-cutoff kills);
    the Red/Blue offsets and Release timing; imbue to next throw 42.55-42.72 s (one 43.06 s); the
    first vial random (Red 3, Blue 2); Biting Chill one debuffed player per cast at 12.9 / 24.3 / 35.6 s
    after Frost Imbued (one cast spread to four players inside its 3-yd area); every Remedy tick is
    25,000 x tick number x a player healing-debuff factor (72 ticks); the phase-two cadence.
  - Differ: the Arcane Storm after Slime Imbued came 3.66, 4.69, 5.34, 6.18 and 6.57 s after the
    imbue, against 4.13-4.92 s before the cutoff and the native fixed 4.0 s; one Green Remedy came at
    14.15 s (7.3-10.9 s before); one Green Release Aberrations began 6.415 s after the imbue (a canceled Begin
    Cast; 7.3-10.5 s before). Two kills repeat the old timing to 0.01 s, so a uniform timer change
    does not explain it; the cause is not in the capture, and the audit found no change. One Blue phase
    also cast Remedy on the storm's slot and the storm 1.6 s late (the native schedule can do the same).
    Coordinator decision 2026-09-30: model the observed spread (storm Cast 3.66-6.57 s, Remedy up to
    14.15 s, a Release begin from 6.415 s) natively on 10N only, in the time the script fires at.
    `EVENT_ARCANE_STORM` fires when the 0.5 s cast begins, so the post-cutoff Cast rows are converted
    to begins: minus the 0.474-0.531 s begin-to-cast
    offset of 31 round-2 Begin/Cast pairs they are 3.13-6.10 s, and with the pre-cutoff begins (3.6-4.4 s)
    the span is 3.1-6.1 s. `EVENT_REMEDY` fires at the cast of an instant spell (Spell.dbc 0 ms; no Begin
    Cast rows in 22 pre-cutoff casts; the post-cutoff aura application equals the Cast row), so its
    observed values need no shift. `EVENT_RELEASE_ABERRATIONS` fires when the 1.5 s cast begins: a Begin Cast
    row (canceled ones included) is a begin as logged and a Cast row is converted by subtracting the 1.5 s
    cast. The first Release begin after Slime Imbued was 7.299, 7.666, 8.888 (displayed as Canceled) and
    10.505 s before the cutoff and 6.415 (canceled), 8.905, 9.312 (canceled) and 9.701 s after it; the
    6.415 s row, omitted from the first round-3 closure, comes 2.6 s before the old fixed 9 s and outside
    the old 7.7-10.5 s range (which had also left out the 7.299 s round-2 row). After Slime Imbued the native 10N
    script draws the Arcane Storm uniformly over 3.1-6.1 s, Remedy over 7.3-14.2 s and the Release begin
    over 6.415-10.505 s (both bounds are Begin Cast rows, so unrounded). Neither Remedy nor Release is
    drawn before the storm; Release and Remedy overlap in range and may fall in either order (both orders
    occur in the kills; a Remedy due during the Release cast waits for it, because `UpdateAI` runs no event
    while Maloriak casts). The draw is `ScheduleGreenPhaseCasts` in `boss_maloriak_shared.h` (ledger
    `green_release_begins_10N` lists every row); 25N, 10H and 25H keep the fixed 5 / 7.5 / 9 s and draw
    nothing.
  - Not observed after the cutoff: a fourth vial (every kill went to phase two after Green), Berserk
    (the longest kill is 212.8 s), health, melee, spell values, Rend, the Growth Catalyst strip, and
    the roles or positions of the Biting Chill and Flash Freeze targets. These stay bounded by the
    pre-cutoff observations and the audit.

Result: the hotfix-cutoff claim and every other 10N part are closed on this evidence or bounded by the
audit. The live timer claim reopened 10N for the Green timer spread (storm, Remedy and the 6.415 s Release
begin) and closed again once the native script drew the observed ranges (`wcl_maloriak_10n_post_cutoff_20260930`,
`official_hotfix_audit_20250113_20250220`); its remaining modes are 10H, 25N and 25H. The per-mode
research gate accepts 10N again.

## Unresolved (fidelity blockers)

10N: none (accepted 2026-09-30, kept by the round-3 fix). The live timer claim closed for 10N when
the native script drew the Green Arcane Storm (3.1-6.1 s), Remedy (7.3-14.2 s) and Release begin (6.415-10.505 s) over the observed
post-cutoff ranges; the fourth vial is not observed after the cutoff and is bounded by the pre-cutoff
kills and the official audit. The two round-3 migrations (Remedy binding, add DamageModifiers) are promoted to
`sql/custom/world`; the round-3 build reconfigures CMake for `boss_maloriak_minions.cpp`.

10H, 25N and 25H:

- Maloriak-specific hotfix carryover to the 2025-02-20 cutoff (no same-mode observation).
- Vial and ability cadence (no heroic or 25-player WCL kill read).
- Target counts and spell samples (Biting Chill: two in 25-man per the 2012 guide).
- 25N health (native 68.7M, Wowhead 86.6M) and the 25N/10H/25H enrage (historical 7 min normal, 12
  min heroic; none native).
- Heroic Prime Subject Fixate (no spell data) and the Black-first vial after a wipe and re-pull.
- Melee calibration of every 25N/10H/25H template (boss, Aberration, Prime Subject, Vile Swill).
- The Remedy ramp and the slime stripping Growth Catalyst (native on 10N only; the guides say both
  apply in every mode).
