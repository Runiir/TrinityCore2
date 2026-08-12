# Ascendant Council — Phase 0 research contract (Cataclysm Classic 4.4.2)

This dossier is a sourced planning contract for the Ascendant Council encounter in Bastion of Twilight. It covers 10-player normal/heroic and 25-player normal/heroic. It is not live-validation evidence. Current-Classic guide claims are kept separate from this checkout's C++ and historical SQL; a local implementation detail is not silently treated as Cataclysm Classic retail truth.

## Bot-safe encounter contract

- Use two tanks through phases 1 and 2, one tank in phase 3. Keep the two active councilors close enough for cleave, but never trade away the movement needed for Glaciate, Inferno Rush, Eruption, Liquid Ice, or a targeted debuff.
- Phase 1 is Feludius (water) plus Ignacious (fire). Interrupt Hydro Lance. Keep Feludius's tank away during Glaciate; clear Waterlogged by touching Ignacious's Inferno Rush fire before Glaciate. Break Aegis of Flame quickly and interrupt Rising Flames. Let Heart of Ice and Burning Blood spread to the intended nearby group before dispelling; their opposite imbues increase damage to the other active boss.
- Balance both phase-1 health bars. The local script transitions when either reaches 25% and prevents councilor death; current guides also describe a 25% transition. Do not finish either councilor before the transition is deliberately observed.
- Phase 2 is Arion (air) plus Terrastra (earth). Lightning Rod targets must leave the raid; interrupt Lightning Blast. Touch a Violent Cyclone for Swirling Winds before Quake. Touch a Gravity Well for Grounded before Thundershock; the two buffs cancel each other. Move the melee group from Eruption and interrupt Harden Skin. Keep Arion and Terrastra near one another and balance them to 25%.
- Heroic only adds Frozen Orb from Feludius and Flame Strike from Ignacious while they are inactive, plus Static Overload from Arion and Gravity Core from Terrastra while they are assisting. Pair Static Overload and Gravity Core carriers away from the raid so the opposite debuffs clear each other. Kite Frozen Orb through Flame Strike fire; a chase/orb failure is a wipe risk. The local schedules and source spell data must be checked against the exact Classic build before automation relies on cadence.
- Phase 3 merges the remaining health of all four councilors into Elementium Monstrosity. Use a single tank, drag it around the edge out of Liquid Ice, spread ranged groups for Electric Instability, move from Lava Seed, and hard-heal Gravity Crush targets for the 6.5-second channel. Treat this as a soft-enrage/DPS race: Electric Instability selects more targets over time and Liquid Ice expands while the boss remains in it.

## Difficulty matrix

Wowhead's current 4.4.2-labelled page publishes a health table under Ignacious: 6.9M (10N), 12.8M (10H), 21.9M (25N), and 38M (25H). The page does not explicitly establish that all four councilors use exactly that same health in every current build, and the local SQL is a historical 4.3.4-era baseline. Health values below are therefore guide-reported Ignacious values, not authoritative Classic mode caps.

| Mode | Guide-reported Ignacious health | Heroic delta reported by guides | Local historical difficulty entries | Fidelity note |
|---|---:|---|---|---|
| 10N | 6.9M | baseline | 43686 / 43687 / 43688 / 43689 | exact 4.4.2 health and all-councilor mapping unresolved |
| 10H | 12.8M | higher damage and heroic helper abilities | 49616 / 49613 / 49607 / 49610 | historical IDs only; exact hotfix/build unresolved |
| 25N | 21.9M | baseline | 49615 / 49612 / 49606 / 49609 | exact 4.4.2 health and all-councilor mapping unresolved |
| 25H | 38.0M | higher damage and heroic helper abilities | 49617 / 49614 / 49608 / 49611 | historical IDs only; exact hotfix/build unresolved |

Entry order in the historical SQL is Ignacious, Feludius, Arion, Terrastra; base entries are normal 10-player and `difficulty_entry_1/2/3` are treated as normal 25, heroic 10, heroic 25 by the repository's `RAID_MODE` convention. The SQL does not prove that this mapping is the live 4.4.2 database.

## Phase and mechanic evidence

### Phase 1 — Feludius and Ignacious

The current Wowhead and Icy Veins Cataclysm Classic guides agree on the qualitative loop: two separate tanks, water/fire counter-buffs, interrupts, Waterlogged cleansing in fire, Glaciate distance, and a 25% transition. Warcraft Tavern independently describes the same phase and role split. Values below intentionally retain guide wording where pages disagree with local timing or spell data.

Feludius:

- Hydro Lance is a random non-tank cast that must be interrupted. Wowhead's narrative says about 120k Frost normal and 220k heroic; its spell table gives 180k–220k, so the damage coefficient is not promoted to a mode contract. The local script schedules the first cast at 8.5s and repeats at 13s, using 82752 in normal and 92509/92510/92511 through `RAID_MODE`.
- Water Bomb lands around Feludius, damages units within 6 yards, and applies Waterlogged (guide: 25% movement reduction, 45s). Local C++ uses the server-side 82697/82675/82699 → 82700 pipeline and historical conditions bind 82699 to Water Bomb NPC 44201; the exact bomb count/selection is not recoverable from the script alone.
- Glaciate has a 3s cast and distance falloff. Wowhead reports roughly 200k in melee, 500k heroic, and about 10k at 20–25 yards; Waterlogged targets become Frozen and suffer the extra effect. Local `spell_feludius_glaciate` subtracts 20,000 damage per yard normal or 25,000 heroic, floors at 10,000, then applies Frozen to Waterlogged targets. Local controller schedules Water Bomb at +2s and Glaciate at +15s whenever its 15s phase-preparation event runs, repeating the preparation every 30s; this is not the same as the guide's approximately 35s bomb / +17s Glaciate wording.
- Heart of Ice is a random non-tank debuff (local first at 15.5s, repeat 24s; guide roughly 20s). It deals increasing Frost damage every 2s and gives nearby players Frost Imbued; local aura logic increases the periodic amount by 10% per tick, removes Burning Blood on application, and removes Frost Imbued when its bearer damages the wrong councilor/loses the distance condition. Exact Classic aura values are not asserted.

Ignacious:

- Flame Torrent is a frontal cone. Wowhead reports about 55k Fire per second normal / 75k heroic for 3s; local first event is 8.5s and repeats 10s, with event deferral around Aegis/Rising Flames. Keep it off the raid.
- Inferno Leap selects a far/random ranged player, deals guide-reported 15k normal / 25k heroic in a 10-yard area, knocks back, then leaves Inferno Rush fire on the return path (guide: 5k normal / 15k heroic each 0.5s). Local first event is +0.5s after each 30s phase-preparation event; it records the previous victim, summons path stalkers every 6 yards, applies the rush, ignites the path +2s, and restores aggressive movement. The Cataclysm Classic bug-report thread documents inconsistent missing fire trails, so path creation is a material 4.4.2 risk.
- Aegis of Flame is a shield and Rising Flames channel. Wowhead reports 1.5M normal / 2M heroic absorption, with interruption immunity; Rising Flames lasts 20s and ticks every 2s for about 15k normal / 20k heroic. Local Aegis is mode-specific (82631/92512/92513/92514), scheduled +16.5s after each phase-preparation event; Rising Flames begins +3.5s after the shield. The local aura makes the caster interruptible while the shield/channel is active, then restores the non-interruptible flag. Exact absorption/coefficient values remain DBC/build-dependent.
- Burning Blood is a random non-tank debuff (local first 30s, repeats 21s; Wowhead says roughly every minute). It ticks every 2s with increasing Fire damage and grants nearby allies Flame Imbued, which adds damage to Feludius; local aura logic increases the periodic amount by 10% per tick and removes Heart of Ice on application. Exact duration and scaling are unresolved.

### Phase 1 transition

The local `DamageTaken` handlers double damage from the opposite imbue, call the controller when either active councilor would cross 25%, then clamp damage so the councilor survives at 1 HP. The controller resets active event maps, pacifies/teleports the two current councilors to balconies, teleports Arion/Terrastra to the floor, and sets its phase to Arion/Terrastra. Guide prose says the councilors teleport away at 25%; it does not document the local 1-HP clamp or exact RP timings.

### Phase 2 — Arion and Terrastra

Arion:

- Call Winds begins locally +9.3s after Arion's floor attack sequence and repeats 31.5s; guides say about 10s then 30s. It creates a Violent Cyclone. Wowhead reports a 50s wandering lifetime, 5k Lashing Winds damage/knockback, and Swirling Winds for 2 minutes. The local cyclone seeks target-stalker waypoints at random 10–14s intervals and does not itself encode a 50s expiry.
- Lightning Rod is local first +17.9s and repeats 19.4s, with Chain Lightning +8–10s after the marker. Local target filtering selects 1 target in 10-player and 3 in 25-player, while Wowhead's current prose says 3 players without a clear 10/25 distinction. Marked players must isolate at least 15 yards; exact target count is fidelity-blocked.
- Disperse is local first +20.5s and repeats 24s. It excludes units within 10 yards, teleports to a target-stalker, then schedules Lightning Blast +2s. Guides describe roughly 30s Disperse and a 4s Lightning Blast cast; local mode spell IDs are 83070/92454/92455/92456. Interrupt every Lightning Blast; exact current cast timing and target selector need live validation.
- Thundershock is locally warned at +55.7s, cast +10s later, and repeated each 60s after the warning. Guides say approximately every minute and report about 80k Nature normal / 150k heroic. Local damage is reduced to 1% for Grounded targets (a 99% reduction), and Grounded is removed by a cyclone hit.

Terrastra:

- Gravity Well is local first +6.9s and repeats 17s; guides say roughly 10s then 20s. A random target's well pulls nearby units, deals guide-reported 3k Nature within 7 yards, and grants Grounded. Local 83572 uses a pre-visual (95760) then magnetic pull auras (83579/83587/83583); touching a well removes Swirling Winds.
- Eruption is local first +9.3s and repeats 17s. Five spikes are placed around Terrastra and deal damage after the local 3.9s target delay; Wowhead reports 4-yard, roughly 25k normal / 50k heroic Physical damage and knockback after about 4s. The local script creates five eruption targets around the boss and despawns them after the damage window.
- Harden Skin is local first +22.7s and repeats 43.8s; current Wowhead says every 15s while Icy Veins only calls for an interrupt. The current guide reports 50% damage absorption up to 1.65M normal / 2.1M heroic, with +20% normal / +100% heroic physical damage until the shield breaks; local 83718 absorbs a percentage from DBC and applies Shatter with accumulated absorbed damage when removed by an enemy spell. This cadence and coefficient conflict is material.
- Quake is locally warned +19.2s, first cast +27.5s, then repeats 68s with a warning 59.7s before each repeat. Wowhead reports first about 30s and then every minute; damage about 70k Physical normal / 150k heroic and 90% mitigation from Swirling Winds. The local target filter removes Swirling Winds targets, i.e. only non-buffed players are hit; guide prose says the buff is required to survive.

Heroic helper abilities:

- At encounter start, local Arion schedules Static Overload first +19.7s then every 20s; Terrastra schedules Gravity Core first +22.7s then every 20s. Static Overload applies to one target excluding existing Gravity Core; Gravity Core applies to one target excluding existing Static Overload. The local triggered spells clear both when the two carriers meet. Wowhead reports Static Overload 6.5k Nature every 2s for 10s normal / 10k heroic and Gravity Core 10k Physical every 2s, with nearby slow/attack/cast hindrance; current Icy Veins confirms the heroic-only pair but omits exact coefficients.
- When phase 1 transitions, local Feludius schedules Frozen Orb first +24s/repeat 20s and Ignacious schedules Flame Strike first +32s/repeat 20s. Wowhead and Icy Veins describe a random pursuing orb that must be led through lingering Flame Strike fire. Local orb targeting randomizes one enemy and increases speed every second; Flame Strike first targets one random player and its stalker dispels the orb. Exact Classic wipe behavior and timer are unresolved.

### Phase 2 transition and phase 3

The local Arion/Terrastra `DamageTaken` handlers use the same 25% threshold and 1-HP clamp. The controller resets all four councilor event maps, applies Elemental Stasis to Terrastra, clears encounter debuffs, teleports each councilor, schedules the merge 14.5s later, disengages the four encounter frames, then summons Elementium Monstrosity. Historical SQL binds Merge Health 82344 to each base councilor; local `SpellHitTarget` sums the four current health values and sets the monstrosity's health only after all four targets are processed. Current guides agree that the remaining health is combined but do not establish the exact client-side spell pipeline.

Elementium Monstrosity:

- Local intro casts Twilight Explosion DND and Merge Health, applies Electric Instability and Cryogenic Aura at +1.5s, enables aggressive combat +3.8s, schedules Lava Seed +19.7s then repeats 21.7s, and schedules Gravity Crush +32.9s then repeats with a random 24–28s delay. Wowhead reports Cryogenic Aura/Liquid Ice about every 2.5s, Lava Seed about +20s then every 30s, and Gravity Crush every 30s; Icy Veins confirms the phase is a DPS race but gives no timers.
- Cryogenic Aura creates Liquid Ice under the boss; local aura either summons a new patch (84916) or scales the caster's existing patch (84917), with Liquid Ice trigger 84915 and historical difficulty variants 92497/92498/92499 on NPC 45452. Wowhead reports the boss takes 25% less damage while in a patch, the pool doubles in size on continued exposure, and deals about 10k Frost/sec normal / 25k heroic. Blizzard's historical Jan. 26 hotfix says an earlier increase to Liquid Ice damage was reverted because the boss hitbox made avoidance difficult; this is not proof of the 4.4.2 value.
- Electric Instability (84526 → 84529) ticks every second. Local target count starts at one and adds one target per 20 aura ticks, then randomly resizes the eligible list; Wowhead reports 7k Nature normal / 16k heroic, 10-yard chaining, and increasing simultaneous targets. Exact target cap/coefficients by 4.4.2 mode are unresolved.
- Lava Seed (84913) marks plume stalkers (45420), which erupt after +1.1s and move their plume +2.3s; Wowhead says each kernel explodes after about 4s for 50k Fire normal / 100k heroic within 4 yards. Local server-side targeting and visual spell identity are confirmed; exact Classic damage/timing remain guide-reported.
- Gravity Crush (84948 → 84947/84952) excludes the current victim and locally selects 1 target in 10-player or 3 in 25-player, then raises the target 30 yards after +1.2s. Wowhead and Icy Veins report three random players in all modes, 9% maximum health every 0.5s for 6.5s (117% before fall damage). The target-count conflict is material; do not encode one rule as retail truth.

## Timer and random ledger (not live-validated)

| Event | Current strategy report | Repository baseline | Status |
|---|---|---|---|
| Hydro Lance | about 10s, then 15s | 8.5s, then 13s | cadence conflict; mode damage conflict |
| Water Bomb / Glaciate | about 35s / 17s after bomb | controller prep +2s / +15s, prep first +15s then every 30s | timer conflict |
| Heart of Ice | roughly 20s | 15.5s, then 24s | timer conflict |
| Flame Torrent | about 10s, then 15s | 8.5s, then 10s with Aegis deferrals | timer conflict |
| Inferno Leap/Rush | about 15s, then 30s | +0.5s after each 30s phase-prep; path +2s | implementation cadence differs; Classic fire-trail bug reported |
| Aegis/Rising Flames | about 30s, then 60s; 20s channel | +16.5s / +20s after phase-prep | timer and coefficient conflict |
| Burning Blood | about 60s | 30s, then 21s | timer conflict |
| Call Winds | 10s, then 30s; cyclone about 50s | 9.3s, then 31.5s; movement 10–14s | timer/lifetime conflict |
| Lightning Rod/Chain | about 20s; shortly after marker | 17.9s, then 19.4s; chain +8–10s | target/timer conflict |
| Disperse/Lightning Blast | about 30s; blast 4s cast | 20.5s, then 24s; blast +2s after target | timer conflict |
| Gravity Well | 10s, then 20s | 6.9s, then 17s | timer conflict |
| Eruption | every 15s, spikes ~4s | 9.3s, then 17s; local damage +3.9s | timer conflict |
| Harden Skin | every 15s (Wowhead) | 22.7s, then 43.8s | major conflict |
| Quake/Thundershock | alternate with first quake ~30s; then ~60s | Quake +27.5s then 68s; Thundershock +65.7s then 60s | timer conflict |
| Heroic Static/Gravity | heroic-only, periodic | +19.7/+22.7s then 20s | local timer not current-proof |
| Heroic Frozen Orb/Flame Strike | orb 20s, fire used to pop it | +24/+32s then 20s | local timer not current-proof |
| Liquid Ice | about 2.5s aura tick | aura periodic; new/scale behavior in C++ | damage/hotfix unresolved |
| Electric Instability | every 1s, increasing targets | aura tick; +1 target per 20 ticks | target cap/coefficient unresolved |
| Lava Seed | +20s then about 30s | +19.7s then 21.7s | timer conflict |
| Gravity Crush | about every 30s; 6.5s channel | +32.9s then random 24–28s | timer conflict; target-count conflict |

## Reset, completion, and credit behavior

- Controller `Reset()` schedules a 1ms reset-state event and returns to phase 1 unless the instance is already `DONE`. The reset event sets the boss state to `NOT_STARTED` and summons the four councilors at fixed spawn positions. On an evade, `ACTION_STOP_ENCOUNTER` disengages and despawns all four councilors and the monstrosity, removes player Static Overload/Gravity Core/Swirling Winds/Grounded auras, marks the encounter `FAIL`, resets the controller events, and schedules fresh councilor summons after 30s.
- Councilor reset methods restore interruptibility/react state but do not expose a separate retail lockout or achievement reset. `OnCreatureCreate` respawns dead councilors whenever the boss is not `DONE`; this is repository behavior, not a claim about the live service.
- On phase 3 death, the monstrosity calls controller `ACTION_FINISH_ENCOUNTER`, disengages its frame, removes player helper auras, and sets `DATA_ASCENDANT_COUNCIL` to `DONE`. The instance maps the encounter to `DATA_ASCENDANT_COUNCIL` and the loader registers `AddSC_boss_ascendant_council`; no separate retail loot/credit semantics are asserted here.
- The instance owns entrance/exit doors 205226/205227 for `DATA_ASCENDANT_COUNCIL`; world state 5621 is the Elementary achievement state. Current official Cataclysm Classic 4.4.2 notes establish the patch context but do not specify an Ascendant Council mechanic or hotfix. Historical Blizzard hotfixes are included only as provenance and conflict evidence.

## Repository spell and creature identity cross-reference

| Role | Creature identity | Important spell identities |
|---|---|---|
| Controller | 43691; `boss_ascendant_council_controller` | 82344 Merge Health; 34098 clear debuffs |
| Feludius | 43687; `npc_feludius`; historical 49612/49613/49614 | 82746 Glaciate, 82699 Water Bomb, 82762 Waterlogged, 82752/92509/92510/92511 Hydro Lance, 82665 Heart of Ice, 92267 Frozen Orb |
| Ignacious | 43686; `npc_ignacious`; historical 49615/49616/49617 | 82631/92512/92513/92514 Aegis, 82636 Rising Flames, 82777 Flame Torrent, 82660 Burning Blood, 82856 Inferno Leap, 82859 Inferno Rush, 92212 Flame Strike |
| Arion | 43688; `npc_arion`; historical 49606/49607/49608 | 83491 Call Winds, 83500 Swirling Winds, 83099 Lightning Rod, 83300 Chain targeting, 83087 Disperse, 83070/92454/92455/92456 Lightning Blast, 92067 heroic Static Overload |
| Terrastra | 43689; `npc_terrastra`; historical 49609/49610/49611 | 83572 Gravity Well, 83581 Grounded, 83718 Harden Skin, 83760 Shatter, 83565 Quake, 83675/83661/83692 Eruption, 92075 heroic Gravity Core |
| Monstrosity | 43735; `npc_elementium_monstrosity`; historical 49619/49620/49621 | 84526/84529 Electric Instability, 84918 Cryogenic Aura, 84913 Lava Seed, 84916/84917/84915 Liquid Ice, 84948/84947/84952 Gravity Crush |
| Helpers | 44201 Water Bomb; 47501 Inferno Rush; 44747 Cyclone; 44824 Gravity Well; 44845 Eruption; 45420 Plume; 45452 Liquid Ice; 45476 Gravity Crush; 49518 Frozen Orb; 49432 Flame Strike | Historical SQL binds helper script names and spell conditions; server-side IDs are not proof of current client tuning |

## Strong sources and unresolved blockers

- Wowhead, “Ascendant Council Strategy Guide — The Bastion of Twilight Raid Cataclysm Classic,” Beanna, updated 2024-06-04, page labelled Patch 4.4.2: https://www.wowhead.com/cata/guide/raids/the-bastion-of-twilight/ascendant-council-strategy
- Icy Veins, “Ascendant Council Encounter Guide: Strategy, Abilities, Loot,” Abide, updated 2024-07-29: https://www.icy-veins.com/cataclysm-classic/ascendant-council-encounter-guide-strategy-abilities-loot
- Warcraft Tavern, “Ascendant Council Raid Guide — Cataclysm Classic,” Passion, retrieved 2026-08-12 (page currently returned 403 to the fetcher; search extract used only for qualitative phase/ability corroboration): https://www.warcrafttavern.com/cataclysm/guides/ascendant-council-raid-guide/
- Blizzard, “World of Warcraft: Cataclysm Classic Patch 4.4.2 Notes,” Kaivax, 2025-02-18 (patch context; no Council tuning): https://us.forums.blizzard.com/en/wow/t/world-of-warcraft-cataclysm-classic-patch-442-notes/2062030
- Blizzard, “Cataclysm Hotfixes — Updated Jan. 26” (historical original-Cataclysm Liquid Ice and soft-reset door changes; not Classic 4.4.2 authority): https://worldofwarcraft.blizzard.com/news/1232869/cataclysm-hotfixes-updated-jan-26
- Blizzard, “Cataclysm Hotfixes — Last Update: January 26” (historical Liquid Ice damage-revert context): https://worldofwarcraft.blizzard.com/en-gb/news/9980095/
- Blizzard forum, “CATA Ascendant Council bugs” (June 2024 player reports of missing Inferno Rush fire trails; observational bug evidence, not an official mechanic specification): https://us.forums.blizzard.com/en/wow/t/cata-ascendant-council-bugs-bugs-in-general/1867921
- Repository C++: `src/server/scripts/EasternKingdoms/BastionOfTwilight/boss_ascendant_council.cpp` (spell IDs 64–180; controller/state machine 315–529; councilors 531–1500; Monstrosity/helpers 1500–1800; SpellScripts 1800–2600), `bastion_of_twilight.h` (IDs/data 25–153), `instance_bastion_of_twilight.cpp` (mapping/doors), and eastern-kingdoms loader registration.
- Repository historical SQL: `sql/old/custom/world/34_2020_02_21/custom_2018_12_21_00_world_updatepack.sql` (difficulty entries/script names 6445–6485; conditions 6593–6607; this checkout baseline is not a 4.4.2 database).

Material blockers remain: exact Classic 4.4.2 client/build and Bastion hotfix cutoff; whether guide health values apply equally to all four councilors; mode-specific health/damage/absorption coefficients; Hydro Lance/Lightning Rod/Gravity Crush target counts; every timer and random range; Liquid Ice hotfix state; Inferno Rush fire-trail behavior; helper target filters and aura durations; merge-health spell effects; controller/councilor custom-field reset semantics; and retail reset/loot/credit behavior. Until these are validated, the contract and ledger remain `fidelity_blocked` and must not drive live boss automation.
