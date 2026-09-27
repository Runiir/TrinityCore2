# Chimaeron (Blackwing Descent)

Status (2026-09-27, raid program round 1): research packet, native script audit and the 10N bot
strategy are done. Warcraft Logs (WCL) 10N data from two kills now resolves health, the boss
melee DamageModifier (20, promoted to `sql/custom/world`), the first Caustic Slime timer and the DPS references (see
"WCL 10N observations"). Other claims stay unresolved, so the fidelity state is still
`fidelity_blocked`.
The fidelity target is Cataclysm Classic 4.4.2 (build 59185); the execution client is
4.3.4 (build 15595). This page separates encounter truth, current repository behavior
and the bot tactic. Machine-readable files:

- contract: `experiments/configs/cata_raid_encounters/blackwing_descent/chimaeron_v1.json`
- claim ledger: `experiments/configs/cata_raid_encounters/blackwing_descent/chimaeron_ledger_v1.json`
- WCL reference and cast timelines: `chimaeron_wcl_dps_reference_v1.json`,
  `chimaeron_wcl_cast_timelines_v1.json` in the same directory
- melee calibration: `sql/custom/world/2026_09_27_20_chimaeron_damage_modifier.sql` and the
  registry patch `chimaeron_damage_calibration_registry_patch_v1.json` (same directory as the ledger)
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
| WCL [MxFq7TRbvnjGY1hJ fight 27](https://classic.warcraftlogs.com/reports/MxFq7TRbvnjGY1hJ?fight=27), 10N kill, 2024-10-28, read 2026-09-27 | observed kill | melee U samples, health, boss timeline, DPS, casts |
| WCL [xAhkN2y9YP3KRmnJ fight 14](https://classic.warcraftlogs.com/reports/xAhkN2y9YP3KRmnJ?fight=14), 10N kill, 2025-06-11, read 2026-09-27 | observed kill | Massacre/Mortality timing, DPS, casts |

## Encounter truth (10N unless stated)

- **Start.** Talking to Finkle Einhorn (44202, gossip menus 11812 → 11834 → 11835 →
  11836 → 11837) activates the Bile-O-Tron 800 (44418). It spreads Finkle's Mixture
  (82705): while a player is above 10,000 health, no hit can take them below 1 health.
  The Bile-O-Tron patrols the room (waypoint path 4441800). Chimaeron wakes up and attacks
  the nearest player within 70 yd (native: 23 s after the gossip; BigWigs shows 30 s).
- **Boss.** Level 88 boss, BaseAttackTime 4000 ms (Icy Veins also reports a 4 s swing), combat
  reach 20 yd (display 33308), so both tank spots and the melee spots are inside his reach.
- **Caustic Slime** (82871 → 82913 → 82935): first cast 15 s after engage (WCL impacts at 17.2 s,
  BigWigs 15 s), then every 5 s, 2 random players (the current victim
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
the guide. Both normal values are exactly the guide value divided by 1.25. For 10N the WCL derivation
settles it: six consecutive resource rows of MxFq7TRbvnjGY1hJ fight 27 give exactly 20,699,972 (WCL
shows "20.7m"), the native value. The guide's 25.9M is not what Classic ran. 25N is still unobserved.

## Timers: native versus pinned addons

| Event | Native | Addons | State |
| --- | --- | --- | --- |
| Massacre | 26 s, then 30 s | DBM 26/30, BigWigs 25 | agree |
| Break and Double Attack | 5 s, then 15 s | DBM 4.5/15, BigWigs 4.8/14.2; WCL 4.6 s, then every third swing (14.4 s) | agree within a swing |
| Break after Massacre start | 11 s | DBM 14, BigWigs 13.6; WCL 13.6 s twice, on a swing | conflict (open, see below) |
| Caustic Slime after Massacre start | 19 s | DBM 19; WCL impacts at +21.5 s (flight) | agree |
| First Caustic Slime after engage | 15 s (was 5 s until 2026-09-27) | BigWigs 15; WCL impacts at 17.2 s | agree (repaired) |
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

5. (2026-09-27) The first Caustic Slime is scheduled at 15 s instead of 5 s. BigWigs and the WCL
   kill agree: the first impacts land at 17.2/17.5 s, after the missile flight, and none earlier.

Still deferred:

- Break and Double Attack after a Massacre. In WCL they land on a melee swing: every third swing,
  and on the second swing after Massacre's swing reset (13.6 s after the cast start at 4.8 s
  swings). The native code uses 11 s/15 s timers. A fixed 13.6 s timer would only match one swing
  speed, so this needs an implementation decision (swing-bound or timer), not a constant swap.
- The knockout rule.
- The Slime repeat: native 5 s, while the WCL impacts are 5.9-6.4 s apart (2 intervals).

The boss melee DamageModifier for 10N is 20, derived from WCL. The migration was promoted to
`sql/custom/world` on 2026-09-27; the DB updater applies it at the next worldserver startup. At modifier 1 a 10N swing rolls 12,142-18,038 before the +1% auto-attack bonus; 20 gives
245-364k at the WCL U stage.

## Bot strategy (canonical 10N composition)

The composition is 2 tanks (Blood Death Knight, Feral Druid) and 3 healers (Holy Paladin,
Discipline Priest, Restoration Shaman), plus 5 DPS: Survival Hunter (Beast Mastery until
2026-09-26), Fire Mage, Retribution Paladin, Assassination Rogue and Demonology Warlock. Duties are
chosen by capability, not by slot:

- **Break tank.** Blood DK first, then Protection Paladin, Protection Warrior and Feral. He only has
  to stay above the floor. The next tank soaks Double Attack. A configured `main_tank` lease wins.
- **Tank healer.** Holy Paladin first, then Discipline Priest, Holy Priest, Restoration Druid and
  Restoration Shaman.
- **Lust owner.** A mage (Time Warp) first, then a shaman (Bloodlust, or Heroism when that is the
  variant the bot knows). The owner is chosen from the shared snapshot, which carries no spell book,
  so the runtime casts only a lust spell the owner knows (`Player::HasSpell`, as Maloriak's raid
  haste does). An owner that knows none skips it with `chimaeron_lust_spell_unknown`; the round-4
  canonical Fire Mage did not know Time Warp until M provisioned it.
- **Barrier owner.** The Discipline Priest.
- **Spirit Link owner.** The Restoration Shaman.

Phase behavior (`src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Chimaeron/`):

- **Prewake** (route nodes `bwd.chimaeron.regroup`, `.finkle` and `.wake_wait` while the boss
  sleeps). Offense is suppressed so nobody pulls him before the Bile-O-Tron is active, unless
  another hostile is fighting a raid member (a patrol or leftover pack in the composed route). On
  the wake wait, the Break tank stands 9 yd north of the boss and everyone else at least 16 yd away,
  so the native wake-up picks the Break tank. The native route keeps the nodes and their
  completions. The Finkle interaction itself is the route's `gossip_select_sequence` node.
  Back asleep at `bwd.chimaeron.encounter` (the native reset after a wipe: out of combat, no victim
  and REACT_PASSIVE, which the script sets only while he sleeps; the boss's own state, not the
  instance-wide encounter flag that another BWD boss in progress would also set), the plan keeps the
  node so the generic boss adapters never pull him without Finkle's Mixture, suppresses offense (`encounter_reset_boss_asleep`), and stages
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

## WCL 10N observations (2026-09-27)

GPT-6 Astra read both kills through its browser surface (`codex exec -m gpt-6-astra` with
`CUA_REPL_ENABLED_SURFACES=browser`). No verification page appeared and none was clicked. Plain
HTTP requests still get the Cloudflare page. Report `Y8ajQ7dbmKMG1RZy` has no Chimaeron encounter.

| Kill | Duration | Item level | Raid DPS | Roster | Massacres | Mortality | Deaths |
| --- | ---: | ---: | ---: | --- | ---: | ---: | --- |
| MxFq7TRbvnjGY1hJ fight 27 | 95.3 s | 359.5 | 217,144.7 | 1 tank (Blood DK), 1 healer (Holy Paladin), 8 DPS | 2 (26.0, 56.0 s) | 78.1 s | tank, Mortality melee at 93 s |
| xAhkN2y9YP3KRmnJ fight 14 | 60.0 s | 401.4 | 345,080.1 | 1 tank (Blood DK), 1 healer (Restoration Shaman), 8 DPS | 1 (26.0 s) | 50.2 s | Fire Mage, Cauterize at 35 s |

- **Melee.** Fight 27 has 23 Chimaeron melee rows on the only tank: 17 landed, with U values of
  253,562-345,349, plus 4 parries, 1 dodge and 1 miss. U does not change with Break stacks (only
  WCL's mitigation % does), so it is the attacker-side stage. Scarlet Fever was up 5.2-34.3 s and
  52.5-81.5 s. The bounds are 19.3757 (largest reduced hit 314,547 / (0.9 x native max)) and 20.88
  (smallest unreduced hit / native min), or 19.1838-20.67 once the +1% auto-attack bonus is
  included. DamageModifier 20 is promoted to `sql/custom/world`.
- **Neither kill had a Systems Failure or Feud** (two Massacres and one). Neither is long enough
  to test the 450 s berserk.
- **Single-tank kills.** Both groups tanked Chimaeron with one Blood DK. He held 4 Break stacks
  without a swap and died to a Mortality swing just before the kill. The canonical bot roster keeps
  two tanks and the taunt exchange. The matched DPS targets (median across both kills) are Blood DK
  25,888.5, Survival Hunter 37,218.05 and Retribution Paladin 25,345.0. Fire Mage, Assassination
  Rogue and Demonology Warlock keep the WoWSims fallback, and the Feral tank has no reference.

## Open items (unresolved)

- WCL 10N: Systems Failure frequency (longer kills), post-Massacre Break timing (swing-bound
  versus timer), Slime repeat, berserk, and a kill that covers Fire Mage, Assassination Rogue,
  Demonology Warlock or a Feral tank.
- The DamageModifier is promoted and the registry row applied (2026-09-27); confirm on a live kill
  that `encounter_fidelity.boss_melee` is within ±10% of WCL.
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
- Round 3 (`blackwing_descent_10n-r03-b1-20260925T200656Z`, T = the combat log's first boss
  melee, 1790366878461): the route reached the encounter, and the prewake plan worked:
  - The gossip opened at T-28.1 (menus 11812 through 11837, one select per second) and the
    Bile-O-Tron had 82705 at T-22.9.
  - The native wake came 22.9 s later: the first victim was the Break tank, staged 9 yd north.
  - The Double Attack exchange ran: Growl at T+5.4 and T+20.5, Dark Command at T+8.4, T+17.3 and
    T+25.9.
  - Each Caustic Slime hit one member alone (163-173k; Finkle's Mixture left them at 1 HP).

  Then the raid wiped with 0 heals and 0 damage (only Eye for an Eye reflects), because every
  member's decision kernel committed `raid.prepull_consumables` (Mechanic, utility 12, GCD, cast
  and target lanes) with `raid_prepull_wait_alive_and_healed` for the whole fight. Heals, rotations
  and the boss adapter were deferred with `resource_lane_owned`. The native wake engages the raid
  before the boss node starts, so the boss-node prepull could never complete. The deaths (combat
  log times of the killing blows):
  - the mage (a slime at T+11.1, then a melee hit at T+12.3), the hunter (a second, split slime at
    T+21.5) and the warlock (a third slime at T+26.4);
  - Massacre at T+30.2 killed the three members left below 10k HP by slimes (Discipline Priest,
    Restoration Shaman, Retribution Paladin) and left the other four at 1 HP;
  - single melee hits killed those four at T+33.9 (Blood DK), T+37.9 (Feral), T+42.0 (Holy
    Paladin) and T+46.0 (Assassination Rogue).

  The recovery ride (`route_recovery_engaged:bwd.transit.lower_wing_elevator`, T+55.8) then carried
  only the three healers. They were the only members without that candidate: an injured member out
  of combat exempts healers. The candidate deferred the other seven members' surface walks (they
  need the cast lanes too) every elevator cycle. Each walk aborted 1 s later with
  `transport_rest_window_too_short`, so `route_recovery_complete` never came.
- Fixes (round 4):
  - Shared prepull patch: stand down while anyone on the roster is in combat or a recovery ride
    is engaged.
  - Chimaeron-owned: a boss back asleep at the encounter node is Prewake and is never pulled.
  - Route request: re-run Finkle's gossip after a wipe at the encounter node.
