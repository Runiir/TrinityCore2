# Raid program error ledger

Updated 2026-09-24. This file holds only open items and an index of every ID.
Closed rows, closed details, the calibration run index, process lessons and
dated notes moved verbatim to [archive/error_ledger_closed.md](archive/error_ledger_closed.md).
IDs are stable. Current per-actor DPS comes from `scoreboard show` and
`scoreboard verdict`, not from these rows; the tuning loop is in
`.agents/skills/raid-tuning-playbook/SKILL.md`.

An item is open while its own finding still needs implementation, review, a
live check or diagnosis. Overall WCL parity is tracked by the scoreboard, not
by keeping rows open. When an item closes, move its row verbatim to the
archive and update its index line.

## Updating and using the ledger

1. Before dispatch or retry, select an existing ID or add one evidenced failure.
   Include that ID, current evidence, rejected approaches, owned callers and the
   acceptance condition in the worker packet. Do not send the entire history.
2. Update the same entry after diagnosis, implementation, review, build and live
   result. These are separate states. A repair with no live outcome stays pending.
3. Record every subsequent attempt as source/run ID plus what changed and its
   outcome. No new run solely because a worker finished or metadata is stale.
4. Count only attempts that reach the same causal edge. Historic counts before
   this ledger are not reconstructed or invented. At ten occurrences, stop
   unchanged retries and write the causal summary against this ID.
5. Keep large traces in DVC. Link the archive and member when published; remove
   obsolete local payload references after verified eviction. A ledger edit
   needs no extra approval, build or live experiment.

## Open items

### Blood Death Knight tank (actor 30002)

| ID | Status | Proven failure / limit | Next action |
| --- | --- | --- | --- |
| TANK-001 | Event-local Blood priority inversion proven on d495; survived current boss | 15 Heart Strikes selected while Death Strike was valid and higher-scored; three at 63–76% health. DS bucket2 loses before score comparison to HS bucket1. Current healing coverage avoids the prior death. | Forward DS49998 bucket2 to1 for the Blood tank profile; replay actual comparator and preserve HS when DS lacks runes. IBF trash expenditure and native enchant readback are separate. Measure actual next-run healing, DPS and rune flow. |
| DPS-026 | Still blocked in shard89, the 241k clear | Source4b24 DK is actual MT, 17,075.296 DPS, 19 DS and20 RS, but zero HS/DRW. Both actions are enabled and learned. | Shard89: Blood30002 12,567.827 elapsed DPS; no landed55050, 46 declarative-area-semantics and47 future-encounter-splash rejections. Same previously proven edge. Actual20/20 execution masks reject HS cleave with forbid_area=true; passive range previews overwrite the last mask with a false appearance of selection. Native cooldown and total-rune hypotheses rejected. Keep existing encounter protection until a safe replacement is reviewed; batch with multi-class findings. |
| DPS-058 | Native AP same-effect grouping omits melee category | Group1126 infers one type from tied166/167 counts; historical53138+19506 melee AP multiplied twice. | Repair aura-type grouping with exact double20% counterexample and unrelated-group controls. Current single-source Blood needs no compensating Might. |
| DPS-055 | Armor overlay landed (3697fb434c); Blood runeforge added 2026-09-24 (f52d106673); live readback pending | The eight armor enchants apply through cata_blood_permanent_enchant_overlays_v1.json. The weapon slot was excluded until f52d106673 added slot 15 enchant 3368 (what runeforge spell 53344 writes; skill 776 is profession-exempt). The live spell_enchant_proc_data row for 3368 is 1 PPM while pinned WoWSims uses 2.0; no character has skill 776, which does not block the proc. | Confirm enchant 3368 and Unholy Strength (53365) procs in the bundle-03 kills; then settle the 3368 PPM from 4.3.4 evidence before crediting the full +0.6-0.9k. |
| TANK-002 | Bundle 03 measured on b3-0dbce440: 20851->24013 (+3163, t=5.28, ratio 0.92); batch not kept (Mangle death in k1, see TANK-003/HEAL-003); source kept for re-measurement with the survival fixes | Blood is rune-limited (Heart Strike/Death Strike rune-check rejections ~900-1,800 per kill; ~25 runes/min spent). It spends ~3.3 runes/min on Icy Touch/Plague Strike where WCL uses Outbreak (1.6/min), and has no Blood Tap or Empower Rune Weapon. | outbreak-ee8547e vs r3-47cd175 (3 kills each side): actor 30002 17714->19621 (+1907, t=1.45 < t95=2.68), party 263442->276804 (+13362, t=2.72 < t95=3.48); both within noise, `scoreboard show` printed revert, so the migration was un-promoted back to sql/custom/staged/world/ and the DB rows read back to their prior state. Ratio to WCL still 0.75. Outbreak alone is a real but too-small effect at n=3; re-measure at `--kills 5` before retrying alone, or bundle it with Blood Tap/ERW (still needs a rune-state profile condition) so the combined effect clears noise. Expected +1.5-2k for the full TANK-002 bundle. b2-fd4ba456 vs r3-47cd175 (5 vs 4 kills): 30002 17714->20851 (+3137, t=2.55, det95 3508), party +12206 improved; kept (`--min-kills 4`, baseline predates kills_per_batch). Smoke evidence: Outbreak 4, Blood Tap 4, ERW 1, Icy Touch/Plague Strike 0, Death Strike 14 (WCL 18), DS ready_rune_gate rejections 1,521, Heart Strike rejections 1,040: still rune-starved. Blood Boil (48721) is rejected by the shared area protection (declarative_area_damage_forbidden 993/kill; `ResolveScopedEncounterAreaSpellId` allows one spell per spec and only Magmaw/head targets): Diagnosis on b2 k4 (2026-09-24): casts/min 37.9 vs WCL 36.2 and runes/min 27.6 vs 27.5-29, so the gap is per-cast damage, not cadence: wrong glyphs (Anti-Magic Shell/Obliterate/Raise Dead instead of Heart Strike +30%, Rune Strike crit, Death Strike; ~+2.0k), Dancing Rune Weapon copies at ~6% instead of 50% because the Rune Weapon guardian never got its scaling auras 51906/61697/110474 (~+1.0-1.3k), Glyph of Death Strike 59336 unhandled (~+0.5-0.9k), no Fallen Crusader runeforge (~+0.6-0.9k at 2 PPM). Blood Boil on parasites is worth <=0.4k (no parasite within 10 yd of the tank) and is not pursued. Setup parity f52d106673 + bundle 03 e2e0e2ce40 implement all four; measured next. Reviewer notes: the Rune Weapon crits ~5 points above the owner (creature base 5% on top of 110474); AP-scaled copy parts and expertise still under-scale. |
| TANK-003 | Recurred on b3-0dbce440-k1 (tank death); implementation in bundle 04 | The pre-Mangle Bone Shield (<=6 s) and a Death Strike before the seize often fail on rune shortage/GCD, so the seized tank starts without Blood Shield or Bone Shield (fid16 kill 5 took a 92k opening hit unabsorbed). b3 k1: the tank met Mangle at 46% with Vampiric Blood spent at 50.2 s (health trigger) and Icebound Fortitude at 60.3 s (35% emergency release) while two healers were stranded (HEAL-003); in the 6 s lead it cast Heart Strike x2 and Rune Strike with Death Strike rune-gated; the Mangle hit was 86.5k vs 37k in b2 k4 where IBF and Bone Shield were up. | Bundle 04: plan the tank's cooldowns around the next Mangle (keep IBF for it, spend Vampiric Blood/Rune Tap in emergencies when Mangle is near; cast VB at the pre-cast if IBF is on cooldown), hold Heart Strike/Rune Strike in the lead until a Death Strike lands and Bone Shield is refreshed, add a Rune Tap row. |

### Elemental Shaman (actor 30010)

| ID | Status | Proven failure / limit | Next action |
| --- | --- | --- | --- |
| DPS-066 | Elemental fell from 1.02 (r3-47cd175) to 0.941 (b2-fd4ba456); within noise (t=-2.40, t95 2.53) but consistent per kill | 30010 per kill: r3 counted 39.5/45.2/42.8/43.8k vs b2 41.8/40.4/38.6/38.6/37.5k, both crash sides. Bundle 02 touched no Elemental row, but the shared moving-cast change now lets an effective-instant cast proceed while moving instead of stopping the bot (StopUncoveredMovingCast), which can delay the next hardcast Lightning Bolt. Casts/min 48.8 vs WCL 51.7 in b2 k5. | Diagnosed 2026-09-24 on r3 k1/k3 vs b2 k1/k4/k5: RNG. Hardcasts/min identical (35.1 vs 35.1), non-proc DPS flat (27.0k vs 26.7k); 92% of the -2.9k gap is proc damage (Dragonwrath copies 440k in r3 k3 vs 75-278k in b2, Lava Burst overloads, Fulmination). HasEffectiveCastTime cannot change any Elemental decision (only Elemental Mastery carries a -100% cast-time modifier and it is never cast). Re-measure on the next batch; close if it recovers. Pre-existing side issue: parasite line-of-sight failures (b2 k1 lost ~14 s at 46.8-48.0 s). |
| DPS-037 | Elemental close-range Lightning Bolt eligibility rejected on 41266; repair queued | At pull+39.844s actor30010 is stationary, not casting, and has no legal candidate. LB403 fails only configured min_range12; bound native SpellRange4 has minimum0. Eleven unique retained evaluations repeat this restriction. | The same row controls preferred positioning, so do not disguise a duplicate filler via tags or silently alter formation. Separate native cast legality from positioning explicitly, or validate the deliberate positioning change. No coefficient tuning admitted. |
| DPS-038 | Elemental action minimum causes unnecessary retreat; repair in review | 0f0 actor30010 profile minimum is0, but8050/421/403/8042/51505 action minima are12 despite native DBC minima0. Retained boss trace has58 profile-range movement rows across12 native receipts, nine targeting boss/head at8-11.5yd. SWG moving casts succeed. | Remove only these five enabled Elemental action floors via tagged idempotent migration. Preserve native spell/ranged restrictions, maximum range and mechanic movement. Compare range receipts, cast activity, survival and DPS on matched route. activity-review.json under trinity-magmaw-activity-20260912; evidence publication pending. |
| DPS-054 | Optional steady earth slot committed e3f78b4501; reviewed, not live | Three routine Tremor casts waste globals; this small issue does not explain the Elemental gap. | Prioritize Lightning Bolt cadence and guardian action mix. Reactive group Tremor remains unimplemented in bot policy. |
| PET-001 | Elemental repair partially exercised on d495 | No targeted reciprocal attack before boss death; one friendly Fire Nova532 remains. Reciprocal pet melee starts after death and is excluded from DPS. Legal Fire Shield has no landed observation. | Native Totem15439 lacks base owner GUID while retaining its Minion owner pointer; guarded Guardian15438 fallback is implemented for review. Fixture now executes production accessor chain. Post-clear lifecycle remains unaccepted. No unconditional raid ban or coefficient change. |

### Affliction Warlock (actor 30008)

| ID | Status | Proven failure / limit | Next action |
| --- | --- | --- | --- |
| DPS-056 | Purpose-aware Bane exclusion committed7644762147; reviewed, not live | Optional parasite Bane replaces body Bane; global lock would break mandatory target changes. | Validate exact optional-purpose exclusion when next material canary is selected; do not claim all Affliction loss is fixed. |
| DPS-039 | Moving Affliction fallback built; end-to-end review pending | 0f0 actor30008 has six moving/no-current-cast no-valid attempts. Existing77799 is known but gated by profile aura89937 before native readiness checks. Native77799 is instant,0-40yd,6%base-mana,ordinaryGCD and no own cooldown; the proc is not a cast requirement. | Add a separate moving-only last-priority77799 row. Preserve stationary proc ordering and native mana/GCD/target gates; do not assume all six attempts would have cast. Live acceptance needs moving non-proc submissions/finishes and observed damage, mana and stationary behavior. No speculative proc pooling. |
| DPS-029 | Affliction Shadowflame area restriction proven on a152 | Actor30008 has zero Shadowflame submissions; all191 corrected a152 boss masks reject declarative_area_damage_semantics_forbidden. | Join with DPS-026 shared area protection. Admit only a reviewed action-aware safety repair; do not clear protections globally or tune coefficients. |

### Fire Mages (actors 30006, 30007)

| ID | Status | Proven failure / limit | Next action |
| --- | --- | --- | --- |
| DPS-044 | Retained evidence; causal diagnosis pending | On ee0504, Mage30006 has a19.138s fresh-direct-attack gap and Hunter a14.910s gap. Their DPS is15.02%/4.68% below26 despite legal fixed-baiter native offense. | Join exact gap endpoints to submissions/finishes, movement and candidate eligibility. DoTs/pets are not fresh casts, but direct-effect gaps are not automatically idle time. No superior eligible AoE bypass or coefficient defect is proven. Use retained ee0504 evidence before another live run. |
| DPS-064 | Range cap fixed on b2-fd4ba456: Fire A 0.99 (pass) | Fire A (30006) is the fixed parasite baiter (lowest-GUID fire mage, BotAdaptiveMagmawParasitePolicy.h:64-86) at 0.87 of WCL on r3-47cd175 vs Fire B 1.14. Kiting within 10 yd claims the GCD and cast slot; while moving only Scorch and instants are castable (Firestarter). | Split duty cost from avoidable loss (idle between waves, instant usage while kiting, Combustion/Living Bomb/Hot Streak timing) against WCL; then the smallest lawful fix. Diagnosed on r3 k4: the baiter idles at the lane anchor 35.043 yd from Magmaw while Pyroblast! 92315, Flame Orb 82731 and Scorch 2948 rows carried a stale 35 yd max_range (native 40 yd), so every Hot Streak was wasted and the Combustion gate never saw a Pyroblast DoT (30006 lost 1.65M of a 1.96M gap on those three abilities; duty cost itself ~5.9k DPS). 2026_09_23_60_fire_hot_streak_native_range.sql raised the rows to 40 yd: b2-fd4ba456 30006 34838->39923 (+5085), ratio 0.99, kept. Baiter alternation was not needed. |

### Several DPS actors and references

| ID | Status | Proven failure / limit | Next action |
| --- | --- | --- | --- |
| REF-003 | Current five-spec exact 300-second measurements captured; reference comparability is separate | Survival 35394, Fire 35324, Affliction 27821, Elemental 30763, Balance 30205 DPS on `50ec676cdb`. Survival reference omits Blood Fury. Fire/Balance actually used an extra ordinary-profile potion before fixture combat use. Affliction/Elemental setup checks passed. | Preserve legitimate racials, correct reference via separately attributable control, fix calibration potion ownership. Do not weaken counters or use the legacy 85% threshold as parity. See current dummy table in magmaw_dps_baseline_20260913.md. |
| OBS-008 | Native terminal observation live exercised on9d29 | Finish-v2 retains exact cast ID/ordinal, prior state, original/terminal target, SpellCastResult and terminal source. It separates success, target death, LOS, interruption and four Fire Scorches ending UNIT_NOT_INFRONT. Cancellation owner remains unknown for interrupted Balance, Affliction and Survival casts. | Preserve the accepted observer. Route the proven Fire facing overwrite to DPS-063; obtain the native interrupt initiator before changing the other rotations. |
| DPS-065 | Bundle 03 measured on b3-0dbce440: Balance 39095 (0.953 of WCL, within noise of b2; passes on DPS once the encounter passes) | Balance is 0.93 on r3-47cd175 after the crash-dodge fix. A Shooting Stars instant Starsurge is rejected while moving because the movement check uses the base cast time (BotWorldPopulationMgrCombatResolver.cpp ~352-356); moving Moonfire/Sunfire filler is staged (sql/custom/staged/world/2026_09_23_20_balance_moving_moonfire.sql, ~+0.4k). | Done in b2-fd4ba456 (BotCastWhileMoving::HasEffectiveCastTime in the resolver, the protected-movement yield and the executor stop; 2026_09_23_20_balance_moving_moonfire.sql promoted): 30001 38151->38690 (+539, within noise), ratio 0.943. Smoke evidence: moving Moonfire row cast 6x, at least one moving Starsurge, 6 movement_requires_instant_action rejections on Starsurge remain (Shooting Stars state not observable in the archive), the moving Sunfire row never fired (bot not moving 1,522x). Diagnosis on b2 k4/k5 (2026-09-24): Inkar's real cast rate is 45.5/min (the 48.2 counted Eclipse/Berserking rows), matching the bot; clean stationary stretches run 45.5-47.6k (1.11-1.16x WCL); the whole gap sits in the parasite windows (4.7-7.1k): switching to a threatening parasite without line of sight (8-11 failed casts per kill, each a 5 s spell block plus a walk toward it), mushroom sets fired on 1-2 parasites (4 GCDs for 24k), Moonfire recast over a live Sunfire (2 GCDs). Bundle 03 e2e0e2ce40 gates the switch on the native LOS opportunity set, requires 3 parasite hits within the 6 yd radius of 78777 (wave-ending exception), and forbids Moonfire over Sunfire (row 2540). Reviewer notes: a non-baiter Fire mage with a threatening parasite inside its 9 yd profile minimum now stays on Magmaw briefly; a full mushroom set whose hits drop to 0 mid-wave is held until a later wave. Smoke-0dbce440 evidence: parasite LOS failures 4 (was 8-11), no 1-2-hit detonations (one 6-hit detonation; two wave-2 sets never detonated), 0 Moonfire casts over Sunfire (841 forbidden_target_aura_active rejections), but Moonfire was recast over its own live Moonfire while moving (85.0/86.0 s). |

### Healers

| ID | Status | Proven failure / limit | Next action |
| --- | --- | --- | --- |
| HEAL-001 | Holy Paladin profile incomplete; bounded repair pending | Actor30004 learned Beacon53563, Aura Mastery31821, Divine Plea54428 and Light of Dawn85222, but its loaded six-action profile contains none of them and no Holy Power spender. | Define one native capability repair using existing tank assignments and normal resource gates. Keep observed zero deaths separate from complete healer behavior. |
| OBS-006 | Discipline shield outcome missing from healing totals | Actor30005 successfully casts Power Word: Shield26 times across ten players, but the full export has no spell17 healing rows and no recorded absorbed_amount. | Trace native absorbed damage into attributed healer outcomes before ranking Discipline by reported HPS; successful shield casts alone do not prove absorption amount. |
| HEAL-002 | Recurred on b3-0dbce440-k1; implementation in bundle 04 | The Discipline Priest (30005) casts nothing for 3-16 s around every Mangle: mangle_midpoint_stage (Survival priority, BotAdaptiveMagmawStrategyHazard.h) re-triggers whenever it is >4 yd from the stage point, and a moving healer may only cast instants (Prayer of Mending on cooldown, Power Word: Shield blocked by Weakened Soul). In fid16 kill 5 the seized tank got 0 priest healing and died. | Skip the stage move for a non-baiter already within 35 yd of the Mangled tank; optionally Pain Suppression (33206) on the seized tank if talented; add adaptive_heal_resolve/adaptive_heal_cast to the boss aggregates so failed heals are visible. |

### Encounter, route and recovery

| ID | Status | Proven failure / limit | Next action |
| --- | --- | --- | --- |
| HEAL-003 | Ranged strand found on b3-0dbce440-k1; diagnosis/implementation in bundle 04 | At 43.6-43.8 s six ranged bots had moves rejected (route_destination_endpoint_mismatch); the priest 30005, druid 30003, warlock 30008 and shaman 30010 moved ~16 yd north and stood at (-308.5, -20.6), 2.7 yd below the platform, until ~88 s, retrying paths that failed path_control_level_gap (24 and 30 events); the healers only buffed each other (no LOS to the tank): priest silent 60.0-98.4 s, druid ~57-90.9 s, shaman 53.4-90.9 s. The tank fell to 32%, spent both cooldowns, and died to the next Mangle. Both healers had 3 parasite escapes that kill (1 in b2 k4), so the contact-escape destination is the suspected trigger; the paladin logged 11 similar path failures in b2 k2. | Validate escape/stage destinations against the platform and a walkable return path before issuing them; after repeated return-path failures fall back to the nearest reachable ranged anchor instead of retrying for tens of seconds. |
| ENC-001 | Drudge survival recurred on 36f8 before boss research | Firehook30007 and Aff30008 die to overlapping Drudge79974/79604 on a152. The>=18yd safety check fails, movement requests the same reached anchor, then ContinuePackCombat permits combat despite tactical safety failure. | Retained 36f8 timeline shows fire mage 30007 escape unavailable, movement deferred by resource conflict, then 196,483 damage / 38,908 healing before death. This does not prove the melee observation patch caused it. Both a4b9 and 36f8 contain the same mage escape delay (~14.6s) and death. The paired route action itself claims movement. Baseline raw has four trash deaths then recovery; its final zero counters reset scope and cannot establish trash survival. Diagnose the later candidate-only full wipe. Boss-only staging is held; it cannot validate trash recovery. Preserve native pathing and tolerances. See magmaw_melee_resolution_20260912 DVC review. |
| REC-001 | Explicit entrance repaired; live full-wipe coverage pending | 36f8 physically recovered all ten bots but admission entrance 0/0/0 prevented runback/re-entry/resurrection receipt advancement. Source 0f0a8c0382 declares verified (6581,0,669) on all seven BWD scenarios. Production tracker fixture and independent review pass. Live admission matches; one trash casualty recovers in 122.493s and original route clears at 189,706.381 DPS, but no full wipe occurred. | Preserve actual progress checks. A recovered trash wipe is acceptable; native_recovery_accepted with required=false is not a recovery observation. Observe the next natural full wipe rather than claiming unexercised acceptance. Corrected prior evidence and new run: magmaw_native_wipe_recovery_20260912 DVC archive, prior-run-correction/recovery-stall.json. |
| DPS-023 | User-observed head-return outage; causal diagnosis active | Manual spectator run on 21c survives beyond exposed head; user reports damage targets recover only after the next Pillar/add switch. Earlier accepted kill ended during head exposure and did not cover this return transition. | Retained evidence proves damage outage but not its internal cause. Fixed-size target/native-stat observation independently approved; one-second capture4b24 is valid but UNEXERCISED because kill ends during first head. The a152 head return passes with 195/195 valid post-return DPS targets and native body damage. This is run-specific acceptance; no targeted repair or universal claim. Preserve the prior intermittent occurrence; no unchanged retry. |
| ENC-007 | Open fidelity work | Only Magmaw 10N (41570) is calibrated. 25N/10H/25H (51101-51103), Lava Parasites (41806/42321), the heroic Blazing Bone Construct (49416) and the route trash (Drudge 42362, Chainwielder 42649) still have DamageModifier 1 from the upstream reset. | Calibrate each from matched WCL damage stages (method in the 41570 migration header), stage the migration, record it in the fidelity registry. |
| ENC-008 | Low; not implemented | The crash-side footprint adds the active crash dummy (47330) to its hull only when observed, but the encounter blackboard never publishes 47330, so the cone tip relies on Magmaw's position. | Publish 47330 with facing during bwd.magmaw.encounter in BotWorldPopulationMgrEncounterBlackboard.cpp. |

### Dummy calibration only (not on the raid tuning path)

| ID | Status | Proven failure / limit | Next action |
| --- | --- | --- | --- |
| PERF-001 | Independently approved; next controller validation pending | Isolated calibration was waiting for ordinary bots, although native calibration owns a separate population. | Skip that ordinary readiness wait only for calibration startup; 47 focused and four existing watchdog tests pass. Do not claim measured 180-second speedup. |
| PERF-002 | Independently approved; live pending | Affliction waits for pet resources during warmup before a final reset that can recover its persistent mana pet natively. | Review bounded self-provided summon bypass; preserve Hunter/Ghoul waits and final exact resource checks. |
| SETUP-001 | Independently approved; live pending | First scored reset erases warmup flask/food receipts while their auras persist, causing a second native use (20 restocked, final receipt 19 to 18). | Preserve current-attempt flask/food receipt state across self-provided reset; test pending and completed native use without preserving scored metrics or potion receipts. |
| DPS-021 | Sequencing mismatch proven; repair not yet admitted | Hunter5c selects Readiness before Chimera and submits Rapid Fire three times versus four exact. | Preserve accepted DPS-016 health gate. Determine whether an existing prerequisite can express the reference sequence; a spell merely being on cooldown may not prove the intended ordering. Do not expand DPS-019 into a new policy framework. |

## Index of every ID

Status is the row's own status text. "Open" rows are above; "archive" rows are in
[archive/error_ledger_closed.md](archive/error_ledger_closed.md).

| ID | Where | Area | Status | Later note |
| --- | --- | --- | --- | --- |
| BUILD-001 | archive |  | Closed blocker |  |
| BUILD-002 | archive |  | Recurred on 3e; unchanged retry succeeded |  |
| CAL-001 | archive |  | Native concurrent dummy lifecycle repaired and live exercised on `50ec676cdb` |  |
| CAP-001 | archive |  | Closed blocker |  |
| CAP-002 | archive |  | Closed blocker | Details section in archive. |
| CAP-003 | archive |  | Live accepted on 90a181db01 | Details section in archive. |
| CAP-004 | archive |  | Independently live accepted on Magmaw21c |  |
| CAP-005 | archive |  | Immutable timeline and native pressure retention accepted |  |
| CAP-006 | archive |  | False failure streak repaired and native accepted on b113 |  |
| COMP-001 | archive |  | Declared one-tank composition accepted on89cef |  |
| DPS-001 | archive |  | Closed blocker |  |
| DPS-002 | archive |  | Closed blocker |  |
| DPS-003 | archive |  | Closed blocker |  |
| DPS-005 | archive |  | Closed blocker |  |
| DPS-006 | archive |  | Straight trajectory live accepted | Details section in archive. |
| DPS-007 | archive |  | Native admission identity accepted on Hunter927 | Details section in archive. |
| DPS-008 | archive |  | Affliction and Fire setup live accepted | Details section in archive. |
| DPS-009 | archive |  | Live accepted on 90a181db01 | Details section in archive. |
| DPS-010 | archive |  | Native stat application accepted on Hunter927 | Details section in archive. |
| DPS-011 | archive |  | Native sockets and reference metadata accepted on Hunter927 | Details section in archive. |
| DPS-012 | archive |  | Independently approved; retained Fire replay passes |  |
| DPS-013 | archive |  | Live launch accepted on 92787b59c4 |  |
| DPS-014 | archive |  | Independently approved; cold retained replay passes |  |
| DPS-015 | archive |  | Live accepted on Hunter3e |  |
| DPS-016 | archive |  | Health gate live accepted on Hunter3e |  |
| DPS-017 | archive |  | Runtime compatibility live accepted on Hunter3e |  |
| DPS-018 | archive |  | Owner buff independently live accepted on Hunter5c |  |
| DPS-019 | archive |  | Native override execution live accepted on e562 |  |
| DPS-020 | archive |  | Independently live accepted on c87 |  |
| DPS-021 | open | Dummy calibration only | Sequencing mismatch proven; repair not yet admitted | Marksmanship Hunter; the Magmaw roster now uses Survival. |
| DPS-022 | archive |  | Independently live accepted on Hunter9ed |  |
| DPS-023 | open | Encounter, route and recovery | User-observed head-return outage; causal diagnosis active |  |
| DPS-024 | archive |  | DS/RS cadence repaired live on4b24; HS/DRW remain DPS-026 |  |
| DPS-025 | archive |  | Native Vengeance repaired; self-owned AP observed on4b24 |  |
| DPS-026 | open | Blood Death Knight tank | Still blocked in shard89, the 241k clear | Later: Heart Strike normal path accepted on 73103e8646 (25 submissions, 677,680 damage); Dancing Rune Weapon not re-reported. See archive, Scoped repairs measured, 2026-09-19. |
| DPS-027 | archive |  | Marksmanship aura and filler accepted live on a152 |  |
| DPS-028 | archive |  | Elemental movement cooldown accepted live on a152 |  |
| DPS-029 | open | Affliction Warlock | Affliction Shadowflame area restriction proven on a152 | Later scoped area admission covered Heart Strike (archive, Restart baseline closed); Shadowflame not re-reported. |
| DPS-030 | archive |  | Affliction combat potion native cast observed on a152; timing issue DPS-032 |  |
| DPS-031 | archive |  | Rejected maintenance-priority hypothesis; no implementation |  |
| DPS-032 | archive |  | Boss-health potion gate accepted live on ff34 |  |
| DPS-033 | archive |  | Moving Scorch candidate reaches submission on 41266; native completion blocked by DPS-036 |  |
| DPS-034 | archive |  | Rejected immediate DK handback hypothesis; no implementation |  |
| DPS-035 | archive |  | Corrective FLOAT migration installed and read back on 41266 |  |
| DPS-036 | archive |  | Early hazard cancellation repair accepted on6882; terminal Scorch gap is OBS-008 |  |
| DPS-037 | open | Elemental Shaman | Elemental close-range Lightning Bolt eligibility rejected on 41266; repair queued |  |
| DPS-038 | open | Elemental Shaman | Elemental action minimum causes unnecessary retreat; repair in review |  |
| DPS-039 | open | Affliction Warlock | Moving Affliction fallback built; end-to-end review pending |  |
| DPS-040 | archive |  | Rejected directional mobility changed facing; repair accepted |  |
| DPS-041 | archive |  | Independent review and native ordering repair accepted on433; throughput unresolved |  |
| DPS-042 | archive |  | Shared range repair independently reviewed and native accepted on26; exact Balance under5 native-success coverage absent |  |
| DPS-043 | archive |  | Independently reviewed and native accepted on ee0504 |  |
| DPS-044 | open | Fire Mages | Retained evidence; causal diagnosis pending | Fire 30006 gap continues under DPS-064 (DPS-062 closed). |
| DPS-045 | archive |  | Survival swap native accepted; broader role gaps remain |  |
| DPS-046 | archive |  | Accepted native Survival shot/ST admission repair |  |
| DPS-047 | archive |  | Accepted narrow native trap removal on05f |  |
| DPS-048 | archive |  | Survival AoE exercised on d495; Horn healthy |  |
| DPS-049 | archive |  | Admission accepted on63d; native behavior repaired under DPS-053 ondb67 |  |
| DPS-050 | archive |  | Missing AP hypothesis rejected; historical MM overstacking proven |  |
| DPS-051 | archive |  | Native admission accepted on779 |  |
| DPS-052 | archive |  | Both actors load40; exact35–40yd branch unexercised |  |
| DPS-053 | archive |  | Native caster repair accepted ondb67 |  |
| DPS-054 | open | Elemental Shaman | Optional steady earth slot committed e3f78b4501; reviewed, not live |  |
| DPS-055 | open | Blood Death Knight tank | Native permanent-enchant absence confirmed on d495; overlays were never implemented |  |
| DPS-056 | open | Affliction Warlock | Purpose-aware Bane exclusion committed7644762147; reviewed, not live | Later: 73103e8646 made zero parasite Bane of Doom submissions (archive, Scoped repairs measured); a live check may close this. |
| DPS-057 | archive |  | Native Combustion accepted for30007 ona3a; overall Fire open |  |
| DPS-058 | open | Blood Death Knight tank | Native AP same-effect grouping omits melee category |  |
| DPS-059 | archive |  | Cross-roster comparison previously prioritized small defects without duty-adjusted impact |  |
| DPS-060 | archive |  | Magmaw WCL denominator contract corrected; parity remains open |  |
| DPS-061 | archive |  | Magmaw WCL denominator was still vulnerable to post-kill telemetry tails; measurement repair committed on `d49921c96f` |  |
| DPS-062 | archive |  | Closed 2026-09-23: superseded by the scoreboard |  |
| DPS-063 | archive |  | Moving-cast facing accepted on d495 |  |
| DPS-064 | open | Fire Mages | Fire A 0.99 on b2-fd4ba456, 0.90 on b3-0dbce440 (sd 6.6k; k1 strand); confirm on the next clean batch |  |
| DPS-065 | open | Several DPS actors and references | Effective cast time + moving Moonfire kept on b2-fd4ba456; Balance 0.943 |  |
| DPS-066 | open | Elemental Shaman | 0.93 again on b3-0dbce440 (k1 29.6k: stranded 53-91 s, HEAL-003); non-proc DPS flat at ~27k |  |
| ENC-001 | open | Encounter, route and recovery | Drudge survival recurred on 36f8 before boss research |  |
| ENC-002 | archive |  | Native two-way swap accepted on6882 |  |
| ENC-003 | archive |  | Actor-specific optional support admission implemented; exercised live on b113 |  |
| ENC-004 | archive |  | Native queue repair reviewed; fixture and 150.254s live clear passed; live collision attribution and overall performance remain unaccepted |  |
| ENC-005 | archive |  | Closed 2026-09-23: Sweltering Armor at Mangle release |  |
| ENC-006 | archive |  | Closed 2026-09-23: DamageModifier 16 calibrated |  |
| ENC-007 | open | Encounter, route and recovery | Open fidelity work |  |
| ENC-008 | open | Encounter, route and recovery | Low; not implemented |  |
| FLOW-001 | archive |  | Fresh-entry read-only trial passed; no new native acceptance |  |
| FLOW-002 | archive |  | Workflow admission repaired; native performance unchanged/unmeasured |  |
| FLOW-003 | archive |  | Earlier narrow closure retained; recurring defects superseded by FLOW-005 |  |
| FLOW-004 | archive |  | Plain-request entry and first diagnostic passed; full autonomous completion unproven |  |
| FLOW-005 | archive |  | Logger repair live-observed; original missing-haste hypothesis superseded by comparator correction | Details section in archive. |
| FLOW-006 | archive |  | DPS loss accounting required before another optimization patch |  |
| FLOW-007 | archive |  | Workflow gate repair; native DPS remains open |  |
| FLOW-008 | archive |  | Bounded diagnostic and review-identity tools repaired; parent performance remains open |  |
| FLOW-009 | archive |  | Completed-run reconciliation and compact entrypoints repaired |  |
| HARN-001 | archive |  | Closed 2026-09-23: heartbeat world freeze fixed |  |
| HEAL-001 | open | Healers | Holy Paladin profile incomplete; bounded repair pending |  |
| HEAL-002 | open | Healers | Recurred on b3-0dbce440-k1; bundle 04 |  |
| HEAL-003 | open | Healers | Ranged strand 2.7 yd below the platform for ~45 s on b3-0dbce440-k1; bundle 04 |  |
| MEAS-001 | archive |  | Closed 2026-09-23: Massive Crash side recorded |  |
| MOV-001 | archive |  | Native hazard traversal accepted on779 |  |
| OBS-001 | archive |  | Observation gap; no repair admitted |  |
| OBS-002 | archive |  | Full-window observation live accepted on Hunter3e |  |
| OBS-003 | archive |  | Full-window proc observation live accepted on e562 |  |
| OBS-004 | archive |  | Preview publication repair built and exercised on a152 |  |
| OBS-005 | archive |  | False fallback reason repair built and exercised on a152 |  |
| OBS-006 | open | Healers | Discipline shield outcome missing from healing totals |  |
| OBS-007 | archive |  | General raid effective-stat observation accepted live on ff34 |  |
| OBS-008 | open | Several DPS actors and references | Native terminal observation live exercised on9d29 | Later: 18 of 20 moving Fire Scorch submissions ended unsuccessfully on 73103e8646 (archive, Scoped repairs measured). |
| OBS-009 | archive |  | Timeline incoming-damage omission repaired |  |
| OBS-010 | archive |  | Activity label and direct-activity acceptance repaired |  |
| OBS-011 | archive |  | Timeline projection repaired on067; existing native records reused |  |
| OBS-012 | archive |  | Native retention accepted on779 |  |
| PERF-001 | open | Dummy calibration only | Independently approved; next controller validation pending |  |
| PERF-002 | open | Dummy calibration only | Independently approved; live pending |  |
| PET-001 | open | Elemental Shaman | Elemental repair partially exercised on d495 |  |
| PULL-001 | archive |  | Hunter Drudge opener verified; route speed not accepted |  |
| REC-001 | open | Encounter, route and recovery | Explicit entrance repaired; live full-wipe coverage pending |  |
| REC-002 | archive |  | Partial-trash release wait repaired |  |
| REC-003 | archive |  | Finalized ghost spline waited for 30s timeout; repair accepted |  |
| REF-001 | archive |  | Independently approved; current status passes |  |
| REF-001 | archive |  | WoWSims input-check false stale result fixed |  |
| REF-002 | archive |  | Closed blocker |  |
| REF-003 | open | Several DPS actors and references | Current five-spec exact 300-second measurements captured; reference comparability is separate | Survival's missing WCL reference is the target file's no_reference status; calibration potion ownership is graph requirement potion_ownership. |
| REV-001 | archive |  | Corrected recent-event attribution on6882 |  |
| SETUP-001 | open | Dummy calibration only | Independently approved; live pending |  |
| TANK-001 | open | Blood Death Knight tank | Event-local Blood priority inversion proven on d495; survived current boss | The Death Strike priority change a283a51228 is already in the baseline (shared_worldserver_workflow_20260907.md). |
| TANK-002 | open | Blood Death Knight tank | Bundle 03 measured 0.92 on b3-0dbce440 (not kept: Mangle death k1); Rune Weapon copies ~36% of owner hits, DRW not recast at 96 s, Fallen Crusader row 1 PPM |  |
| TANK-003 | open | Blood Death Knight tank | Recurred on b3-0dbce440-k1 (tank death); bundle 04 |  |
| TEST-001 | archive |  | Test-only repair independently accepted |  |
