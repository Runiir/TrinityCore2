# Majordomo Staghelm — Phase 0 research contract (Cataclysm Classic 4.4.2)

This dossier targets enUS Cataclysm Classic `4.4.2`, build `59185`, at cutoff `2025-02-18T19:31:51.916Z`. It covers 10-player and 25-player Normal/Heroic. It is sourced planning evidence, not a live-validation result. Blizzard announced that 4.4.2 applies the Firelands-wide `Power of Stormrage` debuff, reducing enemy health and damage by 30%; General Taldris Moonfall can remove it. The aura identity, persistence, and runtime default are not present in this repository snapshot, so those fields remain `fidelity_blocked`.

## Observable encounter contract

- Majordomo is the sixth Firelands boss, after Baleroc, on the northern platform. Official 4.4.1 notes define Firelands as a 10/25-player, seven-boss raid with Normal and Heroic modes. Current guidance says Baleroc's defeat opens the bridge; the local instance summons Majordomo and also has a local Druid-of-the-Flame death hook whose retail prerequisite is not proven.
- The encounter is one repeating form controller, not a fixed health phase split. Staghelm is in Scorpion Form when the clump threshold is met and Cat Form when it is not. Current sources report thresholds of 7 players in 10-player raids and 18 in 25-player raids. The local script confirms those counts, but switches only after three consecutive controller observations; the controller aura interval is DB/DBC-dependent and unresolved.
- At 100 energy, Scorpion Form uses `Flame Scythe`; Cat Form uses `Leaping Flames`. Each special grants Adrenaline (+20% energy regeneration per stack) and a form change resets Adrenaline/energy in current guidance. Each change grants Fury (+8% special damage in current guidance). Local code skips Fury on the first transformation, so the exact initial-stack rule is blocked.
- After the third animal-form change, Staghelm briefly returns to Night Elf/Druid form, casts `Fiery Cyclone`, then casts Searing Seeds if the previous form was Cat or Burning Orbs if it was Scorpion, before the next positioning decision. The local branch matches that previous-form test; current prose has a contradictory shorthand in one source, so sequence and naming remain source-qualified.
- Heroic alone adds Concentration. The local script applies the boss aura only when `IsHeroic()`, then maps alternate power 25/50/75/100 to Uncommon/Rare/Epic/Legendary Concentration. Current guidance reports 0–24/25–49/50–74/75–99/100 as 0/25/50/75/100% damage and healing; any damaging hit clears the bar. Runtime power fill and all mode spell coefficients remain build-sensitive.

## Current four-mode observations and modifier

| Mode | Current guide boss health | Local/guide mode observations | Modifier state |
|---|---:|---|---|
| 10N | 51.0M | clump threshold 7; Concentration absent | `Power of Stormrage`: 0.70 health/damage if active; announced applied with optional removal, runtime persistence unverified |
| 10H | 124.7M | clump threshold 7; Concentration present | same official modifier; heroic spell/orb deltas are conflicting |
| 25N | 178.6M | clump threshold 18; Concentration absent | same official modifier; orb count differs across current pages |
| 25H | 432.1M | clump threshold 18; Concentration present | same official modifier; heroic spell/orb deltas are conflicting |

The Wowhead health table was updated before the 4.4.2 modifier announcement and is therefore retained as an unmodified guide observation, not as a post-modifier runtime value. If the official debuff is active, multiplying those observations by `0.70` is arithmetic only, not a verified 59185 health table. The resulting values would be 35.7M/87.29M/125.02M/302.47M in 10N/10H/25N/25H, but they remain `fidelity_blocked` until client/DBC or runtime evidence confirms application to this boss.

## Mechanics, targets, values, and local evidence

### Unlock, positioning, and form controller

Current guidance places Staghelm after Baleroc and describes a northern platform/bridge prerequisite. Local `instance_firelands.cpp` summons entry `52571` on instance creation/load, maps `DATA_MAJORDOMO_STAGHELM=5`, controls passage firewall `208906`, and sends Baleroc's `DONE` action to Staghelm for a 10s/11s/11s outro. It also counts Druid of the Flame `53619` deaths and starts the local intro move after 3 deaths in 10-player or 6 in 25-player. These hooks do not prove the 4.4.2 retail unlock sequence or whether the pre-summoned boss is attackable.

The local form controller is `98386`, periodically casts clump check `98399`, and counts at least 7 nearby players in 10-player or 18 in 25-player. Three consecutive clustered observations select Scorpion; three consecutive split observations select Cat. Local area radius comes from spell data and is not frozen in the repository. Current guides describe the same thresholds but do not publish the controller tick interval or exact radius.

### Energy, Adrenaline, Fury, and special attacks

Local energy is enabled by `72242`; form controller `98386` starts on engage. The event polls every 400ms and casts the current form ability at exactly 100 energy. Current Wowhead/Icy Veins report about 18 seconds to the first 100 energy, then 12/10/8/7/6/5/4 seconds at 1–7 Adrenaline stacks; the local source does not define the energy fill rate. Adrenaline `97238` is +20% energy regeneration per stack. Fury `97235` is reported as +8% Flame Scythe/Leaping Flames damage per stack; the local first transformation does not cast it, so initial and post-Night-Elf stack timing are blocked.

In Scorpion Form (`98379`), `Flame Scythe` (`98474`) is a frontal Fire attack split among targets. Current Wowhead reports about 1.75M normal and 2.5M heroic; its NPC page exposes a different 2.7M value, and the local spell script has no coefficient. Range, cone, target filter, and the four-mode modifier remain blocked.

In Cat Form (`98374`), local targeting (`101165`) excludes the victim, prefers ranged classes/specs, and falls back to any target; it summons Spirit of the Flame (`52593`) through `101222` and triggers the landing effect. Current guides describe a random ranged target, a 12-yard fire zone lasting 1 minute, and roughly 20k normal/28k heroic or 26,036–29,213 / 30,630–34,368 Fire depending on page. The local source does not establish the patch radius, ground lifetime, damage, or add scaling. Spirit receives local `101224` stun-and-hate and enters zone combat after 1 second; its health/damage and retail ability set are unresolved.

### Night Elf transition and Fiery Cyclone

On the third animal-form change, local code removes both form auras and Adrenaline, casts `Fiery Cyclone` (`98443`), then casts Searing Seeds (`98450`) when leaving Cat or Burning Orbs (`98451`) when leaving Scorpion. It resets form state and waits for the next controller decision. Current sources agree on a 3-second raid-wide stun/invulnerability; the local spell exposes a 200-yard radius and 3-second duration. Exact transition cast ordering, action immunity, energy reset, and whether the current source's “after each form once” shorthand is a guide error remain `fidelity_blocked`.

### Searing Seeds

Local `98450` targets the area enemy list. Its spell script assigns each target `10s + (5s × order)` in 10-player or `10s + (2s × order)` in 25-player, then casts seed effect `98620` when the aura expires. This is executable repository behavior, not proof of retail ordering or whether tanks are excluded. Current Wowhead reports a 4-second cast, 12-yard explosion, 63,750/64k or 75,000 Fire depending page, and timers from roughly 14 seconds to 1 minute; Icy Veins confirms per-player random timers and moving out before expiry. Range, damage, target exclusions, ordering, and all mode coefficients remain blocked.

### Burning Orbs

Local `98451` summons five `53216` Burning Orbs through `98565`, regardless of mode. Current Wowhead's guide describes five random courtyard orbs, 3,750 normal/7,650 heroic Fire every 2 seconds, stacking to 50, resetting after 6 seconds without damage, and despawning after 1 minute. Current Icy Veins instead describes two orbs and says heroic damage doubles; historical comments report two in 10-player Normal and five in 25-player Normal. The local script does not implement orb count, nearest-target selection, tick, stack cap/reset, lifetime, or heroic scaling; every one of those values is retained as a conflict.

### Concentration and heroic delta

On Heroic engage only, local `98256` applies the Concentration controller (script registration is historical SQL `98229`). Its alternate-power thresholds select `98254`, `98253`, `98252`, or `98245` at 25/50/75/100. A damaging proc clears the concentration aura and sets power to zero. Current Wowhead/Icy Veins describe 25% damage/healing per 25 concentration to 100%, with Legendary at +100%; the local source confirms tier IDs and reset handling but not fill cadence, damage-event coverage, or whether every listed spell is present in build 59185. Normal/Heroic Concentration presence is the only stable difficulty delta.

## Reset, prerequisite, completion, and credit audit

- Local `Reset` state is inherited from `BossAI`; constructor state starts in Druid form with first-transformation=true, zero form counters, zero seed counter, and zero add-death counter. `EnterEvadeMode` despawns summons, disengages the encounter frame, sets `DATA_MAJORDOMO_STAGHELM` to `FAIL`, and despawns the boss. Instance `FAIL` schedules a respawn after 30 seconds at `{523.4965,-61.987846,83.94701}`; initial/load spawn is `{570.2274,-61.82986,90.42272}`. Retail leash, wipe cleanup, aura removal, and patrol/reactivation timing are not proven.
- On death, local `JustDied` removes dynamic objects, disengages the encounter frame, removes Searing Seeds from players, and leaves generic `BossAI` completion/loot/state handling to the instance. Historical SQL encounter row `(1185,0,52571,0,'Majordomo Staghelm')` confirms identity only. Lockout, loot recipient, achievement, reputation, and player-credit semantics at the 59185 cutoff remain unresolved.
- Baleroc `DONE`, Druid death counts, firewall passage, boss state `DONE/FAIL`, and respawn are repository hooks. They are not promoted to authoritative retail prerequisite or reset contracts without client/DB/runtime confirmation.

## Repository and DB identity audit

Audited revision: `8eb54f0160b3c3d986ed944f9d64ebf83922c0f8`.

- `src/server/scripts/Kalimdor/Firelands/boss_majordomo_staghelm.cpp` is present and loaded by `kalimdor_script_loader.cpp`. It contains all local spell IDs, form controller, class/spec target preference, seed-duration calculation, Concentration tiers, five-orb summon loop, reset/evade/death handling, and 400ms energy polling.
- `firelands.h` defines map `720`, `DATA_MAJORDOMO_STAGHELM=5`, boss `52571`, Spirit `52593`, Burning Orb `53216`, Druid of the Flame `53619`, and firewall `208906`. `instance_firelands.cpp` maps the boss, passage door, Baleroc action, Druid death hook, initial/load summon, and 30s failure respawn.
- Historical SQL assigns `boss_majordomo_staghelm` to entry `52571`, includes variants `53856`–`53861`, sets historical `DamageModifier`/`BaseVariance` groups, registers the local spell scripts, and maps encounter `1185` to entry `52571`. Variant-to-mode mapping and current 59185 DB/DBC tuning are not established.

## Material blockers

- Exact 59185 client/DBC spell/build data for energy fill, controller periodicity/radius, form transition ordering, damage/range coefficients, orb/seed effects, add scaling, and concentration power fill.
- Firelands guide health values versus `Power of Stormrage` application, plus official modifier aura ID, default/persistence/toggle behavior, and General Taldris interaction scope.
- Baleroc/bridge/Druid prerequisite semantics, initial attackability, instance re-entry, and retail unlock state.
- Scorpion/Cat targeting and thresholds beyond the 7/18 observation count; Fury first-stack and post-transition semantics; Adrenaline reset and energy timing.
- Flame Scythe cone/range/targeting and all four-mode damage; Leaping Flames range, target exclusions, patch radius/lifetime, Spirit health/damage, and heroic scaling.
- Fiery Cyclone cast ordering, immunity/action lock, and Night Elf transition timing.
- Searing Seeds target exclusions/order, duration distribution, explosion damage/range, immunity/death behavior, and four-mode deltas.
- Burning Orb count (local 5 versus current Icy 2 and historical 10/25 split), nearest-target/range, tick/damage, cap/reset/lifetime, and heroic multiplier.
- Concentration fill, proc coverage, tier behavior, and whether current guide values represent 59185.
- Wipe/evade cleanup, respawn/reactivation, lockout, loot, achievements, reputation, and player credit.

## Source metadata

1. [Blizzard: Cataclysm Classic Patch 4.4.1 notes](https://us.forums.blizzard.com/en/wow/t/world-of-warcraft-cataclysm-classic-patch-441-notes/1996710), Kaivax, 2024-10-29. Official Firelands scope, release, seven-boss/10-25 Normal-Heroic definition, and warning that tuning was reverted toward an earlier state.
2. [Blizzard: Cataclysm Classic Patch 4.4.2 notes](https://us.forums.blizzard.com/en/wow/t/world-of-warcraft-cataclysm-classic-patch-442-notes/2062030), Kaivax, 2025-02-18 19:31, cutoff context for build 59185 and the Hour of Twilight release.
3. [Blizzard: Firelands difficulty reduction](https://us.forums.blizzard.com/en/wow/t/firelands-difficulty-reduction-with-hour-of-twilight-patch/2059756), Kaivax, 2025-02-13. Official `Power of Stormrage` 30% health/damage reduction and General Taldris Moonfall removal behavior.
4. [Wowhead Majordomo strategy](https://www.wowhead.com/cata/guide/raids/firelands/majordomo-staghelm-strategy-overview), Beanna, updated 2024-10-25. Current four-mode health, form thresholds, energy/Adrenaline/Fury, spell observations, targets, and current heroic Concentration/orb strategy.
5. [Icy Veins Cataclysm Classic Majordomo guide](https://www.icy-veins.com/cataclysm-classic/majordomo-staghelm-encounter-guide-strategy-abilities-loot), Abide, updated 2024-10-08. Independent current corroboration for form logic, Adrenaline timing table, heroic Concentration, seeds/orbs, adds, and conflicts.
6. [Wowhead Majordomo NPC and linked spell pages](https://www.wowhead.com/cata/npc=52571/majordomo-staghelm). Identity and page-level spell values/ranges; contradictory or legacy fields are not silently promoted.
7. Local repository at revision `8eb54f0160b3c3d986ed944f9d64ebf83922c0f8`: `boss_majordomo_staghelm.cpp`, `firelands.h`, `instance_firelands.cpp`, `kalimdor_script_loader.cpp`, and historical SQL. Used for executable local behavior and identity only, not as proof of 59185 retail tuning.
