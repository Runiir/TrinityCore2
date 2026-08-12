# Ultraxion — Phase 0 research contract (Cataclysm Classic 4.4.2)

This dossier covers Ultraxion in `10N`, `10H`, `25N`, and `25H`. It is an evidence ledger, not a live-validation result. The requested snapshot is build `59185`, enUS, at the official global raid unlock `2025-02-20T23:00:00Z`. No exact-cutoff live sample has been pinned, so guide values remain `fidelity_blocked`; later hotfixes and the March modifier are excluded.

## Observable encounter contract

Ultraxion is a stationary, single-phase race in the Twilight Realm. `Twilight Shift` (`106368`) pulls the raid into that realm and provides `Heroic Will` (`106108`), an instant 5-second escape that prevents movement, attacks, and casts. Players normally stack in melee range: `Unstable Monstrosity` (`106372`) is 1,100,000 Shadow damage split among enemies within 30 yards, beginning every 6 seconds and accelerating by one second per elapsed minute to a 1-second interval after five minutes. Exact 59185 coefficients, target filters, and the minute-boundary implementation are not frozen.

`Hour of Twilight` (`103327`) is reported every 45 seconds, deals 300,000 unresistible Shadow damage, and requires a minimum number of players to remain and soak it. The observed minimums are 1 in 10N, 3 in 25N, 2 in 10H, and 5 in 25H. Normal players can repeatedly soak; Heroic players who soak receive `Looming Darkness` (`106498`) for 2 minutes and must rotate. Historical guides report a 5-second Normal and 3-second Heroic cast, while the spell page exposes an instant cast field; retain the conflict rather than choosing one.

`Fading Light` (`105925`) is applied twice between Hours to the current tank and random non-tank DPS. Current guide counts are 1 DPS in 10-player Normal, 3 in 25-player Normal, 2 in 10-player Heroic, and 6 in 25-player Heroic. A timer of 4–10 seconds (Wowhead) conflicts with 5–10 seconds (Icy Veins). Expiry in the Twilight Realm kills the target; expiry after Heroic Will returns the player and resets threat. The pages disagree on the no-threat window (5 versus 10 seconds), so no exact value is promoted. Heroic `Looming Darkness` prevents an immediate repeat; its exact runtime behavior and any post-Fading physical-damage delta are not frozen for this build.

If no melee player is present, `Twilight Burst` (`106415`) is a 73,125–76,875 Shadow hit and applies +50% magical damage taken for 6 seconds, stacking. `Twilight Eruption` (`106388`) is the six-minute failure/enrage cast and has a 5-second cast-time observation; shield failure or insufficient Hour soakers can also end the attempt. The exact trigger ordering and effective kill timestamp are unresolved.

## Difficulty matrix and official modifier state

| Mode | Current guide health observation* | Hour minimum | Fading Light DPS | Heroic delta | Modifier at requested cutoff |
|---|---:|---:|---:|---|---|
| 10N | 57M | 1 | 1 | no Looming Darkness lockout | none evidenced; raid opens after cutoff |
| 10H | 85M | 2 | 2 | 2 soakers; Looming Darkness rotation | none evidenced; raid opens after cutoff |
| 25N | 184M | 3 | 3 | no Heroic soak lockout | none evidenced; raid opens after cutoff |
| 25H | 276M | 5 | 6 | 5 soakers; Looming Darkness rotation | none evidenced; raid opens after cutoff |

\* The Wowhead Cataclysm Classic page is labelled 4.4.2 but was updated 2025-03-25; Icy Veins independently presents the same historical health table. These values are not asserted as build-59185 cutoff tuning, and no modifier is silently applied.

Blizzard later announced `Presence of the Dragon Soul`, beginning 2025-03-18 at 5% health/damage reduction, increasing by 5 percentage points every two weeks to 30% by the end of May. Lord Devrestrasz can remove it. This is post-cutoff evidence: `active_at_cutoff` is false. Aura/NPC IDs, default persistence, and scaling order are unresolved.

## Mechanics, targeting, and support effects

### Aspects and crystals

The five Aspects support the fight: Thrall provides `Last Defender of Azeroth` (historical local broadcast identity `106218`); Nozdormu provides one `Timeloop` (`105984`) cheat-death effect at about five minutes; and the healer-selected crystals arrive at about 1:30, 2:30, and 3:30. The red `Gift of Life` crystal (`209873`, spell `105896`) is one charge in 10-player and two in 25-player and is reported as +100% healing. The green `Essence of Dreams` crystal (`209874`, spell `105900`) and blue `Source of Magic` crystal (`209875`, spell `105903`) follow the same 1/2 charge pattern. One healer buff may be selected per player. A current guide accidentally labels the green effect Source of Magic; the local object/spell identities support Essence of Dreams. Exact buff values, click eligibility, placement, and 59185 timing remain blocked.

### Roles and failure boundaries

Use two tanks and stack the raid while assigning Heroic Will users for each Hour. Tanks coordinate Fading Light and threat handoff; healers assign each Aspect crystal and rotate Heroic soakers; DPS maintain melee presence, hold cooldowns for the final-minute acceleration, and never consume a Heroic Hour slot twice before Looming Darkness expires. These are role implications of the sourced mechanics, not an executable strategy guarantee.

### Reset, prerequisite, and credit audit

The local header declares `DATA_ULTRAXION = 4` among eight encounters on map `967`, but `instance_dragon_soul.cpp` binds only Madness of Deathwing creatures and has no Ultraxion AI, crystal object data, door, reset, phase, difficulty, or credit wiring. Historical SQL identifies boss entry `55294`, cosmetic/variant entries `55293`, `56259`, `56576`–`56578`, gauntlet entry `56305`, encounter row `1297`, crystals `209873`–`209875`, and the Lesser Cache encounter object `210221`. The historical template rows expose `Health_mod` observations of 660 (`55294`), 2,145 (`56576`), 990 (`56577`), and 3,217 (`56578`); they have no proven 59185 mode mapping and must not be treated as four-mode health. These rows establish identity only; they do not prove mode mapping or runtime behavior.

No exact pull prerequisite, wipe/evade cleanup, reactivation, loot/lockout, achievement recipient, or player-credit path is locally executable. The encounter therefore stays `fidelity_blocked` even where guide mechanics agree.

## Material blockers

- Build-59185/enUS hotfix lineage and an in-snapshot runtime observation; the raid was not open at the cutoff.
- Four-mode health/damage coefficients, historical variant-to-difficulty mapping, and any post-cutoff guide tuning provenance.
- `Presence of the Dragon Soul` aura/toggle IDs, persistence, removal scope, and application order.
- `Unstable Monstrosity` minute-boundary cadence, exact mode split/scaling, and player/realm filtering.
- Hour cast-time contradiction, soak assignment/validation, and Aspect shield failure ordering.
- Fading Light duration distribution, exact schedule, threat-reset window, and Heroic Looming Darkness behavior.
- Twilight Burst trigger geometry, Twilight Eruption effective enrage timestamp, crystal placement/buff values, and Nozdormu/Thrall runtime IDs.
- Wipe reset, prerequisite, encounter credit, loot, achievement, and missing local boss implementation.

## Source metadata

1. [Blizzard Cataclysm Classic Patch 4.4.2 notes](https://us.forums.blizzard.com/en/wow/t/world-of-warcraft-cataclysm-classic-patch-442-notes/2062030), Kaivax, 2025-02-18. Official release context: Dragon Soul opens 2025-02-20, with 10/25-player Normal/Heroic modes.
2. [Blizzard: Presence of the Dragon Soul begins March 18](https://us.forums.blizzard.com/en/wow/t/presence-of-the-dragon-soul-begins-march-18/2074792), Kaivax, 2025-03-12. Official post-cutoff modifier and removal NPC announcement; not applied to the requested snapshot.
3. [Wowhead Ultraxion Strategy Guide](https://www.wowhead.com/cata/guide/raids/dragon-soul/ultraxion-strategy-overview), Cataclysm Classic guide, updated 2025-03-25. Used for post-cutoff health observations, spell summaries, mode counts, and target/timer observations only.
4. [Icy Veins Ultraxion Encounter Guide](https://www.icy-veins.com/cataclysm-classic/ultraxion-encounter-guide-strategy-abilities-loot), Cataclysm Classic guide, accessed 2026-08-12. Independent corroboration for phases, acceleration, soak counts, Fading Light, Aspect timing, and source conflicts.
5. [Wowhead Ultraxion NPC](https://www.wowhead.com/cata/npc=55294/ultraxion) and linked [spell identities](https://www.wowhead.com/cata/spell=106372/unstable-monstrosity). Used for spell/NPC identity and page-level values; legacy fields are not promoted to cutoff tuning.
6. Local repository at revision `f8a7fe6cb58563459c08a775fd56418f37529cda`: `dragon_soul.h`, `instance_dragon_soul.cpp`, `kalimdor_script_loader.cpp`, and historical SQL under `sql/old/4.3.4`. Used for map/data/loader absence and DB identity only.
