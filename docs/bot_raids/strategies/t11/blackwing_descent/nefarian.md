# Nefarian's End: research contract v3

Scope: Blackwing Descent, Nefarian's End, Cataclysm Classic 4.4.2 (build 59185,
hotfix cutoff 2025-02-20) as the fidelity target, run on the repository's 4.3.4
(15595) server. Round 2 of the full-raid program focuses on 10N; all four modes
stay in the packet. State: `fidelity_blocked`. The native script, client rows,
pinned addons and guides are audited. On 2026-09-27 three Warcraft Logs (WCL) 10N
kills were read through the user's authorized Chrome session (on 2026-09-25 a
human-verification page had blocked every request):

- MxFq7TRbvnjGY1hJ fight 35 (2024-10-28, 344.1 s);
- cYg4C93QNdqKfPF1 fight 18 (2025-01-31, 283.5 s);
- farY2cm8JMTB1jGh fight 10 (2025-01-15, 250.6 s).

They supply the DPS references, cast timelines, melee samples, max health and the
cadences below. Values a combat log cannot settle stay unresolved.

All three DPS references were read from WCL's default damage-done view for Nefarian's
End. Only the farY2 capture recorded that this view leaves out Animated Bone Warriors
(41918). For MxFq7 and cYg4 the same exclusion is inferred, not observed: they were
read from the same default view, WCL applies encounter filtering per encounter, and
the round-1 review found raid DPS x duration within 0.031% of the combined boss
health in all three kills, which leaves no room for bone-warrior damage. On that
inferred basis the raid target lists 41918 in `native_dps_excluded_target_entries`,
and the scoreboard subtracts each bot's bone-warrior damage from its encounter-window
DPS, so both sides are meant to count the same enemies. The raw captures have no
per-target split, so bone-warrior-inclusive WCL DPS could not be re-derived.

Machine-readable packet:
- contract: `experiments/configs/cata_raid_encounters/blackwing_descent/nefarian_v1.json`
- ledger: `experiments/configs/cata_raid_encounters/blackwing_descent/nefarian_ledger_v1.json`
- WCL data: `nefarian_wcl_dps_reference_v1.json`, `nefarian_wcl_cast_timelines_v1.json` and `nefarian_wcl_melee_samples_v1.json` in the same directory
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
| 2 platforms | Onyxia dies | Nefarian lifts off with 81582. Three Chromatic Prototypes jump onto the pillar tops. The elevator sinks for 13.333 s. Shadowflame Barrage every 3.2 s (4 targets in 10N; repaired from 2.5 s to the WCL cadence). Blast Nova 3.5 s after the prototypes ready, then every 13 s (4 s cast, then a 30 s room-wide 2 s tick). Fallback to phase 3 after 150 s. | Onyxia's corpse, 81582, prototypes, elevator Z |
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

## 3a. Magma and the pillar ascent (native data)

`experiments/configs/cata_raid_encounters/blackwing_descent/nefarian_magma_v1.json`
holds every number below with its derivation; `tests/test_nefarian_magma.py` re-derives
the surface from the model when `data/vmaps` is present.

- **Magma surface: world z 2.7713, flat over the arena.**
  - It is the liquid of WMO group 0 of `Blackwingv2.wmo` (vmap spawn 857346,
    `data/vmaps/Blackwingv2.wmo.vmo` sha256 `7a081d35…a774b`); the 669 map tiles carry
    no liquid layer. Every sample (the three pillar centres, the centre, the board point,
    the ring) reads 2.7713. The lava navmesh near z 3.0 is not the surface.
  - LiquidType 19 (WMO Magma) becomes 404 "Blackwing Descent - Magma" through area
    5094's override; 404's spell is 81114. The core decides "in the liquid" from the
    static WMO alone (`TerrainInfo::GetFullTerrainStatusForPosition`: feet below the
    surface), so the sinking platform does not shield anyone.
  - 81114 deals 5000 fire every second and each second adds a stack of Magma 81118
    (+250 fire damage taken, 99 stacks, 10 s): n ticks deal 5000 n + 125 n (n − 1).
- **Lowering.** `EVENT_LOWER_ELEVATOR` (0.8 s after the phase 2 lift-off, about 3.8 s
  after Onyxia dies) sets GoState 24. The stop change lasts 13,333 ms and follows
  TransportAnimation.dbc: the origin falls linearly from +13.90172 (13,133 ms) to 0
  (200 ms), 1.0749 yd/s, from 7.03378 to −6.86794.
  - The flat centre goes under 3.66 s after the start, the ring 5.50 s.
  - The pillar tops (local 9.925) stop at 3.0571: **0.286 yd above the surface**. They
    never go under (0.249 above at the animation's 36 mm dip). The native stop height is
    unchanged.
- **Pillar profile** (the platform model, sampled on each slot heading every 0.1 yd):
  a flat top of radius 3.5-3.9, a 25° rim falling 0.465 per yard to a vertical wall at
  radius 5.3-5.7 (the rim edge at local 9.14-9.16 is 0.49 under the surface at the
  lowered stop), a skirt up to local 2.25 out to 6.0, then the ring. The dry part of the
  top at the lowered stop reaches about 0.6 yd down the rim.
- **The ascent is lawful native movement.** A player swims in the magma (the core's
  `Unit::CanSwim` is true for player-controlled units; the spline carries CanSwim).
  From its station 6.7 yd from the centre, with its feet 1.2 yd under the surface, a
  bot's hop onto the rim just above the waterline rises about 1.34 yd over 2.3-2.7 yd.
  The client's jump (7.95577 yd/s up, apex 1.64 yd) lands there in about 0.58 s, at
  4-4.7 yd/s horizontally, below the run speed.
  - The plan checks the exact trajectory the executor runs.
    `MotionMaster::MoveJumpWithGravity` gives `Movement::MoveSpline` one straight
    segment. Its duration is 1 + trunc(3D length × 1000 / speed) ms, and its height is
    the chord plus 0.5 × gravity × t × (T − t).
  - So the spline speed comes from the 3D segment. The duration is the ballistic air
    time rounded down to a whole millisecond, which keeps the launch speed at or under
    the client's jump speed.
  - The whole body clears the rim and the wall edge by at least 0.27 yd on every slot
    (0.16 yd at a 1.35 yd float depth). A single jump
  straight onto the flat top would have to cross the wall edge, 0.7 yd above the feet
  0.3 yd away, and is not planned. Nothing here needs a teleport, a climb or an invented
  effect.

## 4. Sources compared

| Claim | Native | 4.4.2 client / Journal | Pinned addons | Guides | Status |
|---|---|---|---|---|---|
| Health 10N (Ony/Nef/Proto) | 5.58M / 22.76M / 1.63M | — | — | Wowhead NPC pages: same values; Wowhead guide: 7.0M / 28.5M / 6.9M; WCL-derived (11 rows each): 5,582,980 / 22,761,380 / 1,627,290 | resolved: native is right |
| Breath | 1 tick (SpellMgr 1500 ms), 90° | 3 ticks at 0.5 s, 60° | 12 s CD | Wowhead: 35k ×3; WCL: 3 ticks of 35,000 U | ticks resolved (SpellMgr patch requested); cone open |
| Nefarian Tail Lash, phase 1 | every 5 s | −82° rear | BigWigs 12.1 s, DBM 10 s (10–20) | Wowhead ~15 s; WCL: none in three kills (phase 1 under 15 s); phase 3 repeat 11.3–21.0 s | conflict |
| Onyxia charge | 1 per 3 s (SpellMgr) + 1 per 2 s from Nefarian, +17 per Electrocute | 78949 period 1 s | charge shown in the BigWigs infobox | +25 per Electrocute (both guides) | conflict |
| Lightning Discharge | 22 s, 5 s wind-up, 5 pulses, flanks | flanks (Journal) | BigWigs 24/22 s, 5 s cast | turn her 90° at the wing glow | resolved |
| Blast Nova | 3.5 s then 13 s, 4 s cast | 4 s cast, interruptible | counters only | Wowhead ~8 s; WCL 12.5–13.0 s | resolved: native is right |
| Shadowflame Barrage | was every 2.5 s, now 3.2 s | 2 s cast | — | Wowhead 3 s; WCL 3.2–3.3 s (49 intervals) | resolved and repaired |
| Phase 2 window | 150 s fallback | — | DBM Barrage window 150 s | — | resolved |
| Shadowblaze floor | was 10 s in every mode, now 15 s normal / 10 s heroic | — | BigWigs and DBM: 15 s normal, 10 s heroic | Wowhead 10 s (no mode); WCL 30/25/20/15/15 s | resolved and repaired |
| Hail of Bones 10N | 4 warriors | 6 s tick over 24 s | BigWigs counts summons | Wowhead 12; WCL 4 (two kills) | count resolved |
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
- **Repaired (2026-09-27):** on 10N, Shadowflame Barrage repeats every 3.2 s, not
  2.5 s (WCL 10N Begin Cast intervals, 49 in two kills). 25N, 10H and 25H keep
  2.5 s until same-mode evidence exists. The phase 2 survival model is
  regenerated at 3.2 s.
- **Patch requested (SpellMgr, outside this packet):** drop the 77826 `AuraPeriod`
  1500 override so a breath deals 3 ticks, as WCL shows.
- **Fidelity-blocked** (see the ledger's `native_audit`):
  - Nefarian's 5-second phase 1 Tail Lash (no phase 1 Tail Lash in three WCL kills:
    the Onyxia burn keeps his phase 1 under 15 s);
  - Onyxia's charge period (SpellMgr) and the +17 Electrocute increment (WCL has no
    Electrical Charge series);
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
| `BotNefarianMovement.h`, `BotNefarianPhaseMovement.h` | movement goals, the warrior handler's pen and kite, the phase 2 capability blocker |
| `BotNefarianMagma.h` | magma surface, lowering timeline, pillar profile per slot, the hop's jump physics, magma damage |
| `BotNefarianAscent.h` | the swim-and-hop ascent (Float, Swim, Hop, Board) and the phase 3 descent (rim walk, StepOff, Fall, Land) |
| `BotNefarianPath.h` | leg planner on the platform surface |
| `BotNefarianSurfaceIntent.h` | a leg as a `TransportSurfaceMove` Walk |
| `BotNefarianNativeFacts.h`, `BotNefarianNativeObserver.h` | native cast progress, transport placement, running spline, spell readiness |
| `BotAdaptiveNefarianStrategy.h` | composition |

**User tactics (user raid experience 2026-09-26).** The user raided this fight; their
tactics outrank the guides and our own inferences (conflicts are listed below):
1. Composition: 2 tanks, 2 healers, 6 DPS; the shaman stays Elemental.
2. Phase 1: Bloodlust and burn Onyxia before Nefarian lands, which skips most of
   phase 1. No Electrocute pacing.
3. Phase 2: swim in the magma as it rises beside your pillar; once the pillar top is
   level with the surface, hop onto it and kill the prototype there.
4. Bone warriors: the Feral druid kites them and roots them with Nature's Grasp; with
   enough damage on Onyxia there are few. They must never get in front of Nefarian:
   his breath wakes them, refills their energy and buffs them (confirmed by the user;
   natively `spell_nefarians_end_shadowflame_breath` removes the feign death, casts
   Full Power No Regen and the breath's buff).
5. Heroic: the Onyxia burn may not hold there, or with lower gear (open item).

Conflicts with the earlier plan: the guides' Electrocute pacing (Onyxia to 12%,
Nefarian to 73%) is now heroic-only; the three-healer composition, the
stun/root/snare controller rotation and the round-2 `pillar_ascent_unsupported`
blocker are replaced.

Spec selection: druid Feral tank and shaman Elemental (requested from M: patch
`.git/round6_patches/nefarian/M2`, which also declares the druid's Nature's Grasp).
Two tanks, two healers, six DPS. Roster GUIDs 11005001-11005010.

- **Duties.** They are chosen by capability each snapshot, never by roster slot.
  - The Nefarian tank is the best living tank by capability: Blood DK, then Protection
    Paladin, Protection Warrior, Feral. The Onyxia tank is the next tank; it is also
    the bone-warrior handler once Onyxia is dead.
  - Each pillar gets one healer. With two healers the third pillar gets the Nefarian
    tank (a Blood DK's Death Strike sustains it through the swim; pillars are 70 yd
    apart, out of heal range). Then a ≤13 s interrupter wherever a team has none, and
    the rest by head count and damage dealers.
  - Canonical result:
    - pillar 0: Holy Paladin (backup Rebuke), Rogue (Kick), Mage;
    - pillar 1: Disc Priest, Ret (Rebuke), Feral (backup Skull Bash), Warlock;
    - pillar 2: Blood DK (Mind Freeze, no healer), Elemental Shaman (backup Wind
      Shear), Hunter.
  - The shackler is the first living non-tank with Shackle Undead (backup control).
  - Teams are built from the whole roster, dead members included, so a death never
    moves anyone to another pillar. When the Blood DK dies, the Feral takes the live
    Nefarian-tank duty and the shaman takes pillar 2's interrupts, but nobody moves.
  - **The healerless pillar (coordinator default, pending the user's answer).** The
    Elemental shaman off-heals pillar 2 with Healing Surge (8004, in its action
    profile) on the lowest teammate it can reach (40 yd, line of sight) under 90%.
    Interrupts come first. Healing Rain is ground-targeted and is not used.
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
    (`tests/test_nefarian_movement.py`) settles them over 50 yd apart, from both the
    board point and the ledge-drop landing. With the burn Onyxia often dies before
    Nefarian lands; the separation then only matters if she lives longer.
  - On Lightning Discharge's wind-up (78090) the Onyxia tank steps to 7 yd radially
    outward of her. She turns and her tail points at the raid, which is then in her back
    immunity cone.
  - **Trade-off.** That back cone (90°, 60 yd) overlaps Onyxia's Tail Lash cone (82°,
    60 yd): the raid avoids 5 Lightning Discharge pulses (23.4–24.6k each in 10N, about
    120k per player) but risks one Tail Lash (17.5–22.5k and a 2 s stun) if her 17–18 s
    lash lands in the 5 s window. The strategy accepts the lash risk; formation spots
    avoid her rear cone except during a discharge.
  - **Damage: burn Onyxia.** Every DPS attacks Onyxia from the pull until she dies.
    The raid lust is the canonical boss-lust fallback (`BotRaidBossLust.h`): the fire
    mage's Time Warp about 5 s after the Feral holds Onyxia. Onyxia is a boss mob
    (creature_template type_flags 0x4, `Creature::isWorldBoss`), so the hold starts on
    her pull, not when Nefarian lands about 30 s later
    (`tests/test_nefarian_phase_one_lust.py`).
  - **Heroic fallback** (`PhaseOnePacingFor`: the observer reads `Map::IsHeroic`): the
    old Electrocute budget. Onyxia until 12%, then Nefarian down to 73% while Onyxia's
    charge is below 60 (two Electrocutes, +34 natively), then finish Onyxia.
- **Bone warriors.**
  - Hail of Bones raises them when Onyxia is engaged; each Animate Bones tick costs 3
    energy with no regeneration, so they collapse after about 33 s. The burn keeps that
    window short.
  - They must never reach Nefarian's front. Whoever leads warriors (the handler once
    Nefarian is down, or any bot an unheld warrior attacks) only takes destinations
    whose whole straight path, sampled every yard, stays at least 15° outside his breath
    cone and outside his tail (`WarriorPathSafe`). The same holds for the leg it walks
    now, and for every movement path: fire and breath escapes, kites, the pen.
  - A walk already running is re-checked first on every decision. If it would now take
    a following warrior deeper into Nefarian's front (he turned) and no lawful leg
    replaces it, the plan holds the bot with `nefarian_warrior_path_stop`. The same
    happens when the warrior rule refuses the leg. Every decision, that candidate:
    - claims the movement lane;
    - clears the native chase or point path and stops the spline, leaving a
      controlled effect alone;
    - renews a Hazard movement lease at the bot's position, so combat range
      recovery cannot walk it back in.
  - A dragon's tank never leads warriors. This covers Nefarian's victim (or his duty
    tank once he is down) and Onyxia's victim. The tank keeps its tank hold, and a
    warrior on it is shackled or taunted off by the handler. If the shackler cannot
    cast Shackle Undead now, it reserves nothing, and the handler takes the warrior.
  - A rooted (Entangling Roots 19975 or 339), stunned or shackled warrior is held.
    Nobody damages it, because the hold breaks on damage. With only held warriors
    left, the handler holds position instead of walking to Nefarian.
  - The handler (the Feral, free once Onyxia is dead) taunts loose warriors, casts
    Nature's Grasp (16689: baseline druid, usable in Bear Form, 3 charges for 45 s,
    60 s cooldown; each melee hit on the druid roots the attacker with Entangling Roots
    19975 for 27 s) when one attacks it within 12 yd, and kites them along an arc 24 yd
    from Nefarian on his far flank, away from the raid.
  - The handler's kite has hysteresis:
    - it starts when an unheld chaser comes within 6 yd, and ends only when the chaser
      is past 10 yd;
    - a running kite keeps its destination to the end;
    - no destination, kite or pen, heads within 60° of the chaser;
    - cornered at the end of the arc, the handler holds and tanks the warrior.
  - Held warriors never count as chasers, so a rooted warrior cannot mask an unheld
    one behind it.
  - Shackle Undead is the cheap backup: the shackler holds the most empowered warrior
    that is not on the handler and not rooted, one at a time. The stun/root/snare
    rotation of earlier rounds is gone.
  - A non-tank chased by an unheld warrior kites around a ring, to points outside
    Nefarian's cones.
  - `tests/test_nefarian_capabilities.py` checks every spec's interrupt, taunt, control
    and warrior root against Talent.dbc and SkillLineAbility.dbc, and Nature's Grasp's
    bear-form, charge and cooldown rows. No duty is handed to a bot the observer reports
    without the spell.
- **Phase 2: swim and hop.** The data, derivations and tests are in section 3a.
  1. At Onyxia's death (about 3.8 s before the floor starts down) each bot walks to its
     pillar's foot: 9.5 yd from the pillar centre on its own slot heading.
  2. The magma covers the ring 5.5 s after the platform starts down (the flat centre
     after 3.7 s). A bot stands in it until its feet are 1.2 yd deep, then floats: it
     stops standing on the platform, as a client that starts swimming does (`Float`).
  3. It swims to its station 6.7 yd from the pillar centre on its heading, at the float
     depth (`Swim`), and holds there while the platform sinks past it.
  4. At the lowered stop (13.33 s) the pillar top is 0.286 yd above the surface. The
     bot jumps from its station onto the rim just above the waterline (`Hop`, the
     client's jump), reports standing on the platform (`Board`, the swimmer's emerge
     report), and walks up to its slot 3 yd from the centre on the flat top.
  5. A late swimmer when phase 3 raises the platform (one that missed its hop) meets
     the rising floor instead of waiting for it:
     - it swims down to where the floor will be 1.5 yd under its feet;
     - it rides up just slower than the floor (0.25 yd/s slower);
     - it boards when its feet are between 0.45 yd above the floor and 0.3 yd into
       it. The emerge report is made at its actual position; nothing lifts a swimmer
       the floor has passed.
     - At the surface, with no room left to ride, it swims inward toward the ramp.
       On the ramp the floor under its feet then closes at about a quarter of the
       rise speed. Over the flat centre no swim helps, so it holds still
       (`nefarian_rising_floor_armed`).

     The replay boards at decision gaps of 0.1-1.2 s from the pillar station and from
     the surface boundary over the ramp (r 27). Where the floor closes at the full
     rise (the flat ring at r 40, the flat centre at r 12) the band is open 0.7 s. A
     later decision is the typed miss `nefarian_rising_floor_missed`, and the tests
     expect it. Only a member that already missed its pillar hop gets here.
  - Float, Swim, Hop and Emerge are package T stages this package requests (patch N1);
    the strategy turns its steps into them in patch N2, which also sets
    `RuntimePillarAscentSupported()`. Without them every plan carries
    `Blocked = pillar_ascent_unsupported` (decision trace and `nefarian_duty_plan`
    status), and patch W1 ends the diagnostic run at that heartbeat.
  - Team DPS stays on the pillar's prototype (ranged from the magma, everyone once on
    top). With no prototype left, offense is suppressed, because any Nefarian damage
    triggers Electrocute.
  - Each casting prototype has an ordered list of interrupters who can reach it now:
    its pillar's primary, then its backup, then team members, then anyone else, by
    cooldown. The first acts on the cast. The second acts after 1.8 s of the 4-second
    cast when native cast progress is published. While the team swims, only ranged
    interrupts reach the prototype on the top.
  - **Pre-ascent care.** Between Onyxia's death and the floor going under, the Disc
    priest shields everyone without Power Word: Shield or Weakened Soul, pillar 2
    first. The Holy paladin tops up (Flash of Light) anyone under 95%, pillar 2 first.
  - **Barrage on the healerless pillar.** Shadowflame Barrage is cast every 3.2 s
    until the last prototype dies. Each 2 s cast sends missiles at 4 random players,
    which take 1.73 s to arrive. The flight is 52 yd at 30 yd/s from Nefarian's
    phase 2 position (NefarianElevatorLiftOffPosition, z 35.63, over the centre). Pillar 2 is modelled
    by `tests/test_nefarian_phase_two_survival.py`, with its results recorded in
    `nefarian_phase_two_survival_v1.json`. The model has:
    - finite mana: 27% of base mana per Healing Surge, an 80k pool;
    - 1.5 s casts that land on completion and never run across a swim or hop;
    - heal crits at 200% and ±6.65% scaling variance;
    - preparation that lands 80% of the time, and starting health of 80-100%;
    - Death Strike at a conservative 3k/s;
    - a phase 2 that lasts until the last prototype dies.

    Blast Nova interrupts are not modelled.

    The results:

    | Layout | Pillar-2 death before phase 2 ends |
    |---|---|
    | Default | 9% (mean phase 49 s; 44% at the old 2.5 s Barrage) |
    | Default with 1.25x raid DPS | 2% |
    | Default with 1.5x raid DPS | 0.5% |
    | Option A: a pure burn pillar 2 | 100% (pillar 1 slows, so the phase lasts 78 s) |
    | Both tanks on pillar 2 | 68% |

    Changing single assumptions, as in the reviewer's variants, moves the default
    between these values:

    | Change | Default death risk |
    |---|---|
    | 10% damage reduction | 2% |
    | 20% damage reduction | 0% |
    | 40k mana pool | 42% |
    | 120k mana pool | 2% |
    | No mana regeneration | 14% |
    | 300 mana/s regeneration | 6% |
    | No Death Strike self-heal | 16% |
    | No preparation | 28% |

    This is not a native estimate. It ranks the layouts; the live run decides
    whether the healerless pillar is viable.

    Option B, a healer covering two pillars, is geometrically impossible: the nearest
    pillar tops are 62.5 yd apart and heals reach 40 yd.
  - **Magma damage.** About 8.4 s in the magma (5.5 s to the hop landing at about
    13.9 s): 8 ticks of 5000 + 250 k = 47,000 fire before resistance, about 30-40% of a
    DPS's health in T11 gear, on every bot at once. The two healers should top everyone
    up and shield before the ring goes under (they heal natively; the lowest member is
    healed first), and keep healing from the magma. The healerless pillar relies on
    the Blood DK's self-healing and a quick kill.
- **Phase 3: off the pillars.** Nefarian's Shadow of Cowardice (79355, recast when he
  lands, every 2 s) hits any passenger above local z 9.5 for 30,000 plus a stacking
  shadow vulnerability. Once the floor is back at the raised stop (13.33 s after phase 3
  starts; Nefarian lands about 16-19 s after it), each bot on a pillar walks to the rim
  (5 yd from the centre), steps off past the wall, falls 7-8 yd onto the skirt or the
  ring (below the 14.57 yd fall-damage threshold) and lands: T's StepOff, Fall and Land.
  A pillar is recognised only from the bot's transport placement, never its height.
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

Requested from package T (patch N1, `.git/round6_patches/nefarian/`): the swimmer's
stages `Float`, `Swim`, `Hop` and `Emerge` of `TransportSurfaceMove`
(`BotWorldPopulationMgrNativePathTransportLiquid.cpp`). Each re-proves its
preconditions natively (the core's `Map::GetLiquidStatus`, the platform's model, line of
sight, the platform held at its stop) and submits only what a client does: the
`MSG_MOVE_START_SWIM` / `MSG_MOVE_STOP_SWIM` reports, a straight swim spline, and the
client's jump (`MotionMaster::MoveJumpWithGravity` at 7.95577 yd/s up and the core's
gravity, at most run speed). The descent needs nothing new: T's StepOff, Fall and Land
already drop from a raised part of the same transport.

## 7a. First live attempt (round 6 batch, analysed in round 7)

Evidence: `artifacts/cata_raid_program/round6_batch1_20260926.tar.gz`, shard
`blackwing_descent_10n_nefarian_c0`, with the combat log reassembled from the
console export (2,429 chunks). The run reached `bwd.nefarian.encounter` and
then spent 79 minutes in phase 1 until `emergency_wall_clock_timeout`.

**What happened**
- There were about 28 attempts, each 2.5-3 minutes long. Every attempt ended
  with the dragons evading and respawning: a new Onyxia and Nefarian GUID each
  time, and `wipe_generation` stayed at 0.
- Phase 1 never ended. Onyxia took 108.8M damage over the run against 5.58M
  health. In attempts 1-3 and 5-8 she was pinned at 1 health while Nefarian was
  landed and fighting: her no-death-before-landing clamp was still active.
  Later attempts never got her below about 40%.
- Time Warp was cast once, in attempt 1, 38 s after the pull (Temporal
  Displacement 80354 at +28 s on the node). That is when Nefarian landed, not
  about 5 s after the Feral held Onyxia. No lust was cast in later attempts.
- Deaths recycled through corpse runs: releases, the run back and resurrection.
  That is why all 10 bots were alive at the end while 9 deaths were counted in
  the last window.

**Where the damage came from**

| Source | Damage taken |
|---|---|
| Bone warrior melee (on all ten) | 85.5M |
| Onyxia's Shadowflame Breath (on all ten) | 42.8M |
| Magma 81114 (hunter, mage, shaman, warlock, a Flaming Orb, the Doomguard) | 44.4M |
| Electrical Overload | 13.8M |
| Lightning Discharge | 11.5M |
| Tail Lash | 10.7M |
| Nefarian's breath | 9.6M |
| Electrocute | 2.9M |

**Root cause: static navmesh movement under the transport**
- 11,104 of the movement requests at the node were native combat range
  (`MoveBotToProfileRange`, CombatRange owner). 8,612 of them targeted points
  below z 5: the magma bowl (z -1.6) or the liquid surface under the platform
  (z 2.95-3.5).
- The first came 5.9 s after the pull. The mage lost line of sight to Onyxia
  past a pillar, and combat range recovery pathed it off the transport.
- Route regroups did the same.
- Only 1,573 of the plan's own legs were walked, and nothing kept the lane
  between them.
- Onyxia (straight-line chase) and Nefarian (mmaps chase) followed their
  victims down, from z 6.5 to 2.95 and -7.3. Pillars and the platform then
  blocked the rest of the raid's lines of sight. The breath cones and warrior
  control fell apart, and the dragons evaded when their targets became
  unreachable.

**Slow Onyxia pickup (the lust decode)**
- Her first damage came at 1790437213992 ms, but her first melee hit on the Feral
  only at +34.4 s. The lust fallback waits for a tank to hold her, so Time Warp
  landed at +38.9 s.
- The warlock landed first and opened on her 1.2 s before any tank.
- The Feral dropped last: it was still on the ledge approach when the node
  advanced. It landed at local (47.6, -3.7), 7.9 yd from pillar 0's centre.
- Its Growl (6795) and Faerie Fire failed with `native_no_line_of_sight` for 24 s.

**Fixes (round 7, after review)**
- Platform hold (`PlatformHold`, `nefarian_platform_hold`):
  - From the pull through phase 3, a bot on the raised platform always carries
    the hold. When it has no leg, the hold stands alone. Beside a proposed leg it
    is the fallback: CombatMovement, utility 1. An admitted leg wins; a leg that
    native admission rejects leaves the lane to the hold.
  - A diagnostic hold stays visible as `nefarian_platform_hold:<diagnostic>`.
  - The hold stops the native chase or point path and renews a Mechanic lease.
  - Every admitted leg of the plan publishes its own lease: Hazard for a
    survival escape, Mechanic otherwise.
  - A leg in flight renews the lease without being stopped.
- Heal guard (shared patch `R7_protected_movement_heal_guard.patch`): while
  such a lease stands and a spline runs, the heal candidate selects only instant
  heals, and `TryCastFriendlySpell` refuses a cast-time spell
  (`protected_movement_active`) instead of stopping the leg or escape. The
  scope is the Nefarian node (`BotNefarianProtectedMovement.h`).
- Formation spots for ranged and healers:
  - Every line to the damage target, and for healers to the dragon tanks, clears
    the pillars (6.1 yd).
  - Every target is within 36 yd. A healer falls back to the fighting dragon's
    tank alone when the two tanks are too far apart. The search steps toward the
    targets, which covers Onyxia's lead-out to the ring.
  - The arrival tolerance applies only while sight and range still hold from
    where the bot actually stands.
- The pull:
  - Before the pull, and until a tank has Onyxia, damage dealers hold fire. The
    suppression also claims the Target lane; heals and consumables go on. If her
    tank is dead, nobody waits.
  - Until she attacks her tank, the tank walks to a pillar-clear pickup spot
    within 25 yd of her (Growl reaches 30) and taunts.
  - Replay: the Feral from its r06 landing spot sees her after 31 yd, about
    4.4 s at run speed.
- Second review:
  - Pickup ownership: until Onyxia targets her tank, the pickup owns its
    movement. Within reach (Growl 30 less a margin, or melee reach when Growl is
    not usable) and in sight, judged by the pillar model and the native line of
    sight, the tank stands still so the taunt runs. Only once she targets it
    does it lead her out.
  - Pickup recovery: a spot the native line of sight rejects is left for
    another at least 4 yd away, a bounded list.
  - Replay at 100 ms decisions: from r 27.8 the Feral makes no move and taunts
    at once; from r 29 it makes one move, then taunts.
  - Short corrections: a checked leg under NextLeg's 1 yd arrival, when the bot's
    own spot does not serve (sight, range or a dragon's core).
  - Dragon core: arrival and holds also require the bot's actual position to be
    outside it. A non-tank inside a dragon's core walks out whatever the dragon
    casts.
  - Pull without the Feral: the Blood DK takes Onyxia (`OnyxiaTankNow`) before
    and after the pull. With no tank alive the damage dealers do not wait.
- Delta review:
  - The Blood DK standing in for a dead Feral (`ActsAsOnyxiaTank`) keeps
    Onyxia until she dies and holds Nefarian's taunt until then. Once she is
    dead or gone it is the full Nefarian tank again: tank hold and Nefarian
    taunt, through his landing and phase 3.
  - The pickup is bounded across decisions (`BotNefarianPickupMemory.h`, kept
    by the native observer per tank and Onyxia GUID, so a moving victim never
    resets it):
    - spots where the native line of sight failed are never reselected;
    - the budget is 10 s, or 4 rejected spots, or about 3 s standing still
      without sight;
    - once spent, the tank holds with `nefarian_platform_hold:nefarian_pickup_exhausted`
      and keeps trying from there, and the damage dealers start on Onyxia.
- Breath: `Spell.cpp` skips the cone check for a target within its own bounding
  radius (at least 2 yd) of the dragon's centre, so non-tanks keep 4 yd from
  both dragons.
- Route engagement observer (`SubmitAdaptiveNefarianRouteObservation`, wiring
  patch `R7_nefarian_route_observation.patch`): Nefarian (41376) only, landed,
  in combat, attackable. It records the engagement and nothing else, so his kill
  is not rejected as `combined_rejected`.
- Onyxia at 1 health: open. The native chain has no proven missed signal, so the
  native rule is unchanged. The chain is instrumented under
  `server.nefarians_end`:
  - Nefarian's `move_land`, `movement_inform` (type and id), `landed` and
    `landed_signal` (Onyxia GUID, AI enabled and AI pointer);
  - Onyxia's `landed_received` (AI pointer and `_allowDeath`) and her
    `lethal_clamp`.

**Not in these files (reported)**
- The completion watchdog counts any party damage as progress
  (`route_party_damage`, `tools/bot_ml/run_live_bot_validation.py`). An
  encounter that keeps evading and resetting therefore never stalls.
- The route drops the Onyxia tank last. A Feral-first drop would shorten the
  pickup further.

## 7b. Phase 2 pillars, round 8 (user raid experience 2026-09-26, followed literally)

The user's tactic for two healers and three pillars:
- the tanks take the healerless pillar and heal themselves;
- when another pillar kills its prototype, one healer and one DPS from it swim
  across to help finish.

**Teams** (`BotNefarianDutyPlan.h`, `TankPillar`):

| Pillar | Members | Interrupts |
|---|---|---|
| 0 | Holy paladin, rogue, Elemental shaman, hunter | Kick |
| 1 | Discipline priest, Retribution paladin, mage, warlock | Rebuke |
| 2 | Blood DK, Feral (the tanks alone) | Mind Freeze (10 s), then Skull Bash |

- Every primary interrupter is back within Blast Nova's 13 s.
- Skull Bash is 60 s: the canonical Feral has no Brutal Impact.
- The remaining damage dealers balance the healer pillars. Teams stay stable.

**Self-care** (`BotNefarianTankSelfCare.h`), after the pillar interrupt:

| Tank | Spell | Used under |
|---|---|---|
| Blood DK | Death Strike | 80% |
| Feral | Survival Instincts | 30% |
| Feral, with the glyph (canonical) | Frenzied Regeneration, no Enrage | 50% |
| Feral, without the glyph | Enrage then Frenzied Regeneration (rage conversion) | 60% |

- The glyph (aura 54810) is observed on the bot.
- Spells the bot does not know are never named. M provisions Enrage, Frenzied
  Regeneration, and Divine Shield for both paladins.

**Cross-pillar help** (`BotNefarianCrossing.h`):
- Who sends: the first healer pillar to kill its prototype. The observer's kill
  order keeps it, and a pillar whose healer died releases it.
- When: only while the platform rests lowered and the tank pillar's prototype
  keeps at least 25% of its health.
- Who goes: the healer, plus one damage dealer. It is one with a magma defensive
  it actually has ready if any, otherwise the first by slot, and the healer heals
  the pair during the swim.
- The defensive first: at the rim a ready defensive (Divine Shield, Pain
  Suppression) is cast with no movement proposed that decision, so it owns the
  cast lanes. Beside a proposed step it would lose them (tested in the kernel).
  The step waits until the defensive is up with at least 6 s left.
- The step into the lava uses the ledge-drop contract's liquid variant
  (`TransportSurfaceMove::LandInLiquid`, patch `R8_ledge_drop_into_liquid.patch`).
  The dry-ground contract still refuses liquid. Native admission accepts the step
  on all 18 slot headings with the liquid contract and refuses it with the dry
  one. After it: fall, land on the sunken ring, float, swim, hop onto a spare
  slot. Until the executor carries the field, nobody crosses.
- No departure once the platform rises.

**Survival model** (`user_tank_pillar_*`; not a native estimate, recorded without
deviating on it):

| Layout | Tank-pillar death | Mean phase | Helper death | Death on the pillar the healer left |
|---|---|---|---|---|
| The literal layout | 0% | 76 s | 0% | 18% |
| No help | 3% | 106 s | - | - |
| Elemental off-healer on the tank pillar | 3% | - | - | - |
| Off-healer and warlock on the tank pillar | 22% | - | - | - |

Regenerated on 2026-09-27 with the 3.2 s WCL Barrage cadence (the 2.5 s values were
0.2% helper, 50%, 27%, 16% and 75%).

## 7c. Round 7 live run (analysed in round 8)

Evidence: `artifacts/cata_raid_program/round7_batch1_20260926.tar.gz`. The run had
three phase-1 attempts of 139-141 s each, ended by `encounter_reset_loop_watchdog`.
`wipe_generation` stayed 0 and one death was recorded.

**Root cause: Onyxia cannot die.**
- Her 4.3.4 `creature_template` StaticFlags (0x5089000c,
  `sql/updates/world/4.3.4/2023_08_27_00_world.sql`) carry
  `CREATURE_STATIC_FLAG_UNKILLABLE`. `Unit::DealDamage` enforces it after her
  AI's `DamageTaken`.
- The landing chain completed every attempt (`landed_received allow_death=1`).
  She still took exactly max − 1 health (5,582,979), and every later hit landed
  0. She reached 1 health at 61, 80 and 62 s.
- About 140 s after each pull her Electrical Charge reached 100. Electrical
  Overload (78999, 855k-1.045M Nature to everyone) wiped the raid, and the
  dragons reset.
- The same flag explains the r06 1-health stalls.

**Fix** (`boss_nefarians_end.cpp`):
- She is unkillable when she appears, and the flag is cleared with
  `ACTION_NEFARIAN_LANDED`. That is her "no death before Nefarian lands", like
  `_allowDeath`.
- The landing log now also prints the flag.

**What worked**
- The platform hold: one magma event in the whole run.
- The Feral's pickup: Onyxia on the Feral at 0-1.9 s, first damage by the Feral.
- The damage dealers' hold.
- The lust: Time Warp at 5.4 s. Attempt 2 had none because of the cooldown;
  attempt 3 got it at 40 s, once it was ready.

**Also fixed**: in attempt 1 the hunter held Nefarian at the centre while the Blood DK
waited at its pull spot, 48 yd away and out of taunt range. The Nefarian tank now
picks him up the way the Onyxia tank does (`DragonPickupGoal`): into taunt range
with a clear line, and only then leads him out. Replay: a taunt after about 3 s.

**Noted**: a few bots stood 1-3 yd below the floor near the ramp start (r 21-24),
with no magma damage.

## 7d. Round 8 live run: Nefarian killed, route incomplete (analysed in round 9)

Nefarian died at 509 s. The route observer accepted the kill, but the node never
completed and the run ended on the plateau watchdog. Six of the ten bots died.

**Timeline**

| Time | Event |
|---|---|
| 41.1 s | Time Warp (Temporal Displacement 80354 on the raid; the cast 80353 itself is not logged) |
| 78.4 s | Onyxia died |
| ~93 s | The platform reached the lowered stop |
| 95 s | Both tanks on pillar 2 |
| 118 / 127 / 144 s | Prototypes died on pillars 0, 1 and 2 |
| 509 s | Nefarian died, killed by the four survivors |

- The tank pillar held easily. The DK took 108k in phase 2 (Death Strike 91k)
  and the Feral 93k.
- The healer-pillar members reached their swim stations but were refused every
  hop (`native_liquid_hop_transport_moving`, observed). They stayed in the lava
  until phase 3.
- All six died with the body in the lava:

  | Bot | Time | Last hit |
  |---|---|---|
  | Disc | 149.5 s | magma |
  | Hunter | 151.2 s | magma |
  | Rogue | 171.3 s | self-attributed lava damage |
  | Feral | 178.0 s | Nefarian's breath |
  | Shaman | 180.5 s | Electrocute |
  | Holy | 182.1 s | magma |

  The Feral was in the lava under the raised ring, in front of Nefarian, and
  was not tanking. Inferred: these members missed the rising floor at the phase
  change.
- After the kill the route held for about 8m40s.

**Root causes and fixes**
- **Route completion.** Nefarian's Lightning Machine (51089) stayed in combat
  after the kill, so native hostile activity never ended:
  - the fallen never released, because partial-death admission waits for hostile
    inactivity;
  - the survivors held (`native_full_wipe_hold_partial_death`).

  Fix: `boss_nefarians_end.cpp` takes the machine out of combat when Nefarian
  dies or the encounter resets.
- **Hop refusal.** The lowered stop is GoState `GO_STATE_TRANSPORT_ACTIVE` (24).
  The core parks the platform there once `GAMEOBJECT_LEVEL` passes, but the
  boarding rest rule only counted states from 25 up as a stop.

  Fix: patch `R9_stop_frame_zero_rest.patch` for T.

## 7e. BWD 10N raid program, round 1 (analysed in round 2)

Label `blackwing_descent_10n-r01-553da85c98`: three native clears. Two kills
have no combat log (truncated export, since fixed). The one measured kill,
6bf52232, is source `live_r01_6bf52232`.

**The DPS numbers are real.** The measurement is not the problem:
- The boss window, 1087.7 s, runs from Onyxia's first hit to Nefarian's death.
  WCL kills take 250–344 s.
- The bone-warrior exclusion lowers party DPS only from 34.3k to 30.5k.

Phase timeline: Onyxia dead at 64 s, prototypes killed 75–126 s, phase 3 from
about 148 s, Berserk 26662 at 10 min 30 s.

Raid DPS by phase:

| Window | Raid DPS | Low actors |
|---|---|---|
| Phase 3, 150–630 s | 40.6k on Nefarian | rogue 1.1k, shaman 1.5k, warlock 0.4k, Feral kiting 0.3k |
| After Berserk | about 5k | everyone |

Three damage dealers were stranded:

- **Elemental shaman.**
  1. Her pillar-0 prototype died at 100 s.
  2. The plan retargeted the nearest other prototype, on pillar 2, about 70 yd
     away.
  3. Native range recovery walked her from the pillar top toward it at
     pillar-top height. It stopped at local (5.9, 19.7), in the air over the
     lava; the floor under her was 168 yd down.
  4. An elevator passenger does not fall by itself. She rose with the floor
     and hovered at local Z 10.3 for 16 minutes.
  5. In phase 3, Shadow of Cowardice (offset Z over 9.5) hit her 341 times.
- **Rogue.** He ended phase 2 at local (-18.6, 26.6), Z 3.1: 8 yd from pillar
  2's centre, outside its 6.05 yd skirt and 1.7 yd above the ring. No floor leg
  started there, so the platform hold kept him 26 yd from Nefarian for 15
  minutes.
- **Demonology warlock.** He stayed on the pillar-1 top (local Z 9.3) through
  phase 3. The descent was proposed (the replay gives
  `pillar_descent_step_off`), but he never moved. The executor's rejection
  reason is not in the evidence.
  - Class evidence for the class agent: in the encounter he cast nothing that
    dealt damage. Only pet damage appears (Felguard melee, Legion Strike,
    Felstorm), with 47 casts per minute and 0.6% damage uptime.

**Deaths.** The scoreboard counts 1103 lethal damage events in the boss window:
- 341 Shadow of Cowardice on the shaman;
- bone-warrior melee from 318 s;
- breath, Tail Lash and Nefarian melee, mostly after Berserk.

The native signals disagree. They record 0 deaths and 0 resurrections, and
`alive_count` is 10 in every heartbeat. After each lethal hit, the next health
snapshot is pinned at 50% (or 20%) of maximum health, and buffs are gone (the
DK's maximum health fell by 8.5%). So either the deaths are real with
in-place revives that the native observer misses, or the snapshot is wrong.
`boss_window_deaths_unknown` (unreconciled basis) is the correct fail-closed
verdict. The reconciliation flags come from trash only
(`encounter_mismatch_count` 0): the ring buffer dropped 5896 early events.

**Melee fidelity.** Nefarian's harness flag (mean ratio 4.35) is Berserk:

| Nefarian swings | Mean after-attacker damage |
|---|---|
| Before Berserk | 67.6k (WCL 67.1k) |
| After Berserk | 5.8x that |

The calibration is right.

**Round 2 fixes** (`BotNefarianStranded.h`, tests `test_nefarian_stranded.py`):
- **Phase 2 target** (the user's tactic, authoritative). When a healer pillar
  kills its prototype, only the crossing pair leaves: exactly one healer and one
  damage dealer of the first healer pillar to finish swim to the tank pillar.
  - They go by the swim path only: rim, `LandInLiquid` step-off into the lava,
    swim, hop.
  - The pair's damage dealer has no damage target until the tank pillar's
    prototype is in reach (melee reach, or 30 yd for ranged)
    (`nefarian_crossing_under_way`). An earlier target would let native range
    recovery walk it off its pillar.
  - Everyone else whose prototype died holds on its pillar
    (`nefarian_platform_prototype_out_of_reach`). Nobody targets another
    pillar's prototype.
- **Stranded passenger.** On the resting raised floor, a stationary elevator
  passenger falls where it stands (`platform_stranded_fall`, Survival, the
  ledge-drop Fall stage) when it is:
  - clear of every pillar structure (more than 6.55 yd from a centre);
  - more than 1 yd above the model floor under it.

  The descent's Land stage now declares the model floor under the member. That
  is the ring for every pillar rim, as before.
- **Crossing.** The shared-runtime agent applied patch R8 (`LandInLiquid`) in
  round 2, so cross-pillar help is live. `CrossingSupported` is true, and
  TestCrossingHelp runs its departure checks.

## 8. Encounter damage fidelity

Every Nefarian's End creature still has DamageModifier 1 (the upstream reset). Nefarian and
Onyxia 10N are now derived from WCL `U` melee samples of three 10N kills
(`nefarian_wcl_melee_samples_v1.json`) with the registry method, and staged:

- Nefarian 41376: 201 landed rows, 164 under a -10% done aura (Scarlet Fever 81130 or
  Curse of Weakness 702). Bounds on DamageModifier x 1.01 are 12.818–12.928, so
  DamageModifier is 12.691–12.800. Chosen **12.75**; the sample mean implies 12.907
  effective (12.8775 chosen).
- Onyxia 41270: 37 landed rows, 35 under Scarlet Fever. Bounds are 10.314–10.465, so
  DamageModifier is 10.212–10.361. Chosen **10.34375**. The upper bound rests on fully
  absorbed rows, whose `U` is a WCL estimate; two of them read 42,883 in different kills.
- Files: `sql/custom/world/2026_09_27_24_nefarian_damage_modifier.sql` and
  `sql/custom/world/2026_09_27_25_nefarian_onyxia_damage_modifier.sql` (promoted 2026-09-27; the DB updater applies it at worldserver startup). The registry rows are applied.

| Creature | Class, level, attack time | Native swing at DM 1 | Status |
|---|---|---|---|
| Nefarian 41376 (10N) | 1, 88, 1500 ms | 4,553–6,764 | staged 12.75 |
| Nefarian 51104–51106 | 1, 88, 1500 ms | 4,553–6,764 | open |
| Onyxia 41270 (10N) | 1, 88, 1500 ms | 4,553–6,764 | staged 10.34375 |
| Onyxia 51116–51118 | 1, 88, 1500 ms | 4,553–6,764 | open |
| Animated Bone Warrior (41918, one template for all modes) | 4, 85, 2000 ms, BaseVariance 0.5 | 5,470–8,175 | open (rows mix Empower stacks) |
| Chromatic Prototype | PassiveAI, never swings | — | not applicable |
| Lord Victor Nefarius | PassiveAI | — | not applicable |
| Stalkers | — | — | not applicable |

The bone warrior and the other modes wait for stack-matched or same-mode samples.

## 9. Acceptance observations

These are the contract's `acceptance_observations`: passengers before the pull, the lust
within about 5 s of the Onyxia pull and every DPS on Onyxia, separation over 50 yd, no
breath on non-tanks, Onyxia's charge below 100, every bot floating, swimming and hopping
onto its pillar with about 8 magma ticks and none after the hop, every Blast Nova
interrupted, no phase 2 Nefarian damage, pillars left before landing without fall
damage, no active bone warrior in Nefarian's front cone and none hit by his breath,
Nature's Grasp cast when warriors reach the Feral, no repeated Shadowblaze ticks, native
clear with 0 boss-window deaths.

## 10. Unresolved (fidelity_blocked)

1. The creature melee DamageModifier: Nefarian and Onyxia 10N are promoted to
   `sql/custom/world`; the bone
   warrior and the 25N/10H/25H templates are open.
2. Nefarian's phase 1 Tail Lash (unobserved) and the cone geometry. Breath ticks are
   resolved (3; SpellMgr patch requested).
3. Onyxia's charge rate and the Electrocute increment.
4. Barrage targets per cast. The cadences are resolved: Blast Nova 13 s (native is
   right), Barrage 3.2 s (repaired).
5. The Shadowblaze Spark spread. The schedule is confirmed by WCL.
6. The bone warrior lifetime. The 10N count of 4 is confirmed by WCL.
7. Heroic: the user expects the Onyxia burn may not hold on heroic or with lower gear.
   Heroic keeps the Electrocute budget, untested; heroic magma (+2000 per 81118 stack)
   makes the 8.4 s swim cost about 96k per bot.
8. Heroic Dominion, Cinders, and the end of phase 2.

Resolved by WCL on 2026-09-27: the kill references and timelines, and 10N health (native
equals the WCL-derived values; the Wowhead guide is wrong).

Resolved this round: pillar access and the magma level (section 3a). The swim float
depth (1.2 yd) is a modelling choice; the hop stays lawful down to 1.35 yd.

## Sources

0. **User raid experience 2026-09-26** (first-hand; authoritative over the guides):
   composition, the Onyxia burn, the swim-and-hop ascent, the Feral's Nature's Grasp
   kite, and bone warriors kept out of Nefarian's front.
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
9. **Warcraft Logs**, Cataclysm Classic, Nefarian's End 10-player Normal kills, read
   2026-09-27 through the user's authorized Chrome session:
   - <https://classic.warcraftlogs.com/reports/MxFq7TRbvnjGY1hJ?fight=35> (2024-10-28);
   - <https://classic.warcraftlogs.com/reports/cYg4C93QNdqKfPF1?fight=18> (2025-01-31);
   - <https://classic.warcraftlogs.com/reports/farY2cm8JMTB1jGh?fight=10> (2025-01-15).
