# Madness of Deathwing — Dragon Soul

Research dossier for the approved Cataclysm Classic raid-progression snapshot. This is a research artifact, not a claim of live completion or a replacement for encounter validation.

## Snapshot and disposition

- Product: Cataclysm Classic, patch 4.4.2, build 59185, enUS.
- Scope: 10-player Normal, 10-player Heroic, 25-player Normal, and 25-player Heroic.
- Corrected Dragon Soul unlock boundary: `2025-02-20T23:00:00Z` (3:00 p.m. PST on February 20, from the official notes). The boundary is the raid's release moment; it is not a pre-release gameplay observation.
- Research date: 2026-08-12. Local revision audited: `2db8059867f15e58721b92da01f8b7ccf26346cf`.
- Fidelity: `fidelity_blocked`. The contract and ledger intentionally retain unresolved material fields rather than inventing build-59185 values.

The official notes establish an eight-boss raid with 10/25-player Normal and Heroic modes, but do not publish Madness tuning tables. The guide material is dated February 15 and 19, before the unlock, and is useful for mechanic corroboration—not proof of the exact cutoff hotfix state. No Presence of the Dragon Soul reduction is applied at the cutoff: Blizzard announced it later, beginning with the March 18 reset. Later Presence state is documented separately.

No later hotfix or tuning table is silently back-projected into the unlock snapshot. In particular, the later Presence announcement is a named, global modifier with its own start and progression, not evidence that the base 4.4.2 encounter was already reduced at release; guide-published values remain observations until build-matched evidence identifies their hotfix state.

## Source register

| ID | Source and use | Date / authority |
|---|---|---|
| `blizzard_442_notes_59185_cutoff` | [Cataclysm Classic 4.4.2 notes](https://us.forums.blizzard.com/en/wow/t/world-of-warcraft-cataclysm-classic-patch-442-notes/2062030); release time, raid sizes, difficulty names | Blizzard, 2025-02-18; official |
| `blizzard_presence_dragon_soul_2025` | [Presence of the Dragon Soul begins March 18](https://us.forums.blizzard.com/en/wow/t/presence-of-the-dragon-soul-begins-march-18/2074792); later health/damage reduction and Lord Devrestrasz removal | Blizzard, 2025-03-12; official post-cutoff modifier notice |
| `wowhead_cata_madness_2025` | [Madness of Deathwing Strategy Guide](https://www.wowhead.com/cata/guide/raids/dragon-soul/madness-of-deathwing-strategy-overview); 4.4.2-labelled mode health observations, mechanic descriptions, spell ranges | Ease, updated 2025-02-19; secondary, pre-unlock |
| `icy_veins_cata_madness` | [Madness encounter guide](https://www.icy-veins.com/cataclysm-classic/madness-of-deathwing-encounter-guide-strategy-abilities-loot); phase, role, timer, heroic and achievement corroboration | Abide, updated 2025-02-15; secondary, pre-unlock |
| `warcraft_tavern_cata_madness` | [Madness raid guide](https://www.warcrafttavern.com/cataclysm/guides/madness-of-deathwing-raid-guide/); independent strategy corroboration and enrage/role context | secondary; page was not used to settle conflicting numeric fields |
| `repo_dragon_soul_madness_cpp` | `dragon_soul.h`, `instance_dragon_soul.cpp`, `boss_madness_of_deathwing.cpp`, and loader; executable spell IDs, schedules, target filters, reset, credit, and difficulty GO selection | local repository, revision above |
| `repo_dragon_soul_sql_identity` | historical 4.3.4 creature and encounter rows, including encounter 1299 / credit spell 111533 and variant templates | local historical SQL; identity evidence only |

The source summaries are deliberately original and abbreviated; they do not reproduce guide prose.

## Encounter shape

The externally corroborated encounter has two phases. Phase 1 clears one Arm or Wing Tentacle on each of four platforms. Deathwing chooses the platform with the most players, and Carrying Winds moves the raid between platforms. The Aspect above a living limb supplies a raid Presence and a special ability. Killing that limb removes that Aspect's aid and turns the Aspect toward containing the defeated limb. Phase 2 is Deathwing's head on the central/Ysera platform, with all four Aspects restored and a final add-and-burn check.

The recommended Ysera → Alexstrasza → Nozdormu → Kalecgos order is strategy advice, not a source-proven requirement. The local implementation instead counts players on the four platform reference points and chooses the living platform with the greatest count; it does not enforce a fixed order.

### Aspect effects and loss

The Wowhead guide reports the following observable effects; the local spell identities are included for cross-reference, but exact 59185 aura coefficients and application order remain blocked.

| Aspect | Observed aid while its limb lives | Local identities |
|---|---|---|
| Alexstrasza | Presence increases maximum health 20%. Cauterize kills Blistering Tentacles over about 5 seconds and reduces Corrupted Blood damage. | NPC `56099`; Presence `105825`; Cauterize `105565` |
| Nozdormu | Presence increases haste 20%. Time Zone slows the Elementium Bolt and reduces enemy attack speed 50% inside the zone. | NPC `56102`; Presence `105823`; Time Zone `106919` / missiles `105799`, phase-two `107055` |
| Ysera | Presence increases healing done 20%. Dream/Enter the Dream reduces damage taken 50% for 2.5 seconds. | NPC `56100`; Presence `106456`; Dream `106463` |
| Kalecgos | Presence increases damage 20%. Spellweaving deals 19,500–20,500 Arcane damage within 6 yards, excluding the current target. | NPC `56101`; Presence `106026`; Spellweaver `106039` |

At the fourth limb, the local script removes the phase-one Aspect buffs and makes the head selectable. The guide language says the Aspects return for phase two; exact client aura sequencing is not established by the release notes.

### Phase 1 mechanics and observed quantities

- **Limb tentacle:** has no normal melee target and is not tanked. Burning Blood ticks every 2 seconds in the guide account and ramps as limb health falls. The local AI applies spell `105401` once below 90% and lets the spell script derive stacks from lost health.
- **Health control:** the local boss casts shared-health spell `109547` on engage/first assault and its SpellScript chains `109548`. The affected-unit filter, whether this exactly implements the retail limb/head health relationship, and mode coefficients are not established; the guide's reported 20% Deathwing-health damage on limb death is retained separately.
- **Blistering Tentacles:** Wowhead and Icy Veins report waves at 70% and 40% remaining limb health, immunity to area damage, and Blistering Heat of 3,750 Fire every 2 seconds with a 5% damage increase for 3 seconds per stack. The checkout AI instead triggers three waves at 75%, 50%, and 25%, through `105551`, and invokes Alexstrasza Cauterize. This is a material unresolved Classic-versus-checkout conflict, not an assumption to resolve.
- **Hemorrhage / Regenerative Blood:** guides report six Bloods about 90 seconds after combat and thereafter while the platform is active. Bloods gain 10 energy per second and heal to full at 100 energy; melee applies stacking Degenerative Bite. Local spells are `105853`, `105861`, `105932`, `105934`, `105937`, with mode-selected Bite IDs `105841/109625/109626/109627` in repository order. The local periodic script heals at ticks 11 and 20 and ends at tick 20; it does not prove the 4.4.2 retail cadence.
- **Mutated Corruption:** a stationary add is reported about 10 seconds after a platform is selected, requiring a tank. Crush selects a player and deals a line/cone hit; Wowhead lists 130,000 Physical. Impale is a tank-buster; Wowhead lists 1,200,000 Physical and a roughly 35-second cadence, while the local AI schedules its first cast at 10.5 seconds and repeats every 36 seconds. Local IDs are Crush targeting `106382`, Crush `106385`, and Impale `106400`.
- **Elementium Bolt:** guides put the event around 45 seconds into a platform. A landed Bolt deals 456,300–479,700 Fire initially, then 380,250–399,750 Fire every 5 seconds until destroyed; initial damage falls with distance. Nozdormu's Time Zone slows travel. Local event offsets are 41 seconds on the first assault and 58 seconds thereafter, and the C++ path uses a 2.5 velocity only when Nozdormu remains available. IDs are `105651`, `105723`, `110628`, `106242`, `106991`, and `110663`.
- **Cataclysm:** Wowhead describes a two-minute start to a 60-second cast, with failure wiping the raid; Icy Veins describes a three-minute platform failure boundary. The local first assault schedules `106523` at 1:55 and later assaults at 2:13, cancelling it when a limb dies. The cast-start, duration, and failure timestamp therefore remain blocked.
- **Heroic-only Corrupting Parasite:** Wowhead/Icy Veins describe a random-player DoT lasting 10 seconds, an explosion on detachment (Icy Veins reports 250,000 Fire within 10 yards), and a spawned Parasite with a 10-second Unstable Corruption cast. Icy Veins reports raid Fire damage equal to 10% of remaining add health and roughly a 50-second second spawn on its guide route. No local Parasite AI or spell enum is present in this boss script, so target filter, frequency, Alexstrasza interaction, and exact Heroic mode behavior cannot be claimed.

### Phase 2

When all four limbs die, the guides report Deathwing falling forward and becoming attackable at approximately 20% health. Corrupted Blood ticks every 2 seconds and increases at 15%, 10%, and 5% health. The local phase transition casts `106708`, resets the phase-two head damage requirement, removes the head's not-selectable flag, and applies `106843`; the exact health transfer is not encoded as a quantitative value in this script.

- Elementium Fragments: guides report three on 10-player and eight on 25-player, with Shrapnel cast after about 7 seconds at a random player for 390,000–410,000 unresistable Physical damage. Icy Veins reports 90-second waves. The local phase-two event fires once at 11 seconds; its script selects player targets and pairs them with every fragment, then random-resizes when players outnumber fragments. This is a runtime/model divergence requiring validation.
- Elementium Terrors: two spawn, are tanked, and apply stacking Tetanus. Wowhead reports 93,600–98,400 Physical plus 35,100–36,900 Physical each second; local mode spell selection is `106730/109603/109604/109605` in repository order. Icy Veins reports a 25-second relation to the Fragment wave; the local event fires once at 36 seconds.
- Heroic Congealing Blood: sources disagree on eight (Icy Veins) versus ten (Wowhead) per 15/10/5 trigger. Each reaching Deathwing heals 1% of maximum health and sources describe slowing but not stun/root control. The local script summons three on 10-player and eight on 25-player with no Heroic check in this spell script, so it is an implementation identity rather than a 59185 claim.
- Enrage: Wowhead and Warcraft Tavern use a 15-minute encounter timer, but no local event or release-note field establishes how that timer is enforced. Treat it as an observed guide value only.

## Difficulty and modifier matrix

| Mode | Heroic delta reported by sources | Health observation (guide-published before cutoff) | Cutoff Presence |
|---|---|---:|---|
| 10N | No Parasite / Congealing Blood in guide model; three Fragments | 25,000,000 | inactive / not yet introduced |
| 10H | Heroic Parasite and Congealing Blood; three Fragments | 29,000,000 | inactive / not yet introduced |
| 25N | No Heroic additions; eight Fragments | 76,000,000 | inactive / not yet introduced |
| 25H | Heroic Parasite and Congealing Blood; eight Fragments | 87,000,000 | inactive / not yet introduced |

The 25/29/76/87M values are Wowhead's 2025-02-19 page observations, not a frozen build-59185 tuning table. Historical SQL contains multiple Deathwing/add variant template rows and health modifiers, but does not safely map those rows to the four Classic modes. No numeric values are scaled by the later Presence modifier.

### Presence of the Dragon Soul — later state only

Blizzard announced that starting with the March 18, 2025 weekly reset, all Dragon Soul enemies receive a 5% health and damage reduction, increasing by 5 percentage points every two weeks to 30% by the end of May. Lord Devrestrasz can remove it. This was announced and activated after the requested cutoff, so `active_at_cutoff=false`. The aura ID, persistence semantics, default state in the local branch, and exact application to each summon remain unresolved.

## Reset, prerequisite, credit, and repository audit

- Local map is 967, has eight encounter slots, and assigns `DATA_MADNESS_OF_DEATHWING=7`. The boss entry is `56173`; the phase-two head is `57962`.
- Local support identities include limbs `56167/56846/56168`, Tail Tentacle `56844`, Mutated Corruption `56471`, Crush Target `56581`, Platform `56307`, Hemorrhage Target `56359`, Elementium Bolt `56262`, Blistering Tentacle `56188`, Time Zone Target/Time Zone `56332/56311`, Fragments/Terrors `56724/56710`, Thrall `56103`, and the four Aspects `56099–56102`. Final reward GOs are 10N `210079`, 25N `210218` (or LFR `210220`), 10H `210219`, and 25H `210217`.
- Thrall gossip menu `13295` starts the local encounter when the boss state is not `IN_PROGRESS`; the script summons Deathwing and removes gossip. Evade despawns limbs, adds, Thrall, and Aspects and sets cleanup through the BossAI path. Exact retail reset range, respawn, and re-engage rules are not established.
- On local success, `StartDeathSequence` fires achievement/encounter credit spell `111533`, permanently binds players, removes Tetanus and Degenerative Bite, rewards the phase-two loot recipient, summons a mode-specific reward GO for one week, and sets the boss state `DONE`. Historical SQL maps encounter ID 1299 to credit spell `111533`. This is repository behavior, not proof that Classic's loot recipient or lockout semantics are identical.
- The local outro is a separate state: damage cannot kill the body below 1%, `110062` begins the slump/outro, and Thrall's Dragon Soul sequence eventually sends `110101` to Deathwing; the script schedules disengage/despawn after 9 seconds. Exact retail cinematic, death, and credit ordering is blocked.
- `instance_dragon_soul.cpp` wires the boss and support creatures but has no gameobject data table; `kalimdor_script_loader.cpp` registers the instance and Madness AI. This is executable evidence for the current checkout only.
- The local phase-two event schedule is one-shot (Fragments 11s, Time Zone preparation 26s, Terrors 36s), while guides describe recurring waves. No live validation was run.

## Fidelity blockers

All 24 entries are material and remain `fidelity_blocked` in both machine artifacts:

1. Build-59185 hotfix lineage exactly at the unlock boundary.
2. Four-mode health, damage, and phase-two head tuning.
3. Presence aura IDs, application, persistence, and default/toggle state.
4. Limb Blistering thresholds (70/40 guide versus 75/50/25 checkout).
5. Cataclysm start, cast duration, and wipe boundary.
6. First/later assault timing and platform transition cadence.
7. Assault tie-breaking and exact player/platform counting filter.
8. Aspect coefficients, aura order, and loss/restoration semantics.
9. Heroic Parasite frequency, target filter, explosion, and Cauterize behavior.
10. Burning Blood and Blistering Heat exact coefficients and stacking.
11. Hemorrhage count, timer, and Blood scaling.
12. Blood energy reset/heal and mode-specific Degenerative Bite behavior.
13. Crush geometry/filter and Impale target/debuff semantics.
14. Elementium Bolt travel, impact/pulse timing, and Nozdormu path effect.
15. Limb-death stun/shared-health transfer and phase-two head health.
16. Fragment count, Shrapnel target pairing, cast interval, and recurrence.
17. Terror Tetanus targeting, coefficients, and recurrence.
18. Corrupted Blood curve and exact threshold increments.
19. Heroic Congealing Blood count, spawn points, control immunity, and healing.
20. Fifteen-minute enrage enforcement and interaction with add waves.
21. Wipe/evade cleanup, respawn, and re-engagement semantics.
22. Retail start prerequisite, initial platform rule, and order enforcement.
23. Loot, lockout, achievement, and player-credit behavior across all modes.
24. Historical variant-entry-to-mode mapping and official scaling/modifier interaction.

Until those blockers are resolved with build-matched evidence, an autonomy controller should model the encounter as research-only and refuse to report fidelity-complete success.
