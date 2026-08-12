# Baleroc, the Gatekeeper — Firelands

Phase-0 research dossier for Cataclysm Classic 4.4.2, build 59185, enUS, hotfix cutoff `2025-02-18T19:31:51.916Z`. Scope is 10N/10H/25N/25H. This is an original implementation summary, not copied guide text. The endpoint is `fidelity_blocked` because the local script omits the central Vital Spark/Vital Flame system and several timers/scalings differ from current Classic sources.

## Sources and snapshot

- Current secondary corroboration: [Wowhead’s Patch 4.4.2 guide](https://www.wowhead.com/cata/guide/raids/firelands/baleroc-strategy-overview), [Icy Veins’ Cataclysm Classic guide](https://www.icy-veins.com/cataclysm-classic/baleroc-encounter-guide-strategy-abilities-loot), and Warcraft Tavern’s [Baleroc raid guide](https://www.warcrafttavern.com/cataclysm/guides/baleroc-the-gatekeeper-raid-guide/).
- Official/primary provenance: Blizzard’s [Patch 4.2 hotfix page](https://worldofwarcraft.blizzard.com/en-us/news/3019413), including the Baleroc health/damage, blade-order, Torment, reset, and 25H Vital Spark changes; Blizzard’s [Firelands raid announcement](https://worldofwarcraft.blizzard.com/en-gb/news/24145859/cataclysm-classic-face-the-heat-in-the-firelands-raid). The historical hotfix page is used as provenance, not silently assumed to be the 4.4.2 state.
- Official 4.4.2 modifier context: Blizzard states that optional `Power of Stormrage` reduces health and damage of every Firelands boss and other enemy by 30%, removable through General Taldris Moonfall. The local repository has no verified spell/application, so modifier state and guide-health interaction remain blocked.
- Repository sources audited read-only at `8eb54f0160b3c3d986ed944f9d64ebf83922c0f8`: `src/server/scripts/Kalimdor/Firelands/boss_baleroc.cpp`, `firelands.h`, `instance_firelands.cpp`, the Kalimdor loader, historical Firelands SQL, and model/credit updates.

## Mode matrix

| Mode | Current guide health | Local Shards target count | Heroic delta | Modifier |
|---|---:|---:|---|---|
| 10N | 42,100,000 | 1 | baseline | Power of Stormrage optional; run state unknown |
| 10H | 69,900,000 | 1 | Countdown, stronger shard values, 5 Torment per Vital Spark (guide) | same |
| 25N | 133,300,000 | 2 | baseline | same |
| 25H | 195,600,000 | 2 | Countdown, stronger shard values, official 25H five-stack Vital Spark hotfix | same |

Wowhead supplies these health values and labels the page Patch 4.4.2. They are retained as guide-reported values, not asserted post-`Power of Stormrage` values. The local `Is25ManRaid()` count agrees with the 1/2 shard split; local `IsHeroic()` is used for heroic spells but Vital Spark is absent.

## Encounter behavior

### Blades, tank health, and scaling

The current guide describes `Blaze of Glory` on the current tank about every 10s: +20% maximum health and +20% physical damage taken per stack, infinite/no duration until encounter end/reset. Each application also gives Baleroc `Incendiary Soul`, +20% Fire damage per stack. Local scheduling is 8.5s after engage then every 11.5s, so cadence is not safe to promote. Local casts Blaze on the victim and Incendiary Soul on the boss.

At about 30s and every 45s, current Wowhead says Baleroc empowers a blade, initially Inferno, for 15s. Inferno Blade changes successful melee to Fire; Wowhead reports 125k base normal or 200k heroic, with Incendiary Soul scaling, and attacks remain avoidable/mitigable. Local starts at 30.5s, repeats every 47s, randomly chooses Inferno (99350) or Decimation (99352), swaps equipment, disables dual wield, and restores weapons after 15s. Blizzard’s historical hotfix says the first blade should always be Inferno; local random selection conflicts and is blocked.

Decimation Blade replaces successful melee with Shadow equal to 90% of target maximum health, at least 250,000, for 15s. Wowhead reports a 150% attack-speed slow, at most four strikes, and Decimating Strike’s -90% healing for 4s; local spell 99353 computes 90%/250k but does not implement that attack-speed rule in C++. Avoidance remains possible while ordinary mitigation does not. Exact SpellInfo base values, attack cycle, and 10/25 scaling are blocked.

Bot-safe tank contract: maintain a high-health active tank for Inferno/physical pressure, use a low- or moderately-stacked Decimation tank, swap for Decimation, and fully heal between Decimating Strikes. The exact number of opening Blaze stacks and the chosen one-/two-tank plan are strategy choices, not fixed encounter values.

### Shards of Torment and Torment

Wowhead reports the first Shards spawn at 5s and every 35s thereafter, with two crystals in 25-player (one melee and one ranged) and one in 10-player. Local starts at 5s and reschedules after 34s (thus the next event is 39s), selects 1/2 random area targets by raid size, removes the current tank only if enough candidates exist, and converts each target through spell 99260. Exact spawn-location rules and whether target candidates are only players are SpellInfo/DBC dependent.

A shard shows a 5s cosmetic effect locally, then casts Torment (99254/periodic 99255). If no eligible player is within the local 15-yard check, the shard casts Wave of Torment (99261). Current Wowhead reports unattended Wave as 20k Shadow per second normal or 40k heroic to the raid; a soaker within 15 yards instead receives 3k normal or 4.5k heroic Shadow per second, stacking over 25 ticks, and the shard disappears after 25s. These values are guide-reported; local periodic base damage is not independently audited.

The local source records an explicit unresolved damage dispute: comments cite 3,000 normal/4,250 heroic from Wowhead versus 4,000 normal/5,000 heroic from retail logs, then calculate stack-scaled damage from the latter values and SpellInfo’s base-hit multiplier. Treat all Torment tick, stack, range, expiry, and shard lifetime values as blocked until the target build is verified.

When a player leaves a shard after receiving Torment, current Wowhead describes `Tormented` as +500% magic damage taken and -50% healing for one minute. Icy Veins confirms the rotation hazard but does not expose all magnitudes. Local uses Tormented variants 99257/99402/99403/99404, applies the achievement counter on aura application, and casts normal 20 or heroic 40 on removal of the Torment aura; the heroic spread script applies Tormented 40 to nearby hit units. Exact variant semantics, duration, spread radius, and normal/heroic magnitude are blocked.

### Vital Spark and Vital Flame

Current guides describe direct healing of a Torment soaker as granting one Vital Spark per three Torment stacks; Sparks last 60s. Healing a tank carrying Blaze converts the Spark stacks into Vital Flame for 15s, increasing healing to Blaze tanks by 5% per Spark stack. Heroic guides state five Torment stacks per Spark instead of three; the official historical hotfix specifically calls out 25-player Heroic changing from three to five and reducing Baleroc health to compensate.

The repository source begins with a TODO to implement Vital Spark (99262) and Vital Flame (99263) and contains no corresponding aura script. This is a critical implementation blocker, not a cosmetic omission: the encounter’s healing scaling cannot be represented faithfully from this branch.

### Heroic Countdown

Current Wowhead reports Countdown every 45s on two random non-tank players, with 8s to meet within 4 yards; failure explodes for 125k Fire to allies within 100 yards. Icy Veins reports the same 8s/4-yard link but says 85k Fire per player, a material source conflict. Local schedules the first Countdown at 26s and repeats after 48s, selects two random area targets after removing the current victim, links them with 99519, applies 99516, and on expiry casts 99518; a player-side script removes the link when a suitable ally is found. No local code proves the 4-yard/100-yard radii or the explosion damage. Heroic Tormented spread can make the meeting path unsafe.

### Berserk, reset, and completion

There is no phase transition in the sources or local AI. The hard time limit is six minutes: local schedules spell 26662 once at 6m; current Wowhead calls the six-minute Enrage lethal. Blade cycles, tank stacks, shards, and healer scaling all occur in this single phase.

`Reset` restores dual wield/equipment and calls `_Reset`. On evade, local disengages the encounter frame, removes Blaze of Glory from players, moves home, despawns tracked summons, and calls `_DespawnAtEvade`; it does not itself prove removal of every Torment/Vital aura. Historical Blizzard notes say Baleroc’s gate should despawn after reset and Shards should despawn even if spawned after the boss despawns. The local Firelands instance has the Baleroc firewall door commented out, so gate behavior is not represented here.

On death, local `_JustDied` and encounter-frame disengage run, weapons are restored, and Smouldering (101093) is cast if a player has quest item 69848. Historical SQL maps encounter 1200 to credit creature 53494. Achievement criteria 17577 uses `achievement_share_the_pain`; local `DATA_SHARE_THE_PAIN=5830` succeeds only if no tracked player receives more than three Tormented applications. Whether that exactly matches 4.4.2 credit, loot, lockout, and achievement evaluation is not live validated.

## Repository identity audit

`boss_baleroc.cpp` registers boss 53494 and Shard 53495. Spell identities include Inferno Blade/Strike 99350/99351, Decimation Blade/variant/Strike 99352/99405/99353, Blaze/Incendiary 99252/99369, Shards 99259/99260, Torment 99254/99255, Wave 99261, Tormented variants 99257/99402/99403/99404, Countdown family 99515–99519, Smouldering 101093, and Berserk 26662. Historical SQL attaches `boss_baleroc` and `npc_shard_of_torment`, registers the spell scripts, places the boss at map 720, and records model 38621 (boss) / 1126 and 11686 (shard models). `firelands.h` keys Baleroc at encounter index 4; `instance_firelands.cpp` maps it but leaves its firewall door disabled. Historical `instance_encounters` row 1200 credits 53494.

## Fidelity blockers

1. Exact SpellInfo/DBC values and 4.4.2 hotfix state for build 59185 at the specified cutoff.
2. Power of Stormrage spell identity, default/application state, reversibility, and interaction with guide health.
3. Guide health values versus authoritative mode/modified health and damage.
4. Blaze/Incendiary cadence (local 8.5s/11.5s versus guide about 10s), stack behavior and mode scaling.
5. First blade rule (official historical Inferno-first versus local random), blade cadence, attack cycle, and Inferno damage.
6. Decimation attack-speed reduction, strike timing, mitigation/avoidance and exact minimum scaling.
7. Shard spawn interval/location/target filters and 10/25 random range.
8. Wave/Torment damage, tick, range, stacks, expiry, shard lifetime, and local 3k/4.25k versus 4k/5k conflict.
9. Tormented variant identity, duration, magnitude, healing reduction, and heroic spread radius.
10. Vital Spark/Vital Flame behavior and heroic five-stack rule: local implementation is explicitly absent.
11. Countdown first/repeat cadence, target exclusions, link/removal radii, explosion radius and 85k versus 125k damage conflict.
12. Six-minute Berserk SpellInfo magnitude and interaction with optional modifier.
13. Reset aura cleanup, firewall/gate state, summon despawn timing, credit/loot/lockout and achievement semantics.
14. Current DB/DBC mode rows, shard models, and exact locale/build mapping.
