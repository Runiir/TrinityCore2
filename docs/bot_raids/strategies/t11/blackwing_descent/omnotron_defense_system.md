# Omnotron Defense System — research contract v2

Scope is Cataclysm Classic, intended to cover 10-player normal/heroic and
25-player normal/heroic. This is a research and planning contract, not a
claim of 4.4.2 live fidelity. Values which are only present in an external
guide are labelled as such. A bot must not turn a `fidelity_blocked` value
into a fixed schedule.

## Bot contract

- Treat Electron, Magmatron, Toxitron and Arcanotron as one shared-health
  council. The controller randomizes the initial order and keeps at most two
  constructs online. Assign two tanks, but select the current active pair
  from encounter state rather than from a hard-coded order.
- Interrupt Arcane Annihilation/Annihilator. Move a Lightning Conductor mark
  and Magmatron's Acquiring Target/Flamethrower away from the raid. Keep
  players and the tanked construct out of Power Generator unless taking the
  documented benefit is intentional; move away from Chemical Cloud and kite
  Poison Bombs.
- Stop or redirect damage when Power Conversion, Unstable Shield, Barrier or
  Poison Soaked Shell is observed. A shield is an event/state gate, not a
  timer-only gate: the exact 4.4.2 threshold and local timer disagree with
  some guide descriptions (see the ledger).
- In heroic, observe Nefarius' actual cast/summon events. Do not assume the
  historical “every N seconds, fixed order” story; the repository controller
  applies an ability only when the corresponding cloud/generator or golem
  event arrives and enforces a 30-second internal cooldown.

## Cross-source behavior that is safe for planning

The current Cataclysm guide and the local script agree on the encounter's
high-level shape: four constructs share health; one starts, another is brought
online while the first is still active, and two are active at once. A golem
deactivates at the end of its energy cycle and the queue supplies the next
one. The implementation links shared health at reset, shuffles the four GUIDs
and starts recharge at 10 seconds (`boss_omnotron_defense_system.cpp:236-245,
366-375`).

The following are guide-reported planning values, not 4.4.2-verified values:

| Mechanic | Reported behavior | Bot implication |
|---|---|---|
| Shared health | 10N 32.2M; 10H 54.1M; 25N 99.2M; 25H 164.9M | Do not split damage by construct; use encounter health. |
| Rotation | 60s first activation, second after 30s, then another about every 30s; at most two active | Derive active pair from events. The repository has an independent recharge aura and no 60s constant in this AI. |
| Power Generator | 5-yard benefit, +50%, lasts 60s; first report is 15s after activation and repeats about every 20s | Keep intended recipient(s) in the field; keep raid/enemies out when not using it. |
| Electrical Discharge | About 6s; chain to up to three targets within 8 yards; each jump gains 20% | Spread chained targets. The local spell script selects one next target and adds 20% per jump. |
| Lightning Conductor | Marked player is isolated for about 15s; guide text elsewhere says 10s normal/15s heroic | Use the aura/event end, not a mode timer, until 4.4.2 data is confirmed. |
| Unstable Shield | About 40s after activation, 10s; attacks proc Static Shock within about 6 yards | Stop damage and wait for shield removal. Local proc fires at the attacker on any damage event. |
| Incineration | About 10s then about every 30s, four seconds | Move/mitigate the cone; local AI uses 10.5s then 26.5s. |
| Acquiring Target | About 20s; a four-second lead then four-second Flamethrower | One random target is selected by the local script; target and raid clear the line. |
| Barrier | About 40s, 10s; breaking it causes Backdraft | Stop damage unless the controller explicitly authorizes a break. |
| Chemical Bomb | About 25s after activation; cloud about 30s and +50% damage taken | Move the bomb/cloud to a safe edge; do not use it as a fixed timer. |
| Poison Protocol | First report is 15s, with another about 25s later; bombs are about 3s apart | Treat the cast as an interrupt/targeting event. Number and cadence differ between sources. |
| Poison Soaked Shell | About 40s and 10s; attacks apply a stacking poison; Expunge/dispels clear it | Stop damage and clear the poison according to the observed aura. |

The external guide reports 10-player Arcane Annihilation as one random target
and 25-player as an area/three-target cast. The local AI confirms one random
target in 10-player and an area cast in 25-player (`boss_omnotron_defense_system.cpp:948-957`). The exact
spell damage ranges are intentionally omitted from the bot contract: current
pages disagree by patch and are not proof of the Classic 4.4.2 hotfix state.

## Difficulty matrix

| Mode | Confirmed/common contract | Mode-specific report or blocker |
|---|---|---|
| 10N | Shared health; shuffled queue; two active; all four construct kits; one-target Arcane cast in local AI; normal spell IDs | Guide reports 32.2M shared health. Poison Protocol bomb count/cadence and shield threshold are `fidelity_blocked`. |
| 10H | Same controller and shared-health shape; Nefarius is summoned only on heroic by the repository | Guide reports 54.1M health and stronger damage. Nefarius' event-driven interference is confirmed locally; exact external cadence is unresolved. |
| 25N | Same shape; local AI changes Arcane to area targeting; all four kits | Guide reports 99.2M health. Exact area target count and Poison Protocol cadence are source-conflicted. |
| 25H | Same shape; local AI uses area Arcane targeting; Nefarius interference and heroic spell variants | Guide reports 164.9M health and stronger effects. Exact Classic 4.4.2 health, damage, bomb count and Nefarius selection cadence are unresolved. |

The old heroic guide reports roughly 35-second Nefarian upgrades and a random
active golem; the current repository instead routes effects from Lightning
Conductor, Chemical Cloud and Power Generator summons and clears a 30-second
cooldown. These are not interchangeable schedules.

## Repository lifecycle, reset and credit

- `Reset` summons the construct group, links shared health after 5 seconds and
  starts the first recharge after 10 seconds. The four GUIDs are shuffled per
  encounter (`boss_omnotron_defense_system.cpp:236-245,366-375`).
- A recharge aura activates its target only when its periodic energize aura
  expires. The activated aura periodically casts the golem's normal trigger
  spell; when it expires it casts shutting down. Inactive handling applies
  Powered Down and makes the golem not selectable (`boss_omnotron_defense_system.cpp:1243-1305`).
- Starting the encounter sets `IN_PROGRESS`, clears the four worldstates,
  summons heroic Nefarius, zones all constructs into combat and activates the
  queued golem (`boss_omnotron_defense_system.cpp:306-322`).
- A failed/evaded encounter disengages and despawns the constructs, sets
  `FAIL`, removes raid debuffs, despawns summons and evades the controller
  (`boss_omnotron_defense_system.cpp:323-337`).
- Completion calls `_JustDied()` (the boss credit/boss-state transition),
  disengages constructs and removes debuffs (`:338-348`). The instance forwards
  Omnotron `DONE` to the generic Nefarius credit path
  (`instance_blackwing_descent.cpp:254-261`).

## Targeting and heroic controller details

Repository-confirmed target rules:

- Electrical Discharge's trigger list is randomly reduced to one next target;
  damage increases 20% per chain jump (`boss_omnotron_defense_system.cpp:1308-1352`).
- Acquiring Target randomly reduces eligible targets to one and casts its
  periodic flamethrower on that target (`boss_omnotron_defense_system.cpp:1388-1426`).
- A Poison Bomb samples up to 25 random eligible targets, removes targets
  within 10 yards of its summoner when alternatives exist, then randomly keeps
  one and fixates it (`boss_omnotron_defense_system.cpp:1114-1143`).
- In 10-player the local AI selects one Arcane target; in 25-player it casts
  the area spell (`boss_omnotron_defense_system.cpp:948-957`).
- Unstable Shield procs Static Shock at the damage attacker, and Barrier casts
  Backdraft only when removed by an enemy spell (`boss_omnotron_defense_system.cpp:1354-1447`).

On heroic start, Nefarius is summoned. The local controller only manipulates
the longest-active golem at a time. Chemical Cloud schedules teleport/grip and
return, Power Generator schedules Overcharge, Lightning Conductor can trigger
Shadow Infusion/Shadow Conductor, and Acquiring Target can trigger Encasing
Shadows. Each accepted ability sets a 30-second cooldown
(`boss_omnotron_defense_system.cpp:978-1088`). Overcharge grows the generator,
then removes its auras and produces Arcane Blowback (`boss_omnotron_defense_system.cpp:1493-1545`). The
repository therefore supports the presence and event causes of heroic
interference, but not a universal fixed order or encounter-time cadence.

## Repository and database audit

- C++ implementation: `src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent/boss_omnotron_defense_system.cpp` (controller, four AIs, Nefarius, target filters and aura scripts; cited ranges above).
- IDs and mode entries: `blackwing_descent.h:87-123`; base constructs are
  42166/42178/42179/42180 and boss 42186. Historical difficulty entries are
  assigned in `sql/old/4.3.4/world/12_2016_09_28/2016_09_02_00_world.sql:6-9`.
- Instance mapping/forwarding: `instance_blackwing_descent.cpp:31-57,174-183`.
  Encounter registration is the historical row 1027/42180 in
  `sql/old/4.3.4/TDB04_to_TDB05_updates/world/066_instance_encounters.sql:463`.
- Loader: `eastern_kingdoms_script_loader.cpp:76-80,307-312` declares and calls
  `AddSC_boss_omnotron_defense_system`.
- SQL binding is present in the historical custom update
  `sql/old/custom/world/34_2020_02_21/custom_2019_08_20_00_world_updatepack.sql:131229-131356`:
  boss/construct/Nefarius/poison-bomb `ScriptName`s, spell-script bindings,
  difficulty entries and heroic spell bindings. The earlier draft's claim
  that no historical binding exists was incorrect. Current `sql/updates/world/4.3.4`
  has no equivalent Omnotron `ScriptName` row in the searched updates.
- DB support also includes the 78725 Council Energy Drain aura on base golems
  (`sql/old/4.3.4/world/10_2016_03_12/2015_10_02_00_world.sql:155-165`),
  static flags for base/difficulty entries (`sql/updates/world/4.3.4/2023_08_27_00_world.sql:36437-36461`),
  and spell-proc values for Power Conversion/Poison Soaked Shell
  (`sql/updates/world/4.3.4/2025_06_20_00_world.sql:322-333`; cooldown rows for
  79729/79900 in `2025_06_20_01_world.sql:104-111`). These rows corroborate
  proc wiring, not the encounter's wall-clock schedule.

## Conflicts and unresolved fidelity blockers

- The current Cataclysm guide reports 60-second activation/30-second stagger
  and approximately 40-second shields. Local AI uses a 40/50-second heroic/
  normal shield schedule for Electron, Magmatron and Arcanotron, 30/40 for
  Toxitron, and has no 60-second constant. Older Icy Veins documentation says
  100-to-0 energy, a 50-energy shield and roughly 30/45-second rotation.
  Threshold, energy drain rate, activation cadence and shield timing are
  `fidelity_blocked` pending verified 4.4.2 spell/DBC or run evidence.
- Poison Protocol is reported as one normal/two heroic bombs by Wowhead, but
  the Warcraft Wiki reports a 3-second cadence (1.5 seconds in 25-player),
  while the local AI only schedules the channel once per activation. Bomb
  count, channel timing and mode scaling are unresolved.
- Lightning Conductor is reported as 15 seconds by the current guide, but
  Warcraft Wiki/legacy strategy text distinguishes 10-second normal and
  15-second heroic. Use event state only.
- Health and damage numbers, heroic health reductions, the presence of a
  berserk timer and exact 4.4.2 hotfix/build cutoff have no reliable source in
  this repository audit. They remain `fidelity_blocked`; no exact build claim
  is recorded.

## Source metadata

1. **Wowhead — “Omnotron Defense System Strategy Guide”.** Author Beanna;
   page updated 2024-06-04; Cataclysm guide URL
   <https://www.wowhead.com/cata/guide/raids/blackwing-descent/omnotron-defense-system-strategy>;
   accessed 2026-08-11. Reports current guide health values, 60/30 rotation,
   ability timers, ranges, 10/25 targeting and heroic differences. The page
   does not expose a reliable 4.4.2 build/hotfix cutoff.
2. **Icy Veins — “Omnotron Defense System Encounter Guide”.** Cataclysm
   Classic guide, page metadata indicates publication around 2024; URL
   <https://www.icy-veins.com/cataclysm-classic/omnotron-defense-system-encounter-guide-strategy-abilities-loot>;
   accessed 2026-08-11. Used as an independent strategy source for shared
   health/energy shape and heroic ability descriptions; exact page patch
   coverage is not stated.
3. **Warcraft Wiki — “Omnotron Defense System”.** Community-maintained
   ability/reference page; URL <https://warcraft.wiki.gg/wiki/Omnotron_Defense_System>;
   accessed 2026-08-11. Used for historical spell ranges, target ranges,
   Poison Protocol cadence and patch/hotfix history; not treated as proof of
   the Classic 4.4.2 state.
4. **Guías WoW — “Heroic Mode Omnotron Defense System”.** Legacy Cataclysm
   heroic strategy page (page age metadata approximately 15.5 years); URL
   <https://en.guiaswow.com/blackwing-descent/guide-heroic-mode-defense-system-omnotron-defense-system.html>;
   accessed 2026-08-11. Used only as an independent historical report of
   Nefarian's roughly 35-second random upgrades and heroic mechanics; its
   patch is not a 4.4.2 source.
