# Warlord Zon'ozz — Phase 0 research contract (Cataclysm Classic 4.4.2)

This dossier covers `10N`, `10H`, `25N`, and `25H` Warlord Zon'ozz in Dragon Soul. It is research evidence, not a live-validation result. The snapshot is build `59185` at the official global raid unlock `2025-02-20T23:00:00Z`. The current Wowhead page was updated before opening but is not a live exact-cutoff sample, so its health figures are not promoted to an executable tuning table.

## Observable encounter contract

- The fight alternates a controllable main/“ping-pong” phase and a 30-second intermission. Zon'ozz summons an invulnerable, aggro-less Void of the Unmaking in front of himself. A player collision reverses its travel, shares the Shadow hit among nearby players, and starts a five-second re-collision cooldown. Each bounce raises the next bounce's damage by 20% and adds 5% damage taken by Zon'ozz when he absorbs the orb. A wall collision triggers Black Blood Eruption; a boss collision begins the intermission.
- Focused Anger stacks during the main phase, increasing Physical damage by 20% and attack speed by 5% per stack in current Cataclysm Classic guidance. Psychic Drain is a 30-degree frontal cone that leeches health for ten times the damage dealt. Keep it on the tank. Disrupting Shadows is a 20-second Magic DoT ticking every 2 seconds; dispelling causes Shadow damage and knockback, with a 10-yard heroic splash according to the current guide.
- On Normal, Black Blood of Go'rath is a raid-wide Shadow DoT and only Eye of Go'rath tentacles are reported. On Heroic, the intermission starts 8 adds in 10-player (2 Flails, 5 Eyes, 1 Claw) or 14 in 25-player (4 Flails, 8 Eyes, 2 Claws); Black Blood damage scales with living adds. Flails are the immediate damage priority, Eyes cast at random players, and Claws require tanks. Exact normal Eye count, coefficients, spawn coordinates, and add health are not frozen by the requested cutoff evidence.
- The main phase has no fixed transition timer: the raid chooses when to let the orb hit the boss. Current guide strategy examples use seven bounces for 10-player and nine for 25-player Heroic; those are recommendations, not encounter constants. Current Wowhead describes a six-minute enrage and approximately 12 seconds of boss movement/settling before the 30-second intermission; Icy Veins says the intermission lasts exactly 30 seconds and the boss does not auto-attack for its first 15 seconds. These cadence details remain source observations where they conflict.

## Difficulty matrix and official Dragon Soul modifier state

| Mode | Current 4.4.2 guide health observation* | Heroic delta | Modifier at requested cutoff |
|---|---:|---|---|
| 10N | 68M | No tentacle types beyond Eyes reported | No Presence announcement or active Dragon Soul modifier is evidenced by the 2025-02-18 cutoff; raid opens Feb 20 |
| 10H | 86M | 8 intermission adds: 2 Flails, 5 Eyes, 1 Claw | Same |
| 25N | 204M | No tentacle types beyond Eyes reported; Eye count unresolved | Same |
| 25H | 260M | 14 intermission adds: 4 Flails, 8 Eyes, 2 Claws | Same |

\* Wowhead's current page labels the guide Patch 4.4.2 but says updated 2025-02-19, one day before the global unlock cutoff. Values are therefore observations, not a claim about build 59185 hotfix state. Do not silently apply a modifier to these values.

Blizzard later announced `Presence of the Dragon Soul`: beginning 2025-03-18, it reduces Dragon Soul enemy health and damage by 5%, increasing by 5% every two weeks to 30% by the end of May; Lord Devrestrasz inside the entrance can remove it. That announcement is post-cutoff and is not an active modifier in the target snapshot. Its aura/NPC IDs, default persistence across resets, and exact interaction with creature scaling are unresolved.

## Mechanics, targets, and values

### Main phase

`Focused Anger` (`104543` current Cataclysm Classic spell page) stacks while Zon'ozz remains in the main phase. Current guide prose reports +20% Physical damage and +5% attack speed per stack; the stack cadence is approximately 6–8 seconds in Icy Veins, not a verified build-59185 timer. Intermission removes the stacks. `Psychic Drain` (`104322`) is a 30-degree frontal cone, 100-yard spell-page range, dealing Shadow damage and healing the caster for 10× damage; the page exposes legacy/mode-dependent values rather than a frozen four-mode 59185 table. `Disrupting Shadows` (`103434`) targets 1–3 players in 10-player and 6–8 in 25-player, deals 42,099–48,926 Shadow every 2 seconds for 20 seconds in the current page presentation, and causes dispel knockback; heroic dispel splash is reported as 10 yards.

### Void of the Unmaking and collision rules

The ball is identified by current Wowhead as NPC `58473`; historical SQL also has `55334`. It is immune to damage, has no threat table, travels in a straight line, and spawns in front of Zon'ozz. A player collision reverses its direction and applies the shared nearby-player Shadow hit. Every bounce adds one stack of Void Diffusion: the next bounce damage increases by 20%, while the boss receives 5% increased damage taken per stack when the orb collides with him. The five-second post-bounce cooldown is a current guide value. The exact collision radius, speed, damage base, line-of-sight behavior, and whether all hotfixes retain this cooldown are `fidelity_blocked`.

If the orb reaches the room boundary it triggers `Black Blood Eruption` (`108794`), which the current spell page presents as 119,400–120,600 Shadow, knockback, and unlimited range; it is an encounter-failure condition in current guides. If it reaches Zon'ozz, it applies the diffused damage-taken stacks, removes Focused Anger, and starts the intermission. The current guide notes that hitbox/trajectory behavior can be inconsistent; do not encode a geometric radius or fixed travel timer.

### Intermission and tentacles

`Black Blood of Go'rath` (`104377`) covers the raid for the intermission. Current sources disagree on its periodic presentation (every 1 or 2 seconds); the phase duration is 30 seconds. Normal guidance says stack and heal through it. Heroic damage depends on living tentacles, making add kill order part of the scaling rule. `Eye of Go'rath` (`55416` base, with historical variants) casts `Shadow Gaze` (`109391`) at random players; the page reports a 3-second cast and 21,375–23,625 Shadow in its summary, while the spell details expose legacy values. `Flail of Go'rath` (`55417` base; `57877` current variant) and `Claw of Go'rath` (`55418` base; `57890` current variant) are Heroic-only add identities in the historical DB; exact spell sets, health, damage, and spawn locations remain unresolved for 59185.

## Reset, prerequisite, and credit audit

The local instance is map `967`, declares eight encounters, and maps `DATA_WARLORD_ZONOZZ = 1`, but its object-data table only binds Madness of Deathwing. No Zon'ozz C++ AI, boss-specific phase/reset handler, add controller, orb movement, or difficulty branch exists in this checkout. Historical SQL identifies boss `55308` and variants `55309`–`55311`, Void entries `55334`/`58473`, tentacle identities, and encounter row `1294` (`Warlord Zon'ozz`). These are identity rows, not proof of current mode mapping or runtime spell behavior.

No local evidence establishes the retail pull prerequisite (Dragon Soul's first-wing path/order), reset/evade despawn, wipe reactivation, lockout, loot, achievement, or player-credit recipient. The current strategy page documents `Ping Pong Champion` as ten player bounces followed by a Normal/Heroic kill, but achievement credit is not locally executable evidence. The contract and ledger consequently remain `fidelity_blocked`.

## Material blockers

- Build-59185/enUS client and hotfix lineage at the global unlock cutoff `2025-02-20T23:00:00Z`.
- Exact four-mode post-hotfix health, damage, add health, spell coefficients, and mode-to-historical-variant mapping.
- Whether current-guide health values include any later modifier; no second reduction is applied.
- Presence of the Dragon Soul aura/NPC IDs, default state, persistence, and removal semantics in the target build.
- Focused Anger cadence/stack values, Psychic Drain coefficients/cadence, and Disrupting Shadows selection/filter/dispelling damage.
- Void collision radius/speed/base damage, bounce stack reset, collision immunity window, and wall geometry.
- Black Blood periodic cadence conflict (1s versus 2s), normal Eye count, Heroic living-add coefficient, add health/damage, spawn points, and add spell IDs.
- Boss movement/settle timing, intermission auto-attack suppression, enrage enforcement, wipe cleanup, encounter reset, lockout, loot, achievement, and player credit.

## Source metadata

1. [Blizzard Cataclysm Classic Patch 4.4.2 notes](https://us.forums.blizzard.com/en/wow/t/world-of-warcraft-cataclysm-classic-patch-442-notes/2062030), Kaivax, 2025-02-18. Official release context: Dragon Soul opens 2025-02-20, 10/25-player, eight bosses, Normal/Heroic.
2. [Blizzard: Presence of the Dragon Soul begins March 18](https://us.forums.blizzard.com/en/wow/t/presence-of-the-dragon-soul-begins-march-18/2074792), Kaivax, 2025-03-12. Official post-cutoff modifier/toggle announcement; not used as an active cutoff state.
3. [Wowhead Warlord Zon'ozz Strategy Guide](https://www.wowhead.com/cata/guide/raids/dragon-soul/warlord-zonozz-strategy-overview), Riyani, updated 2025-02-19, page labelled Patch 4.4.2. Used for current health observations, orb collision rules, add counts, phase/enrage observations, targeting counts, and spell links; post-cutoff timing is explicitly blocked.
4. [Icy Veins Warlord Zon'ozz Encounter Guide](https://www.icy-veins.com/cataclysm-classic/warlord-zonozz-encounter-guide-strategy-abilities-loot), current Cataclysm Classic guide. Used as independent corroboration for Focused Anger cadence, heroic add behavior, Black Blood phase details, and role targeting; conflicting values remain blocked.
5. [Wowhead Warlord Zon'ozz NPC](https://www.wowhead.com/cata/npc=55308/warlord-zonozz) and linked [Cataclysm Classic spell pages](https://www.wowhead.com/cata/spell=104322/psychic-drain). Used for spell/NPC identity and page-level ranges only.
6. Local repository at revision `c07dbd90c17d9fb10241898b858566e8812545fc`: `src/server/scripts/Kalimdor/CavernsOfTime/DragonSoul/dragon_soul.h`, `instance_dragon_soul.cpp`, `kalimdor_script_loader.cpp`, and historical SQL under `sql/old/4.3.4`. Used for map/data/loader absence and DB identity only.
