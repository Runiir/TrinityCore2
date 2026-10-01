# Magmaw research baseline

Tuning reference: Cataclysm Classic 4.4.2.59185, enUS, hotfix cutoff February 20, 2025. Execution target: 4.3.4 build-15595 client and server. Scope: 10N, 25N, 10H and 25H. The [claim ledger](../../../../../experiments/configs/cata_raid_encounters/blackwing_descent/magmaw_ledger_v1.json) is the quantitative authority; this dossier is its working summary.

The September 12 local inspection confirmed the running client's directory as `/home/runiir/Games/Cataclysm-4.3.4.15595-enUS-x64`; its Sound.log reports 4.3.4 (15595). Its installed Magmaw DBM module is revision 7661, separate from the Classic module previously researched under `_whitemane-60895_`. The legacy module also predicts 22s Spew, 32.5s Pillar (comment allows 30-40s), 90s first/95s repeat Mangle and 30s exposure. Agreement corroborates predictions, not server cast timing. No WoWCombatLog.txt was present at inspection, and addon loading was not verified. Existing Prat ChatLog code uses LoggingCombat(1/0), so standard client logging is the first capture option. This inspection supplies no new damage observation and does not close the melee-pressure or cast-outcome gaps.

The packet supports bounded repairs. Full four-mode fidelity and training admission remain blocked. Research specifies what a live check must observe; implementation validation supplies that observation. A boss clear does not establish correct incoming damage, class performance or mechanic execution.

## What each source establishes

The qualitative strategy comes from the [Wowhead guide](https://www.wowhead.com/cata/guide/raids/blackwing-descent/magmaw-strategy) and [Icy Veins guide](https://www.icy-veins.com/cataclysm-classic/magmaw-encounter-guide-strategy-abilities-loot), checked against the repository. Their approximate values do not override pinned spell rows or attributed combat observations.

- Pinned DBM supplies cooldown predictions with event anchors. Use native spell queues and cast-state leeway. A prediction is not an exact cast-start deadline.
- WCL supplies observed combat outcomes, activity, mitigation estimates and phase evidence for the identified report/mode/date. Selected UI rows are not a complete event export.
- Pinned client spell tables supply effect values, difficulty mappings, durations and triggers. Loaded native DBC, SQL overrides and C++ corrections determine this server's effective inputs.
- The promoted WoWSims catalog supplies exact matched class references. It does not predict an arbitrary raid's total Magmaw DPS. Tank/healer references also require incoming pressure, threat, defenses, mana and preventable deaths.
- Native timelines bind the implementation to a build, database, roster and attempt. An actual-client policy will additionally need client-visible observations and action/latency feedback; server-only facts can be teacher labels, not undeclared policy inputs.

## Current quantitative references

Health below is calculated from the configured native creature data or derived from consecutive WCL resource-bar changes. WCL-derived values are not raw max-HP fields. The selected reports range from September 2024 to April 2025; they do not alone prove exact-cutoff parity.

| Mode | Native calculated boss HP | WCL-derived boss HP | Spit targets in native script |
| --- | ---: | ---: | ---: |
| 10N | 26,798,304 | 26,798,304 | 3 |
| 25N | 81,082,048 | 81,082,048 | 8 |
| 10H | 39,240,616 | 39,240,600 | 3 |
| 25H | 120,016,040 | 120,016,403 | 8 |

The guide's 33.5M normal health must not override the measured 10N reference. The 363 HP difference in 25H may reflect the precision of the stored modifier; the cause has not been verified. The 25H construct derives to 4,500,000 HP across nine resource differences; current native calculation is 4,499,999. The 10H construct derives to 1,410,000 HP; native 1,410,001. The guide's 6M is not the selected reference.

All 32 checked native base/dice rolls across nine damage events match the pinned client mode rows. The [mode table and longer-log observations](../../../magmaw_longer_wcl_20260912.md#client-values-by-mode) retain the values. This does not check every final modifier. In particular, native `SpellMgrCorrectionsPart04.cpp` changes Mangle's initial weapon hit from 150% to 100%; that hit is separate from periodic Mangle damage.

Boss melee is an unresolved material input. The retained 10N run has 24 Magmaw melee events totaling 20,127 health damage to Mgwtankb. The [historical 10N WCL melee view](https://classic.warcraftlogs.com/reports/MxFq7TRbvnjGY1hJ?fight=22&type=damage-taken&view=events&ability=1&options=4098&target=282) has 14 landed U estimates ranging from 111,531 to 178,540, plus seven misses/parries. These are different damage fields and tank setups. Since `sql/custom/world/2026_09_23_30_magmaw_damage_modifier.sql`, the 10N entry 41570 uses DamageModifier 16. That value is fitted to this WCL envelope at the attacker-bonus stage (bounds 15.84-16.33) and cross-checked against Mangle's initial hit; see `experiments/configs/encounter_fidelity/creature_damage_calibration_v1.json`. The 25N/10H/25H entries are still uncalibrated. The envelope comes from a single 2024-10-28 log, so it is still subject to the target-era gap. The inherited migration `2025_06_18_06_world.sql` reset all creature damage multipliers to 1 because formula changes required reevaluation. Commit `68a3622133` is an ancestor of all three compared canary sources; it is not a newly introduced patch between them. The current database updater receipt records application. Do not copy an old multiplier or use this run to qualify Vengeance, tank DPS or healer pressure.

The September 12 incoming-timeline repair recovers all 24 melee callbacks from the original a4b9 stream, including 17 with zero health damage. Their native `raw_amount` ranges from 4,466 to 8,012 (mean 5,993.542). The original stream has 8,367 events, 189 accepted delta responses and no gaps. The 29 retained tank snapshots report armor 40,530 throughout, consistent with the seven positive health/raw ratios of 0.445586-0.445727 under the ordinary-hit armor calculation. Snapshot Vengeance ranges from 0 to 1,131 AP against cap 14,738; these are not same-swing aura observations or a Vengeance implementation verdict. This is an analysis repair, not a new pull or a damage adjustment. The [incoming replay publication](../../../../../artifacts/cata_raid_program/magmaw_incoming_timeline_20260912.publication.json) binds the reconstructed view to that immutable run.

Native melee raw is stored after damage-done/taken aura modifiers and script hooks, before armor and hit-outcome adjustment. Parry/dodge can preserve nonzero raw while producing zero health damage; the damage notifier hardcodes absorbed_amount to zero. These 17 events cannot be labelled full absorbs or counted as the complete attempt stream. WCL's [damage-event documentation](https://de.warcraftlogs.com/scripting-api-docs/warcraft/interfaces/RpgLogs.DamageEvent.html) separates unmitigated damage from mitigation that includes armor, block and damage reductions. Do not equate the two raw fields. The exact next observation is the same swing's weapon roll, post-done/taken value, effective armor, hit outcome, block, resist, absorb and final health damage, plus active relevant modifiers and loaded template/rank/AP inputs. Use normal unblocked/unabsorbed events to compare calculation stages before deriving a correction. Current client combat logging can corroborate outcomes but cannot replace missing internal calculation stages.

## Phase and mechanic contract

Keep the main body 41570, damage head 42347 and Mangle head 48270 distinct. Exclude mirrored 79010 callbacks when accounting for originated damage. Separate owner fresh attacks, owner DoTs and owned pets.

| Mechanic | Supported reference / current native comparison | Required acceptance observation |
| --- | --- | --- |
| Ordinary phase | Immobile boss, tank in melee, Spit/Spew/Pillar queue. Pinned client/native base rolls agree. | Correct eligible targets, cast submissions/outcomes and damage after known defenses; include melee pressure. |
| Spew | DBM 22s prediction anchored to 77690 success with anti-spam. WCL has three ticks about 2s apart. Native 19s initial wrapper scheduling predicts damage near 23s; retained live first damage is 47.020s. | Parent start/finish, periodic effects, immunity/absorb/failure. Missing damage alone cannot prove missing cast. |
| Pillar | DBM first 30s, 32.5s repeat prediction, author allows 30-40s. Native prefers non-vehicle targets beyond 15yd. | Marker, impact, actor positions/range, summons and evasion; preserve mandatory bait ownership. |
| Parasites | Client/native77973 duration 2500ms, period 300ms and extra initial tick imply 9 uninterrupted 77969 summons of 41806. Vomit separately summons 42321. | Actual summon count, interruption and cleanup; do not confuse observed WCL actor count with summons per Pillar. |
| Mangle/Crash | DBM 90s first, 95s repeat. Historical 25H Mangles 95.558s apart; Crashes 99.595/195.151s. | Current victim captured, damage/defenses, Crash evasion and release cause. |
| Armor | Client/native 90s, -50% armor. WCL lifetime 89.992s and application at Mangle removal; native applies at the same release boundary since a5c6606d93 (boarding before). | Apply on supported gameplay release, with separate hooks/timeout/reset/death paths. Retain duration and armor readback. |
| Hooks/head | Two native pincers, both hooks on one target. Both hook auras have 3000ms client duration; guide <1s is coordination advice. Head prediction 30s, +100% damage. | Native seats, hook arrival/expiry, body/head targetability and fresh target return. Player last/first swings only bound activity. |
| Molten Tantrum | Client/native 78403 is +100% fire damage per stack, cap 10; native duration 10s. Client recovery 1500ms is not an AI recurrence. Native out-of-melee 78068 triggers 78403. | Out-of-melee cadence/refresh/expiry, return to melee and damage scaling. Ordinary kills may not exercise this. |
| Heroic adds | DBM Inferno 30s first / 35s repeat. Seven 25H construct Ignitions roughly 35.5s apart. Armageddon aura 8s, triggered below 20% in native. | Actual summons, health, threat, fire geometry, Slash and Armageddon outcomes. Its damage coefficient prevents treating it as a simple flat roll. |
| Heroic below 30% | Shadow Breath U samples fit 25H client range. Native selects two non-vehicle targets and keeps Inferno; DBM cancels the Inferno bar at the phase yell. | A longer 25H kill now supplies 56.523s of Breath without new construct Ignition, supporting cancellation of new Inferno cycles. Verify HP transition, pending launches and primary/splash targets. |

Instant spells, missiles and periodic effects may overlap. Leave incompatible due casts queued; do not introduce arbitrary random jitter or global spacing. The existing queue repair and its still-unaccepted live collision observation are recorded in [ENC-004](../../../error_ledger.md).

The [September 18 heroic kill](https://classic.warcraftlogs.com/reports/LQtcz1wpJVF9AKN8?fight=7&type=casts&hostility=1&ability=92118&view=events) has seven construct Ignitions, last at 244.487s. Breath damage runs from 256.948s through 313.471s. This is stronger evidence for ending new Inferno cycles than the earlier short final phase; it does not expose the exact 30% crossing or pending-launch behavior.

## Strategy and run acceptance

Use player-obtainable frozen gear and exact consumables. Keep the main tank in melee; maintain explicit tank/add ownership and healer preparation for Mangle. Assign Pillar bait, parasite control and two hook users before pull. During head exposure, attack the damage head and use the chosen Bloodlust/cooldown plan; on head hide, reacquire the live body independently of new parasite spawns. An optional unreachable parasite must not suspend body offense, while mandatory threat/bait obligations remain valid tasks.

Measure the same pull-to-death interval with originated hostile damage, owned pets included and 79010/friendly callbacks excluded. Report per-bot DPS/HPS, boss/add split, fresh-cast gaps, movement, target-switch latency, cooldown use, survival and head coverage. Compare with an identified matched native baseline and matched WoWSims inputs. WCL player DPS requires matching gear, buffs, role and phase coverage before drawing tuning conclusions.

Reset and completion require production checks: legitimate engage and prerequisites; wipe ejects passengers and cleans owned summons/auras; a second pull rebuilds body parts; death yields instance DONE/credit; save/load preserves progression and does not respawn the defeated boss. The current source/loader/instance implements those paths, but source presence is not live proof. Loot and achievement parity remain separately unresolved and must not silently block a bounded combat repair or qualify full content parity.

A completion watchdog ends on clear or a typed failure. Report encounter clear, requested repair and overall performance separately. Research evidence and development canaries are not automatically training data.

### Research state for the BWD 10N raid program (2026-09-27)

The 10N scoreboard already passes: label `b5-d1898555` shows WCL parity for every non-healer actor, native clears and no boss-window deaths. That result does not make the research contract `accepted`, and the contract remains `fidelity_blocked`.

On 2026-09-27 GPT-6 Astra read two 10N kills through the user's Chrome. The raw captures, with their SHA-256 hashes, are listed in the ledger `source_catalog`.

- [`MxFq7TRbvnjGY1hJ` fight 22](https://classic.warcraftlogs.com/reports/MxFq7TRbvnjGY1hJ?fight=22): 2024-10-28, before 4.4.2, kill in 2:11.
- [`Y8ajQ7dbmKMG1RZy` fight 22](https://classic.warcraftlogs.com/reports/Y8ajQ7dbmKMG1RZy?fight=22): 2025-05-15, 4.4.2 patch but after the February 20 cutoff, kill in 1:51.

What the two kills establish for 10N:

- **Parasites:** 9 per Pillar of Flame, two Pillars per kill, in both logs. This matches the client/native derivation of 9 uninterrupted summons.
- **Sweltering Armor:** applied at the same timestamp as the Mangle debuff is removed, in both logs. The native script already does the same: since a5c6606d93 (2026-09-23) it applies Armor when a living, in-combat Mangle target leaves the seat, not at boarding (source audit 2026-09-27; `tests/test_magmaw_mangle_sweltering_release.py`). Both `b5-d1898555` and round 1 ran that source, so there is nothing to repair. The scoreboard evidence does not retain aura-apply timestamps, so this rests on the source, not a live readback.
- **Boss melee:** in Y8aj, Vindication and Scarlet Fever together keep a -10% debuff on Magmaw from 0:03.4 to the kill. Its 18 reduced samples (U 109,914-153,626) bound the modifier to 15.14-16.09. Combined with MxFq7, the bounds are 15.84-16.09, so the calibrated DamageModifier 16 stands. Mangle's initial hit and periodic U agree with it.
- **Timings:** Lava Spew is three 77690 casts 2 s apart per sequence. Massive Crash begins about 8.1 s after Mangle in both kills.
- **Molten Tantrum:** none observed.

The items this section left open for 10N (hotfix cutoff, hooks, head exposure, Mangle release, credit/loot/achievement) were resolved in round 3; see the next section.

### 10N research resolved (round 3, 2026-09-30)

The contract and ledger now carry `fidelity_state_by_mode` with `10N: accepted`. 10H, 25N and 25H stay `fidelity_blocked`, and so does the contract-level state. Seven unresolved claims remain; each is scoped to the modes it still covers, and none covers 10N. The evidence is in the ledger `source_catalog`:

- `wcl_magmaw_10n_t11_20260930`: seven T11-era 10N kills (2024-10, raid item level 354.9-359.9, 131-171 s), read through GPT-6.1 Sol in the user's Chrome.
- `blizzard_cata_classic_hotfixes_20250627`: the official hotfix thread.
- `client_442_magmaw_spell_rows_20260930`: 4.4.2 client spell rows.
- `wowhead_cata_magmaw_loot_achievement_20260930`: Wowhead loot and achievement pages.

What each item now rests on:

- **Hotfix cutoff.** The official Cataclysm Classic hotfix thread runs from 2024-05-01 to 2025-06-27. Its only Magmaw entry is dated 2024-06-13: Magmaw no longer falls backwards during Impale. No section from 2024-10 onward mentions Magmaw or Blackwing Descent.
- **Timers.** Every observed time fits the native queue within cast-state delays:
  - Mangle lands at 90.2-90.8 s.
  - Massive Crash starts 8.1-8.5 s after Mangle.
  - The first Lava Spew lands at 19.8-24.7 s, and later ones repeat every 22.7-32.4 s.
  - Pillars land at about 32 s and 63-68 s.
  - After the head is covered, Spew resumes 3.6-4.4 s later and the next Pillar comes 7.7-8.5 s later.
  - Three-target Spit volleys land about 6.5 s apart.
  - No 10N kill reached a second Mangle. The 95 s repeat rests on DBM and the 25H WCL log.
- **Mangle release and Sweltering Armor.** In every kill, Mangle ends 22.6-27.5 s after it is applied, before its 30 s duration runs out. Armor is applied at the same millisecond, and the head takes damage 0.1-1.4 s later, so the impale releases the tank. The native script does the same: when Impale Self (a 6 s cast) lands, it ejects the Mangle seat and applies Armor.
- **Head window.** The head is covered about 30 s after Mangle is released, which is when the second Point of Vulnerability refresh happens. The native head window (Impale Self cast +5 s through the 30 s aura) matches the log to within about 2 s.
- **Hooks.** Both Launch Hook auras (77917/77941) last 3000 ms in the 4.4.2 client, and the native script impales when both auras are up at once. WCL logs no hook events, so hook arrival and expiry can only be checked in a live acceptance run.
- **Parasites.** Three kills show 9 parasites per Pillar. The others list fewer, but they are a lower bound: the damage-done selector only lists parasites that took damage, and WCL records no summon events.
- **Boss melee.** Two more T11 kills fall inside the DamageModifier 16 envelope.
- **Loot and achievement.** The world DB holds the 12 Wowhead N10 items. Wowhead also lists the quest item Soothsayer's Runes 71716; the DB lacks it (`known_repository_gaps`; no combat effect). Parasite Evening 5306 matches native world state 5640.

**Canonical DPS targets.** Round 3 moves to T11 gear (about 359). The seven kills above replace the 395-item-level reference for the canonical c0 shard:

- The references are in `magmaw_wcl_dps_reference_t11_v1.json`, and the cast timelines are in `magmaw_wcl_cast_timelines_t11_v1.json` (fTCjtgrnzm4HRwXP-27 plus RtPXnbZxFkpacw1h-6, eight canonical specs).
- Per-spec medians: Blood DK 17,717; Balance 20,436; Survival 27,410; Fire 23,396; Retribution 23,552; Assassination 25,288; Elemental 23,683; Demonology 20,651. Each rests on 3-7 kills.
- The legacy target, its manifest and its timelines are byte-identical, because the accepted `b5-d1898555` verdict pins their hashes.
- The c0 variant takes the new references through the roster-variant sidecar. That needs the round-3 patch requests to `scoreboard_core`, `graph_acceptance`, `scoreboard_record` and the sidecar.

**Melee on the head.** The canonical roster brings Retribution and Assassination melee, which the legacy roster never had. The ranged head hold needs a configured ranged combat range, so it never admitted melee. Instead, `ranged_formation_restore` pulled them back to the support anchor for the whole head window. Now a melee DPS whose damage target is the Exposed Head keeps normal melee closure (`MeleeHeadAttacker`, `tests/test_magmaw_melee_head_hold.py`). Hazards, hooks and Pillars still take precedence.

### Tier-11 readiness of the canonical c0 shard (round 4, 2026-10-01)

Round 3 (`blackwing_descent_10n-r03-a3864fcf6d`) never reached `bwd.magmaw.encounter`. In all four runs the Demonology warlock's Felguard cast Felstorm at the Drudge spawn during `bwd.magmaw.drudges` and hit "Exposed Head of Magmaw". The raid then wiped to Magmaw on trash. The world DB explains the reach: Magmaw 41570 has CombatReach 15 and both Exposed Heads (42347 at the fixed head position, 48270 on Magmaw) have 18.75. The Drudge home spawn is 18.9 yards from Magmaw, so any area effect around a Drudge still at its spawn reaches the head. Under T11 gear the Chainwielder kill takes 57-65 s instead of 46 s, so Felstorm is off cooldown when the Drudges are pulled.

- **Pre-pull guard** (`BotMagmawPreEncounterGuard.h`, with the world adapter `BotMagmawPreEncounterGuardUnits.h`). Until Magmaw is engaged, no bot or pet area effect may reach a living Magmaw part: Magmaw, either Exposed Head or a Pincer. The check uses the native area test (radius plus the part's combat reach) plus a 5-yard chase margin. That margin is a bot tolerance for a pet that follows its target; it is not an encounter value. Both the caster and its target count as area centres. Before the boss step, direct offense on a Magmaw part is also refused; at the boss step the designated pull tank still opens. The guard only refuses: it adds no movement, cast or aura. The r03 Felstorm positions are refused. The r02 Felstorm 35 yards out and the r02 hold point (-310.9, -63.2) are admitted, as long as the pet's target has left the spawn. Wiring it into the Felguard Felstorm gate is a coordinator patch request.
- **Bloodlust.** The T11 kills keep raid lust for the first exposed head. In `RtPXnbZxFkpacw1h` fight 6, Heroism comes at 116.069 s, after Mangle ends at 112.904 s. The matched actors' major cooldowns also hit the head: Combustion at 125.3 s, Vendetta 127.3 s, Dancing Rune Weapon 130.0 s, Metamorphosis 124.4 s. Every T11 kill lasts at least 16 s past the Mangle release. Canonical cohorts (`blackwing_descent_10n_magmaw_c<N>_diagnostic`) therefore lust on the first exposed head only. The legacy diagnostic shard keeps its pre-Mangle lead at 78.169 s, which comes from the 395-item-level Y8aj kill. The call site passes the scenario through a coordinator patch request.
- **Fight length.** The r02 c0 kills (409 gear) lasted 91.6/95.4/93.0 s and ended just after the first Mangle, so c0 has never had a head window, hook riders or a third Pillar. At T11 the references last 131-171 s, and 3 of 7 show a third parasite wave. What the longer fight exercises:
  - **Parasites:** the baiter rotation already handles wave 3.
  - **Hook riders:** the c0 riders are the Retribution Paladin and Assassination Rogue, the two lowest-GUID non-baiter DPS. Both are melee, and the melee head hold admits them.
  - **Timers and repeats:** Mangle repeat (95 s), hook lead and Crash timing are native timers and do not depend on gear.
- **Open, needs a live T11 run:**
  - Sole-BDK health through Mangle at about 190k max HP. The T11 BDK reference casts Icebound Fortitude 19.5 s into Mangle, not before it.
  - Healer mana over about 150 s with two healers (Holy Paladin and Discipline Priest; at Chimaeron in r03 the disc priest ran about 70 % dry).
  - Whether a second Mangle (about 185 s) is reached.
  - No Magmaw strategy value was changed without that evidence.

DPS parity baseline for c0: r02 means at 409 gear, against the T11 target and the T11 WCL casts per minute from the cast timelines. The r02 DPS is not comparable with the T11 targets; the cast rate carries over.

| Spec | r02 DPS | r02 cpm | T11 target | T11 WCL cpm |
| --- | ---: | ---: | ---: | ---: |
| Blood DK (gated tank) | 29,943 | 37.7 | 17,717 | 31.7 |
| Balance | 40,159 | 46.1 | 20,436 | 40.7 |
| Survival | 37,988 | 48.6 | 27,410 | 70.2 (incl. Auto Shot) |
| Fire | 37,591 | 42.2 | 23,396 | 45.0 |
| Retribution | 39,910 | 38.4 | 23,552 | 35.7 |
| Assassination | 38,060 | 23.6 | 25,288 | 33.1 |
| Elemental | 43,455 | 48.6 | 23,683 | 42.5 |
| Demonology | 31,995 | 47.6 | 20,651 | 38.9 |

The first T11 c0 label is the baseline. Compare each actor with its T11 target. Look first at the cast rates below WCL: Assassination (23.6 against 33.1 cpm, so check Mutilate and energy pooling) and Fire (42.2 against 45.0). Head-window cooldown alignment for Combustion, Vendetta, Metamorphosis and DRW belongs to the class owners.

### Fire Mage on the canonical roster (round 2, 2026-09-27)

Round 1 (`blackwing_descent_10n-r01-553da85c98`, 3 kills) put the single Fire Mage at 36.4k, 91% of WCL. On `b5-d1898555` the two Fire Mages averaged 42.5k and 46.6k. The retained kills (two b5 kills, all three r01 kills) split the 8-11k loss into two parts:

- **Combustion (class rotation, about -6.7k DPS):** Combustion 83853 dealt 431-469k per r01 kill, against 0.94-1.43M on b5. Its ticks copy the Ignite on the target, and Combustion goes out as soon as the class gate (Ignite at least 10k, plus Living Bomb and a Pyroblast DoT) passes. On b5 the Ignite at the cast was 62-69k; on r01 it was 27-30k. Hit sizes (Fireball, Pyroblast!, Living Bomb) and crit (46-47%) match, so this is Combustion timing, not gear or raid buffs. It belongs to the class owner.
- **Bait load (roster, about -4.1k DPS):** without Combustion, Fire does 35.0-37.5k on b5 and 29.1-34.0k on r01. The rotation (DPS-064) alternates the Blink bait lane between two Fire Mages, one wave each. With one Fire Mage (`single_mage`) that mage baits both waves. During a bait wave the baiter deals 18-35k (boss plus parasites), against about 37k for a non-baiting mage on b5.

The lane transition needs both a mage and a hunter baiter (`HasAssignedBaiters`, `IsArrived`), and the canonical roster has no second Blink-capable spec. Taking the Fire Mage off alternate waves therefore needs a vacant-mage-slot mode in the lane transition, plus a hook-rider list that stays stable, and a live batch. Otherwise the lowest-GUID free DPS, the Fire Mage, would become hook rider 1. Head-phase uptime does not explain the loss. Every retained kill ended 0-10 s after the first Mangle (about 90 s), before any head exposure.

### Magmaw-side prerequisite trash

- Phase 1 is intentionally Magmaw-only: entrance regroup, Chainwielder 250050, Drudges 250140/250141, then Magmaw. Omnotron Golem Sentries and Laser Strike are ordered after Magmaw.
- Repository SmartAI casts Thunderclap 79604 with a client-data radius of 15 yards. Native Rush 79630 is linked from Hate to Zero 63984 every 20 seconds and selects the farthest player within 80 yards on that Drudge's threat list. Death casts Vengeful Rage 80035 on the surviving Drudge.
- Permanent slots 1/3/4/6/7 form lane A and 2/5/8/9/10 form lane B, with tanks 1 and 2. Walkable anchors are derived from the exact native home spawns and must pass native pathfinding. Tanks take the add currently occupying their lane; non-tanks remain beyond both 15-yard Thunderclap circles; a native Rush triggers ownership re-evaluation and reseparation.
- Area damage and multidot are forbidden. A lower-health lane pauses with zero invented health tolerance; after the first death, damage waits for native Vengeful Rage. No fabricated kill-sync threshold or Rush-impact radius is accepted. The 2-yard navigation margin and arrival tolerance are bot execution tolerances, not 4.4.2 encounter values.

## Reproduce and continue

```bash
pixi run python -m tools.raid_program.encounter_research_view experiments/configs/cata_raid_encounters/blackwing_descent/magmaw_ledger_v1.json
pixi run python -m tools.raid_program.derive_encounter_health <retained-wcl-health-observations.json> --output <derived.json>
pixi run python -m tools.bot_ml.build_wowsims_reference_requests --check
pixi run python -m tools.bot_ml.run_wowsims_exact_references validate-catalog
```

Use `--key boss_melee_pressure` to inspect the new priority question. Read the [reproducible research skill](../../../../../.agents/skills/raid-encounter-research/references/reproduce-boss-research.md) for extraction and native comparison, rather than repeating broad searches.

Selected health, native inputs, melee observations and validation are retained under `artifacts/cata_raid_program/magmaw_baseline_20260912.tar.gz.dvc`. Earlier immutable archives and exact source links remain in the ledger. Full four-mode fidelity still needs the named external gaps resolved and the specified native observations executed.
