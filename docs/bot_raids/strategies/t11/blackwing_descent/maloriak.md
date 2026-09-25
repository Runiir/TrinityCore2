# Maloriak — research contract v3 (2026-09-25)

Scope: Cataclysm Classic 4.4.2-labelled behavior for 10-player Normal (10N), 10-player
Heroic (10H), 25-player Normal (25N) and 25-player Heroic (25H). The bot program runs the
4.3.4 client and server with 4.4.2 reference tuning
(`experiments/configs/cata_raid_acceptance_policy_v1.json`). State: `fidelity_blocked`. Nothing
here is live-validated. Where the native script and a source disagree, both are kept and the
bot does not treat the disputed value as exact.

Machine-readable packet: `experiments/configs/cata_raid_encounters/blackwing_descent/maloriak_v1.json`
(contract) and `maloriak_ledger_v1.json` (values, sources, research completion). WCL references
(pending): `maloriak_wcl_dps_reference_v1.json`, `maloriak_wcl_cast_timelines_v1.json`. Finish line:
`experiments/configs/raid_targets/blackwing_descent_10n_maloriak.json`.

## Contract

- Interrupt every Arcane Storm.
- Remove every Remedy at once: Spellsteal, Purge, priest Dispel Magic or Tranquilizing Shot.
- Release Aberrations: let it through while few Aberrations are loose. Current guidance is to
  handle about nine at a time; the historical guide releases nine per cycle and interrupts the
  first cast. Interrupt the rest. At 25% Maloriak releases the whole remaining reserve anyway.
- Vial order. Normal: random Red or Blue, then the other color, then Green. Heroic: Black first
  and again after each Green.
- Red: stand in front of the boss, inside the Scorching Blast cone, which splits its damage among
  everyone hit. A Consuming Flames target leaves the cone.
- Blue: spread at least 5 yards apart. Ranged damage dealers break Flash Freeze blocks; everyone
  else stays out of the 5-yard shatter; a Biting Chill target steps away from allies.
- Green: Debilitating Slime doubles damage taken for 15 s. Burn the Aberrations then.
- Aberrations are tanked away from Maloriak. Growth Catalyst reaches 10 yards.
- Phase two (25%–0%): burn the boss. The off-tank holds the Prime Subjects and any remaining
  Aberrations. The raid stays out of the front. The tank steps out of Magma Jets. Everyone
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

## Native script audit (repository)

Files: `boss_maloriak.cpp` (creature AIs), `boss_maloriak_spells.cpp` (spell scripts, split out of
the 1,293-line file), `boss_maloriak_shared.h` (identifiers and the vial-order helper).
`AddSC_boss_maloriak` registers the spell scripts, so the Eastern Kingdoms loader is unchanged.
Classification: `source_present_ready_for_diagnostic_shard`, still `fidelity_blocked`.

Repaired:

1. **Counters survived a wipe.** `Creature::Respawn` reuses the AI and only calls `Reset()`
   (`Creature.cpp` 2052-2053), while `Reset()` never cleared `_currentVial`, `_usedVialsCount` or
   `_releasedAberrationsCount`. The constructor also started from Red, so the first normal vial
   was always Blue. `Reset()` now starts every attempt at the cycle start. `SelectNextVial` and
   `AdvanceUsedVials` reproduce the original order exactly and are replay-tested.
2. **Phase two leaked vial events.** The walk, drink, imbue, green slime and attack events carry no
   phase mask. A 25% crossing during a cauldron visit could still re-apply a colored imbue after
   Drink All Bottles, or slime the room in the nuke phase. Phase two now cancels those events at
   the 25% crossing, stops a cauldron walk already in progress and ignores late cauldron arrivals.
3. **Observation.** `GetTimeUntilEncounterMechanic` publishes the native EventMap time to Arcane
   Storm, Release Aberrations, Remedy, the Red and Blue abilities, the phase-two abilities and the
   next vial. It returns 0 while the cast runs. It is read-only; wiring it into the blackboard is a
   coordinator patch.

Patch requested: `SpellMgrCorrectionsPart04.cpp` assigns Biting Chill EFFECT_0 `TargetA` twice. The
second assignment was meant for `TargetB`.

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

Maimgor 250109 hovers 34-37 yd from both approach paths and is not pulled. Both fixes are patch
requests: the rows go to package M, the route observer to the coordinator.

## Bot tactic (`Encounters/Maloriak/BotAdaptiveMaloriakStrategy.h`)

Duties are chosen by capability from the observed roster, never by roster slot.

| Duty | Canonical 10N owner | Rule |
|---|---|---|
| Main tank | Blood DK | lease, else Blood DK > Prot Paladin > Prot Warrior > Feral; taunts back an aggressive boss, not under Shadow Imbued |
| Off-tank | Feral (bear) | picks up and taunts loose Aberrations, Prime Subjects and Vile Swills; holds them at an add spot ≥ 20 yd from the boss |
| Arcane Storm | Retribution (lowest-GUID melee 10 s interrupt) | the owner at the cast; the second short interrupter after 0.8 s of channel; everyone capable after 2 s |
| Release Aberrations | Rogue and Elemental Shaman | interrupt only when six or more are loose (heroic Dark: while Vile Swills live) |
| Remedy | Mage (Spellsteal) | Shaman Purge after 1.5 s, Hunter and Priest after 3 s |
| Raid haste | Elemental Shaman (else a Mage) | in phase two |
| Flash Freeze | ranged damage dealers | break the nearest block; others leave the 5-yard shatter |

Formations are logical anchors for native pathing, computed from the boss and main-tank frame and
clamped to the room floor:

- pre-pull: the entrance line about 28 yd from the boss, with offense held until the pull tank
  engages. The pull tank waits for the play-mode pull timer, for nobody dead, for everyone at 70%
  health or more, and for every non-tank within 15 yd of its slot;
- Red: rows in front inside the cone, melee at ±25° beside the tank, Consuming Flames targets
  behind;
- Blue, Dark and phase two: a fan behind the boss at 18 yd, 40° apart, and melee behind at ±50°
  (a third melee straight behind at 8 yd). A chilled player, and anyone whose slot lies near an
  ice block, keeps its hazard-exit position;
- Green and the vial transitions: no formation.

Hazards preempt formations: Absolute Zero (7 yd) and jet fire (4.5 yd), each exiting from the
nearest source and rotating the exit until it clears every other sphere and fire; the tank's
Magma Jets sidestep (8 yd perpendicular); shatter clearance; and Biting Chill isolation (not for
tanks, who hold the boss and the adds).

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
per Prime Subject hit. Calibration needs same-mode WCL melee U samples; the WCL extraction plan
lists the reports and views. No value is staged until then (registry entries are requested as
`open`, with the non-melee helpers `not_applicable`).

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
6. Warcraft Logs was behind a human-verification gate on 2026-09-25, and no report was read.

## Unresolved (fidelity blockers)

- Maloriak-specific hotfix carryover to the 2025-02-20 cutoff.
- Live and WCL vial and ability cadence in all modes.
- Runtime 4.3.4 DBC parity with the client rows, and the Biting Chill target defect.
- Normal health (native vs Wowhead 4.4.2) and the enrage timer.
- Heroic Prime Subject Fixate and Rend.
- A live wipe/re-pull observation of the repaired Reset.
- A live read-back of the historical script bindings and `spell_custom_attr`.
- Melee calibration (Maloriak, Aberration, Prime Subject) from matched WCL U samples.
