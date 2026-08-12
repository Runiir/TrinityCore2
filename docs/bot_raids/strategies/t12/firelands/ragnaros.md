# Ragnaros — Firelands

Phase-0 research dossier for Cataclysm Classic 4.4.2, build 59185, enUS, hotfix cutoff `2025-02-20T23:00:00Z`. Scope is 10N/10H/25N/25H. This is an original implementation summary, not mirrored guide text. The endpoint remains `fidelity_blocked`: the local encounter is detailed, but current Classic sources and the local SpellInfo/SQL layer do not prove every quantitative field at the requested snapshot.

## Sources and snapshot

- Current Cataclysm Classic corroboration: [Wowhead’s Ragnaros strategy](https://www.wowhead.com/cata/guide/raids/firelands/ragnaros-strategy-overview) (page labeled Patch 4.4.2; updated 2024-10-25) and [Icy Veins’ encounter guide](https://www.icy-veins.com/cataclysm-classic/ragnaros-encounter-guide-strategy-abilities-loot) (updated 2024-10-08). They supply the four-mode health table, phase mechanics, current Classic heroic phase, and most guide-reported values.
- Concise secondary corroboration: [Warcraft Tavern’s Firelands Ragnaros guide](https://www.warcrafttavern.com/cataclysm/guides/ragnaros-raid-guide/). It is used for broad phase/prerequisite context only; no unique numeric field is promoted from it where the page could not be independently checked.
- Official modifier context: Blizzard’s [Firelands difficulty-reduction announcement](https://us.forums.blizzard.com/en/wow/t/firelands-difficulty-reduction-with-hour-of-twilight-patch/2059756) says 4.4.2 applies an optional 30% health/damage reduction through `Power of Stormrage`, removable by General Taldris Moonfall. The local repository has no verified application spell or initial state.
- Historical primary provenance: Blizzard’s [Patch 4.2 hotfixes](https://worldofwarcraft.blizzard.com/en-us/news/3019413) are retained as historical tuning provenance only; inaccessible/uncertain hotfix carryover is not silently treated as the 4.4.2 state. The requested build is also cross-checked against the [public client-build reference](https://warcraft.wiki.gg/wiki/Public_client_builds).
- Repository revision audited read-only: `8eb54f0160b3c3d986ed944f9d64ebf83922c0f8`. Sources are `boss_ragnaros_firelands.cpp`, `firelands.h`, `instance_firelands.cpp`, `firelands.cpp`, `SpellMgr.cpp`, `2022_02_02_00_world.sql`, `TDB04_to_TDB05_updates/world/066_instance_encounters.sql`, and Firelands map/model SQL.

## Mode matrix and modifier

| Mode | Guide-reported Ragnaros health | Guide-reported intermission-1 Son health | Intermission-2 Son health | Local count/scaling hooks |
|---|---:|---:|---:|---|
| 10N | 67,000,000 | 124,000 | 1,500,000 | Wrath max 1; Molten Seed max 10; Dreadflame initial cast count 2; Cloudburst clicks 1 |
| 10H | 74,200,000 | 212,000 | 2,500,000 | Heroic SpellInfo paths; Sons are random-position path; Dreadflame 2; Cloudburst 1 |
| 25N | 201,000,000 | 622,000 | 4,700,000 | Wrath max 3; Molten Seed max 20; Dreadflame 5; Cloudburst 3 |
| 25H | 246,900,000 | 1,100,000 | 7,400,000 | Heroic SpellInfo paths; Sons random-position path; Dreadflame 5; Cloudburst 3 |

The health values are current-guide observations, not asserted post-modifier values. Blizzard’s 4.4.2 announcement says `Power of Stormrage` reduces health and damage of all Firelands bosses and other enemies by 30%; players can ask General Taldris Moonfall to remove it. Whether it is initially present, whether it can be re-enabled, its spell identity, and whether the guide table is before or after that state are unresolved. Do not apply a guessed 0.70 multiplier in the bot contract.

## Encounter behavior

### Arena, arrival, and tank contact

Ragnaros is anchored in the lava during phases 1–3. At least one player must remain in melee; otherwise the local AI uses `Magma Blast` (98313). Current Classic documentation describes roughly 75,000 raid Fire damage every 2 seconds and a stacking +50% Fire-damage-taken component; repository SpellInfo tables must be checked before treating either the cadence or the exact value as contract data. Local arrival is an active intro: the boss is reset to `NOT_STARTED`, stalker group 459 is spawned, emerge animation is delayed 200 ms, base visual 98860 is scheduled at 2 s, and the arrival completes at 7 s. The boss applies `Burning Wound` (99401) on engage and again at the arrival event.

`Burning Wound` is a melee-proc tank debuff, reported by the current guide as roughly 4,000 normal/5,500 heroic Fire every 2 s for 20 s with unlimited stacking. It also enables `Burning Blast` (99400); the local aura script adds 10% to its calculated base damage per wound stack. The guide’s 4–6-stack tank swap is a strategy recommendation, not a verified hard reset. Exact mode SpellInfo, proc chance, and whether the 20-second duration is the Classic 4.4.2 duration remain blocked.

### Phase 1 — 100% to 70%, “By Fire Be Purged”

Local events begin at 6 s (`Wrath of Ragnaros`, 98259), 26 s (`Hand of Ragnaros`, 98237), 16 s (`Magma Trap`, 98159), and 31 s (`Sulfuras Smash`, 98703). Their local repeats are 30 s, 26 s, 26 s, and 30 s respectively; a Sulfuras summon adds 5.5 s to the pending Wrath timer. Current guides instead describe Wrath at about 5 s then 30 s, Hand about 25 s, Magma Trap about 15 s then 30 s, and Sulfuras about 30 s. The differences are material and remain blocked.

- `Wrath of Ragnaros`: local max targets are 1 in 10-player and 3 in 25-player. Current guides describe random ranged targets, a 6-yard splash and knockback, with about 45,000 normal/64,000 heroic damage. The local effect scripts only prove the spell identities and target-count override; range, target exclusion, knockback, and mode damage are SpellInfo-dependent.
- `Hand of Ragnaros`: a raid-wide knockback around the boss. Current guide values are about 22,000 normal/34,000 heroic within 55 yards. The implementation casts the base spell and does not establish an independent target filter or the final radius.
- `Magma Trap`: local target count is one. Current guides report a random ranged location, a short visual lead, and an eruption for about 60,000 normal/100,000 heroic raid damage plus a very large knock-up. Icy Veins reports a heroic Magma Trap Vulnerability timer after detonation; the local C++ does not name that aura. The trap persists until triggered in guide behavior, while the local visual/periodic NPC lifecycle and SpellInfo control exact persistence.
- `Sulfuras Smash`: local summons a target marker, faces the boss, then casts the impact and three directional wave spells (north/west/east IDs 98874/98876/98875), a lava pool (98712), and later Scorched Ground (100119). Current guide values are about 105,000 normal/550,000 heroic within 5 yards at impact, then three Lava Waves for about 75,000/125,000 plus a roughly 110,000/210,000 five-second follow-up. The documented safe strip is between Ragnaros and his weapon; exact cast delay, wave travel/radius, follow-up aura, and mode SpellInfo are blocked.

### Intermission 1 — 70%, Sons of Flame

At the 70% health check the local AI changes to intermission phase 1 and casts `Splitting Blow` (98951). It selects one pre-placed splitting-blow target, removes Son spawn points within 30 yards, randomly retains eight from the remaining positions, submerges Ragnaros, and leaves Sulfuras. The current guide describes three possible hammer sites and eight Sons, with fixed normal positions and random heroic positions; Icy Veins independently confirms that heroic positions are random. The local static source contains fifteen candidate coordinates, while the map SQL contains the same family of Son points, so the geometry is known locally but the exact 4.4.2 difficulty selection is not proven.

Each Son of Flame (53140) is initially rooted/non-selectable and is invoked by `Burning Speed` (98473) after the Splitting Blow script. The local periodic script sets its speed-aura stacks to `ceil(health_pct / 10)`, then removes speed as health falls; movement toward the Sulfuras hand begins after 2.5 s and checks each second, stopping at 4.4 yards. A Son that reaches the weapon casts `Supernova` (99112) and server-side suicide spell 3617. Current guide values are 100,000 normal/500,000 heroic raid damage, with +75% movement speed per 5% health above 50% (up to +750% at spawn). Guide health is 124k/212k/622k/1.1M for 10N/10H/25N/25H. Exact SpellInfo, the normal/heroic spawn branch, and movement/health values are blocked.

While submerged, current guides report `Lava Bolt` every 4 s at four random players in normal and ten in heroic, for about 45,000/70,000 Fire damage. The repository’s `SpellMgr.cpp` identifies the mode families as 98981/100290 (10-player, max four) and 100289/100291 (25-player, max ten); there is no boss event in this C++ file, so cadence, heroic-only behavior, and damage remain SpellInfo/DBC fields rather than asserted script facts.

The local intermission announces an end after 42 s, then schedules finish 5 s later in normal or 20 s later in heroic. If all eight Sons die first, finish is scheduled 1.5 s later. Current guides describe approximately 45 s or up to one minute. On completion the hand despawns after 3 s, the boss becomes selectable, removes the submerge aura, picks up Sulfuras, and schedules phase 2 or 3 events. These local lifecycle times are recorded for reproducibility but are not promoted over the external timer without build validation.

### Phase 2 — 70% to 40%, “Sulfuras Will Be Your End”

On leaving intermission 1 the local AI becomes aggressive after 5 s, casts Sulfuras Smash at 5.5 s, `Molten Seed` at 15 s, and `Engulfing Flames` at 40 s. Molten Seed targets a maximum of ten players in 10-player and twenty in 25-player, then repeats every 60 s. The local spell script sorts by caster distance and keeps one target per seed spell effect; the underlying DBC target selection is still material. Current sources say each player’s current location is marked, seeds land after a short travel time, deal about 42,000 normal/63,000 heroic within 6 yards, and explode ten seconds later into `Molten Inferno` with distance falloff, spawning one Molten Elemental per seed.

The current guide reports about 350,000 health per Molten Elemental. Normal elementals can be slowed/stunned/knocked; heroic `Molten Power` makes them crowd-control immune and adds 25% damage for every nearby elemental within 6 yards (the guide’s all-twenty stack is +475%). Icy Veins also reports a 10% size increase. The local script applies the Molten Power aura through the seed visual and uses a custom distance falloff for Molten Inferno (`damage / (distance_2d / 5)` beyond 5 yards); local creature flags and mode entries supply additional immunity paths. Exact element health, impact/Inferno values, timing, and aura stacking are blocked.

`Engulfing Flames` selects near, middle, or far segment through a random parameter 0–2. Local repeats it every 60 s in phase 2 and 30 s in phase 3; the first phase-2 event is at 40 s. Current guides report a three-second warning and roughly 55,000 normal/75,000 heroic Fire each second for the targeted third of the platform. Heroic replaces it with `World in Flames` (100171/100190), whose local periodic script chains four different segments and avoids the immediately previous segment; the current source does not establish the exact inter-segment delay beyond the SpellInfo aura. Keep the segment/range/damage and chain cadence blocked.

### Intermission 2 — 40%, Sons and Lava Scions

At 40% the same Splitting Blow/Sons logic runs, and the local boss invokes two Lava Scions (53231) through summon group 6. The current guide reports two Scions in all modes, with second-intermission Son health 1.5M/2.5M/4.7M/7.4M for 10N/10H/25N/25H. A Scion’s local AI begins `Blazing Heat` at 15 s and repeats every 23 s; current guides report roughly 20 s. The effect targets one player per Scion, warns for 3 s, then leaves fire at that player’s position each second for 10 s. Current guide values are about 38,000 normal/60,000 heroic Fire per second within 3 yards and 10% maximum-health healing per second to a Son standing in the patch. Exact target exclusion, Scion health, trail tick geometry, and mode SpellInfo are blocked.

The local end-of-intermission path is the same 42-second announce plus normal 5-second/heroic 20-second finish, or 1.5 s after eight Sons die. When phase 3 starts, surviving Scions remain available for cleave and can continue their own Blazing Heat schedule. Guides describe the intermission as 45 s or up to one minute; do not hard-code that guide range in place of the local event path.

### Phase 3 — 40% to 10%, “Begone From My Realm”

The local phase-3 schedule is Sulfuras Smash at 15 s, Engulfing/World in Flames at 30 s, and Living Meteor at 45 s. Smash repeats at 30 s, Engulfing at 30 s, and local meteor repeats at 60 s; a meteor delays a pending Smash by 2 s. Current Wowhead reports Living Meteor every 45 s and a sequence of one, one, two, two, then four meteors on later casts. This is a direct local/current timer and count conflict, so the count and cadence are blocked.

`Living Meteor` (local creature 53500; spell family 99267/101387–101389) lands on a random player with about 65,000 Fire and knockback within 5 yards, then fixates a random raid unit within 100 yards after roughly 3 s. The meteor gains speed; local AI starts `Combustible` after 2.5 s, re-fixates 400 ms after a combustion/impact action, and resumes chase after 2 or 4 s. Direct attacks can trigger `Combustion` and knock it back; current sources report a 99% damage reduction, 100-yard knockback, a five-second no-repeat window, and `Meteor Impact` for about 120,000 normal/500,000 heroic within 8 yards. The local AI does not destroy meteors and removes their damage/speed auras on proc. Exact impact, knockback, target, and mode values remain blocked.

At 10% normal, the local boss ends the encounter victorious and cannot be killed earlier because lethal damage is clamped until the phase rule. In heroic, 10% instead transitions to phase 4 and summons the archdruids.

### Heroic phase 4 — 10% transition and platform fight

Heroic-only phase 4 brings Cenarius (53872), Malfurion Stormrage (53875), and Archdruid Hamuul Runetotem (53876). Current sources say Ragnaros retreats, is drawn out, and returns at 50% health with legs. Local sequencing is explicit: archdruid arrival starts legs submerge; after 5.5 s the boss casts legs heal 100346 and transform 100420, teleports to Z=56, faces home after 8 s, emerges 500 ms later, damages the platform gameobject 208835, talks after 3 s, and breaks free after another 10 s. Break Free destroys the platform and enables collision, removes gravity, permits lethal damage, and starts the phase-4 timers. The exact heal amount, all DBC spell variants, and movement collision behavior are blocked.

- `Superheated` (100593) begins 5 s after Break Free. Current sources report 6,000 Fire damage to the raid every second and +10% damage from each subsequent tick, stacking without a stated cap. The local filter excludes units standing on `Breadth of Frost`; it does not independently verify the base damage or stack reset.
- `Breadth of Frost` is first scheduled 6 s after Break Free and repeats locally every 46 s. Current Icy Veins describes one patch at phase start and new patches about every 45 s; standing on one removes/blocks Superheated. The same source reports that a patch can freeze a Living Meteor, consume itself, and expose the frozen meteor to greatly increased damage. Local SQL/conditions contain the meteor freeze/lavalogged spell identities, but the C++ does not independently prove the damage multiplier or every transition.
- `Entrapping Roots` is first scheduled locally at 41 s, then every 55 s. A roots cast schedules `Empower Sulfuras` 15 s later. Current sources describe a five-second Empower cast; if it completes, melee attacks become a raid wipe. The tank must lead Ragnaros through roots; current guide text reports a 10-second stun and +50% damage taken. Local empowerment changes the weapon visual and has a 25% periodic chance to fire its triggered wipe effect; exact SpellInfo timing, stun, damage and cast-interruption rules remain blocked.
- `Dreadflame` begins locally 16 s after Break Free. Its area controller samples unoccupied on-platform cells from a 961-entry grid, then spreads to available cardinal neighbors. Each grid step is 5 yards in the local data; spread chooses `ceil(occupied / 2)` positions. The local aura’s first cast tick is 1, then the next interval is 9 minus `floor(tick / 2)` capped at 8, producing progressively shorter tick intervals. It casts 2 initial/control positions in 10-player and 5 in 25-player. Current Classic sources describe patches spreading about every 3.5 s and report roughly 49,725–52,275 initial Fire plus 3,400 per second for 30 s. Exact aura period, damage, grid conversion, and four control-aura variant behavior remain blocked.
- `Cloudburst` is created by Malfurion’s draw-out sequence; local timing is 27 s after his draw-out event. The cloudburst permits one spell click in 10-player and three in 25-player, each awarding `Deluge` (100713). Current sources say Deluge grants Dreadflame immunity and extinguishes a patch by walking over it. The local Deluge script removes the dynamic object and releases that grid index; reset removes Deluge from players.
- Current Classic sources explicitly say Magma Geyser is absent from this version. The local branch has no Ragnaros Magma Geyser event; `SPELL_MAGMA` 108773 is an instance-side knockback helper for magma objects. Do not add the removed Geyser mechanic to the bot contract.

### Reset, prerequisite, completion, and credit

The Firelands instance is map 720 with seven encounter slots; Ragnaros is `DATA_RAGNAROS=6`, creature 52409, door 209073, platform 208835, spawn group 458, and stalker group 459. `firelands.cpp` spawns group 458 when the Ragnaros area trigger is entered if the boss is not done and no boss GUID exists. The area-trigger code does not itself check Majordomo’s boss state; the Ragnaros room door/passages and preceding-boss progression therefore require an integration check, not a guessed prerequisite assertion.

On evade, the local AI disengages the encounter frame, despawns summons/stalkers, removes player Deluge, restores an intact platform, despawns heroic archdruids, resets events, and uses `_DespawnAtEvade`. On victory it casts achievement check 101091 and reputation 101620; normal also summons chest 101095, plays death 99430, and binds all players. Heroic signals the archdruids’ outro. Both modes issue serverside kill credit 102237, update encounter state, set Ragnaros spawn group 458 inactive, and set the boss state `DONE`. The local file leaves Heart of Ragnaros 101253 commented as TODO. Exact aura cleanup, door reset, lockout/loot semantics, achievement conditions, and quest-item heart behavior remain blocked.

## Repository identity audit

`boss_ragnaros_firelands.cpp` registers `boss_ragnaros_firelands`, Son 53140, Lava Scion 53231, Living Meteor 53500, the three archdruids, Dreadflame 54127, and Cloudburst 54147. Material spell identities include Burning Wound/Burning Blast 99401/99400; Wrath 98259; Hand 98237; Magma Trap family 98159/98172/98175; Magma Blast 98313; Sulfuras 98703/98706/98710; wave family 98873–98876; Splitting Blow 98951; submerge variants 98982/100295–100297; Molten Seed 98333/98497/98520; Molten Power/Inferno 100158/100253; Engulfing/World in Flames 99171/100171/100190; Blazing Heat 100459/99128; meteor family 99267/99269/99287/99296/99303/100904/100910; heroic transition 100310–100346 and 100420; Superheated 100593; Roots/Empower 100645/100604; Dreadflame 100675/100679/100691 and control/damage 100692/100695/100696/100905/100941; Breadth/Cloudburst/Deluge 100472/100503/100713/100751/100758; and kill credit 102237.

`firelands.h` confirms map identity, encounter index, creature/gameobject IDs, spawn groups, and the 961-cell Dreadflame grid. `instance_firelands.cpp` maps the boss, platform, and door, clears Ragnaros helper GUIDs on FAIL, and does not define a Ragnaros boss boundary. `SpellMgr.cpp` explicitly fixes Lava Bolt mode maxima (10-player IDs 98981/100290 to four; 25-player IDs 100289/100291 to ten) and removes the World in Flames channel flag. Historical SQL attaches the scripts, map 720 spawn group 458/459, and `instance_encounters` entry 1203 to creature 52409 before the later update changes that encounter to kill-credit spell 102237. The requested 4.4.2 client/hotfix rows and Power of Stormrage application are not locally verifiable.

## Fidelity blockers

1. Exact build 59185/enUS SpellInfo and hotfix lineage at the supplied cutoff.
2. Power of Stormrage identity, initial/default state, reversibility, and health/damage interaction.
3. Guide health values versus authoritative four-mode health after optional modifier.
4. Local versus current-guide phase-1 event cadence and spell queue behavior.
5. Wrath target filter, splash/knockback range, and 10/25 damage scaling.
6. Hand target radius, knockback and mode damage.
7. Magma Trap timing, persistence, heroic vulnerability, trigger radius and damage.
8. Burning Wound/Magma Blast variants, proc/stack timing and exact damage.
9. Sulfuras cast delay, wave/scorched-ground ranges, follow-up damage and mode scaling.
10. Splitting Blow target/placement branch, normal versus heroic positions, and intermission timer.
11. Son health/SpellInfo, Lava Bolt timing/targets/damage, and Supernova scaling.
12. Molten Seed snapshot/timing, elemental health, Molten Power and Inferno falloff.
13. Engulfing/World in Flames cadence, segment geometry and damage.
14. Lava Scion health, Blazing Heat target/cadence/trail and healing values.
15. Living Meteor count/cadence, fixate/Combustible window, impact and knockback scaling.
16. Heroic transition heal, platform interaction, druid path and spell timing.
17. Heroic Dreadflame/Breadth/Cloudburst/Deluge/Empower values and meteor freeze behavior.
18. Reset cleanup, room prerequisite, door/platform state, and helper despawn behavior.
19. Credit, loot, lockout, achievement, reputation, and Heart of Ragnaros semantics.
