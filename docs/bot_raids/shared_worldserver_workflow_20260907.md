# Shared-worldserver workflow status

Updated 2026-09-13. This is the current status. Historical run narratives remain
in Git; failed assumptions and bounded next repairs belong in the
[error ledger](error_ledger.md). Closed generated evidence is tracked by DVC.

## Current work and latest native run

Source `779f62087f` cleared Magmaw in129.792s at217,217.725 exact raid DPS
and12,961.739 exact-window HPS. The all-bot review accepted Balance33831
(three Treants,34 landed hits,83,995 damage), OBS-012 periodic outcome retention,
and MOV-001's actual native hazard traversal (receipt373, endpoint reached).
No Infection or boss-window deaths occurred. Overall roster performance is open;
the latest DPS is0.54% below a3a. Historical head-to-body failure is not covered
by this kill, which ended during head exposure.

The active task is the duty-aware, spell-level WCL comparison linked in the
[all-actor table](magmaw_dps_baseline_20260913.md#active-parent-objective-and-actor-acceptance).
Fresh WCL breakdowns expose larger cadence, guardian and strike-damage gaps,
plus excess native components that can conceal losses. Drain Soul is above the
selected reference; its variance does not explain the roster deficit. Separate
investigation priorities from small proven bugs and from recoverable damage.
No additional worldserver or dummy experiment was launched for this comparison.
The next causal check should resolve a material gap using retained evidence first.

Affliction Bane-purpose, Fire/Survival potions and optional Elemental earth slot
are committed and independently reviewed, but not built/applied/live validated.
The authserver remains available; worldserver is stopped after clean closure.
Current evidence: `artifacts/cata_raid_program/magmaw_balance_outcome_779f62087f_20260913.tar.gz.dvc`.
The82,856,023-byte archive and every member passed fresh-cache remote verification.
Exact raw/full timeline and archive/cache/reconstruction duplicates were evicted.
The readable comparison, normalized references and timeline HTML remain local.

The sections below retain September10 diagnostic history. Their run-specific
acceptance and follow-up descriptions do not override the current status above.

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
