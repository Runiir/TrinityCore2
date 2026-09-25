# Chimaeron (Blackwing Descent)

Status (2026-09-25, round 2): research packet, native script audit and the 10N bot
strategy are done. Warcraft Logs (WCL) extraction is blocked by a human-verification
gate, so every WCL-dependent value is still open. Fidelity state: `fidelity_blocked`.
The fidelity target is Cataclysm Classic 4.4.2 (build 59185); the execution client is
4.3.4 (build 15595). This page separates encounter truth, current repository behavior
and the bot tactic. Machine-readable files:

- contract: `experiments/configs/cata_raid_encounters/blackwing_descent/chimaeron_v1.json`
- claim ledger: `experiments/configs/cata_raid_encounters/blackwing_descent/chimaeron_ledger_v1.json`
- WCL reference and cast timelines (empty until extraction): `chimaeron_wcl_dps_reference_v1.json`,
  `chimaeron_wcl_cast_timelines_v1.json` in the same directory
- raid target: `experiments/configs/raid_targets/blackwing_descent_10n_chimaeron.json`

## Sources

| Source | Authority | Used for |
| --- | --- | --- |
| 4.3.4 client `data/dbc/enUS` Spell/SpellEffect/SpellDifficulty/SpellDuration rows (hashes in the ledger) | execution client | damage, radius, durations, stacks, mixture threshold, Mortality text |
| TDB 4.3.4.22011 snapshot plus the `sql/updates` audit | historical DB | templates, gossip chain, waypoints, spell_proc, health and melee inputs |
| Blizzard, [Patch 4.0.6 hotfixes](https://worldofwarcraft.blizzard.com/en-gb/news/9981073/patch-406-hotfixes-and-406a-changes-last-update-march-29), entry of 9 February 2011 | official | Caustic Slime excludes Break-affected targets |
| BigWigs_Cataclysm v11.0.13 `Blackwing/Chimaeron.lua` (commit 650bab0) | pinned addon | timers |
| DBM-Cataclysm `BlackwingDescent/Chimaeron.lua` (commit 4b02efe) | pinned addon | timers, outage rule |
| Wowhead, [Chimaeron Strategy Guide](https://www.wowhead.com/cata/guide/raids/blackwing-descent/chimaeron-strategy), Beanna, updated 2024-06-04, read 2026-09-25 | current guide | tactics, health |
| Icy Veins, [Chimaeron Encounter Guide](https://www.icy-veins.com/cataclysm-classic/chimaeron-encounter-guide-strategy-abilities-loot), Abide, updated 2024-07-29, read 2026-09-25 | current guide | tactics, swing interval |
| repository `boss_chimaeron.cpp`, `blackwing_descent.cpp`, `instance_blackwing_descent.cpp` | implementation | native behavior |

## Encounter truth (10N unless stated)

- **Start.** Talking to Finkle Einhorn (44202, gossip menus 11812 → 11834 → 11835 →
  11836 → 11837) activates the Bile-O-Tron 800 (44418). It spreads Finkle's Mixture
  (82705): while a player is above 10,000 health, no hit can take them below 1 health.
  The Bile-O-Tron patrols the room (waypoint path 4441800). Chimaeron wakes up and attacks
  the nearest player within 70 yd (native: 23 s after the gossip; BigWigs shows 30 s).
- **Boss.** Level 88 boss, BaseAttackTime 4000 ms (Icy Veins also reports a 4 s swing), combat
  reach 20 yd (display 33308), so both tank spots and the melee spots are inside his reach.
- **Caustic Slime** (82871 → 82913 → 82935): every 5 s, 2 random players (the current victim
  excluded) take 235,200 Nature damage split among players within 6 yd of the impact, plus
  -75% hit chance for 2.5 s. The 25-player row is 270,480, which is the value in Wowhead's ability
  table. Since the 4.0.6 hotfix, Break-affected players are only chosen when too few others remain.
- **Break** (82881): the current victim takes +25% physical damage per stack and does 15% less
  healing per stack, 4 stacks, 60 s.
- **Double Attack** (88826): a one-charge buff (spell_proc: next auto attack) that makes the next
  swing strike twice (82882, one extra attack). Natively it shares Break's 15 s timer, and DBM agrees.
- **Massacre** (82848): a 4 s cast that deals 999,999 damage to every player. First cast starts at
  26 s, then every 30 s (native and DBM). Afterwards Chimaeron drops Double Attack and resets his swing
  timer (Blizzard hotfix of January 2011).
- **Systems Failure.** After some Massacres the Bile-O-Tron is knocked out: stunned (88853), with no
  mixture for 26 s (Reroute Power 88861). Chimaeron gets Feud (88872) for 30 s and does not melee.
  Caustic Slime resumes 19 s after the Massacre cast start (native, DBM).
- **Mortality at 20%**: 82890 reduces healing received by players by 99%. 82934 makes Chimaeron
  immune to taunt (client text) and increases his damage taken by 10%. Slime, Break and Massacre stop.
  Double Attack comes 1 ms after the transition.

### Mode matrix

| Mode | Entry | Native health | Guide health | Swing | Slime damage | Slime targets |
| --- | --- | ---: | ---: | --- | ---: | --- |
| 10N | 43296 | 20,699,972 | 25.9M | 4.0 s | 235,200 | 2 |
| 25N | 47774 | 72,492,848 | 90.6M | 2.0 s | 270,480 | 4 (script) / 2 (guides) |
| 10H | 47775 | 36,246,424 | 36.2M | 2.0 s | 235,200 | 2 (script) / 4 (guides) |
| 25H | 47776 | 126,776,592 | 126.8M | 2.0 s | 270,480 | 4 |

Native health is `gt_npc_total_hp_exp3[88].Warrior` 85,892 × HealthModifier. The heroic values match
the guide. Both normal values are exactly the guide value divided by 1.25. This is **unresolved**
until a WCL health derivation.

## Timers: native versus pinned addons

| Event | Native | Addons | State |
| --- | --- | --- | --- |
| Massacre | 26 s, then 30 s | DBM 26/30, BigWigs 25 | agree |
| Break and Double Attack | 5 s, then 15 s | DBM 4.5/15, BigWigs 4.8/14.2 | agree |
| Break after Massacre start | 11 s | DBM 14, BigWigs 13.6 | conflict, waits for WCL |
| Caustic Slime after Massacre start | 19 s | DBM 19 | agree |
| First Caustic Slime after engage | 5 s | BigWigs 15 | conflict |
| Knockout | 40/60/80/100% per Massacre | DBM: after the 2nd or 3rd, the 3rd always | conflict |
| Wake-up after gossip | 23 s | BigWigs 30 | conflict |
| Berserk | none | 450 s (DBM marks it heroic) | unresolved |

## Native script audit (repository)

Registration, instance bindings (boss 43296, Finkle 44202, Bile-O-Tron 44418), encounter 1023,
the gossip chain and the waypoint path are present. The TDB rows cover all the scripted spells.
Round-2 repairs in `boss_chimaeron.cpp`:

1. `_killedPlayerCount` was never initialized, and a compatibility-mode respawn (same AI object,
   `Reset()` only) kept the knockout chance, counter and Feud state. `Initialize()` now restores
   them, and engage resets the counter.
2. Caustic Slime targeting now follows the official Break exclusion (4.0.6 hotfix text). The
   victim stays excluded, as before.
3. TrinityCore maps Mortality's mechanic-immunity misc value 477 to Bladestorm-style control
   immunity, not taunt. Phase two now applies taunt immunity (ATTACK_ME effect and MOD_TAUNT state),
   and Reset and evade remove it.
4. `GetTimeUntilEncounterMechanic(82848)` publishes the native Massacre schedule for observers
   (0 while casting or overdue). This is observation only.

These are deferred until WCL evidence exists. We do not change the native code on addon data alone:
Break and Double Attack at 13.6-14 s after a Massacre, the first Slime at 15 s after engage, the
knockout rule, normal health, and the boss melee DamageModifier (still the upstream value 1; at
modifier 1 a 10N swing rolls 12,142-18,038 before the +1% auto-attack bonus).

## Bot strategy (canonical 10N composition)

The composition is 2 tanks (Blood Death Knight, Feral Druid) and 3 healers (Holy Paladin,
Discipline Priest, Restoration Shaman), plus 5 DPS: BM Hunter, Fire Mage, Retribution Paladin,
Assassination Rogue and Demonology Warlock. Duties are chosen by capability, not by slot:

- **Break tank.** Blood DK first, then Protection Paladin, Protection Warrior and Feral. He only has
  to stay above the floor. The next tank soaks Double Attack. A configured `main_tank` lease wins.
- **Tank healer.** Holy Paladin first, then Discipline Priest, Holy Priest, Restoration Druid and
  Restoration Shaman.
- **Lust owner.** A mage (Time Warp) first, then a shaman (Bloodlust, or Heroism when that is the
  variant the bot knows).
- **Barrier owner.** The Discipline Priest.
- **Spirit Link owner.** The Restoration Shaman.

Phase behavior (`src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Chimaeron/`):

- **Prewake** (route nodes `bwd.chimaeron.regroup`, `.finkle` and `.wake_wait` while the boss
  sleeps). Offense is suppressed so nobody pulls him before the Bile-O-Tron is active, unless
  another hostile is fighting a raid member (a patrol or leftover pack in the composed route). On
  the wake wait, the Break tank stands 9 yd north of the boss and everyone else at least 16 yd away,
  so the native wake-up picks the Break tank. The native route keeps the nodes and their
  completions. The Finkle interaction itself is the route's `gossip_select_sequence` node.
  Back asleep at `bwd.chimaeron.encounter` (the native reset after a wipe: not in combat and the
  instance encounter not in progress), the plan keeps the node so the generic boss adapters never
  pull him without Finkle's Mixture, suppresses offense (`encounter_reset_boss_asleep`), and stages
  as on the wake wait once the Bile-O-Tron is active again. Waking him again needs Finkle's gossip,
  which is a route request (see Live evidence).
- **Mixture up.** Both guides say to spread at least 6 yd, which minimizes the -75% hit debuff and
  keeps each Slime on one player. Slots are at least 11 yd apart, and a member only moves when
  more than 2 yd off its slot, so two members are always more than 6 yd apart:
  - Break tank 10 yd north of the boss;
  - Double Attack tank 13 yd at -60 degrees;
  - up to three melee 11 yd behind (±30 degrees for two, 60 degrees apart for three);
  - healers, then ranged DPS, 22 yd behind over ±75 degrees (at most six; melee reach against
    Chimaeron is 22.8 yd); any overflow sits on a 33 yd arc 20 degrees apart.

  The formation centre is the boss's home while he is tanked in place. Slots are clamped to the
  Bile-O-Tron patrol extent.
- **Outage** (no mixture): everyone, tanks included, stacks on a 1.5 yd ring 8 yd behind the boss,
  so every Slime is split across the raid. Healer cooldowns:
  - the Discipline Priest casts Power Word: Barrier at 16.5-12 s of Feud remaining (Slimes resume);
  - the Restoration Shaman casts Spirit Link Totem at 11-7 s.
- **Taunt exchange:**
  - when Double Attack is up and the Break tank holds the boss, the Double Attack tank taunts;
  - once the charge is spent, the Break tank taunts back;
  - during Feud, neither taunts until the last 2.5 s;
  - a non-tank victim is taken back by the Break tank;
  - the burn release makes the Double Attack tank's taunt the first action: he takes the boss and
    retakes it from anyone until Mortality, and the Break tank never taunts again (before the
    release the ordinary exchange continues at any health);
  - under Mortality nobody taunts.
- **Healing:**
  - the boss victim at or below 20,000 gets the tank healer and the first raid healer;
  - the Double Attack tank is healed toward full while a doubled swing is due;
  - every mixture-protected player at or below 20,000 health (bot margin over the 10,000 floor) is
    healed in health order, and the healers split that list;
  - during an outage, healers heal by health percentage;
  - under Mortality nothing is published (healing is 99% reduced).
- **Burn window** (both guides pause around 22-25%, then lust and push). One sequence, held →
  armed → handoff → push:
  - from 23%, non-tanks hold damage; tanks keep attacking above 21.5% (threat, Death Strike) and
    hold below it, so their damage cannot carry the boss into Mortality;
  - the release needs readiness: mixture up, no Massacre casting or due within 8 s, both tanks at
    80% or more (the Break tank is healed to 80% inside the window). The hold is bounded: after two
    Massacre cycles (60 s) or with fewer than two living healers it releases anyway;
  - last chance: if damage the hold cannot stop (damage over time, pets) carries the boss to 21%
    unreleased, the handoff arms anyway while the non-tanks keep waiting for the release. The 1%
    margin is about 12.5 s of the hold's residual damage, longer than the 8 s taunt cooldown, so a
    taunt just spent on a Double Attack soak is back before 20%. Above 20.5% the arm is not sticky
    while held: if the boss stops losing health for 16 s (longer than Bane of Doom's 15 s tick), the
    drift is over, the arm and its handoff are dropped and the Break tank takes Break again; a new
    drift at or below the line re-arms it. At or below 20.5% it stays armed;
  - once armed (release, last chance, hold cap or healers down) the Double Attack tank taunts first,
    even during Feud (taunting the pacified boss is harmless and sets the victim his melee resumes
    on), and holds the boss into Mortality; the Break tank stops taunting and stands down while the
    Double Attack tank lives, so his threat never pulls the boss back onto his Break stacks;
  - non-tanks are released once the handoff lands, or after one taunt cooldown (8 s). If that
    timeout fires with the handoff still missing, the Break tank resumes attacking to keep his
    threat, recovers any non-tank victim, and the Double Attack tank keeps retrying (the retry is
    its own mechanic, `taunt_mortality_handoff_retry`, in the decision trace);
  - then the lust owner lusts and the raid pushes into Mortality.

  Every step is a cohort latch (`src/server/game/Bots/BotEncounterLatches.h`, module `chimaeron` in
  `BotChimaeronBurn.h`): the blackboard publisher sets it once per revision for the Chimaeron node,
  so every bot reads the same state whatever its decision cadence. Latches reset on a new scope key
  (attempt, wipe generation, route node), on a new boss object, and when the boss is seen out of
  combat. The native encounter epoch in the key is authoritative only for Magmaw today, so for
  Chimaeron the disengage reset is the pull boundary. In Mortality the Discipline Priest shields the
  victim whenever Weakened Soul allows and uses Pain Suppression on a failing tank unless it was cast
  within its 3 minute cooldown. Absorbs still work.

## Open items (unresolved)

- WCL 10N references:
  - per-spec DPS, roster and duration;
  - cast timelines;
  - melee U samples for the DamageModifier calibration;
  - health derivation;
  - Systems Failure frequency;
  - post-Massacre Break timing.

  The planned reports are in the ledger's `wcl_extraction_plan`.
- The 4.4.2 client rows for the spell chain (`extract_442_client_spell_rows --follow-triggers`).
- Heroic behavior (Shadow Whip delay, Mocking Shadows), the 25N/10H Slime target mapping, and
  retail reset, loot and achievement persistence.

## Acceptance observations for the live shard

1. `native_route_postcondition` `aura_present` (44418 has 82705) after the Finkle node, then
   `creature_aggressive_with_victim` with the Break tank as the first victim.
2. No Massacre deaths while the mixture is up. Each Double Attack charge is consumed on the Double
   Attack tank.
3. During an outage the raid is stacked within 6 yd of each Slime target, with no outage deaths.
4. No taunt lands after Mortality. The kill is a native clear with 0 boss-window deaths.

## Live evidence

- Round 2 (`blackwing_descent_10n-r02-b1-20260925T172051Z`, instance 1, Magmaw and Omnotron
  seeded DONE, Chimaeron NOT_STARTED): `native_interaction_timeout` at `bwd.chimaeron.finkle`
  after exactly the contract's 90 s. The gossip never opened:
  - The Finkle owner (hunter, lowest dps GUID) asked the planner for Finkle's own position.
  - Finkle stands on a Soapbox gameobject (180403), 1.585 yd above the navmesh floor (72.36).
  - The planner rejected that position on every tick with `route_destination_endpoint_mismatch`:
    horizontal distance 0, vertical 1.585, above its 1.5 yd tolerance.
  - The rejected approach counted no attempt, so the node could only time out.

  The lockout, Finkle's spawn and gossip state, and the prewake suppression were not involved:
  - Finkle resolved uniquely.
  - The suppression claims only the pet resource and committed beside the rejected move.
- Fix (shared, round 3): the interaction owner walks the complete native path to a point
  2.5 yd short of the target, when the target is within reach from there. For Finkle that
  point is (-113.41, 40.89, 72.36), 2.96 yd from him.
- Round 3 (`blackwing_descent_10n-r03-b1-20260925T200656Z`, T = first boss melee): the route
  reached the encounter, and the prewake plan worked:
  - The gossip opened at T-27.7 (menus 11812 through 11837, one select per second) and the
    Bile-O-Tron had 82705 at T-22.4.
  - The native wake came 22.9 s later: the first victim was the Break tank, staged 9 yd north.
  - The Double Attack exchange ran (Growl at T+5.8 and T+21.0, Dark Command at T+8.9 and T+17.8).
  - Each Caustic Slime hit one member alone (163-179k, Finkle's Mixture left them at 1 HP).

  Then the raid wiped with 0 heals and 0 damage (only Eye for an Eye reflects), because every
  member's decision kernel committed `raid.prepull_consumables` (Mechanic, utility 12, GCD, cast
  and target lanes) with `raid_prepull_wait_alive_and_healed` for the whole fight. Heals, rotations
  and the boss adapter were deferred with `resource_lane_owned`. The native wake engages the raid
  before the boss node starts, so the boss-node prepull could never complete. The deaths:
  - the mage (slime then melee, T+13.1), the hunter (T+22.2) and the warlock (T+27.2);
  - Massacre at T+30.6 took everyone below 10k HP;
  - single melee hits killed the four members left at 1 HP (T+34.3 to T+46.5).

  The recovery ride (`route_recovery_engaged:bwd.transit.lower_wing_elevator`, T+56.3) then carried
  only the three healers. They were the only members without that candidate: an injured member out
  of combat exempts healers. The candidate deferred the other seven members' surface walks (they
  need the cast lanes too) every elevator cycle. Each walk aborted 1 s later with
  `transport_rest_window_too_short`, so `route_recovery_complete` never came.
- Fixes (round 4):
  - Shared prepull patch: stand down while anyone on the roster is in combat or a recovery ride
    is engaged.
  - Chimaeron-owned: a boss back asleep at the encounter node is Prewake and is never pulled.
  - Route request: re-run Finkle's gossip after a wipe at the encounter node.
