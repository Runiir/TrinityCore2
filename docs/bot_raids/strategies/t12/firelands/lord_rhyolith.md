# Lord Rhyolith — Firelands (Cataclysm Classic 4.4.2)

Phase-0 research dossier for 10N/10H/25N/25H. This is an original implementation summary, not a mirrored guide. `fidelity_blocked` is intentional: current Classic guides, historical hotfixes, and the local implementation disagree on behavior-changing values, and the exact 4.4.2 build/modifier state is not proven.

## Evidence and official modifier

- Raid: Firelands, map 720; endpoint: Lord Rhyolith; research date: 2026-08-12.
- Local revision audited: `8eb54f0160b3c3d986ed944f9d64ebf83922c0f8`.
- Current guides: [Wowhead, Patch 4.4.2](https://www.wowhead.com/cata/guide/raids/firelands/lord-rhyolith-strategy-overview) and [Icy Veins](https://www.icy-veins.com/cataclysm-classic/lord-rhyolith-encounter-guide-strategy-abilities-loot). Wowhead reports health 15.5M/23.3M/47.3M/78.1M for 10N/10H/25N/25H.
- Blizzard’s [official 4.4.2 announcement](https://us.forums.blizzard.com/en/wow/t/firelands-difficulty-reduction-with-hour-of-twilight-patch/2059756) says the optional `Power of Stormrage` debuff reduces health and damage of all Firelands bosses and other enemies by 30%; General Taldris Moonfall can remove it. The local repository has no verified spell or application. Do not assume the guide health values are before or after the modifier.
- Historical Blizzard hotfixes are provenance only. They include several Rhyolith changes (10-player turning, Eruption, Phase 2 clearing, Magma Flow, volcano activation, and armor-charge changes) but do not establish the exact Classic 4.4.2 state.

## Mode matrix

| Mode | Guide health | Local Molten Armor spell | Local steering threshold | Modifier |
|---|---:|---:|---:|---|
| 10N | 15,500,000 | 98255 | 3,000 | Power of Stormrage optional; state unknown |
| 10H | 23,300,000 | 101158 | 3,000 | same |
| 25N | 47,300,000 | 101157 | 9,000 | same |
| 25H | 78,100,000 | 101159 | 9,000 | same |

The local `RAID_MODE<uint32>` order is normal-10, normal-25, heroic-10, heroic-25; the table is reordered to the program’s mode order. The 30% modifier must be recorded as run state, not silently applied.

## Encounter contract

### Phase 1: drive, armor, and hazards

Rhyolith has no normal aggro table while driving. Attack the called left or right foot to change a 0–50 balance (center 25); torso damage is the non-steering option. The local script samples two one-second foot-damage slots every 500ms, uses 3,000 damage per balance unit in 10-player and 9,000 in 25-player, exposes alternate power, and sets world state 5931 (`Not an Ambi-Turner`) after balance first falls below center. A controller samples every second, offsets facing by up to 45 degrees, and intersects the route with a 50-yard circle centered at `(-371.577393,-318.680725,102)`. Missing intersection enters evade. Exact Classic steering curve, latency, and foot scaling are blocked.

Bot-safe behavior: one caller owns direction; focus only that foot; use torso for free DPS; never kill a foot; keep the boss away from the lava edge. The local 5-second event averages both foot health and synchronizes it to boss health. Current guides describe extreme balance as `Burning Feet` (+100% movement speed); local spell 98837 is applied when within 10 yards of a volcano.

The boss starts with 80 Obsidian Armor stacks (98632). Current guides describe 1% damage reduction per stack. Concussive Stomp (97282) creates 2–3 dormant volcanoes. Current Wowhead timing is 15s then 30s; local timing is 16s then 30s. Heated Volcano (98493) is local 30s then every 25s, activates after 5s, and prefers in-front targets when any exist (source comment attributes this to a 2011 hotfix).

Current Wowhead reports Eruption (98264/Aura 98492) every second at 3–6 random players, 12k fire, 15s duration, 20-stack cap, +5% fire damage per stack normal and +10% heroic. When Rhyolith crushes a heated volcano, the current guide says 10 armor stacks are removed; local C++ removes 16 from boss and both feet. This is a material unresolved conflict. Local heroic handling summons five Armor Fragments per heated volcano.

Crushed volcanoes become craters. Wowhead reports Magma (98472) about 13.5k fire every 3s within 5 yards, then after about 40s seven Magma Flow trails which explode after about 5s for about 75k plus knockback; crater about 20s. Local spells are 97225/97230/97234, choose 4–6 lines with random frequency/angle, and schedule Lava Line 11s after the first break then every 10s. Exact spell period, values, line lifetime, and crater lifetime are blocked.

Drink Magma (98034) is the edge failure; local code faces the boss toward platform center and casts Molten Spew (98043). Wowhead describes four raid-wide hits for about 140k fire each. Reaching lava is a route failure, not a valid tactic.

### Adds

Local Thermal Vent starts at 23s and repeats every 23s; spell data selects Fragment or Spark. Current Wowhead says about every 20s, alternating five Fragments and one Spark, with about 15k fire within 7 yards. Strict alternation and current cadence are not established.

- Fragment 52620: local Meltdown 98646 and activation after 1s. Current guide says detonation after 30s on a random player for 50% of remaining health. Spell base points and targeting are blocked.
- Spark 53211: local Immolation 98597 after 1s. Current guide says 7.2k fire per second within 12 yards; Infernal Rage 98596 after 10s adds 10% damage done/received every 5s to +100%. Spell tick and stack details are blocked.
- Heroic local path: five Armor Fragments (98558) on heated volcano and Liquid Obsidian via spell 98146. The C++ does not explicitly guard Liquid Obsidian by difficulty; health, speed, fuse distance, armor restoration, and mode scaling are blocked.

### Phase 2 and soft enrage

Local transformations are 75% -> 54192, 50% -> 54199, 25% -> 53772. Lethal damage is clamped before the final entry. At the final transition the local AI interrupts, removes feet, active adds/volcano forms/pillars, stops the controller, casts Immolation 99846, clears players’ Eruption Aura 98492, stands after 3s, and starts Concussive Stomp after 7s; heroic Unleashed Flame starts after 1s. Current Wowhead says Phase 2 has no further volcanoes/adds and Stomp every 15s; local repeats it every 30s. This is unresolved.

Current guides report Phase 2 at 25%, raid Immolation around 8k fire per second, and a five-minute Superheated enrage. Icy Veins reports Superheated starts at six minutes normal/five heroic and stacks every 10s; local schedule matches those starts and repeat. Local heroic Unleashed Flame 101324 targets a random player within 50 yards every 6s and moves a radius-10 circle for six steps using aura/channel 101313/101314. Exact 4.4.2 heroic target/beam/path semantics are blocked.

At death, `BossAI::JustDied` cleans the encounter. Historical SQL credits creature 53772 for encounter 1204, while instance data uses `DATA_LORD_RHYOLITH=1`. Reset paths include missing feet, broken controller intersection, evade, edge Drink Magma, or death; cleanup removes encounter frames, Balance Bar, and summons. Retail reset timing, lockout, loot, and achievement behavior are not live validated.

## Repository identity audit

`src/server/scripts/Kalimdor/Firelands/boss_lord_rhyolith.cpp` (namespace typo `LordRhylith`) supplies IDs: boss 52558; controller 52659; feet 52577/53087; volcano/heated/crater 52582/54071/52866; phase-two 53772; damaged forms 54192/54199; pillar 53122; Fragment/Spark 52620/53211; Unleashed Flame 54347. Spells include 98632, 98226, 97282, 98493, 98034/98043, 98264/98492, 97225/97230/97234, 98646, 98597/98596, 99846, 101304, 101324, 99875, and serverside 103019/98192/98266.

`firelands.h` and `instance_firelands.cpp` establish map 720, encounter index 1, creature identities, object data, and a radius-60 boss boundary (the movement controller uses its own radius-50 platform circle). The loader registers the scripts. Historical 4.3.4 SQL/model updates establish ScriptName, difficulty-entry, model, world-state 5931, and credit identity only; they are not current 4.4.2 tuning. Exact current DB/DBC mode rows and historical difficulty-entry mapping remain blocked.

## Fidelity blockers

1. Exact 4.4.2 build/hotfix lineage.
2. Power of Stormrage spell ID, default/application/toggle persistence, and guide-health interaction.
3. Authoritative four-mode health, damage, armor, and add-health values.
4. Armor removal (guide 10 versus local 16).
5. Retail steering curve, foot threshold/scaling, and latency.
6. Stomp timing/damage/knockback/volcano targeting and Phase 2 cadence (guide 15s versus local 30s).
7. Heated Volcano/Eruption target, tick, range, stack, and damage scaling.
8. Magma Flow line/timing/damage/knockback and crater lifetime.
9. Add cadence and Fragment/Spark selection.
10. Fragment Meltdown base points and targeting.
11. Spark tick/range/Rage scaling.
12. Liquid Obsidian and heroic add eligibility/scaling.
13. Unleashed Flame target/path and heroic delta.
14. Phase cleanup, reset/achievement, Superheated magnitude, credit/loot in 4.4.2.
15. Current DB/DBC rows and difficulty-entry mapping.
