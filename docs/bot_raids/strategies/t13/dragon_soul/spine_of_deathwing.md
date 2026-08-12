# Spine of Deathwing — Phase 0 research contract (Cataclysm Classic 4.4.2)

This dossier covers `10N`, `10H`, `25N`, and `25H` Spine of Deathwing in Dragon Soul. It is a source-and-identity audit, not a live-validation result. The target is Cataclysm Classic 4.4.2, build `59185`, `enUS`, at the corrected official Dragon Soul unlock cutoff `2025-02-20T23:00:00Z` (February 20, 3:00 p.m. PST). No inferred four-mode tuning is promoted to executable behavior.

## Observable encounter contract

After Warmaster Blackhorn, the raid speaks to Sky Captain Swayze and parachutes onto Deathwing's back. Four Corruptions occupy the initial exposed holes. Corruption casts Searing Plasma on a random player and Fiery Grip on players; damaging the casting Corruption breaks the grip. A Corruption death spawns a Hideous Amalgamation, while the last living Corruption is reported to respawn so at least one remains.

Deathwing periodically rolls toward the side with more raid weight. Players standing in Grasping Tendrils are tethered to the back and survive the roll; Amalgamations do not receive that protection and can be thrown away. Corrupted Bloods spawn from exposed holes, can be killed for a raid-wide Burst and an indestructible Residue, and the residue crawls back toward a hole to reform a Blood. Feeding nine residues to one low-health Amalgamation gives Superheated Nucleus. Killing it near a plate triggers Nuclear Blast, exposes a Burning Tendon, and starts Seal Armor Breach. The same side's tendon must be exposed twice per plate; three plates end the encounter.

Current Cataclysm Classic sources agree on those relationships. Exact spawn cadence, roll weighting, hitboxes, add health/damage, four-mode coefficients, and all local reset/credit behavior remain blocked. The current Wowhead guide was updated March 27, 2025, after both the target cutoff and the first Presence modifier, so it is used for mechanics rather than a cutoff tuning table. Icy Veins was updated February 15, 2025, before the cutoff and is the principal pre-cutoff corroboration.

## Difficulty matrix and modifier timeline

| Mode | Historical secondary health observations* | Stable observed delta | Modifier at target cutoff |
|---|---|---|---|
| 10N | Corruption 442k; Blood 166k; Amalgamation 7M; Tendon 2.9M | 1–2 tanks, 2–3 healers, 5–7 DPS; Normal has no Degradation/Blood Corruption package | Dragon Soul is unlocked at `2025-02-20T23:00:00Z`; Presence was not yet announced or active |
| 10H | Corruption 800k; Blood 300k; Amalgamation 9.8M; Tendon 12.6M | 2 tanks, 3 healers, 5 DPS; Degradation and Blood Corruption are active; each plate generally needs two exposures | Same; exact build-59185 health/damage is blocked |
| 25N | Corruption 1.5M; Blood 581k; Amalgamation 25M; Tendon 9.3M | 2 tanks, 5–6 healers, 17–18 DPS; Normal mechanics otherwise repeat with larger scaling | Same |
| 25H | Corruption 2.5M; Blood 900k; Amalgamation 30M; Tendon 39.3M | 2–3 tanks, 6 healers, 16–17 DPS; add saturation and Heroic debuffs are the major deltas | Same |

\* These numbers are from an older retail Icy Veins strategy table, not a Cataclysm Classic 4.4.2 build-59185 evidence table. They are retained as historical comparison only. Current Classic guides expose qualitative and page-level values but no complete four-mode health table.

Blizzard later announced `Presence of the Dragon Soul`: starting March 18, 2025, Dragon Soul enemies received 5% less health and damage, increasing by 5 percentage points every two weeks to 30% by the end of May; Lord Devrestrasz can remove the aura. This is post-cutoff and is not applied. Aura ID, toggle NPC ID, default persistence, and ordering relative to mode scaling are unresolved. Later February 21 hotfix notes changed Yor'sahj's Forgotten Ones/Mana Voids, not Spine. The April 3 hotfix added an Essence of Corrupted Deathwing drop to Spine, a later loot delta rather than target encounter behavior.

## Mechanics, targets, values, and timers

### Pull, Corruptions, and Fiery Grip

The encounter starts through Sky Captain Swayze; current guidance reports four starting Corruptions and at least one living Corruption at all times. `Searing Plasma` (`105479`) is an unlimited-range instant aura: the current page presents a `420,000` healing absorb and `12,000` Physical damage every 10 seconds, while its effect rows include lower Normal and legacy mode values. Exact target count, mode values, duration, and the relationship between current and legacy rows are blocked.

`Fiery Grip` (`105490`) is an unlimited-range channel displayed as 30 seconds and 90,000 Fire damage every 3 seconds in current page prose. Current Icy Veins says damage equal to 16% of Corruption health breaks it; the current Wowhead guide says 20%. The page's effect rows also show lower/legacy values. Preserve the channel, target/stun relationship, and conflict, not a single break threshold.

### Roll and Grasping Tendrils

Deathwing rolls toward the side with the greater raid distribution. `Grasping Tendrils` (`105563`) is a 5-yard effect that deals `5,250–6,750` Fire damage, reduces movement speed by 35%, and prevents a player from being flung off. Current guides describe a short grace period before the roll and require players to be in a tendril area before the roll begins. The roll trigger weighting, grace duration, side geometry, player count threshold, add cleanup, and exact tendril duration are not frozen. A roll can be deliberately used to discard Amalgamations and some Bloods; killing/retaining the last Corruption around a roll is a phase-control decision.

### Corrupted Blood and Residue

Corrupted Blood (`53889`) has a weak melee profile and a normal threat table in historical guidance. On death, `Burst` (`105219`) is an instant Physical explosion with a 200-yard page radius; the page shows `26,718–29,531` and legacy mode rows. The exact current mode damage, whether all living raid members are affected by the practical room radius, and kill/reset cadence are blocked. The death leaves `Residue` (`105223`), an indestructible, pacified object that crawls toward the nearest exposed hole and reforms into a new Blood. Crawl speed, target-hole selection, lifetime, and reformation timing are not established.

### Hideous Amalgamation and plate exposure

Hideous Amalgamation (`53890`) absorbs nearby Residues. Each `Absorbed Blood` stack is reported as +10% damage and +20% attack speed, with nine stacks granting `Superheated Nucleus` (`106264`). The current page presents `30,450–39,550` Fire to all enemies every 3 seconds while superheated. Killing a superheated Amalgamation casts `Nuclear Blast` (`105845`), a 5-second cast with `350,625–399,375` Fire within 8 yards, and pries up a nearby plate. The exact Absorb Blood radius, stack range, mode coefficients, superheated tick implementation, and plate-proximity geometry remain blocked.

`Burning Tendons` (`56341`/`56575`, with historical left/right variants) become attackable when a plate is lifted. `Seal Armor Breach` (`105847`) is a 23-second cast that re-covers the tendon; current comments/guides describe roughly 3 seconds of non-targetability, leaving about 18–20 seconds of practical damage time. A tendon must be reduced by about half on each exposure in current guidance, but the exact 4.4.2 window and health values are not frozen. Two successful exposures on the same side detach one plate; three detached plates end the encounter.

### Heroic-only deltas

Heroic adds `Degradation` whenever a Hideous Amalgamation dies, reducing raid maximum health by 5% per current Icy Veins presentation. Historical guidance reports 6%, so the coefficient is blocked. `Blood Corruption: Death` (`106199`) is a dispellable, jumping debuff that current guidance gives 15 seconds before a raid wipe; its page presents 16 seconds. Repeated/random dispels can mutate it to `Blood Corruption: Earth` (`106200`), the beneficial version; current Icy Veins says up to two stacks of 20% damage reduction (40% total), while other page/guide summaries differ. The exact mutation probability, jump filter, stack cap, and failure event are blocked.

Heroic 25 commonly uses a third tank to kite the increasing Blood/Amalgamation population. The number and cadence of Corrupted Blood spawns grow as plates are removed and as the fight continues; current guides describe eight exposed areas by the later stages. This is a qualitative scaling relationship, not a fixed spawn table.

## Phase, reset, prerequisite, and credit audit

Normal and Heroic both repeat the same three plate stages. Stage 1 begins with four Corruptions; later stages add exposed holes and therefore more Corruption/Blood spawn opportunities. The final successful tendon/plate removal instantly ends Spine and leads toward Madness of Deathwing. The local checkout declares `DATA_SPINE_OF_DEATHWING = 6` and a map-object ID for the spine head, but does not bind Spine creatures, a Sky Captain trigger, plate/tendon lifecycle, roll, or difficulty branches.

Historical SQL identifies encounter row `1291`, journal key `104574`, Corruption `56162`, Corrupted Blood `53889`, Hideous Amalgamation `53890`, Burning Tendons `56341`/`56575`, Sky Captain Swayze `55870`, and historical variants. Those rows are identity evidence only. No targeted local map-967 spawn/lifecycle record or Spine AI was found. The raid overview establishes that Blackhorn precedes Spine, but local prerequisite enforcement, wipe reset, parachute/teleport, soft reset, roll-death reactivation, lockout, loot cache, achievement and player-credit semantics remain unresolved.

`Maybe He'll Get Dizzy...` (`6106`) requires Left, Right, Left, Right rolls, and `Fall of Deathwing` (`6107`) includes Spine, but achievement credit is not locally executable proof. The April 3, 2025 Essence drop change is explicitly later than the target snapshot and is not applied to the contract.

## Material blockers

- Exact build-59185/enUS four-mode health, damage, add, tendon, and variant tuning; historical table values are non-executable.
- Release/hotfix lineage at `2025-02-20T23:00:00Z`; later February/March/April changes are separated and not silently applied.
- Presence aura/toggle IDs, state, persistence, and mode-scaling order; target cutoff has no Presence modifier.
- Sky Captain trigger, parachute timing, initial Corruption count/respawn, Corruption Searing Plasma target/coefficients, Fiery Grip threshold conflict, and channel cadence.
- Roll weighting, side geometry, grace window, tendril lifetime/radius, player/add cleanup, and death/rejoin behavior.
- Blood spawn cadence/health, Burst mode damage, Residue crawl/reformation timing, Amalgamation Absorb radius, Superheated ticks, Nuclear Blast proximity/damage, and plate/tendon side mapping.
- Seal Armor Breach exposure window, tendon health, stage spawn counts, Heroic Degradation coefficient, Blood Corruption mutation/jump/failure semantics, and 25H kite scaling.
- Wipe/reset, prerequisite/order, lockout, loot cache, later credit, achievements, and absent local implementation.

## Source metadata

1. [Blizzard Cataclysm Classic Patch 4.4.2 notes](https://us.forums.blizzard.com/en/wow/t/world-of-warcraft-cataclysm-classic-patch-442-notes/2062030), Kaivax, February 18, 2025. Official release: Dragon Soul becomes available February 20 at 3:00 p.m. PST; 10/25-player Normal/Heroic, eight bosses.
2. [Blizzard: Presence of the Dragon Soul begins March 18](https://us.forums.blizzard.com/en/wow/t/presence-of-the-dragon-soul-begins-march-18/2074792), Kaivax, March 12, 2025. Official post-cutoff global health/damage modifier and toggle; not applied.
3. [Blizzard Hotfixes: February 21, 2025](https://worldofwarcraft.blizzard.com/en-us/news/24148555/hotfixes-january-3-2025). Post-cutoff notes contain Yor'sahj changes, not Spine tuning; retained to distinguish unrelated hotfixes.
4. [Blizzard Hotfixes: April 3, 2025](https://news.blizzard.com/en-us/article/24179333/hotfixes-april-3-2025). Post-cutoff: LFG enabled for Dragon Soul and Essence of Corrupted Deathwing added to Spine loot.
5. [Wowhead Spine of Deathwing strategy guide](https://www.wowhead.com/cata/guide/raids/dragon-soul/spine-of-deathwing-strategy-overview), Riyani, updated March 27, 2025. Post-cutoff and post-Presence; used for current qualitative mechanics and page-linked identities, not target tuning.
6. [Icy Veins Spine encounter guide](https://www.icy-veins.com/cataclysm-classic/spine-of-deathwing-encounter-guide-strategy-abilities-loot), Abide, updated February 15, 2025. Pre-cutoff corroboration for stage flow, targets, current page-level values, Heroic deltas and timing observations.
7. [Icy Veins historical Spine strategy](https://www.icy-veins.com/wow/spine-of-deathwing-strategy-guide-normal-heroic), updated for an older retail expansion. Historical health table and old Heroic coefficient comparison only.
8. [Wowhead current Spine spell/NPC identities](https://www.wowhead.com/cata/spell=105479/searing-plasma), including linked Searing Plasma, Fiery Grip, Burst, Residue, Superheated Nucleus, Nuclear Blast, Grasping Tendrils, Seal Armor Breach, Blood Corruption and Burning Tendon pages. Used for IDs/page values; legacy rows and comments remain blocked.
9. [Warcraft Tavern Spine of Deathwing raid guide](https://www.warcrafttavern.com/cataclysm/guides/spine-of-deathwing-raid-guide/), accessed August 12, 2026. Secondary corroboration for no known enrage, role shape, and Heroic 5% Degradation; no unique exact value is promoted.
10. Local repository revision `6989485d452b10c40408b259c43e251f8af80cd2`: `dragon_soul.h`, `instance_dragon_soul.cpp`, and `kalimdor_script_loader.cpp`. Used for map/data/loader absence only.
11. Local historical SQL at `sql/old/4.3.4/TDB04_to_TDB05_updates/world/066_instance_encounters.sql`, `047_creature_template.sql`, `128_creature_template.sql`, `004_creature_template.sql`, and `037_spell_target_position.sql`. Used for historical encounter, NPC, spell-position, and variant identities only; it does not establish 4.4.2 tuning, reset, loot, or credit.
