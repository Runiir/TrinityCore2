# Raid program error ledger

Updated 2026-09-23. This file holds only open items and an index of every ID.
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
| DPS-055 | Native permanent-enchant absence confirmed on d495; overlays were never implemented | All four role presets intentionally emit zero permanent enchants; native equipped-item readback agrees, including Blood78478. Earlier commits added generic plumbing and source research only, not role overlay application. | Apply native-legal enchant-only overlays from retained per-slot sources after the matched Blood/Orb canary. Preserve items/gems/reforges; validate professions and refreshed admission/readback. Runeforge remains separately unobserved. Research completion is not implementation acceptance. |
| TANK-002 | Diagnosed on base-8ee1047/bundle1; not implemented | Blood is rune-limited (Heart Strike/Death Strike rune-check rejections ~900-1,800 per kill; ~25 runes/min spent). It spends ~3.3 runes/min on Icy Touch/Plague Strike where WCL uses Outbreak (1.6/min), and has no Blood Tap or Empower Rune Weapon. | Outbreak: staged sql/custom/staged/world/2026_09_23_10_blood_outbreak_disease_upkeep.sql needs 77575 in cata_434_action_profiles.json, all_spec_targets_cata_p4_v1.json and QUALIFICATION_TUNED_ACTION_SPELL_IDS, then `dvc repro validation_provisioning_verify` and regenerated BotAdmissionIdentityGenerated.h (class_native). Blood Tap/ERW need a rune-state profile condition. Expected +1.5-2k. |
| TANK-003 | Diagnosed on fid16-8586fdd; not implemented | The pre-Mangle Bone Shield (<=6 s) and a Death Strike before the seize often fail on rune shortage/GCD, so the seized tank starts without Blood Shield or Bone Shield (kill 5 took a 92k opening hit unabsorbed). | Hold rune spenders briefly in the Mangle lead so Bone Shield and one Death Strike land before the seize (combat resolver, shared_runtime). |

### Elemental Shaman (actor 30010)

| ID | Status | Proven failure / limit | Next action |
| --- | --- | --- | --- |
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
| DPS-064 | Mapped, diagnosis pending | Fire A (30006) is the fixed parasite baiter (lowest-GUID fire mage, BotAdaptiveMagmawParasitePolicy.h:64-86) at 0.87 of WCL on r3-47cd175 vs Fire B 1.14. Kiting within 10 yd claims the GCD and cast slot; while moving only Scorch and instants are castable (Firestarter). | Split duty cost from avoidable loss (idle between waves, instant usage while kiting, Combustion/Living Bomb/Hot Streak timing) against WCL; then the smallest lawful fix. |

### Several DPS actors and references

| ID | Status | Proven failure / limit | Next action |
| --- | --- | --- | --- |
| REF-003 | Current five-spec exact 300-second measurements captured; reference comparability is separate | Survival 35394, Fire 35324, Affliction 27821, Elemental 30763, Balance 30205 DPS on `50ec676cdb`. Survival reference omits Blood Fury. Fire/Balance actually used an extra ordinary-profile potion before fixture combat use. Affliction/Elemental setup checks passed. | Preserve legitimate racials, correct reference via separately attributable control, fix calibration potion ownership. Do not weaken counters or use the legacy 85% threshold as parity. See current dummy table in magmaw_dps_baseline_20260913.md. |
| OBS-008 | Native terminal observation live exercised on9d29 | Finish-v2 retains exact cast ID/ordinal, prior state, original/terminal target, SpellCastResult and terminal source. It separates success, target death, LOS, interruption and four Fire Scorches ending UNIT_NOT_INFRONT. Cancellation owner remains unknown for interrupted Balance, Affliction and Survival casts. | Preserve the accepted observer. Route the proven Fire facing overwrite to DPS-063; obtain the native interrupt initiator before changing the other rotations. |
| DPS-065 | Diagnosed; not implemented | Balance is 0.93 on r3-47cd175 after the crash-dodge fix. A Shooting Stars instant Starsurge is rejected while moving because the movement check uses the base cast time (BotWorldPopulationMgrCombatResolver.cpp ~352-356); moving Moonfire/Sunfire filler is staged (sql/custom/staged/world/2026_09_23_20_balance_moving_moonfire.sql, ~+0.4k). | Use the effective cast time in the moving check; promote the moving filler with a batch. |

### Healers

| ID | Status | Proven failure / limit | Next action |
| --- | --- | --- | --- |
| HEAL-001 | Holy Paladin profile incomplete; bounded repair pending | Actor30004 learned Beacon53563, Aura Mastery31821, Divine Plea54428 and Light of Dawn85222, but its loaded six-action profile contains none of them and no Holy Power spender. | Define one native capability repair using existing tank assignments and normal resource gates. Keep observed zero deaths separate from complete healer behavior. |
| OBS-006 | Discipline shield outcome missing from healing totals | Actor30005 successfully casts Power Word: Shield26 times across ten players, but the full export has no spell17 healing rows and no recorded absorbed_amount. | Trace native absorbed damage into attributed healer outcomes before ranking Discipline by reported HPS; successful shield casts alone do not prove absorption amount. |
| HEAL-002 | Diagnosed on fid16-8586fdd and bundle2; not implemented | The Discipline Priest (30005) casts nothing for 3-16 s around every Mangle: mangle_midpoint_stage (Survival priority, BotAdaptiveMagmawStrategyHazard.h) re-triggers whenever it is >4 yd from the stage point, and a moving healer may only cast instants (Prayer of Mending on cooldown, Power Word: Shield blocked by Weakened Soul). In fid16 kill 5 the seized tank got 0 priest healing and died. | Skip the stage move for a non-baiter already within 35 yd of the Mangled tank; optionally Pain Suppression (33206) on the seized tank if talented; add adaptive_heal_resolve/adaptive_heal_cast to the boss aggregates so failed heals are visible. |

### Encounter, route and recovery

| ID | Status | Proven failure / limit | Next action |
| --- | --- | --- | --- |
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
| DPS-064 | open | Fire Mages | Mapped, diagnosis pending |  |
| DPS-065 | open | Several DPS actors and references | Diagnosed; not implemented |  |
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
| HEAL-002 | open | Healers | Diagnosed; not implemented |  |
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
| TANK-002 | open | Blood Death Knight tank | Diagnosed; not implemented |  |
| TANK-003 | open | Blood Death Knight tank | Diagnosed; not implemented |  |
| TEST-001 | archive |  | Test-only repair independently accepted |  |
