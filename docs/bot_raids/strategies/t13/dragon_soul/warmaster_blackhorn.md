# Warmaster Blackhorn — Phase 0 research contract (Cataclysm Classic 4.4.2)

This dossier covers Warmaster Blackhorn in `10N`, `10H`, `25N`, and `25H`. It is research evidence, not live validation. The requested snapshot is Cataclysm Classic `4.4.2`, build `59185`, enUS, at the official global Dragon Soul content-release cutoff `2025-02-20T23:00:00Z` (February 20, 3:00 p.m. PST). Blizzard's notes announce that release boundary; no in-snapshot runtime or exact hotfix lineage is available here. The current Wowhead guide was updated February 19, before the global unlock, and is retained as a pre-release observation rather than exact unlock-state tuning.

## Observable encounter contract

The sixth Dragon Soul encounter is a two-phase gunship defense. `Sky Captain Swayze` starts the encounter after Ultraxion. Blackhorn and Goriona remain airborne in Phase 1 while three waves each deliver two Twilight Assault Drakes, one Twilight Elite Dreadblade, and one Twilight Elite Slayer. Phase 1 ends after all six drakes die; the Skyfire has its own health and Phase 1 failures damage it. Twilight Barrage from drakes targets a random deck location, deals Shadow damage in a 5-yard area, and is split among players in the area; if no player is hit, the ship receives the full hit. Goriona's Twilight Onslaught is the larger 10-yard soak and always damages the ship. Exact 59185 ship-health, projectile, and mode coefficients are not frozen.

Dreadblades use frontal Degeneration (`107558`) and a one-minute stacking Shadow damage-over-time effect; Slayers use Brutal Strike (`107567`) and a one-minute stacking Physical damage-over-time effect. Both use Blade Rush against a random distant player. Twilight Sappers (`56923`) periodically land in stealth/smoke, run toward the bridge, and Detonate for 20% of Skyfire durability if they reach it. Historical guidance reports a first Sapper around 70 seconds and roughly 40-second intervals; this is not an exact build timer.

Phase 2 starts after the sixth drake dies and Blackhorn lands. `Devastate` (`108042`) applies `Sunder Armor` (`108043`), reducing armor by 20% per stack for 30 seconds; tank swaps around two stacks are the sourced operating rule. `Disrupting Roar` (`108044`) deals raid-wide Physical damage and interrupts/silences casters within 10 yards for 8 seconds, with current Classic guidance reporting a roughly 20-second cadence. `Shockwave` (`108046`) is a random-facing 80-yard frontal cone, 95,000–105,000 Physical in the current spell page, stunning for 4 seconds after a 2.5-second cast. `Vengeance` (`108045`) increases Blackhorn's damage by 1% per 1% missing health; the current guide reports +90% at 10% health.

On Normal, Goriona stays airborne and current Classic guidance says she leaves at 20% health; an older guide says 25%, so the threshold is blocked. `Twilight Flames` (`108051`) targets a random player, impacts in an 8-yard area, and leaves a 7-yard fire patch for 30 seconds. Heroic adds deck fire and changes Goriona: current Classic guidance has her land at 80% health, while older material says 90%; on deck she uses Twilight Breath and applies non-tank `Consuming Shroud`, a healing absorb whose absorbed healing becomes raid damage. Heroic Blackhorn can use Siphon Vitality at 20% if Goriona remains, stealing her health and healing himself; the exact spell identity is not frozen in the local database. The final Heroic/Normal phase remains a Vengeance-scaled burn.

## Difficulty matrix and modifier state

| Mode | Blackhorn guide health* | Goriona/add health observations** | Heroic deltas | Modifier at cutoff |
|---|---:|---|---|---|
| 10N | 21M | Blackhorn 21M; Goriona/add values not exact-cutoff | no deck fire, Goriona airborne | no Presence evidenced; raid unopened |
| 10H | 37M | Blackhorn 37M; historical Goriona 26M | deck fire; Barrage shadow-taken debuff; Goriona lands; Breath/Shroud/Siphon | no Presence evidenced; raid unopened |
| 25N | 51M | Blackhorn 51M; historical Goriona 40M | no Heroic-only mechanic; higher coefficients | no Presence evidenced; raid unopened |
| 25H | 90M | Blackhorn 90M; historical Goriona 80M | same Heroic mechanics with 25-player scaling | no Presence evidenced; raid unopened |

\* Wowhead's Cataclysm Classic guide (updated 2025-02-19, before the global unlock) lists `21M/37M/51M/90M` for 10N/10H/25N/25H. Icy Veins' older table independently lists the same Blackhorn values. They remain pre-release or historical observations, not a build-59185 unlock-state assertion.

\* The old Icy Veins table lists add health observations of 2.8/4/8.5/13.6M for each Elite, 0.89/1.5/2.5/4.8M for Drakes, and 0.34/0.475/1.2/1.7M for Sappers across the four modes. It is not a Cataclysm Classic cutoff table and is retained only in the ledger as blocked historical evidence.

Blizzard later announced `Presence of the Dragon Soul`: from the March 18 weekly reset, all Dragon Soul enemies receive 5% health/damage reduction, increasing by 5 percentage points every two weeks to 30% by the end of May; Lord Devrestrasz can remove it. This announcement is post-cutoff, so `active_at_cutoff` is false. Aura/NPC IDs, persistence, and scaling order remain unresolved.

## Targeting, scaling, phases, and ship failure

- Barrage and Onslaught target deck locations, not fixed players. Barrage is a 5-yard small soak; Onslaught is a 10-yard large soak. Current spell data lists Onslaught at 3,000,000 Shadow with legacy mode rows of 800,000 Normal 10, 1,200,000 Heroic 10, 2,000,000 Normal 25, and 3,000,000 Heroic 25. Current Barrage data lists 280,000 Shadow and legacy rows that disagree on the four modes; do not silently select a coefficient. Heroic Barrage adds +50% Shadow damage taken for 6 seconds in current Classic guidance; older material says 15 seconds.
- Each Drake wave has two Drakes and one of each Elite. Harpoons periodically reel a Drake to the ship for melee access; current sources do not freeze harpoon hit, leash, reload, or recapture timing. Sappers are not tanked and must be slowed, gripped, interrupted or killed before the bridge.
- Elite charge paths are marked; Dreadblade Degeneration is frontal and must face away, while Slayer Brutal Strike is described as single-target in current guidance. Both debuffs last one minute and stack; exact 59185 damage coefficients remain blocked.
- The transition is a Drake-count gate rather than a fixed phase timer. Ship health is a material win condition in Phase 1; after Phase 2 begins, current guidance says it no longer decreases. Exact health threshold, damage sources, ship reset, and failure event are unresolved.
- Current sources disagree on Normal Goriona's leave threshold (20% versus 25%) and Heroic landing threshold (80% versus 90%). Treat both as source observations only. Heroic `Consuming Shroud` values also differ between current and historical pages.

## Reset, prerequisite, and credit audit

The local Dragon Soul header declares `DATA_WARMASTER_BLACKHORN = 5` on map `967`, but `instance_dragon_soul.cpp` binds only Madness of Deathwing creatures, has no Blackhorn AI, no Skyfire/harpoon/gameobject data, and no boss-specific reset, ship-health, phase, difficulty, or credit logic. Historical SQL identifies Blackhorn `56427`, Goriona `56781`, Skyfire variants, Drakes `56587`/`56855`, Elite variants `56848`/`56854`, Sapper `56923`, Swayze `55870`, harpoon gun `56681`, deck-fire controller `57920`, and encounter row `1298`. Historical variant health modifiers have no proven 59185 mode mapping.

Wowhead's current NPC identity page says Swayze becomes available after Ultraxion; this is secondary prerequisite evidence and is not locally executable. No exact pull dialogue, wipe/evade cleanup, reactivation, parachute transition, lockout, loot, achievement recipient, or player-credit path is frozen. `Deck Defender` is described as defeating Blackhorn on Normal or Heroic without any Twilight Barrage damaging Skyfire, but the local checkout cannot award it.

## Material blockers

- Build-59185/enUS hotfix lineage and an in-snapshot runtime observation at the exact global unlock boundary.
- Four-mode Blackhorn/Goriona/Skyfire/add health and damage, ship health threshold, historical variant mapping, and modifier interaction.
- Barrage/Onslaught mode coefficients, ship damage split, Heroic debuff duration, projectile cadence, and target/impact rules.
- Harpoon hit/reload/leash timing, Drake despawn, wave timing, Sapper spawn interval, stealth, Detonate spell identity, and bridge path.
- Degeneration/Brutal Strike/Blade Rush exact coefficients and cooldown distributions.
- Normal Goriona leave threshold and Heroic landing threshold conflict; Breath, Shroud, Siphon, and deck-fire runtime IDs/values are incomplete.
- Disrupting Roar/Shockwave cadence, enrage start/effective kill timestamp, Vengeance implementation, and ship reset/failure ordering.
- Local boss absence, pull prerequisite details, wipe reactivation, parachute/next-boss transition, lockout, loot, achievement, and player credit.

## Source metadata

1. [Blizzard Cataclysm Classic Patch 4.4.2 notes](https://us.forums.blizzard.com/en/wow/t/world-of-warcraft-cataclysm-classic-patch-442-notes/2062030), Kaivax, 2025-02-18. Official release timing and Dragon Soul scope; no encounter tuning table.
2. [Blizzard: Presence of the Dragon Soul begins March 18](https://us.forums.blizzard.com/en/wow/t/presence-of-the-dragon-soul-begins-march-18/2074792), Kaivax, 2025-03-12. Official post-cutoff modifier/toggle announcement; not applied at cutoff.
3. [Wowhead Warmaster Blackhorn Strategy Guide](https://www.wowhead.com/cata/guide/raids/dragon-soul/warmaster-blackhorn-strategy-overview), Riyani, updated 2025-02-19, page labelled Patch 4.4.2. Used for pre-release health, wave/phase relationships, 20%/90% observations, and mode strategy; not an exact unlock-state observation.
4. [Icy Veins Cataclysm Classic Warmaster Blackhorn guide](https://www.icy-veins.com/cataclysm-classic/warmaster-blackhorn-encounter-guide-strategy-abilities-loot), Abide, updated 2025-02-15. Used for ship, wave, ability, target, Heroic, and timer observations; conflicts remain blocked.
5. [Icy Veins historical Warmaster Blackhorn guide](https://www.icy-veins.com/wow/warmaster-blackhorn-strategy-guide-normal-heroic), updated 2012-07-25. Used only for historical health/add values, 4-minute Phase 2 enrage, and legacy mode observations.
6. [Wowhead Warmaster Blackhorn NPC and spell pages](https://www.wowhead.com/cata/npc=56427/warmaster-blackhorn), including [Twilight Onslaught](https://www.wowhead.com/cata/spell=106401/twilight-onslaught), [Twilight Barrage](https://www.wowhead.com/cata/spell=107439/twilight-barrage), [Degeneration](https://www.wowhead.com/cata/spell=107558/degeneration), [Brutal Strike](https://www.wowhead.com/cata/spell=107567/brutal-strike), [Disrupting Roar](https://www.wowhead.com/cata/spell=108044/disrupting-roar), [Shockwave](https://www.wowhead.com/cata/spell=108046/shockwave), [Devastate](https://www.wowhead.com/cata/spell=108042/devastate), [Sunder Armor](https://www.wowhead.com/cata/spell=108043/sunder-armor), and [Twilight Flames](https://www.wowhead.com/cata/spell=108051/twilight-flames). Used for identities and page-level values; legacy fields are not promoted to cutoff tuning.
7. Local repository at revision `b550972efb04d8b4cadf72455e57e1a2e6213e4f`: `dragon_soul.h`, `instance_dragon_soul.cpp`, `kalimdor_script_loader.cpp`, and historical SQL under `sql/old/4.3.4`. Used for map/data/loader absence and identity rows only.
