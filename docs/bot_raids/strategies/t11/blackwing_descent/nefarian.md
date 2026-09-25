# Nefarian's End: research contract v3

Scope: Blackwing Descent, Nefarian's End, Cataclysm Classic 4.4.2 (build 59185,
hotfix cutoff 2025-02-20) as the fidelity target, run on the repository's 4.3.4
(15595) server. Round 2 of the full-raid program focuses on 10N; all four modes
stay in the packet. State: `fidelity_blocked`. The native script, client rows,
pinned addons and guides are audited. Warcraft Logs (WCL) was not readable on
2026-09-25: a human-verification page blocked every request, and an agent must not
pass it. Every value that needs a combat log is listed as unresolved.

Machine-readable packet:
- contract: `experiments/configs/cata_raid_encounters/blackwing_descent/nefarian_v1.json`
- ledger: `experiments/configs/cata_raid_encounters/blackwing_descent/nefarian_ledger_v1.json`
- WCL extraction plans: `nefarian_wcl_dps_reference_v1.json` and `nefarian_wcl_cast_timelines_v1.json` in the same directory
- raid target: `experiments/configs/raid_targets/blackwing_descent_10n_nefarian.json`

## 1. Lifecycle (native)

- **Prerequisite.** Spawn group 402 holds Lord Victor Nefarius, the Orb of
  Culmination and two stalkers. It spawns once Magmaw, Omnotron, Chimaeron, Atramedes
  and Maloriak are done. The shard seeds that lockout; the seeding is diagnostic
  assistance and never certifies those kills.
- **Intro.** Gossip option 0 of menu 11492 on the orb (GO 203254, spawn 239510) runs
  the intro:
  - Nefarius summons Nefarian.
  - 20.5 s: the elevator starts rising. GO 207834 takes 13.333 s to travel.
  - 33 s: the intro is done.
  - About 37 s: Nefarian lifts off and reanimates Onyxia.
- **Engage.** Onyxia's Start Fight periodic (81516 → 81517, every 1 s) targets only
  players who stand on the elevator transport (the script filters on `GetTransGUID`).
  The first such hit calls `DoZoneInCombat` for Onyxia, which engages every living
  player in the instance, passenger or not. So the first passenger starts the fight for
  everyone; bots still on the ledge are in combat too. Package T's ledge drop therefore
  waits until every living member is at the lip (`transport_drop_waiting_for_cohort`),
  and the descent node hands over to the encounter node as soon as boss index 5 is
  IN_PROGRESS.
- **Wipe.** Evade sets FAIL and raises the elevator, despawns the summons and spawn
  group 402, and resummons Nefarian 30 s later without the intro. The intro flag is
  not written to the instance save (low-priority gap).
- **Kill.** Nefarian's death gives DONE and credit for encounter 1026 (41376).

## 2. Phase graph

Phase timers below are native (repository). Where the sources differ, the ledger has the
conflict.

| Phase | Trigger | Native behaviour | What bots observe |
|---|---|---|---|
| Pre-engage | orb, intro | Onyxia feign-dead at the centre (29266) | Onyxia not in combat |
| 1a Onyxia | start-fight pulse | Hail of Bones: 4 warriors in 10N (one per 6 s tick over 24 s, on the 42844 stalkers). Onyxia's Breath 11–12 s then 13–17 s, Tail Lash 20 s then 17–18 s, Lightning Discharge 22 s then 22 s. | Onyxia in combat, Nefarian flying |
| 1b both dragons | landing 24 s after engage | Children of Deathwing: +100% attack speed while the dragons are within 50 yd. Nefarian's Breath 9–10 s then 9–14 s, Tail Lash 18 s then **every 5 s**. Electrocute 5 s after each 10% of Nefarian's health, +17 Onyxia charge. | Nefarian landed and attackable |
| 2 platforms | Onyxia dies | Nefarian lifts off with 81582. Three Chromatic Prototypes jump onto the pillar tops. The elevator sinks for 13.333 s. Shadowflame Barrage every 2.5 s (4 targets in 10N). Blast Nova 3.5 s after the prototypes ready, then every 13 s (4 s cast, then a 30 s room-wide 2 s tick). Fallback to phase 3 after 150 s. | Onyxia's corpse, 81582, prototypes, elevator Z |
| 3 Nefarian | third prototype dies (normal) | The elevator rises; Nefarian lands after about 15.5 s. Shadow of Cowardice punishes transport offset Z > 9.5 (pillar tops). Shadowblaze Spark on a bone warrior 5 s after engage, then 30/25/20/15 s, then 15 s (normal) or 10 s (heroic). Breath 9 s then 17–22 s, Tail Lash 1 s then 15–22 s. | 81582 gone, fires 42595/42596 |

## 3. Native geometry the bots rely on

- **Platform.** GO 207834 spawn 235179 is at (-107.213, -224.62), rotated by π. A
  local offset (x, y) maps to world (-107.213 − x, -224.62 − y).
  - Raised origin Z 7.03378; lowered origin Z −6.86794.
  - The floor is not flat. It comes from the collision model of display 10363,
    `data/vmaps/Blackwingv2_Elevator_Onyxia_Transport.wmo.vmo` (992 triangles, sha256
    `b51adf90…597de`). A vertical ray was cast every 5° and every 0.5 yd, and the
    samples are committed in
    `experiments/configs/cata_raid_encounters/blackwing_descent/nefarian_platform_floor_profile_v1.json`.
    `tests/test_nefarian_platform_profile.py` re-derives them from the model. In local Z:
    - the centre is flat at −0.546 out to r 21.2. Two decorative ridges rise
      +0.2 near r 10 and r 19–21;
    - from r 21.2 to r 32.4 a 10° ramp rises 0.1763 per yard;
    - from r 32.4 to r 60 the ring is flat at 1.439 (world 8.47 raised).
    - The strategy's floor model (`FloorLocalZAt`) is within 0.234 yd of every sample
      that is 7.5 yd or more from a pillar.
  - At the route's board point, local (25, 0), the floor is on the ramp at +0.074
    (world 7.1075 raised). The route rows still say 6.5714, which is 0.54 below the
    floor; patch request M1 corrects them.
  - Onyxia's summon height (−7.33029 lowered) is 0.084 above the flat centre.
  - The pillar blocks sit at headings 0/120/240° and r 40.5, and their tops are at
    local 9.925. With its skirt (up to local 2.2), each block reaches 5.2–6.0 yd from
    its centre. The profile records this per heading (`pillar_footprints`), so every
    pillar stands wholly on the ring.
  - No static navmesh covers the platform (the lava navmesh is at z 3.0), so every
    move on it is a transport-surface walk.
  - The ledge lip is at x −157.65. The lawful ledge drop lands on the ring at z 8.51,
    for 34.9% of maximum health in fall damage.
- **Magma.** LiquidType 404 "Blackwing Descent - Magma" casts 81114 on anything in it:
  5000 fire per second, plus Magma 81118, which stacks +250 fire damage taken per
  stack (99 stacks, 10 s) in normal.
- **Pillar tops.** They are part of the transport. The native prototype jump
  destinations are local (40.51, −0.06), (−20.47, −34.22) and (−20.44, 34.40), all at
  local Z 9.925. The prototypes become passengers.
- **Melee reach** (creature_model_info plus the player's reach): Nefarian 22.8 yd,
  Onyxia 20.8, Chromatic Prototype 7.2, Animated Bone Warrior 6.6.
  - A dragon only turns while its tank stays inside that reach.
  - To move a dragon, its tank must leave the reach; the chasing dragon stops at the
    reach short of its tank.
  - So a tank standing on the ring at r 52 beyond the dragon's end pulls the dragon out
    to about r 29–31 (52 minus the reach). A tank inside r 34 cannot: its dragon stops
    near r 13, and two such dragons stay within Children of Deathwing's 50 yd.
- **Cones, all 60 yd.**
  - Breath: native 90° front. The DBC has no cone angle, so the SpellMgr default
    applies; the 4.4.2 client has 60°.
  - Tail Lash: 82° rear. The Journal says 60°.
  - Lightning Discharge: 77833 (CONE_BACK in spell_custom_attr) and 77836 (front) make
    targets immune. Damage 77943 hits everyone else within 60 yd, so it lands on
    Onyxia's flanks. This matches the Journal: "from the orbs along her sides".
- **Bone warriors.**
  - 38.7M health; not immune to stun, root, snare or Shackle Undead.
  - Each Animate Bones tick costs 3 energy, with no regeneration: about 33 s of
    activity.
  - Empower: +100% damage and +10% speed per 4 s stack in normal. A stunned warrior
    gains no stack.
- **Shadowblaze.** Brushfire Start targets an Animated Bone Warrior (conditions).
  Shadowblaze hits and reanimates within 4 yd.

## 4. Sources compared

| Claim | Native | 4.4.2 client / Journal | Pinned addons | Guides | Status |
|---|---|---|---|---|---|
| Health 10N (Ony/Nef/Proto) | 5.58M / 22.76M / 1.63M | — | — | Wowhead NPC pages: same values; Wowhead guide: 7.0M / 28.5M / 6.9M | conflict |
| Breath | 1 tick (SpellMgr 1500 ms), 90° | 3 ticks at 0.5 s, 60° | 12 s CD | Wowhead: 35k ×3 | conflict |
| Nefarian Tail Lash, phase 1 | every 5 s | −82° rear | BigWigs 12.1 s, DBM 10 s (10–20) | Wowhead ~15 s | conflict |
| Onyxia charge | 1 per 3 s (SpellMgr) + 1 per 2 s from Nefarian, +17 per Electrocute | 78949 period 1 s | charge shown in the BigWigs infobox | +25 per Electrocute (both guides) | conflict |
| Lightning Discharge | 22 s, 5 s wind-up, 5 pulses, flanks | flanks (Journal) | BigWigs 24/22 s, 5 s cast | turn her 90° at the wing glow | resolved |
| Blast Nova | 3.5 s then 13 s, 4 s cast | 4 s cast, interruptible | counters only | Wowhead ~8 s | conflict |
| Phase 2 window | 150 s fallback | — | DBM Barrage window 150 s | — | resolved |
| Shadowblaze floor | was 10 s in every mode, now 15 s normal / 10 s heroic | — | BigWigs and DBM: 15 s normal, 10 s heroic | Wowhead 10 s (no mode) | resolved and repaired |
| Hail of Bones 10N | 4 warriors | 6 s tick over 24 s | BigWigs counts summons | Wowhead 12 | conflict |
| Berserk | 10:30, all modes | — | BigWigs all modes, DBM heroic only | — | conflict |

## 5. Native audit

- **Repaired:** `spell_nefarians_end_brushfire_pre_start_periodic`. The Shadowblaze
  Spark floor is now 3 ticks (15 s) on normal and 2 (10 s) on heroic, backed by both
  pinned addons.
- **Split:** the 2100-line `boss_nefarians_end.cpp` is now four files, split by
  concern:
  - `boss_nefarians_end.h`: the shared enums;
  - `boss_nefarians_end.cpp`: Nefarian and Onyxia;
  - `boss_nefarians_end_adds.cpp`: Nefarius, the orb, the bone warriors, the
    prototypes and Shadowblaze;
  - `boss_nefarians_end_spells.cpp`: the spell scripts.

  Statements are unchanged except for the repair. `AddSC_boss_nefarians_end` calls the
  two new registration functions, so the loader is unchanged. The two new `.cpp` files
  need a CMake configure.
- **Unchanged, no effect:** the orb's `GossipSelect` returns false. The option (menu
  11492, option 0) is type 1 with no action menu, so the core sends nothing afterward.
- **Fidelity-blocked, waiting on WCL** (see the ledger's `native_audit`):
  - Nefarian's 5-second phase 1 Tail Lash;
  - the breath tick period (SpellMgr);
  - Onyxia's charge period (SpellMgr) and the +17 Electrocute increment;
  - the 90° default cones.
- **Instance, low priority:** the intro flag is not written to the save.

## 6. Bot strategy (canonical 10N composition)

The code is in
`src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/`, all header-only:

| File | Contents |
|---|---|
| `BotNefarianFacts.h` | observation and phase detection |
| `BotNefarianGeometry.h` | platform frame and cones |
| `BotNefarianCapabilities.h` | per-spec interrupt, taunt and control capabilities |
| `BotNefarianDutyPlan.h` | duties by capability |
| `BotNefarianLayout.h` | dragon ends and tank leading |
| `BotNefarianTactics.h` | targets, interrupts, bone warrior control |
| `BotNefarianMovement.h`, `BotNefarianPhaseMovement.h` | movement goals and the phase 2 capability blocker |
| `BotNefarianPath.h` | leg planner on the platform surface |
| `BotNefarianSurfaceIntent.h` | a leg as a `TransportSurfaceMove` Walk |
| `BotNefarianNativeFacts.h`, `BotNefarianNativeObserver.h` | native cast progress, transport placement, running spline, spell readiness |
| `BotAdaptiveNefarianStrategy.h` | composition |

Spec selection: druid Feral tank and shaman Restoration. Two tanks, three healers, five
DPS. Roster GUIDs 11005001-11005010.

- **Duties.** They are chosen by capability each snapshot, never by roster slot.
  - The Nefarian tank is the best living tank by capability: Blood DK, then Protection
    Paladin, Protection Warrior, Feral. The Onyxia tank is the next tank.
  - Each pillar gets one healer, then a ≤13 s interrupter wherever its healer has none.
    The rest are balanced by head count and damage dealers.
  - Canonical result:
    - pillar 0: Holy Paladin, Rogue (Kick), Feral, Warlock;
    - pillar 1: Disc Priest, Blood DK (Mind Freeze), Mage (backup Counterspell);
    - pillar 2: Resto Shaman (backup Wind Shear), Ret (Rebuke), Hunter.
  - The shackler is the first living priest. The controllers are the other living
    non-tanks with a stun, snare or root, ordered stuns, roots, cooldown-free snares,
    then snares with a cooldown.
- **Phase 1.**
  - The ends: Onyxia's is 30° from her tank's pillar; Nefarian's is opposite it.
  - **Pull.** The Onyxia tank walks to the ring at r 52 on a radially clear heading at
    her end (a dragon off its heading is pulled past its end by the same angle, up to
    25°). Onyxia chases out from the centre and stops at about r 31.
  - **Hold.** Once the dragon is at r ≥ 27.5 within 15° of its end, the tank stands
    7 yd from it, tangentially and 25° outward, inside its reach. The dragon only turns
    and faces along the wall, with the raid (at the centre) on its flank.
  - The Nefarian tank does the same at the opposite end once Nefarian lands. Opposite
    ends at r ≥ 27.5 are at least 2 × 27.5 × cos 15° = 53 yd apart; the chase-model test
    (`tests/test_nefarian_movement.py`) settles them at r 32 and r 30, 62 yd apart, from
    both the board point and the ledge-drop landing.
  - On Lightning Discharge's wind-up (78090) the Onyxia tank steps to 7 yd radially
    outward of her. She turns and her tail points at the raid, which is then in her back
    immunity cone.
  - **Trade-off.** That back cone (90°, 60 yd) overlaps Onyxia's Tail Lash cone (82°,
    60 yd): the raid avoids 5 Lightning Discharge pulses (23.4–24.6k each in 10N, about
    120k per player) but risks one Tail Lash (17.5–22.5k and a 2 s stun) if her 17–18 s
    lash lands in the 5 s window. The strategy accepts the lash risk; formation spots
    avoid her rear cone except during a discharge.
  - The raid holds a band between the dragons, on both dragons' inner wings. Any spot
    in a front or rear cone is rotated to a safe one; Onyxia's rear is allowed during
    her discharge.
  - Damage (Electrocute budget):
    1. Onyxia until 12%.
    2. Then Nefarian down to 73%, while Onyxia's charge is below 60. That gives two
       Electrocutes (+34 natively).
    3. Then finish Onyxia.
- **Bone warriors.**
  - The shackler holds the most empowered free warrior with Shackle Undead, one at a
    time.
  - Exactly one controller acts on a warrior per decision: the first in rotation that
    is in range and whose control spell is ready (the native observer reads
    `SpellHistory`). A 60 s Hammer of Justice on cooldown hands the warrior to the next
    controller, down to the cooldown-free Curse of Exhaustion. Nobody reapplies over a
    held warrior or damages the shackler's candidate:
    - Hammer of Justice: Holy and Ret;
    - Concussive Shot: Hunter;
    - Frost Shock: Shaman;
    - Curse of Exhaustion: Warlock;
    - Frost Nova: Mage.
  - A non-tank chased by an unheld warrior kites around a ring.
  - In phase 3 the free Feral tank taunts loose warriors and keeps them in a pen on the
    wing away from the raid.
- **Phase 2.**
  - At Onyxia's death each bot heads to its pillar's foot. With a pillar ascent it
    then goes to its slot on the pillar top once the floor moves.
  - Today there is no ascent. Every plan carries `Blocked = pillar_ascent_unsupported`,
    and so do the decision trace and the `nefarian_duty_plan` status (`"blocked"`). The
    bots hold the pillar feet and sink with the floor into the magma. That is a known
    capability limit, not a strategy failure: patch W1 makes the completion watchdog end
    the diagnostic run at the first heartbeat that reports the blocker
    (`encounter_capability_blocker_watchdog`), keeping everything captured through
    phase 1.
  - Team DPS stays on the pillar's prototype. With no prototype left, offense is
    suppressed, because any Nefarian damage triggers Electrocute.
  - Each casting prototype has an ordered list of interrupters who can reach it now:
    its pillar's primary, then its backup, then team members, then anyone else, by
    cooldown. The first acts on the cast. The second acts after 1.8 s of the 4-second
    cast when native cast progress is published.
- **Phase 3.**
  - With a pillar ascent, everyone would stay on the pillars while the floor rises and
    then drop before Nefarian lands (Shadow of Cowardice). The drop is a 10 yd fall off a
    near-vertical side (StepOff, Fall, Land), not a walk; until it is wired, a bot on a
    pillar top reports `pillar_descent_unsupported` and does not move. A pillar top is
    recognised only from the bot's transport placement, never from its height alone.
  - The Nefarian tank holds him near the centre, facing the tank's pillar. The raid
    takes the wing farther from fires and warrior piles.
  - Everyone leaves any Shadowblaze fire (4 yd radius) for a spot 12 yd from its
    centre, and steps 9 yd out of the front cone of a casting breath.

## 7. Movement on the platform (package T's transport-surface walk)

No static navmesh covers GO 207834, so an ordinary `Move` is refused there for the whole
fight. The strategy picks a standing spot (`SurfaceGoal`: purpose, `Floor` or
`PillarTop`, transport-local point and Z, world point at the observed origin, elevator
GUID, arrival tolerance, pillar, urgency) and walks to it in legs
(`BotNefarianPath.h`), one per decision, each submitted as
`BotNativeAction::TransportSurfaceMove` Walk with `EndOnTransport`:
- A leg is at most 9.5 yd; the executor refuses anything over `MaxSurfaceWalkYards` (12).
- The whole floor inside r 57 is walkable: the flat centre, the ramp and the ring.
  Standing spots keep 9 yd from a pillar centre.
- Every leg ends at the model floor height of its end (`FloorLocalZAt(leg.To)`), with a
  0.6 yd floor tolerance. The executor moves at the linearly interpolated height, so a
  straight chord over one of the ramp's two creases leaves the floor by at most
  slope × a × b / (a + b), where a and b are the parts of the leg on either side. A leg
  that crosses a crease is therefore capped at 6 yd (at most 0.26 yd off the floor).
- A leg keeps 7 yd from every pillar centre: the widest footprint is 6.0 yd, plus the
  body radius of 0.389. When the straight segment does not clear the pillars, the leg
  goes through one or two waypoints, picking the shortest clear path. The waypoints lie
  every 10° on two circles: r 27 on the ramp, inside the pillars, and r 50, outside
  them. This takes a bot from the ledge-drop landing behind pillar 0 (local 49.2, 0)
  around the pillar.
- The plan is recomputed every decision. A new Walk replaces one still running (T). A
  walk that is still running is not relaunched (`nefarian_leg_in_flight`) when its
  destination lies in the direction of the newly planned leg (within 10°) and no farther
  from that leg's end than the leg's own length. As the bot advances, the end of a long
  walk slides forward, so the check compares directions, not end points. A goal change
  or a refused walk relaunches it.
  Walks claim movement, GCD and cast: hazard escapes are Survival priority, tank and
  pillar moves Mechanic, and a formation spot more than 5 yd away is Mechanic; small
  corrections yield to the rotation.
- Typed holds, recorded in the decision trace: `nefarian_elevator_unobserved` (never
  an ordinary move instead), `nefarian_not_on_platform` (not a passenger of the
  elevator), `nefarian_movement_stunned` (Tail Lash stun; wait it out),
  `nefarian_no_surface_path`.
- The planner converges on all 13,608 pairs of standing spots it was tested on.
  Every leg is probed against the sampled model with an emulation of T's surface-walk
  checks (0.25 yd samples, floor tolerance, unsupported span, body sweep):
  - the 432 legs of the whole-raid simulation, from the board point and from the
    ledge-drop landing;
  - the 61,232 distinct legs of the planner coverage.

  None is refused (`tests/test_nefarian_movement.py`). A level leg up the ramp or a
  smaller pillar clearance is refused.

Still needed from package T:
1. **Pillar ascent** (not supported: T can neither swim nor climb). Players swim up
   through the magma onto a pillar lip (Wowhead). Without it phase 2 is a typed blocker
   (section 6). `NativeFacts::PillarAscentSupported` switches the strategy to pillar-top
   goals once it exists.
2. **Ledge drop from a pillar top** (StepOff → Fall → Land from a raised part of the same
   transport; T's executor supports it, the strategy does not drive it yet). Only needed
   once the ascent exists.

## 8. Encounter damage fidelity

Every Nefarian's End creature still has DamageModifier 1 (the upstream reset). None is
calibrated: that needs WCL `U` melee samples, which the extraction plan lists.

| Creature | Class, level, attack time | Native swing at DM 1 | Status |
|---|---|---|---|
| Nefarian (41376 and difficulty entries) | 1, 88, 1500 ms | 4,553–6,764 | open |
| Onyxia (41270 and difficulty entries) | 1, 88, 1500 ms | 4,553–6,764 | open |
| Animated Bone Warrior (41918, one template for all modes) | 4, 85, 2000 ms, BaseVariance 0.5 | 5,470–8,175 | open |
| Chromatic Prototype | PassiveAI, never swings | — | not applicable |
| Lord Victor Nefarius | PassiveAI | — | not applicable |
| Stalkers | — | — | not applicable |

No staged SQL is written until a matched sample exists.

## 9. Acceptance observations

These are the contract's `acceptance_observations`: passengers before the pull,
separation over 50 yd, no breath on non-tanks, two phase 1 Electrocutes, pillar tops
reached, every Blast Nova interrupted, no phase 2 Nefarian damage, pillars left before
landing, controlled bone warriors, no repeated Shadowblaze ticks, native clear with 0
boss-window deaths.

## 10. Unresolved (fidelity_blocked)

1. The WCL 10N kill references and timelines are pending (human-verification gate).
2. The creature melee DamageModifier is uncalibrated (Nefarian, Onyxia, bone warrior).
3. The guide's health values conflict with native health.
4. The dragons' Tail Lash and Breath cadence and cone geometry.
5. Onyxia's charge rate and the Electrocute increment.
6. Blast Nova and Barrage cadence.
7. The Shadowblaze Spark schedule and spread (the floor is repaired; the first offset
   and the spread are unverified).
8. The Hail of Bones warrior count and lifetime.
9. Pillar access and the magma level.
10. Heroic Dominion, Cinders, and the end of phase 2.

## Sources

1. **Wowhead:** "Nefarian Strategy Guide - Blackwing Descent Raid Cataclysm Classic".
   Beanna, patch 4.4.2, updated 2024-06-10.
   <https://www.wowhead.com/cata/guide/raids/blackwing-descent/nefarian-strategy>,
   accessed 2026-09-25.
2. **Wowhead NPC pages** 41376, 41270, 41948 and 41918 (health tables):
   <https://www.wowhead.com/cata/npc=41376>, accessed 2026-09-25.
3. **Icy Veins:** "Nefarian Encounter Guide: Strategy, Abilities, Loot". Abide, updated
   2024-07-29.
   <https://www.icy-veins.com/cataclysm-classic/nefarian-encounter-guide-strategy-abilities-loot>,
   accessed 2026-09-25.
4. **BigWigs_Cataclysm** v11.0.13, commit 650bab03981eb06b5fa6ded88e47c523caa3c7c3,
   `BlackwingDescent/Nefarian.lua`, sha256 `a903c83d…2d83f`.
5. **DBM-Cataclysm** commit 4b02efec4552aef3df43c75fb19c6d8c7fdb3e6e, Nefarian module,
   sha256 `5fb1bc95…7a3d2`.
6. **4.4.2.59185 client rows** (wago.tools, through
   `tools.raid_program.extract_442_client_spell_rows`), including the Journal sections of
   encounter 174.
7. **4.3.4 client DBC** in `data/dbc/enUS`; hashes are in the contract.
8. **Repository:**
   - `boss_nefarians_end*.cpp` and `boss_nefarians_end.h`;
   - `instance_blackwing_descent.cpp`;
   - `SpellMgrCorrectionsPart04.cpp:424-481`, `SpellMgrCorrections.cpp:89-91`;
   - TDB 434.22011 with the `sql/updates/world/4.3.4` deltas: creature_template,
     creature_model_info, summon groups, spawn group 402, spell_custom_attr, conditions.
