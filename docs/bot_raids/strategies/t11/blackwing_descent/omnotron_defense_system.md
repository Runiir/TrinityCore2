# Omnotron Defense System — research contract v3

Scope is Cataclysm Classic 4.4.2 (reference build 59185, hotfix cutoff
2025-02-20) executed on the 4.3.4 client/server. 10N is researched for a
live-attempt-ready shard; 10H, 25N and 25H keep their earlier guide-level
status. The claim ledger is
`experiments/configs/cata_raid_encounters/blackwing_descent/omnotron_defense_system_ledger_v1.json`
and the mechanic contract is `omnotron_defense_system_v1.json` next to it. The
encounter stays `fidelity_blocked`: ten material values are unresolved, most of
them because Warcraft Logs showed a human-verification page during this pass
(no agent may pass it). Nothing below is a bot timer.

## What changed in round 2 (2026-09-25)

- **Client rows** (4.4.2.59185 via wago.tools, and the 4.3.4 execution DBC,
  identical for every 10N row compared) resolve the rotation, durations, radii
  and 10N damage ranges.
- **DBM** `DarkIronGolemCouncil.lua` r20241103125714 (sha256 `77a4f0ed…`)
  corroborates the normal and heroic timers from logs.
- **Native script audit**: four real defects fixed (below); the 1,591-line
  script was split under the repository's 1,000-line rule.
- **Kill attribution**: the route row named Arcanotron (42166), but only the
  encounter credit creature Toxitron (42180) is a dungeon boss, so a native
  kill could never produce boss-kill evidence. Patch requested.
- **Bot strategy**: `Encounters/Omnotron/` now holds a real adaptive strategy
  (duties by capability, no timers).

## Phase graph (all modes)

1. **Pre-pull.** The controller (42186, passive, 20 yd south on a ledge)
   summons four inactive constructs: Inactive (78726: stun and immunity),
   Powered Down (82265), not selectable. 10 s after reset the first queued
   construct gets Recharging (45 s normal), then walks a patrol between
   (-309.8, -393.0) and (-342.3, -392.7). It is attackable but has no
   Activated aura.
2. **Engage.** Any construct entering combat sets IN_PROGRESS, zones all four
   into combat and applies Activated (78740) to the patrolling one. The next
   construct starts Recharging at once.
3. **Rotation.** Activated lasts 90 s on normal and 60 s on heroic.
   Recharging lasts 45 s and 30 s, so a new construct joins every 45 s
   (30 s heroic) and two are active after the first 45 s. Each active
   construct shields once, 50 s (heroic 40 s) after activation: a 1.5 s cast
   and a 10 s aura. At expiry it casts Shutting Down (78746, 3 s) and becomes
   inactive.
4. **Kill.** Shared Health (79920) links the four. When the pool empties
   they all die, the controller calls `_JustDied` (boss index 1 DONE) and the
   credit creature is 42180.
5. **Wipe.** Any construct evading despawns all four, sets FAIL and respawns
   the controller after 30 s (fresh AI: default spawn group, not
   compatibility mode).

## 10N abilities (client rows; native agrees unless noted)

| Construct | Ability | 10N value | Bot handling |
|---|---|---|---|
| Electron | Electrical Discharge 95499→79879 | 23,399-24,600 nature, chain 3 within 8 yd, every 6 s | No spread (guides); the chain now starts on a random player |
| Electron | Lightning Conductor 79888 | 10 s (15 s heroic); every 2 s 19,499-20,500 to allies within 8 yd | Carrier isolates beyond 11 yd; others keep out of 10 yd |
| Electron | Unstable Shield 79900 | 10 s; hits proc Static Shock 29,249-30,750 in 6 yd | Stop direct damage |
| Magmatron | Incineration Security Measure 79023 | 11,699-12,300 fire per second for 4 s, raid-wide | Heal through |
| Magmatron | Acquiring Target 79501 → Flamethrower 79505/79504 | 4 s mark, then a 25° cone, 20,474-21,525 per second for 4 s | Marked player leads the cone away; others leave the line |
| Magmatron | Barrier 79582 | Absorb 300,000 (client; Wowhead says 900,000), 10 s; breaking it casts Backdraft 73,124-76,875 on everyone | Stop all damage |
| Toxitron | Chemical Bomb 80157 → Chemical Cloud 42934 | 30 s; +50% damage taken for players within 12 yd and constructs within 13 yd | Leave the cloud; no construct dragging (1 yd band) |
| Toxitron | Poison Protocol 80053 | 9 s, one Poison Bomb every 3 s (3 per cast), twice per activation | Fixated player kites; ranged kill bombs where the blast reaches nobody |
| Toxitron | Poison Bomb 42897 | Fixate 20 s; on contact 73,124-76,875 nature in 6 yd plus Poison Puddle (6 yd, 11,699-12,300 per second, 30 s) | Leave puddles and other players' bombs |
| Toxitron | Poison Soaked Shell 79835 | 10 s; attackers get Soaked In Poison (5,000 per stack every 2 s, 30 s, poison) | Stop direct damage; dispel 3+ stacks |
| Arcanotron | Arcane Annihilator 79710 | 38,999-41,000 arcane, 1.5 s cast, one random target | Interrupt rotation |
| Arcanotron | Power Generator 79624 → 42733 | 60 s, 5 yd: +50% damage done and 250 mana per 0.5 s for players and constructs | Tanks move constructs out; ranged and healers stand in |
| Arcanotron | Power Conversion 79729 | 10 s; each hit gives +10% magic damage and cast speed for 30 s | Stop direct damage (DoT ticks do not proc) |

Native melee: constructs are level 88, unit class 4, BaseAttackTime 1.5 s.
At DamageModifier 1 the native roll is 4,520.5-6,731.4 per swing. That value
stays uncalibrated until matched WCL samples exist. Native 10N shared health
is 25,767,600 (85,892 × 300). The Wowhead guide says 32.2M; WCL derivation is
pending.

## Native script audit (round 2)

Split: `boss_omnotron_defense_system.cpp` (controller and constructs),
`boss_omnotron_defense_system_spells.cpp` (Nefarius, Poison Bomb, spell
scripts) and `boss_omnotron_defense_system_shared.h`. The loader is unchanged.
Fixed defects, each with two sources:

1. **Electrical Discharge target.** The AI cast 79879 without a target, which
   falls back to the construct's victim (the tank). It now casts the
   registered random-target trigger 95499. Sources: Wowhead ("to a random raid
   member") and the client trigger row.
2. **Acquiring Target count.** A 26 s repeat gave three Flamethrowers per 90 s
   normal activation. Normal now repeats after 40 s. Sources: DBM (40 s) and
   Wowhead ("twice per activation"). Heroic keeps 26 s, which already gives
   two casts in 60 s.
3. **Poison Protocol count.** It was scheduled once per activation; it now
   casts a second time 45 s (heroic 25 s) later. Sources: DBM and Wowhead.
4. **Poison Soaked Shell timing.** It came at 40 s normal and 30 s heroic,
   10 s before every other construct's shield. It is now 50 s and 40 s.
   Sources: DBM and Wowhead's heroic 40 s.

Left unchanged because the sources conflict or only one source exists (all
listed as `unresolved`):

- normal-mode first-cast offsets (Chemical Bomb, Lightning Conductor, Power
  Generator, Poison Protocol);
- the Electrical Discharge +20% per jump, whose script is a no-op (no
  `SetHitDamage`);
- whether a killed Poison Bomb explodes;
- the Barrier absorb amount;
- the Static Shock centre;
- Nefarius' heroic cadence.

## Bot strategy (canonical 10N composition)

The Omnotron shard uses 2 tanks and 2 healers: Blood DK, Feral druid (tank),
BM hunter, Fire mage, Holy paladin, Ret paladin, Disc priest, Assassination
rogue, Elemental shaman and Demonology warlock. Every duty is chosen from
observed state and capability, never from a roster slot:

- **Ownership.** The strategy owns the node only while a construct is engaged;
  the validation route approaches and pulls the patrolling construct.
- **Staging and pull.** The route node's own position (-324.78, -399.08) is a
  patrol waypoint, and walking onto it body-pulled Arcanotron before the
  pre-pull setup in round 3. The encounter rows therefore navigate to
  (-336.08, -356.46, 213.871), observed walkable corridor ground 36.7 yd from
  the patrol line (construct aggro is 15 yd minus combat reach: level 88 is
  above the expansion cap) and at most 45 yd from any patrol point. Flask, food
  and pre-pot finish there; then the raid pulls. The pull target is whichever
  construct the controller powered up at random. The other three are not
  selectable (creature_template unit_flags 0x82000000), so the pre-pot
  boss-target check must accept the route row's alternate entries, not only
  the credit entry 42180.
- **Tanks.** A tank owns the active construct whose victim it is. A new
  construct goes to the tank whose construct is gone or shutting down. The
  owner taunts its construct if it attacks anyone else. While its construct is
  shielded, the owner stops attacking and drags it away from the other
  construct: it samples points around itself (sideways ones too, so a tank on
  the arena rim can slide) and moves only for at least 4 yd more separation.
  It walks the construct out of a Power Generator. A tank without a
  construct waits next to the construct whose Recharging aura ends within
  12 s and does not attack meanwhile.
- **Damage.** The focus is an active construct whose one shield of this
  activation has been seen and has ended (it cannot shield again before it
  shuts down); otherwise the newest active construct without a shield or
  shield cast. If every active construct is shielded, offense is suppressed.
  Why: Barrier is an absorb, periodic damage depletes it, and depletion counts
  as removal by an enemy spell, which casts Backdraft on the raid. DoTs last up
  to 21 s. With "newest first" alone, the older construct was the focus until
  the newer one activated, only 5 s before its own shield, so its DoTs ticked
  into the shield every rotation. With the spent-shield preference each
  construct is left alone from ~16 s after its activation until its shield
  ends. Only the opening construct, alone for 45 s, still carries fresh DoTs
  into its shield; Backdraft breaks by periodic damage are a live signal.
- **Offense restriction.** Per bot, all four construct entries are restricted
  and only the active unshielded constructs are allowed, so no direct cast
  lands on a shielded construct and no area spell (Divine Storm, Blood Boil,
  Death and Decay, Fan of Knives) is cast beside one. An interrupt or a taunt
  on a shielded construct is widened for that single native cast and the
  restriction is restored right after it; it never enters the allowed set.
- **Interrupts.** The Arcane Annihilator rotation goes by class/spec and
  reach: in-range melee 10 s interrupts (Rebuke, Kick), then ranged (Wind
  Shear 15 s, Counterspell 24 s), then tanks (Mind Freeze), then long
  cooldowns (Skull Bash 60 s). A player with a personal movement debuff comes
  last. A per-cohort ledger counts casts: one primary per cast and one backup
  450 ms in. Under Power Conversion the rotation keeps interrupting: natively
  every interrupt that lands procs one Converted Power stack, damaging or not
  (spell_proc 79729 has SpellTypeMask 0 and a no-damage hit still raises a
  proc), which is judged cheaper than a 39-41k Annihilator. Whether 4.4.2
  behaves the same is an open research item; stacks per interrupt are a live
  signal. A taunt is the same for Arcanotron under Power Conversion (one
  Converted Power stack) and procs nothing on the other shields: Unstable
  Shield (79900, 91447-91449) and Poison Soaked Shell (79835, 91501-91503)
  have TDB 434.22011 spell_proc rows with SpellTypeMask 1 (damage), which no
  later update removes, so `CanSpellTriggerProcOnEvent` rejects a no-damage
  hit before the Unstable Shield script's check runs. No Static Shock or
  Soaked In Poison comes from a taunt.
- **Dispels.** Poison dispellers (Cleanse, Remove Corruption; never a Bear Form
  tank) clear Soaked In Poison at 3+ stacks or below 50% health. Healers go
  first.
- **Movement**, in priority order: Lightning Conductor isolation, Poison Bomb
  kiting, Acquiring Target cone steering, Flamethrower cone dodge, hazard exit
  (Chemical Cloud, Poison Puddle, bomb blast), clearance from a conductor, tank
  positioning (generator exit, shield separation, then the centre slot; see
  round 2 below), healer coverage of every tank, then Power Generator
  stacking for ranged and healers.
  Destinations stay on a 20 yd disc around the route node. The map 669
  navmesh is walkable on the full 21 yd disc.

Not implemented, deliberately:

- dragging constructs into the Chemical Cloud (guides call it optional; the
  12/13 yd band leaves no safe margin);
- pre-positioning Toxitron before Poison Protocol;
- Bloodlust timing (no reviewed release window, so the shared reservation
  stays closed);
- Spellsteal of Converted Power.

## Conflicts and unresolved items (`fidelity_blocked`)

1. `wcl_matched_10n_kill_references`: per-spec 10N kill DPS and cast
   timelines. WCL gated.
2. `construct_melee_damage_modifier_10n`: matched U samples per construct.
3. `shared_health_10n_wcl_derivation`: native 25.77M against guide 32.2M.
4. `electrical_discharge_chain_damage_scaling`: Wowhead same damage, Icy Veins
   increasing, native no-op.
5. `poison_bomb_death_explosion`: Wowhead explodes; native does not.
6. `barrier_absorb_amount`: client 300k against Wowhead 900k.
7. `normal_mode_first_cast_and_repeat_timers`: native against DBM normal
   offsets.
8. `heroic_nefarius_selection_order_and_cadence`.
9. `heroic_poison_bomb_count_and_non_10n_scaling`: Wowhead 2 bombs per tick
   against client 1; other modes' health and damage.
10. `static_shock_center_attacker_or_construct`.

Open research questions (ledger `open_questions`): whether 4.4.2 Power
Conversion procs on a non-damaging interrupt or taunt, now also the material
claim `power_conversion_no_damage_proc`; whether DoTs can break the 10N
Barrier.

## Raid-program round 1 (2026-09-27): WCL 10N results

The first attempt of the day was still gated: HTTP 403 with the Cloudflare
challenge page. GPT-6 Astra then read three 10-player Normal kills through
the Codex Chrome plugin in the user's Chrome:
`MxFq7TRbvnjGY1hJ` fight 24 (2024-10-28), `Y8ajQ7dbmKMG1RZy` fight 24
(2025-05-15) and `xAhkN2y9YP3KRmnJ` fight 12 (2025-06-11). The values are in
the ledger (source `wcl_omnotron_10n_20260927`), the DPS reference manifest
and the cast timeline manifest.

- **Construct melee.** 136 landed rows carry U. Rows inside Power Generator
  windows are excluded. The unreduced range is 51,220-75,687; the smallest
  value under Scarlet Fever or Vindication is 46,798. The native roll at
  DamageModifier 1 is 4,520.5-6,731.4, plus the +1% auto-attack bonus. That
  bounds the effective multiplier to 11.244-11.331. DamageModifier **11.2**
  (effective 11.312) is in
  `sql/custom/world/2026_09_27_23_omnotron_defense_system_damage_modifier.sql`
  for 42166, 42178, 42179 and 42180 (promoted 2026-09-27; the DB updater applies it at worldserver startup). The registry rows are applied.
  Difficulty entries stay open.
- **Shared health, 10N.** The WCL health tooltip at pull reads 25,767,600 in
  all three kills. In the Y8aj kill, damage on the two constructs totals
  25.77m. The native value is right, and the guide's 32.2M does not apply.
- **Timers after Activated (78740).** Activations come 44.1 s apart. Shields
  start 50-51.6 s after activation. First casts: Chemical Bomb 11.1-11.3 s,
  Poison Protocol 22.4-22.6 s (repeat 45.3 s), Lightning Conductor 15.9 s
  (repeat 26 s), Power Generator 12.9-15.9 s (repeat 30.75 s), Incineration
  10.0-11.1 s, Acquiring Target 21.4 s (repeat 40 s). The native normal-mode
  timers in `boss_omnotron_defense_system.cpp` now match: Chemical Bomb 11 s,
  Poison Protocol 22.5 s, Lightning Conductor repeat 26 s, Power Generator
  repeat 30 s. Heroic timers are unchanged because there is no heroic sample.
- **Electrical Discharge.** Each cast hits 3 players, all with U
  23,432-24,581. Damage does not ramp between jumps, and the first target
  varies.
- **Barrier.** DoT ticks were absorbed for 267,864 over the full 10 s without
  a break or Backdraft. That is below both the client's 300,000 and
  Wowhead's 900,000, so the absorb amount stays unresolved.
- **Poison Bombs.** Five bombs were killed in each of MxFq and xAhk. No
  Poison Bomb 80092 damage was logged, so killed bombs do not explode, which
  matches the native despawn. The single Static Shock hit landed on the
  paladin tanking Electron.
- **DPS references.** The raid target matches Y8aj fight 24 and xAhk
  fight 12 (item level 395-401). MxFq fight 24 (item level 360) is context
  only. The WCL references cover the Blood DK, Fire mage, Elemental shaman
  and Survival hunter. Retribution, Assassination and Demonology use the
  WoWSims fallback. The Feral tank has no reference.

10N research is not complete: `fidelity_state_by_mode` keeps 10N
`fidelity_blocked` because three 10N material claims stay open (each
`unresolved` entry lists its modes). `barrier_absorb_amount`: 267,864
absorbed without a break is below both 300,000 and 900,000, so it cannot
tell them apart. `static_shock_center_attacker_or_construct`: the one hit
landed on the attacking tank beside Electron, which both centres explain.
`power_conversion_no_damage_proc`: no WCL row shows whether a non-damaging
interrupt grants Converted Power. The two heroic items also remain.
Full-raid run r11 killed the council natively; its
`encounter_fidelity.boss_melee` recorded no construct swings.

## Raid-program round 2 (2026-09-27): positioning and WCL follow-up

Round 1 (label `blackwing_descent_10n-r01-553da85c98`) cleared 3 of 3 but
counted one kill (102.7 s), with one boss-window death. The two other runs
lost their combat logs.

- **The death.** The Feral tank died to Magmatron melee at 75.9 s. From 60 s it
  took Magmatron melee, Incineration, Electrical Discharge and four
  Flamethrower ticks, with no healer heal (only its own Leader of the Pack).
  The Blood DK held the pulled Electron about 30 yd north of the arena centre.
  The Feral tank had waited at Magmatron's southern spawn and tanked it there.
  Both healers stayed north, 50-57 yd from the Feral tank. The Holy paladin's
  trace shows Holy Shock `out_of_range` at 48.6 s and 61.2 s and
  `requires_ally_target` (nobody in range needs a heal) for most of 51-76 s.
- **DPS runs.** Damage uptime was about 83% for most actors. The gaps sit at the
  45-50 s focus switch (Electron north to Magmatron south) and the 61-75 s
  switch back, each a run of about 30 yd.
- **Shields held.** The window has no Static Shock, Backdraft, Soaked In
  Poison, Lightning Conductor or Poison Bomb damage. Time Warp was cast
  (Temporal Displacement 80354 on the pets).

Strategy change (`BotOmnotronPositioning.h`):

- **Centre slots.** Each tank holds its unshielded construct on one of two
  slots 5 yd west and east of the route node (-324.78, -399.08). Both tanks
  compute the same pairing from one snapshot (the smaller total walk wins).
  A tank moves when its construct is more than 6 yd from the slot and walks
  3.5 yd past it, so the construct following it stops on the slot. A slot
  inside a Power Generator's reach moves 15 yd out along the line from the
  generator. A slot in a hazard is not taken. A shielded construct is still
  dragged 12+ yd from the other one first and walked back after its shield.
  The 10 yd spacing keeps cleave on both unshielded constructs. The matched
  WCL kill xAhkN2y9YP3KRmnJ fight 12 (one Blood DK tank) shows this: one Heart
  Strike at 00:51.069 and one Blood Boil at 00:57.088 each hit both Toxitron
  and Magmatron, and the Replay at 00:57.085 shows them adjacent. Y8aj fight 24
  (two tanks) kept Electron and Arcanotron apart.
- **Healer coverage.** A healer with a living tank beyond 30 yd walks to the
  nearest clear point around the tanks' centroid that reaches every tank.
  Clear means outside hazards and outside a Lightning Conductor carrier's
  reach. If no clear point reaches every tank, it takes the clear point
  nearest the farthest tank. A healer stands in a Power Generator only if the
  generator is within 30 yd of every living tank.

WCL round 2 (GPT-6 Astra in the user's Chrome; ledger source
`wcl_omnotron_10n_r2_20260927`). All three claims stay open:

- **Barrier absorb.** No Backdraft 79617 row in 11 accessible 10N kills, so
  no Barrier broke; the absorb size stays unresolved.
- **Static Shock centre.** In zPVW3nfwMhgjGAFr fight 22, single bursts hit a
  Fire mage, an Elemental shaman and the Blood DK tank together. Overlapping
  attacks prevent tying a burst to one attacker, so the centre stays
  unresolved.
- **Power Conversion on a non-damaging interrupt.** In PGAKmyYbanW3wN9z
  fight 24, a Wind Shear at 00:57.288 under Power Conversion gave no Converted
  Power stack within 0.5 s. It landed 139 ms after the previous gain, inside
  the native 500 ms proc cooldown (spell_proc 79729 Cooldown 500), so it does
  not decide. The native row is unchanged.

Class evidence from round 1, for the class agents (no class file changed
here):

- **Elemental.** 39 casts/min against 56 in WCL. No Chain Lightning (15 WCL
  casts, hitting both constructs), no Elemental Mastery, no Spiritwalker's
  Grace.
- **Blood DK.** No Dancing Rune Weapon, Blood Tap, Blood Boil, Outbreak or
  Empower Rune Weapon. A 12.3 s owner gap from 49.5 s while Electron was
  shielded.
- **Demonology.** 66% of the WoWSims fallback with no WCL-only rows to compare.

WCL extraction plan (executed 2026-09-27; kept for heroic and 25-player follow-ups):

- **Reports.** Start from the BWD 10N reports already used for Magmaw:
  `MxFq7TRbvnjGY1hJ` (2024-10-28), `Y8ajQ7dbmKMG1RZy` and `xAhkN2y9YP3KRmnJ`.
  Select the Omnotron Defense System kill fights. Otherwise use the 10N
  rankings for encounter 1027.
- **Per kill, extract:**
  - summary DPS by spec;
  - completed casts (timelines);
  - enemy casts and auras: 78740, the four shields, 80053, 80157, 79501, 79888,
    79624, 79710;
  - damage-taken ability 1 from each construct with mitigation (U), excluding
    Power Generator windows (+50%);
  - 79879 hit sequences;
  - 80092 events after bomb deaths;
  - absorbs on 79582 and any Backdraft 79617;
  - Converted Power 79735 applications right after SPELL_INTERRUPT of 79710;
  - resource-bar health samples for `derive_encounter_health`.

## Repository and database audit

- Scripts: see the split above. Loader `eastern_kingdoms_script_loader.cpp`
  still calls `AddSC_boss_omnotron_defense_system` only.
- DB (TDB 434.22011 plus `sql/updates/world/4.3.4`):
  - constructs 42166/42178/42179/42180 (10N): HealthModifier 300,
    BaseAttackTime 1500, unit class 4, rank 1, level 88;
  - difficulty entries 49047-49058 use BaseAttackTime 2000;
  - addon auras 78726 82265 78725 73059;
  - summon group 0 of 42186;
  - conditions limit 78696, 79920 and 80164 to the four entries;
  - 79629 (Power Generator) has no conditions, so it affects every unit in
    5 yd;
  - `instance_encounters` 1027 credits 42180 (creditType 0);
  - upstream `2025_06_18_06` set DamageModifier 1 everywhere.
- Instance: boss index 1; Omnotron has no prerequisites. The inner door opens
  when Magmaw and Omnotron are done.
- Approach: two stationary Golem Sentries (42800, level 85 elite, spawns
  250049 at (-338.622, -347.5) and 250048 at (-311.602, -347.373)) guard the
  corridor 50 yd north of the room; they are the `bwd.omnotron.sentries`
  trash node. The regroup anchor and a shard's start position must stay well
  outside their aggro (at most 15 yd against level-85 bots, 15 - CombatReach).
  Round 2 batch 1 started the c0 cohort on sentry
  250049 and lost it to future-encounter contamination; the regroup anchor
  moves to observed ramp ground at (-340.36, -299.07, 206.88), 48.5 yd from
  the nearest sentry (`tests/test_omnotron_route_geometry.py`).

## Source metadata

1. **Wowhead — "Omnotron Defense System Strategy Guide"** by Beanna (updated
   2024-06-04), <https://www.wowhead.com/cata/guide/raids/blackwing-descent/omnotron-defense-system-strategy>,
   re-read 2026-09-25. Mode-unspecific rotation text (60/30 s), ability table,
   tank/melee/ranged tips, "no enrage timer".
2. **Icy Veins — "Omnotron Defense System Encounter Guide"** by Abide (last
   updated 2024-07-29), <https://www.icy-veins.com/cataclysm-classic/omnotron-defense-system-encounter-guide-strategy-abilities-loot>,
   re-read 2026-09-25. 50-energy shields, dispelling Soaked In Poison, tank
   the target into the cloud and next to the generator.
3. **Warcraft Wiki — "Omnotron Defense System"**, <https://warcraft.wiki.gg/wiki/Omnotron_Defense_System>,
   accessed 2026-08-11 (legacy values).
4. **Guías WoW heroic guide**, <https://en.guiaswow.com/blackwing-descent/guide-heroic-mode-defense-system-omnotron-defense-system.html>,
   accessed 2026-08-11 (heroic history).
5. **Client rows** 4.4.2.59185 (wago.tools, full-CSV sha256 prefixes in the
   ledger) and the 4.3.4 execution DBC (`data/dbc/enUS`).
6. **DBM** `DarkIronGolemCouncil.lua` r20241103125714 (local install, sha256 in
   the ledger).
7. **Repository**: TDB 434.22011 snapshot, map 669 navmesh tiles, the native
   script and the route attribution code (paths in the ledger).
