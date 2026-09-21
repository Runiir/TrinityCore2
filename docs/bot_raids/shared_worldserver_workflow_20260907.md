# Shared-worldserver workflow status

Updated 2026-09-21. Work continues on master. The separate ongoing JEV branch
is preserved.

## Current work and latest native run

The user has reprioritized Balance regression diagnosis. Resume
`magmaw:balance_regression_91pct_07` through `raid_workloop resume`.
The graph pins the earlier 91.93% Balance run to its actual binary source
`618b20a2d2793e3f26b3b9d45ed2728f3b97d881`; the historical run adapter was
written at `6253c9766f1af4e09b10e62db0bec1940d8ccf9`. Do not confuse those identities.
The continuation contract is
`artifacts/cata_raid_program/magmaw_balance_regression_continuation_20260921.json`.
It retains the full suspended Blood assignment, including its source base and
independently reviewed workflow support. Reuse that unchanged support review in
the next native plan; do not rebase over or drop those source requirements.

| Retained Balance run | DPS | Current reference ratio |
| --- | ---: | ---: |
| Unit04, neutral opener | 32,585.297 | 91.93% |
| Unit05, lunar-window gate | 31,544.057 | 88.99% |
| Unit06, attribution observer | 30,881.980 | 87.12% |

All used a 35,447.589 DPS reference and an exact 300-second scored window.
The total decline is 1,703.317 DPS. The historical 91.93% result is a measured
comparator, not current 95% qualification or a perfectly matched experiment.
Unit04 recorded startup aura 75170 (+580 intellect) absent in unit05. Its full
uptime/contribution and the older runs' landed direct DTR copies remain unresolved.
Neither this aura nor DTR randomness is a quantified explanation of the decline.
The latest observer run also retains incomplete evidence identity; it is not accepted.

Use retained unit04/unit05/unit06 evidence first. If it cannot settle causality,
prepare one bounded matched pair on common current shared code, comparing only
the Balance post-opener `balance_starfall_lunar_window` profile condition. The
historical neutral-opener behavior stays in both. Record actual database/profile
readback; deleting an old SQL file does not undo an applied migration. Match or
explicitly account for natural proc coverage rather than manufacturing a buff.
Keep ordinary casts, periodic damage, pets and landed DTR copies separate, and
leave unattributed damage unknown. Revert or replace only a proven harmful change.

Current master retains other-spec fixes. Blood's Death Strike priority change
`a283a51228` was already in the historical baseline, so it does not need to be
cherry-picked back. Preserve current DTR observation and workflow fixes in both
comparison conditions. After the Balance regression work, resume the suspended
Blood task and the remaining actor requirements. Every DPS still needs >=95% of
its current promoted self-provided WoWSims reference; DTR gives no extra waiver.
This graph update changes no combat code, database, live run, or acceptance.

The earlier Moonkin haste expectation of 1.332199768 was a comparator error:
WoWSims already included the 5% form multiplier. Native speed 1.269 matches the
correct expectation 1.26876. The comparator repair is retained; the old handler
probe and `workflow_loop_native_review_20260920.json` are historical evidence,
not authority to reopen a missing-haste hypothesis. The active graph owns
continuation and source binding; do not rebase past unreviewed gameplay changes.

Do not remove the parity worktree: it supplies verified runtime assets. The JEV
worktree contains unrelated uncommitted work. New builds use host12; historical
build receipts retain their own policy. Use `workflow_build run` for a new
reviewed build, with its claim committed first. It creates canonical configure
and build receipts without committing between the two steps.

The earlier baseline is the `50ec676cdb` five-spec dummy batch, with all exact
300-second measurements complete and concurrent native isolation/cleanup
proved. Per-spec DPS and remaining setup/cadence findings are in the
[current dummy table](magmaw_dps_baseline_20260913.md#current-dummy-batch-50ec).
The user accepted the near-reference Fire/Survival totals for moving forward
and requested Jev/Laya checkpoints to keep Luna workers on task. A narrow
calibration duplicate-potion repair is committed at `fe3dadce4d`; tests and
review passed, while native build/live validation remain pending. Workflow
checkpoints are committed at `cbe81b0ffc`. The full continuation instructions
are in [the handoff](handoff_magmaw_dps_20260919.md). No class coefficient change is justified by this batch.

### Latest raid run (696a)

Clean source `696a8f6f38` cleared in **123.672s**, with **228,230.950 exact
DPS**, **17,884.153 exact HPS**, and all ten bots alive. The scored hostile total
is 28,225,778, including owned pets and excluding friendly/mirror callbacks.
DPS declined 4.86% against d495. Performance is not accepted; all-actor causal
reviews and both model reviews are complete; neither model added a new actionable finding. Balance fell to 24,303.335 DPS
and Blood to 12,090.125; regular Fire rose to 45,540.033 and Affliction to
38,853.944. The Blood migration loaded profile267 v25 and both priority buckets1.
Its selected/native outcomes confirm DS delivery and HS fallback. Throughput and
mitigation tradeoffs remain unresolved; no revert is justified by the aggregate alone. The elemental owner-chain fix is live accepted: zero reciprocal
friendly events, 605,865 legal guardian damage, and observed legal Fire Shield.
Capture has 8,236 combat events, 29,641 trace rows and no gaps or identity rejects.
Cleanup, zero bots/leases and server exit0 passed. Raw evidence is fresh-remote
verified at `artifacts/cata_raid_program/magmaw_master_696a8f6f38_20260919.raw.tar.zst.dvc`
(MD5 `26e76d8c152518090527a096c2a98274`). Reviews and closure are also remotely
verified; 1,009,972,252 logical bytes of exact raw/archive/cache duplicates were
removed. Compact report, summary and HTML remain.

The preceding next step was to reuse the retained 300-second class evidence and verified current simulator
cohort. Fire/Affliction/Elemental retain valid historical repair evidence, but
85% optimization passes are not class parity. Balance's historical reference/setup
compatibility needed checking; Survival then had no retained exact-300 native run.
Embedded `all_spec_references` DPS must not override the promoted request catalog.
The bounded Balance primary-DoT density repair is committed and independently
reviewed at `db16de2412`; no live benefit is claimed. Do not launch another full
raid simply to repeat the same unresolved class comparison.

### Previous reviewed baseline

WCL remains the performance benchmark. Clean native source `d495bd1556`
killed Magmaw in 117.523 seconds with 28,193,123 originated hostile damage,
**239,894.514 exact DPS** and **14,412.302 exact HPS**. Owned pets are included;
friendly damage and mirrored 79010 callbacks are excluded. All ten bots survived
through native boss death. The completion watchdog accepted the clear, capture,
cleanup and exit. There are 8,089 combat events and 28,647 trace entries without
gaps or identity rejects. This clear is not overall WCL performance acceptance.

DPS rose 9.23% against the matched `9d29edd376` run (128.742s, 219,627.332 DPS,
one Blood death). The lawful `ab829858df` restart reached 234,721.796 DPS in
119.991s; its route asset differs, so it is not an exact matched comparison.
Historical shard89's 241,249.360 used enlarged Mushroom targeting and is not a
lawful floor. The roster remains one Blood tank, three healers and six DPS.
Per-actor results and unresolved work are in [the DPS baseline](magmaw_dps_baseline_20260913.md#active-parent-objective-and-actor-acceptance).

The moving-cast facing repair is live exercised: five moving Scorch preparations
succeeded, four finished while still moving, and neither Fire actor had a
Scorch UNIT_NOT_INFRONT failure. A dead-parasite BAD_TARGETS failure remains
correctly distinct. Native arc checks, movement and spell geometry were preserved.

The elemental repair has only partial acceptance. Targeted reciprocal attacks
ceased during the boss window, but one Fire Nova still hit the allied wolf for
532. Reciprocal melee resumed after boss death and is excluded from DPS. Fire
Shield has no landed event, so its legal-enemy preservation remains unproved.
Do not attribute the full post-clear pet fight to encounter throughput.

The passive Blood observation exposed the next proven policy defect. Heart
Strike won 15 times while Death Strike was valid and had the higher score,
including at 63.33% health. Death Strike's bucket 2 lost to Heart Strike's bucket
1 before score comparison. A forward profile correction passed its two focused tests and independent review;
Heart Strike must remain available when Death Strike lacks valid runes. No rune
cost, spell coefficient, target or encounter change is proposed. The reviewed
Flame Orb change filters native-illegal candidates before choosing the nearest
target. A narrowly guarded Fire Elemental owner-chain correction is also ready
and independently approved. These repairs require the next native canary.

All represented actors remain under review. Balance's post-pincer landing gap
fell to 0.338s; same-tick replacement submissions do not identify interruption
owners. Survival has no unexplained in-window rotation loss in this run and
landed two Multi-Shots. Affliction's largest decline is proc/target and phase
variation; short-lived parasite UA is a smaller proven waste. Healer critical
coverage improved, while major cooldowns were again spent on trash. Fire Orb
still has zero damage and repeated native failures on a nonattackable body part.

Laya and hosted Jev each completed ten actor reviews without errors or
truncation. Native reviewers discard unsupported cadence/assignment diagnoses.
The original packets omit useful retained facts, including exact healer-window
results; the new projection joins the existing native-death timeline summary.
A separate focused Blood case supplied exact pre-spend decisions and the native
comparator. Jev selected the supported profile-ordering cause; Laya selected
rune legality despite the observed valid Death Strike. Both suggested a rune
probe already covered by the retained control. Neither supplied a new repair.
The revised collector binds exact native report and summary identity, preserves
unknowns and comparison context, and fits all ten deployed-tokenizer packets
(maximum 941/1024 tokens). Independent review and 31 focused tests passed.
The corrected retained replay is pending; packet correctness is not diagnostic
accuracy. Neither model has supplied repair authority. Follow [the shadow workflow](local_jev_shadow.md).

Raw evidence is published and fresh-remote verified at
`artifacts/cata_raid_program/magmaw_master_d495_20260919.raw.tar.zst.dvc`
(MD5 `c9b27044cae9c7c628bb8473c3c29e35`, 20,431,486 bytes). The compact review archive is also fresh-remote verified at
`magmaw_master_d495_20260919.review.tar.gz.dvc` (77 hash-checked members,
MD5 `6df4b6147083f750b2f52d28f6ff905c`). The closure archive retains remote verification and exact eviction receipts;
985,219,163 bytes of duplicate raw/log/timeline/archive/cache payloads were removed.
The 9d29 raw/review/closure publications remain verified historical evidence;
its original survival summary has a separate corrected replay. The 73103 and
ab829 publications are also retained remotely.

The later `2fcd4133aa` run at 152,244.042 DPS remains regression evidence, not the
restart source or target. Its review pointer is
`artifacts/cata_raid_program/magmaw_native_parity_2fcd4133_20260919_review.dvc`.
Shard89 evidence is `artifacts/cata_raid_program/magmaw_jev_canary_compact_20260919.tar.gz.dvc`.

Historical entries below do not override this current result.

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

The adjacent Hunter override fixture dependency drift is repaired in eafe0cca2e;
its two tests now pass. This test-only repair changes no native behavior.
