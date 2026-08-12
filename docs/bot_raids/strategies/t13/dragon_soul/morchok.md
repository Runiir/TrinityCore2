# Morchok — Phase 0 research contract (Cataclysm Classic 4.4.2)

This dossier covers Dragon Soul's first endpoint in `10N`, `10H`, `25N`, and `25H` for build `59185`, locale `enUS`, and the official global raid-unlock cutoff `2025-02-20T23:00:00Z`. It is sourced planning evidence, not a live observation. Later hotfixes and the March `Presence of the Dragon Soul` modifier are excluded.

## Observable encounter contract

Current Cataclysm Classic sources describe Morchok as a repeating Stomp/crystal phase followed by an Earth intermission, line-of-sight Black Blood, and another Stomp/crystal phase. The cycle continues until death or a reported seven-minute enrage. At 20% health, `Furious` is reported to increase damage by 20% and attack speed by 30%.

`Stomp` (spell `103414`) is a 1.5-second cast whose physical damage is split among units within 25 yards. The current target and nearest ally receive double portions. The guide mode table reports 750,000 for 10N/10H, 2,500,000 for 25N, and 2,000,000 for 25H, while the generic NPC/spell references expose 2,000,000 or legacy effect rows. Those are observations in conflict, not fixed bot values. Heroic sources add a 100% physical-damage-taken effect for 10 seconds, but its target, stacks, and reset are not frozen.

`Resonating Crystal` (spell `103494`) explodes after 12 seconds and uses distance-scaled Shadow damage. Guides report three assigned targets in 10-player and seven in 25-player; the current guides describe nearest selection while the NPC/reference text describes random selection. The link is an indicator rather than damage. Spawn cadence, distance curve, link range, knockback, and target exclusions remain blocked.

Normal sources report `Crush Armor` (spell `103687`) on the current target: 120% normal melee, 10% armor reduction for 20 seconds, up to 10 stacks. Heroic sources report it absent. Application cadence and mode enforcement are not repository-backed. The Earth transition is variously placed around 55 seconds or one minute. It pulls players, damages them for five seconds, and creates Earth shards in a circular arrangement. The strategy guide reports 1% total health per second; the NPC page reports 5% per second. Shards are reported to deal 15,000 Physical within 2 yards and provide line-of-sight cover.

Black Blood of the Earth (spell `103785`) deals 5,000 Nature damage per tick, doubles Nature damage taken, and stacks to 20 while players remain exposed. Guides describe a roughly 15-second channel behind shards; the spell page exposes a six-second aura. The aura duration is not substituted for the encounter channel timer.

## Difficulty matrix and heroic split

| Mode | Guide health observation | Guide Stomp observation | Crystal targets | Reported delta |
|---|---:|---:|---:|---|
| 10N | 36.0M | 750,000 | 3 | normal; Crush Armor reported |
| 10H | 42.0M | 750,000 | 3 | split/twin at 90%; heroic Stomp debuff; no Crush Armor reported |
| 25N | 102.0M | 2.5M | 7 | normal; Crush Armor reported |
| 25H | 180.0M | 2.0M | 7 | split/twin at 90%; heroic Stomp debuff; no Crush Armor reported |

These health figures are current-guide observations with unspecified modifier state. Do not apply another reduction. At about 90% remaining health, heroic guides report Kohcrom: a twin with shared health, the same spells a few seconds later, and one tank plus an assigned raid group on each side. The exact twin entry, synchronization window, cross-side target filter, reset, and completion credit are not present locally.

## Official modifier state

Blizzard's 4.4.2 notes announce Dragon Soul as an eight-boss, 10/25-player raid with normal and heroic modes; the official live announcement freezes the global opening at this dossier's cutoff. A later official Classic announcement names `Presence of the Dragon Soul`: 5% health and damage reduction from the March 18 weekly reset, increasing by 5% every two weeks to 30% by the end of May; Lord Devrestrasz can remove the aura. Its aura/NPC IDs and default persistence are not published, and it is post-cutoff evidence. The original retail `Power of the Aspects`/Lord Afrasastrasz mechanic is historical and must not be used as a Classic identity. No modifier is applied to this contract.

## Repository, DB, reset, prerequisite, and credit audit

The audited revision is `6f94d85117cca3155ae4bce179beaee7754d6267`.

- `dragon_soul.h` defines map `967`, `EncounterCount = 8`, `DATA_MORCHOK = 0`, and the `DS` data header, but no `BOSS_MORCHOK` constant or executable Morchok class.
- `instance_dragon_soul.cpp` maps only Madness of Deathwing actors. The loader registers the instance and Madness script, not `boss_morchok`; there is no current Morchok spawn/object mapping, phase, spell, reset, or credit path.
- Historical SQL records encounter `1292` as entry `55265` (`Morchok`). Later historical template updates provide variant slots `57409`, `57771`, and `57772`; their mapping to current four modes is unresolved. Historical access rows for map `967` label difficulties 0/1 normal with no quest and 2/3 heroic with quest `6177`; the quest meaning and current Classic lockout/entry semantics are unresolved.
- Historical loot rows use loot identity `55265`, but no current 4.4.2 completion, loot, achievement, synchronized twin credit, or player-credit implementation was found.

No spawn coordinate, live timer, exact target filter, reset cleanup, or difficulty coefficient is promoted from the local checkout. A validation implementation must observe encounter events and resolve every blocker below before scheduling any source-only value.

## Material blockers

1. Exact 4.4.2 build/DBC and enUS hotfix state at the cutoff.
2. Cutoff raid availability and default modifier state.
3. Presence of the Dragon Soul aura/NPC identities, toggle, and persistence.
4. Retail Power of the Aspects versus Classic Presence identity.
5. Complete four-mode health and damage tables and modifier interaction.
6. Conflicting mode-specific Stomp damage.
7. Stomp cooldown, ordering, and jitter.
8. Stomp eligible-target ordering and 25-yard runtime filter.
9. Heroic Stomp debuff target, stack, and reset behavior.
10. Resonating Crystal spawn cadence and position selection.
11. Crystal nearest-versus-random target selection.
12. Crystal distance curve, link range/visual, knockback, and exclusions.
13. Crush Armor cadence and normal-only enforcement.
14. Furious activation and runtime cancellation.
15. Conflicting Earth pull damage (1% versus 5% per second for five seconds).
16. Earth shard count, geometry, timing, and damage identity.
17. Black Blood channel versus six-second aura duration.
18. Phase-loop and first-intermission timing.
19. Heroic split/shared-health implementation and twin credit.
20. Heroic raid partition and cross-side target rules.
21. Seven-minute enrage runtime and Furious interaction.
22. Crystal target-count scaling and heroic delta.
23. Evade/wipe reset and crystal/shard cleanup.
24. Current prerequisite, access, and lockout semantics.
25. Loot, achievement, completion, and player-credit behavior.
26. Historical variant-slot mode mapping and absent local Morchok AI/loader/spawn proof.

## Source metadata

1. [Wowhead Morchok strategy overview](https://www.wowhead.com/cata/guide/raids/dragon-soul/morchok-strategy-overview), updated 2025-02-19. Current Cataclysm Classic source for guide health, phase flow, values, and heroic split; it is one day after the cutoff and its conflicting values remain blocked.
2. [Icy Veins Morchok encounter guide](https://www.icy-veins.com/cataclysm-classic/morchok-encounter-guide-strategy-abilities-loot), updated 2025-02-15. Before-cutoff Cataclysm Classic corroboration for twin, crystal, Stomp, Black Blood, phase flow, and achievements; it does not supply a complete mode table.
3. [Warcraft Tavern Morchok guide](https://www.warcrafttavern.com/cataclysm/guides/morchok-raid-guide/). Concise secondary corroboration only; no exact value is promoted over conflicts.
4. [Wowhead Morchok NPC/Encounter Journal](https://www.wowhead.com/cata/npc=55265/morchok). Used for entry `55265`, generic ability text, and spell-effect cross-checks; generic/legacy fields are not a current four-mode table.
5. [Wowhead Stomp](https://www.wowhead.com/cata/spell=103414/stomp), [Resonating Crystal](https://www.wowhead.com/cata/spell=103494/resonating-crystal), [Black Blood](https://www.wowhead.com/cata/spell=103785/black-blood-of-the-earth), [Crush Armor](https://www.wowhead.com/cata/spell=103687/crush-armor), and [Furious](https://www.wowhead.com/cata/spell=103846/furious). Spell identities and effect references; aura/legacy rows are retained as uncertainty.
6. [Cataclysm Classic 4.4.2 notes](https://www.bluetracker.gg/wow/topic/us-en/2062030-world-of-warcraft-cataclysm-classic-patch-442-notes/), Blizzard/Blue Tracker mirror, 2025-02-18. Official raid scope and February 20 opening announcement.
7. [Presence of the Dragon Soul begins March 18](https://us.forums.blizzard.com/en/wow/t/presence-of-the-dragon-soul-begins-march-18/2074792), Kaivax, 2025-03-12. Official post-cutoff modifier schedule, 5% increments/cap, and Lord Devrestrasz toggle; not applied to cutoff values.
8. [Original Dragon Soul difficulty changes](https://worldofwarcraft.blizzard.com/en-us/news/4326384/dragon-soul-difficulty-changes), Blizzard, 2012-01-19. Historical retail Power of the Aspects comparison only.
9. Local audit at revision `6f94d85117cca3155ae4bce179beaee7754d6267`: `src/server/scripts/Kalimdor/CavernsOfTime/DragonSoul/dragon_soul.h`, `instance_dragon_soul.cpp`, `boss_madness_of_deathwing.cpp`, and `kalimdor_script_loader.cpp`; historical SQL under `sql/old/4.3.4`. Used for map/slot/entry/access identity and the absence of Morchok lifecycle code.
