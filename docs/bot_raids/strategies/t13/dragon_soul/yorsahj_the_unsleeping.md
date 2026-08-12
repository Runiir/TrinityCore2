# Yor'sahj the Unsleeping — Phase 0 research contract (Cataclysm Classic 4.4.2)

This dossier covers `10N`, `10H`, `25N`, and `25H` Yor'sahj the Unsleeping in Dragon Soul. It is a source-and-identity audit, not a live-validation result. The requested snapshot is Cataclysm Classic 4.4.2, build `59185`, `enUS`, at the official global raid unlock `2025-02-20T23:00:00Z`. Guide observations around opening do not by themselves become an exact executable tuning table.

## Observable encounter contract

Yor'sahj is a single-room fight built around repeated calls of Blood of Shu'ma. A wave presents three differently colored globules on Normal and four on Heroic. The raid chooses one to kill before it reaches the boss; the surviving globules become immune after the first death. Current Cataclysm Classic guides agree on six allowed combinations rather than every mathematical color combination, but exact runtime selection, movement speed, spawn coordinates, and variant mapping are not frozen for the requested build.

The first call is reported at about 25 seconds after pull and subsequent calls about 75 seconds apart. Globules emerge from fixed colored mounds and travel toward the boss. During the approach, the boss's ordinary attack/ability cadence is reported as paused, but no local script exists to establish the pause or reset behavior. Yor'sahj's innate Void Bolt is a tank-directed Shadow hit with a stacking damage-over-time component; tank swaps at roughly two to three stacks are common guidance, not a four-mode executable contract.

The color that reaches the boss determines the phase package:

- Green/Acidic Blood applies Digestive Acid about every 10 seconds to the raid. It splashes to allies within 4 yards, so current guidance spreads players by at least 5 yards. The current Classic spell pages expose hidden/server-side dummy components, not a reliable damage table.
- Red/Crimson Blood applies Searing Blood to random players; current guides describe three targets, while the Wowhead Encounter Journal says eight in 25-player. Damage increases with distance from Yor'sahj, so the raid stacks near him. The conflict is retained rather than selected.
- Blue/Cobalt Blood summons Mana Void, which drains mana and stores it. Killing the void returns stored mana to players in its return area; current guides describe a 25-yard return area, while older guidance reports 30 yards. Yellow plus Blue is reported to create a second Mana Void.
- Purple/Shadowed Blood applies Deep Corruption. Every fifth qualifying heal or absorb causes a raid-wide detonation; the aura is shown for 25 seconds before stacks reset. The exact heal/absorb filter, mode damage, and reset timing are not frozen.
- Black/Dark Blood creates Forgotten Ones. They fixate random players and cast Psychic Slice; they cannot be handled as a normal boss tank target. Current guides describe one wave, and two waves with Yellow, but do not provide a verified four-mode count.
- Yellow/Glowing Blood empowers Yor'sahj: nearby Void Bolt gains an additional Shadow component, affected abilities occur twice as often, and attack speed rises by 50%. Green and Red are described as five-second effects instead of ten; Blue gains another Mana Void and Black another Forgotten One wave. Purple has no reported additional benefit.

## Difficulty matrix and six observed combinations

| Mode | Current guide health observation* | Globules | Observed six-color table / heroic delta | Modifier at requested cutoff |
|---|---:|---:|---|---|
| 10N | 47M | 3 | `Black-Blue-Yellow`, `Black-Green-Red`, `Black-Purple-Red`, `Blue-Green-Purple`, `Blue-Purple-Yellow`, `Green-Red-Yellow` | No Presence announcement or active modifier evidenced by the cutoff; raid opens after cutoff |
| 10H | 90M | 4 | `Black-Blue-Green-Purple`, `Black-Blue-Green-Red`, `Black-Green-Red-Yellow`, `Black-Blue-Purple-Yellow`, `Black-Purple-Red-Yellow`, `Blue-Green-Purple-Yellow` | Same |
| 25N | 142M | 3 | Same six Normal combinations; red target count conflicts between sources | Same |
| 25H | 232M | 4 | Same six Heroic combinations; kill priority and target/count scaling are not fully frozen | Same |

\* Wowhead's current Cataclysm Classic guide labels these values 4.4.2 but was updated on 2025-02-19, one day before the global unlock cutoff. They are retained as observations only. A historical Icy Veins table gives add health observations (Normal 10: ooze 1.8M, Mana Void 1.5M, Forgotten One 490k; Heroic 10: 2.5M/2M/830k; Normal 25: 5.4M/5M/1.5M; Heroic 25: 8.2M/6.5M/2.7M), but it is not current Classic build evidence and is not used as executable tuning.

The normal combination-to-kill guidance is: kill Yellow for Black-Blue-Yellow and Blue-Purple-Yellow; kill Green for Black-Green-Red, Blue-Green-Purple, and Green-Red-Yellow; kill Purple for Black-Purple-Red. Heroic tables commonly recommend killing Green in the first three listed Green-heavy combinations and Yellow in the other three, but a four-mode runtime table is not confirmed. Surviving globules' immunity is the stable relationship; exact health threshold and immunity timing remain blocked.

## Mechanics, targets, and values

### Void Bolt and globule lifecycle

`Void Bolt` is current Classic spell `104849`. The Encounter Journal and current guide present an initial `92,500–107,500` Shadow hit followed by `46,250–53,750` every 2 seconds; the linked spell page also exposes legacy/effect rows that do not agree with a clean four-mode table. It is described as tank-only/primary-target damage, stacking until the next phase, but exact target filter, stack reset, cast cadence, and mode coefficients remain `fidelity_blocked`.

`Fusing Vapors` (`103635`) is reported below 50% globule health: it heals every other active globule for 5% of maximum health. The current page gives a very large radius (200 yards), but threshold implementation, tick/cast behavior, and whether that radius is an effective encounter radius are unresolved. Once a globule dies, the remaining globules are immune; the precise server event and path/despawn timing are unresolved. Current guidance says the boss does not attack while the raid kills a globule, but no local AI validates this.

### Color effects

The current Classic pages expose `Digestive Acid` components `1224941` and `1224942` as hidden/server-side effects (one with a 1.5-second page cooldown and one with a 55-second aura presentation). They do not establish damage or exact target selection. `Searing Blood` is `105033`; its page shows a 3-second cooldown and legacy values including 35,000, 38,500, and 55,200, while the current Encounter Journal lists 55,200 base damage and three random targets, or eight in 25-player. Keep this as a source conflict, not a mode formula.

`Mana Void` is current Classic page `105530`: it absorbs 100% mana over 1 second, presents a 4-second duration and one-second periodic drain, and has a 200-yard page radius. The older summon identity `105034` is not used as the current Classic spell identity. Stored-mana return amount, kill/return distance, target filtering, and the second-void trigger remain unresolved.

`Deep Corruption` (`105171`) is a 25-second aura. Wowhead's Encounter Journal describes every fifth qualifying heal/absorb as a violent detonation for `89,725–104,275` Shadow to all players; the spell page does not supply a clean current mode table. `Psychic Slice` (`108922`) is linked to Forgotten Ones and is shown as a 0.6-second cast, 5-second cooldown, 20-yard range, with a page narrative of `55,770–58,630` Shadow but a conflicting effect row. `Glowing Blood of Shu'ma` (`104901`) has the documented +50% attack speed, half ability cooldowns, nearby Void Bolt component `53,625–56,375`, and a one-minute page duration; all mode application and cleanup details remain blocked.

The encounter enrage is reported as 10 minutes in current guides. Exact enforcement, whether it is hard or soft, and whether it resets on a wipe are not locally present. The random-target, splash, distance, and healing rules above are observable relationships only; no inferred spell coefficient should be used for bot execution.

## Reset, prerequisite, and credit audit

The local Dragon Soul header declares map `967`, eight encounter slots, and `DATA_YORSAHJ_THE_UNSLEEPING = 2`. The instance script's creature data binds only Madness of Deathwing actors, and the loader registers only the instance and Madness script. There is no local Yor'sahj AI, globule controller, spell script, loader binding, object lifecycle, or boss-specific reset/credit path.

Historical SQL identifies encounter row `1295` and boss entry `55312`. It also names base globules `55862` Acidic, `55863` Shadowed, `55864` Glowing, `55865` Crimson, `55866` Cobalt, and `55867` Dark, with historical variants `57382`, `57384`, `57386`, `57387`, and `57388`. Historical template health/speed/flags and access rows for map 967 are identity evidence only; they do not establish current mode mapping, spawn placement, or tuning. No targeted local spawn row was found.

The release notes establish Dragon Soul availability and four raid modes, not Yor'sahj wing order. No local evidence freezes whether Morchok must be defeated first, wipe despawn/reactivation, lockout behavior, loot recipient, achievement credit, or player-credit semantics. `Taste the Rainbow` (`6129`) is a historical achievement identity, not local executable proof.

## Official modifier state

Blizzard later announced `Presence of the Dragon Soul`: from the 2025-03-18 weekly reset, Dragon Soul enemies receive 5% less health and damage, increasing by 5 percentage points every two weeks to 30% by the end of May; Lord Devrestrasz can remove the aura. This announcement is after the requested cutoff, so `active_at_cutoff=false` and no reduction is applied to the health observations. Aura ID, toggle NPC ID, default persistence, reset ordering, and interaction with mode scaling are unresolved.

## Material blockers

- Build-59185/enUS hotfix lineage and the pre-open cutoff prevent a direct four-mode runtime observation.
- Exact current four-mode boss/globule/add health, damage, color-variant mapping, target counts, spell coefficients, and all difficulty deltas.
- Presence aura/toggle IDs, default state, persistence, and application order; no post-cutoff modifier is applied.
- Void Bolt stack/cadence/reset/target filter; globule first/repeat timer, path, mounds, threshold, immunity, and Fusing Vapors event.
- Normal/Heroic combination selection and kill results, Red target-count conflict, Blue return amount/radius, Purple qualifying-heal semantics, Black add count/fixate wave, and Yellow doubled-cadence enforcement.
- Green damage/splash implementation, Red distance curve, Blue Mana Void lifecycle, Purple detonation mode values, Black Psychic Slice mode values, and Yellow cleanup.
- Enrage enforcement, boss ability pause, wipe reset/despawn/reactivation, prerequisite/order, lockout, loot, achievement, player credit, and the absent local implementation.

## Source metadata

1. [Blizzard Cataclysm Classic Patch 4.4.2 notes](https://us.forums.blizzard.com/en/wow/t/world-of-warcraft-cataclysm-classic-patch-442-notes/2062030), Kaivax, 2025-02-18. Official release context: Dragon Soul opens 2025-02-20, with 10/25-player Normal/Heroic and eight bosses.
2. [Blizzard: Presence of the Dragon Soul begins March 18](https://us.forums.blizzard.com/en/wow/t/presence-of-the-dragon-soul-begins-march-18/2074792), Kaivax, 2025-03-12. Official post-cutoff modifier/toggle announcement; not active in the target snapshot.
3. [Wowhead Yor'sahj strategy guide](https://www.wowhead.com/cata/guide/raids/dragon-soul/yorsahj-strategy-overview), updated 2025-02-19, page labelled Patch 4.4.2. Used for post-cutoff health observations, combinations, qualitative phases, spell links, and enrage.
4. [Icy Veins Yor'sahj encounter guide](https://www.icy-veins.com/cataclysm-classic/yor-sahj-the-unsleeping-encounter-guide-strategy-abilities-loot), updated 2025-02-15. Used for pre-cutoff timing and role/target observations; conflicts remain explicitly blocked.
5. [Icy Veins historical Yor'sahj strategy](https://www.icy-veins.com/wow/yor-sahj-the-unsleeping-strategy-guide-normal-heroic), updated for an older retail expansion. Used only as historical secondary corroboration for add-health observations and enrage.
6. [Wowhead Yor'sahj NPC](https://www.wowhead.com/cata/npc=55312/yorsahj-the-unsleeping) and linked [Void Bolt spell](https://www.wowhead.com/cata/spell=104849/void-bolt), [Fusing Vapors](https://www.wowhead.com/cata/spell=103635/fusing-vapors), [Searing Blood](https://www.wowhead.com/cata/spell=105033/searing-blood), [Deep Corruption](https://www.wowhead.com/cata/spell=105171/deep-corruption), and [Mana Void](https://www.wowhead.com/cata/spell=105530/mana-void) pages. Used for current page identities/ranges only; contradictory legacy rows are preserved as blocked.
7. Local repository revision `b550972efb04d8b4cadf72455e57e1a2e6213e4f`: `src/server/scripts/Kalimdor/CavernsOfTime/DragonSoul/dragon_soul.h`, `instance_dragon_soul.cpp`, `kalimdor_script_loader.cpp`, and historical SQL under `sql/old/4.3.4`. Used for map/data/loader absence and DB identity only.
