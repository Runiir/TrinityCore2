# Shared-worldserver workflow status

Updated 2026-09-13. This is the current status. Historical run narratives remain
in Git; failed assumptions and bounded next repairs belong in the
[error ledger](error_ledger.md). Closed generated evidence is tracked by DVC.

## Current work and latest native run

Latest source `05f5c2f959` cleared Magmaw in 130.217 seconds at
216,508.774 exact raid DPS and 11,177.634 HPS. All ten survived the boss;
one Drudge casualty recovered before the pull. Native death, capture, build
verification and cleanup passed. DPS-047's invalid remote trap removal is
accepted: zero spell13813 attempts and zero associated range-reconciliation
moves, with zero Infection78941 hits. Survival remains at 37,131.143 DPS and
lands eight head Cobra casts. DPS-046's shot admission repair is preserved.

Multi-Shot remains loaded and unchanged, but did not submit in this run.
Observed masks reject it for its owned-target aura gate, busy/GCD state or
range; no observed eligible Multi-Shot bypass is proven. Its native use is
unexercised here. The 23.789-second head window ends in boss death, so this
run cannot validate a later head-to-body return.

Raid DPS recovered from the prior Survival run's 191,627.988 and exceeds the
same-composition MM baseline's 213,253.077 by 1.53%. This is an observed
single-run recovery, not proof of stable WCL parity or every actor's correctness.
Affliction recovers 25,204→37,712 DPS; Fire recovers 20,781/24,389→28,858/27,929.
Balance and Blood remain low. Keep missing guardians, role item enchants,
parasite spell selection and shared escape/range re-entry in the review queue.
Do not change coefficients from aggregate DPS or repeat this accepted trap test.

The prior `69903f785e` run accepted DPS-046's shot repair but failed overall
performance/safety: 148.635 seconds, 191,627.988 DPS, six Infection hits on three
actors, and caster head movement/range losses. Its remotely verified archive:
`artifacts/cata_raid_program/magmaw_survival_admission_69903f785e_20260913.tar.gz.dvc`.
The current evidence pointer is
`artifacts/cata_raid_program/magmaw_survival_trap_05f5c2f959_20260913.tar.gz.dvc`.
Its 88,448,397-byte archive and every member passed fresh-cache remote
reconstruction. Exact raw/full-timeline and duplicate archive/cache payloads
were evicted; HTML, summary and frozen review remain available. Targeted DVC
status reflects deliberate local eviction; DVC push confirms the remote is current.

Earlier8146 Survival canary: clear137.163s,205,544.666DPS; native setup/duties
passed but shot admission and performance failed. Its83,391,167-byte archive
was remotely reconstructed and every member verified; exact raw/full timeline
and duplicate payloads were evicted. Pointer:
`artifacts/cata_raid_program/magmaw_survival_8146a06b40_20260913.tar.gz.dvc`.

The earlier source `ee0504cc0c` cleared Magmaw with the same sole Blood
DK, three healers and six DPS in132.205 seconds. Native death, complete capture,
post-run build verification and cleanup passed. All ten survived the full
route and boss, with zero Infection78941. First retained event to boss death
spans336.387 seconds; capture sampling spans349.064 seconds.
Independent review accepts the bounded DPS-043 targeting repair.

| Native source | Boss seconds | Exact raid DPS | Effective HPS |
| --- | ---: | ---: | ---: |
| ff226ad52b | 132.828 | 212,252.861 | 11,764.605 |
| 4337116eeb | 138.556 | 203,478.182 | 14,563.664 |
| 2af61a1cef | 131.609 | 214,218.807 | 11,647.995 |
| 26c536140a | 133.998 | 210,399.581 | 10,868.625 |
| ee0504cc0c | 132.205 | 213,253.077 | 10,279.195 |
| 8146a06b40 (Survival) | 137.163 | 205,544.666 | 12,335.433 |
| 69903f785e (Survival) | 148.635 | 191,627.988 | 12,954.445 |

The first six runs have28,193,123 originated hostile damage;699 has28,482,626,
including289,503 more add damage. The first five share
the MM composition; ee0504 is1.356% above26 and0.471% aboveff226. The Survival
run is3.615% belowee0504 and changes spec/setup. These development comparisons
are not exact WCL/WoWSims parity or proof that every class is optimized.

DPS-042 is accepted as a shared range repair. Native/configured minimums now
agree across candidate admission, both combat consumers and rejected-candidate
movement recovery. Sixteen focused tests passed independently. The first patch
missed the rejection-to-movement handler; its deterministic eight-yard case
fails on2af and passes on26. Native Hunter receipt307 starts11.163yd from the
body, selects an outward25.323yd endpoint, reconciles the minimum and resumes
Auto Shot/Steady Shot with landed damage. Native terrain/pathing is unchanged.
Balance's exact former post-exit4.650yd position did not recur. Two nearer
pincer attempts reached native execution but returned176; that is policy-level
coverage, not successful under-five-yard native casting. No unchanged range
retry is requested. Balance measured25,641DPS versus17,670 on433 and29,498 on2af.

DPS-043 is accepted for legal fixed-baiter binding and native offense. The
old selector bypassed actor-filtered opportunities for raw NearestParasite;
Hunter's two Multi-Shots on26 then failed LOS. Thirteen focused tests passed
independently. On ee0504 all13 Mage and15 Hunter parasite-binding transitions
record alive, attackable and LOS true. Hunter submits two Multi-Shots and lands
11 effects, including106,795 add damage. Mage30006 lands Blast Wave on eight
parasites and17 Flamestrike damage events. Contact escape remains active and
no Infection occurs. Exact-tick blocked-nearer alternatives are not recorded;
that selection counterexample is proven by the production fixture, not invented
from live snapshots. Native terrain/pathing and class coefficients are unchanged.

In the earlier MM run, performance remained mixed. Hunter was31,513DPS versus33,060 on26;
Fire30006 is27,936 versus32,875, while Fire30007 rises to30,140 and Balance
to30,423. These totals do not prove the remaining class rotations are correct.
The next review covers the whole roster against the newly selected
[111.3-second WCL reference](magmaw_dps_baseline_20260913.md), which includes
Balance, Fire, Elemental, Affliction and Blood at roughly395 average ilvl.
Its nine-player2/2/5 roster does246,232.7DPS; it is a useful class comparison,
not an exact passing floor. DPS-045 retains the outstanding phase, gear,
aura/cooldown and accounting normalization. There is no matched MM player yet.

DPS-044 remains open: Mage30006's19.138-second and Hunter's14.910-second
fresh-direct-effect gaps require candidate/native-outcome diagnosis; a gap
is not automatically idle casting time. Affliction is14.11% belowff226 across
owner, periodic and pet output. Balance's area-policy suppression remains a
separate lead. Native admission also shows no permanent item enchants on Blood
or the three healers, while all DPS characters are enchanted. Use the actual
admitted manifest, not intermediate generic profile flags or their item levels.

DPS-041 remains accepted: ordinary add setup Marks are zero, seven Marks use
normal ranking, and body/head setup remains. MOV-001 retains its earlier
native acceptance onff226; the latest run has zero Infection78941, but does
not independently exercise the personal-threat task. Its contact-evade and
range-movement records must not be confused with that earlier task proof.

OBS-011 joins existing native effective/combat stats into the timeline at their
actual observation times. Thirty-nine focused tests passed. The433 replay
retained700 snapshots with unchanged damage, actor totals, scoring window and
phases. Analysis source067 is distinct from native433. Earlier raw snapshots
show temporary proc differences, not a proven permanent post-recovery stat loss.

Evidence pointers:
`artifacts/cata_raid_program/magmaw_parasite_escape_ff226ad52b_20260913.tar.gz.dvc`,
`artifacts/cata_raid_program/magmaw_hunter_mark_4337116eeb_20260913.tar.gz.dvc`,
`artifacts/cata_raid_program/magmaw_native_range_2af61a1cef_20260913.tar.gz.dvc`,
the verified26 publication
`artifacts/cata_raid_program/magmaw_range_recovery_26c536140a_20260913.tar.gz.dvc`,
and latest `artifacts/cata_raid_program/magmaw_baiter_targets_ee0504cc0c_20260913.tar.gz.dvc`.
The latest compact review is `magmaw-development-ee0504cc0c/dps_review.md`;
older runs retain `dps_review.json`. Latest `remaining_attack_gaps.timeline.json.gz`
retains unmodified Mage/Hunter events from+88..+114s with original identity and
input hash. The remote archive and every member were verified through a fresh-cache
reconstruction. Exact local raw/full timeline and duplicate archive/cache
payloads were evicted. Raw capture and full timeline remain remotely reconstructible.

The one-tank composition was first accepted on `89cef294b6`, replacing only
the Prot Paladin slot with the catalog Balance loadout. All other nine actors
were preserved. Its extra965,745 damage versus the two-tank baseline was
entirely adds; its1.78% greater raid DPS was not a performance acceptance.
Evidence: `artifacts/cata_raid_program/magmaw_one_tank_balance_20260913.tar.gz.dvc`,
member `magmaw-development-89cef294b6/dps_review.json`.

The last two-tank baseline, `c5700590e7`, cleared in 147.272 seconds at
191,961.907 exact raid DPS and 12,169.034 effective HPS. All ten survived the
boss; eight trash death episodes recovered. This accepted the focused DPS-040
repair. Evidence:
`artifacts/cata_raid_program/magmaw_mobility_readiness_20260912.tar.gz.dvc`.
The following paragraphs describe that earlier baseline and its predecessors.

The matched earlier `0f0a8c0382` result was 149.023 seconds at 189,706.381 DPS,
with the same 28,270,614 originated hostile damage. Latest DPS is 1.19% higher.
The intermediate `3329f0b407` and `b5215c35b6` runs remain published under
`magmaw_activity_20260912` and `magmaw_recovery_repath_20260912`; their lower
DPS is not relabeled as acceptance. Overall class tuning and boss fidelity are
still incomplete.

DPS-040 found that failed directional mobility attempts changed facing before
native cooldown/GCD rejection. Readiness now precedes facing/native submission;
other native rejections restore the prior orientation. Ready emergency mobility
still uses the native executor. Six focused tests, independent review and the
native build passed. Fire30006 now finished 17 Fireballs successfully during
head exposure; all 17 landed for 993,679 damage, with zero failed Fireball or
native Blink finishes in that window. Typed cooldown rejections occurred before
native Blink submission.
The prior run had zero successful and ten failed Fireball finishes, alongside
62 failed Blinks. Cast-instance/facing correlation remains unavailable; do not
attribute every point of raid DPS change to this one repair.

REC-002 removes partial-trash pre-release waiting. REC-003 retries a native
spline that finishes short of the entrance once, preserving the 30-second
fallback for active paths. The latest eight death episodes released within
1.514 seconds and returned in 41.846-46.455 seconds; all regrouped and resumed.
The preceding run exercised the early retry and returned in 53.047 seconds
instead of retaining the earlier 78.198-second stall. Full-wipe recovery was
not exercised. The requested universal 30-40-second return is not yet proven.

PULL-001's Hunter Misdirection to the assigned tank and Drudge opener are
verified. Faster total trash completion and fewer casualties are not established.
DPS-038 removed Elemental's artificial 12-yard retreats. DPS-039's moving
Affliction Fel Flame fallback produced native damage on trash. Remaining
bounded leads include Hunter's Mark on short-lived adds, trash survival and
pull staging, and recovery episode bookkeeping across focus cleanup.
Review actual diagnosis `effective_stats`/`native_combat_stats` and modifier
auras before claiming missing stats or tuning damage from unmatched proc state.

REC-001's full-wipe deadlock is repaired in configuration. In the previous
`36f8ab0bc3` run all ten bots physically released, ran back, re-entered and
resurrected, but admission recorded entrance `0/0/0`. The tracker therefore
rejected their runback evidence and held the alive cohort. All seven BWD
scenarios now explicitly declare the DBC/database-verified entrance
`(6581, 0, 669)`. The production tracker fixture covers actual ghost progress,
re-entry/resurrection in the same update, and rejection of missing/mismatched
observations. Independent review approved this configuration-only repair;
19 focused scenario/recovery tests and the native build passed.

The previous `0f0` live admission contained the correct entrance. Fire mage 30007 died on
Drudges, released, ran back, re-entered and resurrected after 122.493 seconds;
the full cohort then resumed and killed Magmaw. This run did not have a full wipe, so full-wipe recovery has fixture coverage but remains unexercised
live. The controller's `native_recovery_accepted=true` is vacuous when
`native_recovery_required=false`; it is not proof of observed recovery.
Trash wipes are acceptable when bots recover, regroup and resume progress.
Do not weaken native evidence checks or manufacture a wipe to claim acceptance.

The previous `0f0` boss DPS was 0.70% above the earlier successful a4b9 run. This does not
establish every class's correctness or complete boss fidelity. Fire DPS fell
6.69%; Discipline DPS/HPS fell 24.38%/22.16%, while other actors improved.
There is no blanket role-performance acceptance. The independent closed-run
review separates per-bot changes, encounter clear and repair scope.
The first setup-only launch rejected a missing fresh stat seed before admitting
bots; canonical provisioning corrected it. It is not a failed gameplay canary.

The preceding 36f8 failure and its corrected causal analysis remain attributable.
Earlier baseline review incorrectly reported zero trash casualties because its
final watchdog counters had reset scope. The a4b9 run lost four bots on trash
and recovered; it did not exercise a full wipe. Both old runs contained the
same roughly 14.6-second Fire mage escape delay. Different Rush targets and
healing pressure preceded the 36f8 wipe, but no causal telemetry regression was
established. Boss-only staging remains held and was not used for this clear.

An older successful native run is source `a4b9ab9bd7`:
150.254 seconds, 28,305,736 hostile originated damage, 188,385.907 exact raid
DPS and 11,624.203 effective HPS over the same interval. It cleared with zero
boss deaths among the bots. Its source, review, build and closed capture are in
`artifacts/cata_raid_program/magmaw_fidelity_20260912.tar.gz.dvc`.
This is a development clear, not full fidelity or performance acceptance.

The pending boss-research edge is ENC-006. The `0f0` capture contains native
melee calculation stages: 485 observations with all nine stage fields, 466
matched health callbacks, and 19 unmatched swings explicitly marked as native
misses. The retained incoming-damage view contains 23 ordinary Magmaw callbacks
with raw 4,431-6,538 and 9,939 total health damage. These values are not WCL's
unmitigated boundary; review the stage observations before choosing any damage
modifier. No fresh capture is needed to obtain those stages. See the
[current baseline](strategies/t11/blackwing_descent/magmaw.md) and the published
closed-run review. Full 4.4.2 fidelity is still not accepted.

The following b113 comparison is the prior diagnostic run, preserved for
performance context. It does not supersede the later a4b9 capture.

## Prior diagnostic run

Native source `b1132dd087de9216c1d77694a8d7b37ddc209955` cleared Magmaw 10N
in **156.064 seconds**, with **28,352,550 hostile originated damage** and
**181,672.583 exact raid DPS**. Owned pets are included; friendly damage and
mirrored spell 79010 callbacks are excluded. Effective healing over that same
pull-to-death interval is 2,298,732, or **14,729.419 HPS**. The actual roster is
2 tanks, 3 healers and 5 DPS. All ten survived the boss. Fire hook and Affliction
died on Drudges and recovered before the pull. Native exit, zero bots/leases,
cleanup and post-run build verification passed.

| Source | Exact fight seconds | Exact raid DPS | Comparison |
| --- | ---: | ---: | --- |
| 4b24d7242f | 140.359 | 200,864.383 | Faster benchmark; no living-body return after its first head phase |
| 41266a508c | 151.420 | 186,703.302 | Prior matched setup; current DPS is 2.69% lower |
| 6882d0c204 | 209.211 | 138,307.847 | Primary reviewed baseline; current DPS is 31.35% higher |
| b1132dd087 | 156.064 | 181,672.583 | Current development clear |

Every DPS actor improved against 6882, by approximately 9% to 47%; both tanks
improved. The five DPS contribute 138,633.599 DPS, 33.25% above 6882 but 5.60%
below 41266. Fight length, head exposure and target opportunities remain
comparison variables. This pair does not assign all recovery to one patch.
No controlled retained comparison proves a particular recent gameplay change
caused the original decline. No blind revert or coefficient tuning was made.

## Separate acceptance outcomes

- **Encounter clear: accepted.** Native Magmaw death, exact accounting and
  complete capture are verified. This is not full-raid qualification or training data.
- **Requested repairs: exercised and reviewed.** Optional support admission uses
  actor-specific native LOS and effective action ranges. Production fixtures
  cover blocked optional parasites, mandatory bait/threat, hidden-head to live-body
  binding and simultaneous movement/casting. The live run exercises legal support,
  mandatory bait and fresh body attacks after head disappearance. It does not
  expose every rejected nearby candidate, so fixture and live coverage stay distinct.
- **Overall performance: inconclusive, diagnosis required.** The comparator
  identifies the baseline and matching roster/loadout/profile/route/assets. The
  instance-listener port is an explicit infrastructure-only difference and slower
  full diagnosis is recorded. Legacy target-switch observations are insufficient.
  Healer activity/HPS flags require demand review; lower raid damage taken and zero
  boss deaths do not explain every actor's change. Do not promote all-role throughput.

Preserve accepted tank swaps, native Vengeance, MM haste/filler, Affliction
boss-health potion, Elemental moving Lava Burst and early moving-cast cancellation
repairs. A later unsuccessful cast does not undo the proven interruption repair.

## Timeline and capture

The [timeline tooling](bot_timeline.md) joins existing native combat, trace and
diagnosis records. This run retains 26,345 trace rows and 8,868 combat events,
with no identity rejection or trace/combat gap. Recording-time context separates
proposed/bound/native targets, native action outcomes and stale observations.
The complete HTML has 74,153 joined events, actor/phase/target/spell/time filters
and lazy event details. Chrome filtering and detail expansion were checked.
Lossless packaging is 7,061,175 bytes instead of 213,524,963 bytes; the original
inventoried HTML remains immutable in the evidence archive. Renderer revision
`a9431b973e` is separate from native run revision `b1132dd087`.

CAP-005 retention passed a native 4,097-event pressure emission, all 33 drain
pages and final zero backlog. Its deliberately overflowing actor reports the
expected gap; no unreported loss is accepted. CAP-006 was diagnosed directly in
the first live timeline: the native same-action counter ignored result changes,
so successful attacks contributed to a watchdog failure streak. The repair resets
on outcome changes without relaxing thresholds. The next run crossed both trash
nodes and cleared the boss; reviewed outcome transitions reset correctly.

Five-second diagnosis with two-second trace capture reduced native capture bytes
per elapsed second by 31.39% against 6882. Trace parsing used approximately 0.51%
of one core; mean server CPU changed from 32.255% to 33.720% of one core and peak
RSS increased about 0.59 MB. These are whole-run observations, not isolated proof
of instrumentation CPU cost. Keep aggregate counters, identity/readback receipts
and original raw evidence alongside the timeline in DVC.

## Prior diagnostic follow-ups (still unresolved)

The original manual head-hide outage remains **DPS-023, cause unknown**. Its
128-row decisions were overwritten. Current successful returns do not disprove
that occurrence or prove its precise cause repaired. Do not retry it unchanged
or claim a universal head-return fix.

A separate actionable observation remains **OBS-008**: terminal native cast failure reason
and cast-instance correlation remain unavailable. The timeline says so explicitly;
accepted submission, finish and landed effects are separate records. Obtain that
native outcome before guessing why a moving-permitted cast later fails.
Keep DPS-037 (Elemental artificial 12-yard gate), DPS-026/DPS-029 (area protection),
ENC-001 (Drudge safety), HEAL-001 (Holy Paladin capabilities) and OBS-006
(Discipline absorption attribution) visible for separate bounded work units.

## Evidence

Current closed run, prior failed attempts, pressure validation, independent
reviews, focused tests, accounting and capture-cost receipts are bundled under
`artifacts/cata_raid_program/magmaw_development_b1132dd087_20260910.tar.gz.dvc`.
The adjacent publication receipt records fresh empty-cache remote verification
and exact local eviction. Consult it for publication status rather than assuming
that a pointer alone proves uploaded bytes. The compact HTML and reviews remain
locally inspectable; large duplicate payloads are evicted only after verification.

The [active work unit](../../experiments/configs/cata_raid_active_work_unit_v1.json)
closes this canary and routes OBS-008. No additional native run is required for
post-close HTML packaging or comparator/documentation changes.
