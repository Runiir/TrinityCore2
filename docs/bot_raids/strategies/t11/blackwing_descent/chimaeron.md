# Chimaeron (Blackwing Descent)

Status (2026-09-27, raid program round 1): research packet, native script audit and the 10N bot
strategy are done. Warcraft Logs (WCL) 10N data from two kills now resolves health, the boss
melee DamageModifier (20, promoted to `sql/custom/world`), the first Caustic Slime timer and the DPS references (see
"WCL 10N observations"). Other claims stay unresolved, so the fidelity state is still
`fidelity_blocked`. Round 2 of the raid program (2026-09-27) diagnoses the round-1 runs (see "Live
evidence: raid program round 1") and makes these changes:

- It keeps the native Break/Double Attack timers.
- Healers pre-heal the Double Attack soaker after each Massacre.
- The raid pushes during Feud and releases the hold when a tank is down.
- Hunters stand beyond their minimum range.

Round 3 (2026-09-30, tier-11 gear, about item level 359) replaces the DPS references with seven
tier-11 kills, resolves the knockout rule, the Slime repeat and Feud behaviour for 10N from WCL
(see "WCL 10N observations, round 3"), and repairs the native script to match for 10N only: 25N,
10H and 25H keep the previous script rules (see "Round-3 repairs"). The user then
settled the berserk (2026-09-30, see "Berserk decision"), so 10N stays `fidelity_blocked` on two
claims: the helper reset observation and retail reset/credit/loot.
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
| WCL [xAhkN2y9YP3KRmnJ fight 14](https://classic.warcraftlogs.com/reports/xAhkN2y9YP3KRmnJ?fight=14), 10N kill, 2025-06-11, read 2026-09-27 | observed kill | Massacre/Mortality timing (DPS reference dropped in round 3: item level 401.4) |
| WCL tier-11 10N kills (nine, 2024-10-10 to 2024-10-28, raid item level 354.8-361.1), read 2026-09-30 | observed kills | DPS references, Massacre/Feud/Mortality times |
| WCL [Chimaeron 10N rankings](https://classic.warcraftlogs.com/zone/rankings/1023?boss=1023&difficulty=3&size=10&search=duration.95.900), first 12 distinct kills (Phase 4.5), read 2026-09-30 | observed kills | knockout census, Slime cadence, Feud and Mortality events, berserk search |
| wago.tools 4.4.2.59185 client tables (`extract_442_client_spell_rows --follow-triggers`), read 2026-09-30 | reference client | 4.4.2 spell rows (equal to 4.3.4 for every 10N value) |

## Encounter truth (10N unless stated)

- **Start.** Talking to Finkle Einhorn (44202, gossip menus 11812 → 11834 → 11835 →
  11836 → 11837) activates the Bile-O-Tron 800 (44418). It spreads Finkle's Mixture
  (82705): while a player is above 10,000 health, no hit can take them below 1 health.
  The Bile-O-Tron patrols the room (waypoint path 4441800). Chimaeron wakes up and attacks
  the nearest player within 70 yd (native: 23 s after the gossip; BigWigs shows 30 s).
- **Boss.** Level 88 boss, BaseAttackTime 4000 ms (Icy Veins also reports a 4 s swing), combat
  reach 20 yd (display 33308), so both tank spots and the melee spots are inside his reach.
- **Caustic Slime** (82871 → 82913 → 82935): first cast 15 s after engage (WCL impacts at 17.2 s,
  BigWigs 15 s), then every 6 s on 10N (WCL: two volleys per Massacre cycle, 5.8-6.1 s apart; 25N, 10H and 25H keep
  the native 5 s), 2 random players (the current victim
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
  mixture for 26 s (Reroute Power 88861). Chimaeron gets Feud (88872) for 30 s (WCL 30.011 s), cast
  at the Massacre's completion, and does not melee; on 10N no Break or Double Attack lands during it
  (25N, 10H and 25H still cast them).
  Caustic Slime continues, from 19 s after the Massacre cast start (native, DBM, WCL). The next
  Massacre still comes 30 s after the previous one and completes as Feud ends.
- **Knockout rule (10N, WCL census of 22 kills).** Count the Massacres since the pull or the last
  knockout: never on the first (0 of 30), about half on the second (11 of 24), always on the third
  (8 of 8). DBM's comment says the same ("after massacre 2~3 ... 3rd 100%"). 25N, 10H and 25H have
  no sample and keep the previous 40/60/80/100% roll.
- **Mortality at 20%**: 82890 reduces healing received by players by 99%. 82934 makes Chimaeron
  immune to taunt (client text) and increases his damage taken by 10%. Slime, Break and Massacre stop.
  Double Attack comes 1 ms after the transition; on 10N a Double Attack that comes due while Feud
  is still up is held until Feud ends (`Logic::HoldsDoubleAttackForFeudEnd`), then the 15 s cycle
  restarts. WCL: no Massacre after Mortality, and Double Attack returns every ~14.4 s (swing-bound).

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
| Break after Massacre start | 11 s | DBM 14, BigWigs 13.6; WCL 13.6 s twice, on a swing | native timer kept (doubled swing 13.5 s live) |
| Caustic Slime after Massacre start | 19 s | DBM 19; WCL impacts at +21.2-21.7 s (flight) | agree |
| Caustic Slime repeat | 10N 6 s (5 s until 2026-09-30); 25N/10H/25H 5 s | WCL 10N two volleys per cycle, 5.8-6.1 s apart, never a third | agree on 10N (repaired); other modes unresolved |
| First Caustic Slime after engage | 15 s (was 5 s until 2026-09-27) | BigWigs 15; WCL impacts at 17.2 s | agree (repaired) |
| Knockout | 10N 0/50/100% by position in the cycle (40/60/80/100% until 2026-09-30); 25N/10H/25H 40/60/80/100% | DBM: after the 2nd or 3rd, the 3rd always; WCL 10N 0/30, 11/24, 8/8 | agree on 10N (repaired); other modes unresolved |
| Break and Double Attack during Feud | 10N skipped (cast until 2026-09-30); 25N/10H/25H cast | BigWigs stops the normal Break bar; WCL 10N no Double Attack inside Feud | agree on 10N (repaired); other modes unresolved |
| Wake-up after gossip | 23 s | BigWigs 30 | conflict |
| Berserk | none | BigWigs 450 s; DBM marks it heroic; no 10N log past 160 s found | resolved, none in any mode (user raid experience 2026-09-30) |

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

Decided (2026-09-27, raid program round 2): Break and Double Attack keep the native 11 s/15 s
timers. In WCL they land on a melee swing (every third swing, and the second swing after
Massacre's swing reset, 13.6 s after the cast start at 4.8 s swings). Live round 1 with the native
timers put the doubled swing 13.5 s after each Massacre cast start and 14.6 s apart otherwise
(4.87 s swings under Frost Fever), within one swing of WCL. A swing-bound model would change no
observable 10N timing. The one real difference is when Break lands:

- natively at 11 s, instantly on the current victim, which is the Break tank who holds the boss;
- with a swing-bound model, on the doubled swing, which after the taunt is the Double Attack tank.

So the timer suits the two-tank exchange. Heroic and 25N (2 s swings) should be rechecked before
reuse.

Round-3 repairs (2026-09-30), each backed by the WCL observations below. Repairs 6-8 apply to 10N
only: the WCL evidence is 10N, and 25N, 10H and 25H keep the rules they had before (base c8e8bfe85b)
until they have logs of their own. The gate is `GetDifficulty() == RAID_DIFFICULTY_10MAN_NORMAL`
(`IsTenNormal()`), the idiom of the other Blackwing Descent scripts. The no-berserk decision below is
separate and covers every mode.

6. On 10N the knockout roll (40% at the first Massacre, +20% per miss, back to 40% after a knockout)
   became a cycle count: `_massacresInCycle` counts the Massacres since the pull or the last
   knockout and `Logic::KnockoutChancePct(tenNormal, position)` gives 0%, 50% and 100% for positions
   1, 2 and 3+. The other modes still get 40/60/80/100% from the same count. Round 1
   knocked out after Massacre 1 in 2 of 4 pulls and then after every Massacre, so the boss was
   pacified for most of those kills. No WCL kill has a first-Massacre or back-to-back knockout.
7. On 10N Caustic Slime repeats every 6 s instead of 5 s (`Logic::CausticSlimeRepeatMs`). A 5 s repeat
   adds a third volley 29 s after each Massacre cast start; WCL never shows one in ten cycles. The
   other modes keep 5 s.
8. On 10N, Break and Double Attack are skipped while Feud is up; their timers keep running. Pacify
   does not block them (the spells have no prevention type), so natively Break stacked on the pacified
   boss's victim during Feud. The other modes keep casting them
   (`Logic::SkipsBreakAndDoubleAttack`).

`tests/test_chimaeron_mode_gating.py` pins both sides: 10N gets repairs 6-8, and the previous rules
are compared with the base commit for every other mode.

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
    Chimaeron is 22.8 yd);
  - hunters first on a 33 yd arc 20 degrees apart, then any overflow. A hunter's shots have a
    5 yd minimum range that `Spell::GetMinMaxRange` extends by the melee range, 27.8 yd from
    the boss centre against his 20 yd reach. In round 1 the Survival Hunter on the 22 yd arc was
    rejected with `min_range_required` and meleed instead.

  The formation centre is the boss's home while he is tanked in place. Slots are clamped to the
  Bile-O-Tron patrol extent.
- **Outage** (no mixture): without a living hunter everyone, tanks included, stacks on a 1.5 yd
  ring 8 yd behind the boss, so every Slime is split across the raid. With one, the stack is a
  column on the rear axis. Within a band members are 1 yd apart sideways, compressed so the band
  is at most ±1.5 yd wide:
  - tanks and melee at 21.5 yd (inside the 22.8 yd melee range);
  - healers and casters at 25.1 yd;
  - hunters at 28.75 yd (beyond 27.8 yd).

  The column's arrival tolerance is 0.5 yd, not the stack's 1 yd. With it, two members of
  neighbouring bands are within 6 yd even when each is off its slot by the full tolerance directly
  away from the other. Static asserts in `BotChimaeronFormation.h` enforce this, and a test covers
  the worst corner. A Slime on either end is therefore still shared by six to nine players.

  The first version (bands at 20/24.5/29.5 yd with a 1 yd tolerance) failed that corner in
  review: with the hunter 0.9 yd back and the middle band 0.9 yd forward, the hunter's Slime had
  one recipient. Healer cooldowns, cast from the healers' band:
  - the Discipline Priest casts Power Word: Barrier at 15.5-12.5 s of Feud remaining (16.5-12 s
    until round 4). WCL puts the volleys at 12.3-12.8 s and 6.2-7.0 s left, so the 10 s Barrier
    covers both;
  - the Restoration Shaman casts Spirit Link Totem at 11-7 s.

  The two Slime volleys of an outage come at about 15 s and 9 s of Feud left, one for each
  cooldown. A second outage within their 3 minute cooldowns gets neither: the rule allows one
  every two to three Massacres, so a 150 s kill can have two. The executor rejects the cast and the
  healers keep healing by health percentage.
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
  - the Double Attack soaker is healed toward 95% while a doubled swing is due. The soaker is the
    Double Attack tank, or the victim once no second tank lives.
  - A swing is due while the charge is up, and also in the post-Massacre window. That window uses
    the native Massacre timer at 26-14 s: from the end of the cast until one swing after the 11 s
    reschedule. It also covers the first 12 s after engage.
  - In that window the first raid healer joins the tank healer on the soaker once the victim is
    off the floor, and the third healer starts on the raid floor. No Caustic Slime lands before
    19 s after the cast start. Round 1 lost both tanks to exactly this swing: the Feral at 34%
    health and the Blood DK at 65% with 4 Break stacks. The Discipline Priest and the Restoration
    Shaman were healing DPS players at 1 health.
  - every mixture-protected player at or below 20,000 health (bot margin over the 10,000 floor) is
    healed in health order, and the healers split that list;
  - nothing else is healed while the mixture is up (round 4). Every Massacre sets the raid back to 1
    health, so health above the floor is lost mana: Wowhead says to heal everyone above 10,000, and
    Icy Veins heals the Break tank to 10,000 and the Double Attack tank to full. A healer with no
    entry holds (`HealingDisabled`, reason `mixture_floor_only_conserve_mana`) instead of the
    runtime's default top-up of the lowest member below 94%. A hostile other than the boss fighting
    the raid lifts the hold;
  - during an outage, Feud pacifies the boss for the whole outage, so tanks are ordinary members of
    the stack. Everyone is first raised above the slime line, lowest absolute health first. The
    line is the member's share of both volleys (10N 2 × 235,200 / living, 25N 4 × 270,480 / living)
    plus 10,000: 57,040 with ten alive. Then members below 90% are healed by health percentage;
  - under Mortality nothing is published (healing is 99% reduced).
- **Healer mana cooldowns** (round 4). While the mixture is up, with no floor, soak or slime-line
  entry, the Massacre timer at 10 s or more and the boss above 23%, the Holy Paladin proposes
  Divine Plea and the Restoration Shaman Mana Tide Totem. Divine Plea halves healing for 9 s, so it
  ends before the Massacre lands. The snapshot carries no mana, so the runtime casts one only below
  the caster's own mana line (85% and 75%), and only when the spell is known and ready. Otherwise
  it skips with `chimaeron_mana_cooldown_not_needed`. The canonical Discipline Priest knows neither
  Shadowfiend nor Hymn of Hope (provisioning), so it has no mana cooldown here.
- **Burn window** (both guides pause around 22-25%, then lust and push). One sequence, held →
  armed → handoff → push:
  - from 23%, non-tanks hold damage; tanks keep attacking above 21.5% (threat, Death Strike) and
    hold below it, so their damage cannot carry the boss into Mortality;
  - the release needs readiness: mixture up, no Massacre casting or due within 8 s, both tanks at
    80% or more (the Break tank is healed to 80% inside the window);
  - a Feud with 10 s or more left also releases, with both tanks at 80% or more. The pacified
    boss cannot swing, and Mortality stops Slime and Massacre, so this is the safest push. Round 1
    held 12-27 s at 20-23% during Feud.
  - fewer than two living tanks also releases: nobody is left to take the boss fresh.
  - The hold is bounded: after two Massacre cycles (60 s) or with fewer than two living healers it
    releases anyway;
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
  two tanks and the taunt exchange. The round-1 DPS targets from these two kills (Blood DK
  25,888.5, Survival Hunter 37,218.05, Retribution Paladin 25,345.0, WoWSims fallback for the other
  specs) are superseded by the round-3 tier-11 set below.

## WCL 10N observations, round 3 (2026-09-30)

GPT-6.1 Sol read the kills in its own tab of the user's Chrome (`codex exec -m gpt-6.1-sol`, profile
Runiir). No verification check appeared. Chrome stopped running once mid-read (about 10:40Z); the
census resumed after it restarted.

**DPS references** (`chimaeron_wcl_dps_reference_v1.json`, raid target `matched_reference_ids`).
The roster wears tier-11 gear (about 359), so the references are kills with raid item level
352-366. Seven kills qualify: MxFq7TRbvnjGY1hJ-27 (359.5, 95 s), JLvtbwNpFrzf6qjQ-14 (359.9, 123 s),
B4J8vQVnbxFdjf3P-22 (361.1, 124 s), HF62ky4w8ThJmrbY-33 (358.2, 122 s), AztLjaG8wJh2fvbk-37 (359.0,
144 s), TtAL96aBnyHgXNMJ-3 (358.5, 121 s) and zg18Kt3FkAdyv7jn-11 (356.3, 163 s). All are dated
2024-10-10 to 2024-10-28. xAhkN2y9YP3KRmnJ-14 (401.4) is dropped. Per-spec targets (median, kills):

| Spec | Target | Kills | Before (409-gear set) |
| --- | ---: | ---: | --- |
| Blood DK (tank) | 15,316.5 | 5 | 25,888.5 WCL |
| Survival Hunter | 26,254.9 | 4 | 37,218.05 WCL |
| Fire Mage | 24,654.6 | 4 | WoWSims fallback 0.9 x 35,139 |
| Retribution Paladin | 26,133.6 | 4 | 25,345.0 WCL |
| Assassination Rogue | 26,350.7 | 3 | WoWSims fallback 0.9 x 33,425 |
| Demonology Warlock | 23,443.3 | 3 | WoWSims fallback 0.9 x 38,038 |

**Knockout census** (ledger `knockout_census_10N`). There are 22 kills:

- the nine tier-11 kills, chosen with a preference for a Feud;
- the twelve first distinct kills of the Phase 4.5 rankings (95-900 s), chosen before any mechanic
  was read;
- xAhkN2y9YP3KRmnJ-14.

| Massacre position in the cycle | Knockouts |
| --- | ---: |
| 1st since the pull or the last knockout | 0 / 30 |
| 2nd | 11 / 24 |
| 3rd | 8 / 8 |

The Feud preference cannot raise the second-position rate: all nine kills reach a third Massacre,
where a Feud is certain anyway. The unbiased Phase 4.5 subset alone gives 4 of 12 at the second
position. The native script uses 50% on 10N (DBM's "2~3"); 25N, 10H and 25H keep 40/60/80/100%.

**Slime, Feud and Mortality** (vnwd3D61GcaYfHrg-29, 160 s, and 9DrAgFWwQj4dV2Tq-53, 117 s):

- Every Massacre cycle has exactly two Slime volleys: the first 17.2-17.7 s after the Massacre
  completion, the second 5.8-6.1 s later. The next pair follows about 24 s after that.
- Slime continues during Feud.
- Feud lasts 30.011 s in both windows. Double Attack is removed 1 ms after Feud starts and is never
  applied during it.
- No Massacre follows Mortality. Double Attack resumes every ~14.4 s.

**Berserk.** The longest 10N kill found is vnwd3D61GcaYfHrg-29 at 160 s, with no Berserk or Enrage
row in the enemy casts or buffs tables. Phase 4.5 lists no normal 10N kill of 180 s or more. The
Phase 1 query failed to load. Wowhead mentions no enrage. No log could test 450 s, so the question
went to the user (see "Berserk decision").

### Berserk decision (user raid experience 2026-09-30)

The handoff question (`chimaeron_10n_berserk`) was whether 10N normal has no berserk, or 10N research
stays blocked until a normal log past 7:30 turns up. The user answered (source
`user_raid_experience_20260930_chimaeron_berserk`, "user raid experience 2026-09-30"):

> "Chima hc and normal doesnt have berserks. After the 20% its basically a soft enrage. Kill it before it kills you due to the 99% reduced healing"

- There is no berserk on normal or heroic, in any mode. The native script has none and stays
  unchanged. BigWigs' unconditional `Berserk(450)` and DBM's commented `--Heroic` timer do not apply.
- The soft enrage is Mortality at 20%: -99% healing received, taunt immunity, no more Massacre. The
  kill must finish before it kills the raid (`mortality_burn`; deaths after Mortality begins are
  exempt from the boss-window death gate).
- This resolves the berserk part of `event_cadence` for every mode. Nothing else was open for 10N
  (Slime repeat and Feud skipping are resolved, wake time is pre-engage), so `event_cadence` no
  longer covers 10N. It stays open for 10H, 25N and 25H, where the 2 s swings need their own logs.

**4.4.2 client rows.** They come from wago.tools, build 59185, via `extract_442_client_spell_rows
--follow-triggers` on 19 spell ids. The 25-player and heroic spell ids are folded into DifficultyID
rows of 82935/82934. Every 10N value equals the 4.3.4 rows.

## Live evidence: raid program round 1 (2026-09-27)

Label `blackwing_descent_10n-r01-553da85c98`, DamageModifier 20 live (`encounter_fidelity.boss_melee`
mean ratio 0.95-1.01 to WCL). T is the first boss melee.

| Run | Outcome | Massacres with a knockout | Deaths |
| --- | --- | --- | --- |
| 521c17d8 | clear, 131.5 s | 1, 2, 3 | Feral in Mortality at T+130.5, 1 s before the kill |
| 250536fd | clear, 144.1 s, excluded (world-tick stalls 4.5% > 2%) | 1, 2, 3, 4 | none |
| 6bf52232 | pull 1 wiped at 8.4%; pull 2 killed at T+466.9; watchdog plateau | pull 1: 3; pull 2: 3 | 12 |

- **The wipe (6bf52232 pull 1).** No knockout at Massacres 1 and 2, so the boss kept swinging.
  1. The doubled swing 9.5 s after Massacre 2 found the Feral at 83,041 health: hit 1 left 1,
     hit 2 killed.
  2. The next doubled swing, 15 s later, found the Blood DK alone at 146,575 health with 4 Break
     stacks: 137,363, then lethal.
  3. The hold at 23% then kept a tankless raid waiting through a Feud while Mortality came. The
     boss killed the raid one member at a time down to 8.4%.
- **Pull 2.** It killed the boss. The route's terminal advance (`boss_killed`) stayed pending for
  190 s with the Feral dead, and `semantic_progress_plateau_watchdog` ended the run. That is route
  scope, not this strategy.
- **Excluded run (250536fd).** The stall was 11 native world-tick stalls of 0.5-0.73 s, 4
  attributed to console commands, on the shared round worldserver. That is infrastructure.
- **Survival Hunter at 33%.** He stood on the 22 yd arc in the spread and 8 yd behind the boss in
  the outage stack. Both are inside his 27.8 yd minimum range, which gave
  `min_range_required` 138 idle waits and 1,300+ shot rejections, and 82 melee swings at 22.8 yd.
  Only DoT ticks, the pet and melee did damage. Both runs spent most of the fight in outage.

## Open items (unresolved)

- Berserk: resolved 2026-09-30 by user raid experience (none on normal or heroic; the soft enrage is
  Mortality at 20%). `event_cadence` stays open only for 10H, 25N and 25H (2 s swings).
- A wipe and re-pull, to observe the helper reset. A stale knockout count would show as a Systems
  Failure on the new pull's first Massacre.
- The DamageModifier is promoted and the registry row applied (2026-09-27); confirm on a live kill
  that `encounter_fidelity.boss_melee` is within ±10% of WCL.
- Heroic Nefarius 4.4.2 rows (Mocking Shadows chain) are not extracted.
- Heroic behavior (Shadow Whip delay, Mocking Shadows), the 25N/10H Slime target mapping, and
  retail reset, loot and achievement persistence.

## Acceptance observations for the live shard

1. `native_route_postcondition` `aura_present` (44418 has 82705) after the Finkle node, then
   `creature_aggressive_with_victim` with the Break tank as the first victim.
2. No Massacre deaths while the mixture is up. Each Double Attack charge is consumed on the Double
   Attack tank.
3. During an outage the raid is stacked within 6 yd of each Slime target, with no outage deaths.
4. No taunt lands after Mortality. The kill is a native clear with 0 boss-window deaths before
   Mortality (deaths after Mortality begins are exempt: `mortality_deaths`, user decision
   2026-09-27).
5. Systems Failure only at the second or third Massacre of a cycle, never twice in a row.
6. Two Caustic Slime volleys per Massacre cycle, about 6 s apart.
7. No Break application and no Double Attack buff while Feud is up.

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
- Raid program round 3 (label `blackwing_descent_10n-r03-a3864fcf6d`, tier-11 gear, four runs; the
  diagnosis is in the round-3 coordinator notes): 4/4 wipes at the first outage, which the 10N
  knockout rule moved to the third Massacre (about 90 s in).
  - The two Slime volleys after the knockout killed 7-8 members at 1-25k health within 6 s. The
    stack was correct: the volleys hit 10, 6 and 13 targets.
  - Healing in the outage window was 0.77-0.81 M, against 1.70 M in round 2. The Discipline Priest
    did 86-107k there (349k in round 2) and moved to the slow Heal, the pattern of a mana-gated
    profile.
  - Between the first two Massacres the healers did 1.19-1.22 M healing. The floor needs about
    0.2 M; the rest was the runtime's default top-up, which the next Massacre erased.
  - The tank healer spent the outage on the tanks, although Feud pacifies the boss.
  - Chimaeron melee was 0.881 times WCL over 30 swings in one run. That is just outside the ±10%
    band, and the scoreboard recorded it as a warning. It is below WCL, so it does not explain the
    wipes. The DamageModifier stays at 20.
- Fixes (round 4, strategy only, native script unchanged): hold the mixture top-up, add the slime
  line and pacified tanks in the outage, move the Barrier window, and add the healer mana cooldowns
  (see "Healing" and "Healer mana cooldowns" above).
- Open (runtime and roster, outside the strategy): the heartbeat status does not show healer mana.
  The canonical Discipline Priest has no Shadowfiend or Hymn of Hope. Nothing uses mana potions
  in combat.
- World-tick spikes after the first Massacre (0.5 s, in every batch, the quiet one included).
  - The Chimaeron plan is O(players) per bot and revision: duties, the urgency list and the slots,
    ten members, a few sorts. The native script has no per-tick work that scales with raid health.
  - What changes at that moment is that all ten members sit at 1 health. That starts the runtime's
    heal path (`SelectHealSpell`, which builds candidate masks and JSON receipts on every attempt)
    for every healer on every decision. Mana-gated profiles then return `no_trained_heal` retries,
    each with a combat-attempt receipt.
  - The mixture hold removes those attempts while the mixture is up, but it does not prove that
    they were the cost. Settling it needs per-stall CPU and per-candidate timing in the tick
    recorder (a runtime request).
