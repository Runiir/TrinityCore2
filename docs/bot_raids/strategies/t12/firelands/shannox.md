# Shannox — Phase 0 research contract (Cataclysm Classic 4.4.2)

This dossier covers `10N`, `10H`, `25N`, and `25H` Shannox. It is sourced planning evidence, not a live-validation result. Blizzard's 4.4.2 announcement applies a Firelands-wide modifier, `Power of Stormrage`, reducing boss and enemy health and damage by 30% and offering an in-instance removal option. The announcement does not publish the aura/NPC IDs, default persistence, or a DBC build, so guide health values are not reduced a second time and those fields remain `fidelity_blocked`.

## Observable encounter contract

- Shannox patrols the front Firelands paths with Riplimb and Rageface. Current Cataclysm Classic guidance says enough trash must be cleared before he appears; the pull location is chosen by the raid. The exact trash threshold, controller, patrol path, and activation persistence are not frozen by the local source/DB snapshot.
- Keep Shannox, Riplimb, and Rageface apart enough to avoid their separation enrage, but within the mode-specific maximum distance. Current Wowhead reports 60 yards in normal and 80 in heroic; current Icy Veins describes 60 yards without publishing a heroic delta. This is a material difficulty conflict.
- Shannox and Riplimb are taunt-immune. Shannox's `Arcing Slash` and Riplimb's `Limb Rip` apply stacking `Jagged Tear`. Hurling the spear removes Shannox's slash while Riplimb fetches it, creating the tank reset window; a Crystal Prison can delay the return.
- Shannox throws Immolation and Crystal Prison traps at random nearby player locations. Traps arm after 2 seconds. Players avoid them; tanks deliberately route dogs through them when a reset is needed. The local trap AI prioritizes Riplimb, then Rageface, then the nearest player within 2.5 yards, which is an implementation detail rather than proof of retail targeting.
- Rageface has no conventional threat table, switches random targets, and periodically uses `Face Rage`; a sufficiently large single hit breaks the channel. Riplimb is tanked and leaves its tank to retrieve the spear. Current guides disagree with the local first-delay/periodic schedules and spell identities for these actions.
- Normal guidance requires both dogs to die before Shannox reaches 30%, because `Frenzied Devotion` otherwise wipes the raid. Current heroic guidance says the dogs do not gain that 30% enrage and Rageface may resurrect; the local script has no 30% health branch, so this difficulty delta is not executable evidence.
- After both pets die, Shannox receives two Frenzy effects and uses `Magma Rupture` instead of Hurl Spear once Riplimb is dead. The local script models a generic `Berserk` cast after each pet death and switches the spear event to a local Magma Rupture spell; its coefficients and aura semantics require a frozen client/hotfix source.

## Difficulty matrix and modifier state

| Mode | Current Cataclysm Classic guide health | Current guide pet observations | Heroic/modifier delta |
|---|---:|---|---|
| 10N | 24.0M | Riplimb 8.2M; Rageface 8.2M | normal separation threshold reported as 60 yd; dogs must die before 30% |
| 10H | 33.7M | Riplimb 4.1M; Rageface 36.5M | current guide reports 80 yd, no dog 30% enrage, Rageface resurrection; exact mode table blocked |
| 25N | 81.6M | Riplimb 25.3M; Rageface 25.3M | normal separation threshold reported as 60 yd; dogs must die before 30% |
| 25H | 114.2M | Riplimb 14.3M; Rageface 127.8M | current guide reports 80 yd, no dog 30% enrage, Rageface resurrection; exact mode table blocked |

These are current-guide observations and are not asserted to include or exclude `Power of Stormrage`. The old Icy Veins table reports different health values (20.4/28.6/69.4/96.9M for Shannox) and different pet values; that page is explicitly historical. Do not combine the old table with current values or apply a second 30% reduction.

## Mechanics, targets, and local evidence

### Patrol and pull activation

Wowhead says Shannox appears after enough trash and patrols in a circle with both dogs; Icy Veins describes him as one of the first five Firelands bosses and likewise a patrolling encounter. No exact threshold or activation state is exposed in the local instance script. Historical DB identities include Shannox Controller `53910`, but an identity row does not prove the controller's 4.4.2 event logic. Treat spawn threshold, patrol route, path reset, and pull leash as `fidelity_blocked`.

### Separation Anxiety and spear distance

`Separation Anxiety` (`99835`) increases damage and attack speed by 100% for 4 seconds while the group is too far apart. Current Wowhead reports 60 yards normal and 80 heroic; Icy Veins reports 60 yards without a heroic value. Current guides recommend keeping Shannox and Riplimb about 55–60 yards apart while arranging the spear return. The local C++ file does not implement the distance aura, so the range and mode delta are sourced observations rather than executable local facts.

`Hurl Spear` (`100002`) is a 2-second cast in the spell page. Current Wowhead reports 99,450–104,550 Physical in its table and the spell page reports 117,000–123,000 Physical; the landing also triggers a fire deluge. Current guide prose describes a random area, a 3-second landing warning, about 40,000 raid-wide Fire, and circular eruptions roughly 2 seconds later. Local C++ schedules the first event at 30 seconds and repeats every 45 seconds, but calls `DoCastVictim`, not a random area target. This target/value conflict is retained.

When Riplimb is alive, local Shannox casts Hurl Spear; when Riplimb is dead, the same local event casts `Magma Rupture` (`99840`) to the area. Wowhead's related spell page is `99842` and reports 118,750–131,250 Fire, while the current guide gives roughly 70,000 normal/105,000 heroic eruption damage. Do not select one spell variant or coefficient without build evidence.

### Slash and Jagged Tear

`Arcing Slash` (`99931`) is a 125% weapon-damage frontal cone; the current page exposes a 10-yard radius and says it cannot be dodged, parried, or blocked. `Jagged Tear` (`99936`) is reported by the page as 8,000 Physical every 3 seconds for 30 seconds and stacks; current Wowhead narrative gives 6,800, so the coefficient is blocked. Local C++ first schedules Arcing Slash at 6 seconds and repeats every 12 seconds, while current guidance says roughly every 10 seconds. Both Shannox and Riplimb are taunt-immune in the current guides.

### Traps

Local Shannox schedules Immolation Trap (`99839` throw / `99838` effect) at 8 seconds then every 25 seconds, and Crystal Prison Trap (`99836` throw / `99837` effect) at 18 seconds then every 25 seconds. Each throw chooses a random valid player with `SelectTarget(SELECT_TARGET_RANDOM)`. The local trap NPCs are `53724` and `53713`; they arm after 2 seconds, poll every 500 ms, trigger within 2.5 yards, and despawn 250 ms after activation. The trap target priority is Riplimb, Rageface, then a player.

Current guides describe both trap types as random nearby placements every 25 seconds. The Immolation page reports a 9-second Fire DoT, 28,500–31,500 periodic Fire in its current presentation, and +40% damage taken; Wowhead narrative gives 65k/100k initial and 51k/75k over-time examples by difficulty. Crystal Prison can trap a player indefinitely until its roughly 2.8M crystal is destroyed, or a dog for about 10 seconds; hounds become `Wary` for 25 seconds after a trap. The local C++ does not implement the Wary/crystal-health/duration rules, so those values remain blocked.

### Riplimb

Riplimb (`53694`) has an aggro table and uses `Limb Rip` (`99832`) on its victim. Local C++ schedules the first Limb Rip at 6 seconds and repeats every 12 seconds; current guide prose says roughly every 10 seconds. When Hurl Spear lands, local C++ does not explicitly script a fetch path, while current sources say Riplimb abandons its tank, fetches the spear, and returns it. The exact movement, slow resistance (`Dogged Determination`), trap immunity window, return target, and spear handoff are therefore separated into source observations and blockers.

### Rageface

Rageface (`53695`) has no threat table in current guidance. Local C++ first switches it to a random valid player at 5 seconds and repeats every 10 seconds; it first schedules `Face Rage` at 20 seconds and repeats every 30 seconds. Current Wowhead/Icy Veins guidance describes random target periods of about 15 seconds and `Face Rage` roughly every 45 seconds. Local spell identity is `100129`, while the current Wowhead page links `99947`. During Face Rage, current guidance reports 8,000 true damage every 0.5 seconds that ramps and requires a single 30,000 damage hit in 10-player or 45,000 in 25-player; attacks are guaranteed criticals while the channel is active. These target, timer, and ID conflicts are fidelity-blocked.

### Pet death, 30% gate, and final burn

Local pet `JustDied` calls Shannox's pet-death action. The boss increments `_frenzyStacks` and casts generic `Berserk` (`26662`) when the second pet dies. Current Wowhead instead describes `Frenzy` as +40% attack speed and +25% Physical damage for 5 minutes per hound, stacking twice; Icy Veins reports a different +30% description. The local script has no Shannox-at-30% check and no `Frenzied Devotion` cast, while normal-mode strategy sources require both pets dead before 30% and heroic sources describe a different rule. This phase/difficulty delta cannot be promoted without runtime evidence.

## Repository, DB, reset, unlock, and credit audit

The audited revision is `8eb54f0160b3c3d986ed944f9d64ebf83922c0f8`.

- `src/server/scripts/Kalimdor/Firelands/boss_shannox.cpp` is present and loaded by `kalimdor_script_loader.cpp`. It defines the local spell IDs, event schedule, random target selectors, dog actions, trap AI, generic reset/evade/death handling, and the local Hurl/Magma branch. It does not implement patrol activation, separation anxiety, 30% dog enrage, Wary/Dogged Determination, spear fetch movement, or retail mode scaling.
- `firelands.h` defines map 720, `DATA_SHANNOX=2`, boss `53691`, dogs `53694`/`53695`, trap NPCs `53713`/`53724`, and the seven-boss instance. `instance_firelands.cpp` maps the boss/dogs and generic door/boss state but has no Shannox-specific activation or `SetBossState` branch.
- Historical TDB identifies Shannox `53691`, variants `53979`, `54079`, `54080`, `54105`; Riplimb `53694`; Rageface `53695`; Crystal Prison Trap `53713`; Immolation Trap `53724`; Spear of Shannox `53752`/`54112`; and Shannox Controller `53910`. Encounter row `1205` maps entry `53691` to Shannox. These are identity rows, not a 4.4.2 mode/scaling table.
- Local `Reset()` resets Frenzy state and disengages the encounter. `EnterEvadeMode()` tells both dogs to evade, returns Shannox home, despawns summons, and calls `_DespawnAtEvade()`. On death, generic `_JustDied()` runs and dogs are despawned after 5 seconds. Generic boss state supplies a local completion path, but retail lockout, loot, achievement, and player-credit recipients are not proven by this audit.

## Material blockers

- Exact 4.4.2 client/DBC build, hotfix cutoff, four-mode health/damage table, and whether guide values include `Power of Stormrage`.
- Official modifier aura/NPC IDs, default/toggle persistence, and interaction with DB creature modifiers.
- Trash-clearing threshold, Shannox Controller activation, patrol route, spawn/despawn, leash, and reset behavior.
- Separation Anxiety range (60 versus 80 heroic), aura refresh semantics, and target set.
- Hurl target (local victim versus guide random area), spear landing/deluge/eruption spell variants, timers, ranges, and Fire/Physical coefficients.
- Arcing/Limb Rip cadence (local 6/12 versus guide about 10 seconds), Jagged Tear coefficient, tank reset, taunt immunity, spear fetch, Dogged Determination, Wary, and crystal health/duration.
- Rageface target/cadence and local `100129` versus current `99947`, Face Rage break threshold by mode, Feeding Frenzy reset, and heroic resurrection.
- Normal 30% `Frenzied Devotion` versus heroic dog behavior, local generic Berserk values, final Magma Rupture scaling, and all difficulty deltas.
- Retail wipe cleanup, door/lockout, loot, achievement, and player credit semantics.

## Source metadata

1. [Wowhead Shannox strategy guide](https://www.wowhead.com/cata/guide/raids/firelands/shannox-strategy-overview), Beanna, updated 2024-10-25, page labelled Patch 4.4.2. Used for current four-mode Shannox/pet health, patrol activation summary, distances, trap/spear values, pet behavior, heroic delta, and current spell links.
2. [Icy Veins Cataclysm Classic Shannox guide](https://www.icy-veins.com/cataclysm-classic/shannox-encounter-guide-strategy-abilities-loot), Abide, updated 2024-10-08. Used independently for patrol, spear, traps, dog handling, normal/heroic strategy, final Magma Rupture, and achievement scope.
3. [Historical Icy Veins Shannox guide](https://www.icy-veins.com/wow/shannox-strategy-guide-normal-heroic), updated 2012. Used only to document legacy health/pet and ability conflicts; not treated as 4.4.2 authority.
4. [Blizzard: Firelands difficulty reduction with Hour of Twilight patch](https://us.forums.blizzard.com/en/wow/t/firelands-difficulty-reduction-with-hour-of-twilight-patch/2059756), Kaivax, 2025-02-13. Official 4.4.2 source for `Power of Stormrage`, 30% health/damage reduction, and General Taldris Moonfall deactivation.
5. [Blizzard: Cataclysm Classic Patch 4.4.1 notes](https://us.forums.blizzard.com/en/wow/t/world-of-warcraft-cataclysm-classic-patch-441-notes/1996710) and [4.4.2 notes](https://us.forums.blizzard.com/en/wow/t/world-of-warcraft-cataclysm-classic-patch-442-notes/2062030). Used for Firelands endpoint and cutoff context; neither publishes Shannox's client/DBC table.
6. Wowhead [Shannox NPC page](https://www.wowhead.com/cata/npc=53691/shannox) and linked [spell pages](https://www.wowhead.com/cata/spell=100002/hurl-spear). Used for identity and page-level ranges; legacy/malformed or contradictory fields remain blocked.
7. Local repository at revision `8eb54f0160b3c3d986ed944f9d64ebf83922c0f8`: `boss_shannox.cpp`, `firelands.h`, `instance_firelands.cpp`, `kalimdor_script_loader.cpp`, and historical SQL under `sql/old/4.3.4`. Used for executable local schedules/actions and DB identity only.
