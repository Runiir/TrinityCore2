# Shared-worldserver workflow status

Current objective: resolve roster DPS, continuing past individual repair acceptance.

Source `8160201cb1` passed independent review and one verified build. Its exact
300-second Elemental calibration is closed: 6,729,475 damage, 22,431.583 DPS,
zero HPS, zero deaths, zero movement loss, native exit0, cleanup and post-run
binary verification passed. The previous 18ff window was 21,943.477 DPS. The
current exact WoWSims reference remains 36,999.280 DPS. DPS is unresolved.

Ordinary provisioning added only 5675/8143/87507. Native skill loading restores
12 dependent default spells which native saving correctly omits; the persisted
46-row spellbook was checked against that exact closure before adding three
ordinary rows. No aura was installed manually. Mail specialization is now
observed through native 5% intellect (8091 versus7706). Corrected totem setup
selects Tremor8143, ManaSpring5675 and WrathAir3738. Wrath aura2895 is active in
589/601 samples, while prior Strength8076 and Windfury8515 are absent. The
weapon-imbue manifest projection now passes with actual native enchant5.

The remaining compatibility gate falsely categorizes aura2895 by ID as external.
Current evidence cannot prove caster ownership because that field is missing.
The owner-aware observation/consumer repair passed independent review; old
evidence stays rejected. Only a frozen-spec-matched aura cast by the bot's own totem may
receive the self-provided exception. Foreign/unknown provenance remains rejected.
Fire Elemental2894 submission is observed, but guardian presence, lifetime and
originated damage remain unproven. Read-only guardian, owner-target and native haste sampling passed independent
review. No coefficient or speculative pet-policy repair is admitted.

The prior source18ff Magmaw canary cleared with zero deaths, ten alive,
118,358.965 hostile DPS and 20,110.681 HPS over254 active damage seconds
(287.006 elapsed,104,747.556 elapsedDPS). Crash-floor admission is accepted;
fixedFire improved5679.923DPS. All four vehicle exits reconciled, but the new
pre-occupancy carry branch was not exercised. Parasite escape paths remain
rejected without a proven safe replacement. The complete all-bot review is
published and exact raw payloads evicted. Head-target rows include shared-damage
forwarding, so they do not prove direct head targeting for every actor; preserve
`head-attribution-18ff-addendum.md` separately from the published report.

Published verified evidence pointers:
- `artifacts/cata_raid_program/elemental_calibration_18fffe3bee_20260908.tar.gz.dvc`
- `artifacts/cata_raid_program/magmaw_development_18fffe3bee_20260908.tar.gz.dvc`
- `artifacts/cata_raid_program/elemental_calibration_8160201cb1_20260908.tar.gz.dvc`

All16 references are promoted and remotely reconstructed. Current fixture SHA256
is `0a8f4cf3ef92e179700e97fc4c7535e2e591f2cb0d0cc9d15245b8bbe283849f`.
Runtime spell reconciliation leaves simulator requests unchanged. Reuse the
reference cohort for observation and role changes with unchanged reference inputs.

The closed 816 review also proves Elemental polling is 500 ms in calibration
and 1,000 ms in ordinary combat. A bounded change to the existing shared 100 ms
reaction policy passed independent review. The amount of DPS recovered remains
unmeasured; in-progress casts must not be counted as idle time. Independent
review covered both callers and the unchanged channel-interruption behavior.

The affected observation suite passed 126 tests; the scheduling fixture passed
two executable tests. All changed C/C++ files remain below 1,000 lines.

Next: build the combined batch once and run the
next exact calibration. Both closed raw payloads are published, remotely
verified and evicted. Keep actual 2 tank / 3 healer / 5 DPS raid composition
fixed; diagnostic runs are not qualification or training admission.

## Earlier result: fc Magmaw clear, DPS still unresolved

Source `fc8caa430de98a37b530bd22933c66d5d3b6dbed` completed the canonical Magmaw
10N development run with capture exit0, native boss death, all ten bots recovered,
cleanup passed and post-run build receipt verified. Two casualties occurred during
Drudges and one during Magmaw. That run is closed.

Boss hostile damage 29,200,494 yields 130,359.348 DPS and final 18,267.009 HPS over 224 active
callback seconds, only a small gain over source88's127,953.806 DPS/227 seconds.
This is a development clear, not full-raid qualification or overall DPS acceptance.

Elemental's range/ordinary-formation oscillation is accepted as repaired: it reaches
stable casting range and lands Lightning Bolt and Lava Burst. Heroism was submitted
once at the first observed exposed-head switch; raid-wide aura coverage is unproved.
All four observed vehicle exits eventually reconciled with fresh landed hardcasts,
but substantial delays remain. The next exact shared edge is Affliction receipt570:
its post-exit POINT is submitted before native launch, while binding is attempted
only synchronously. The bounded late-binding repair passes its three affected behavioral tests and is under independent Sol review. Fire's
pre-exit receipt563 remains excluded; its first elevated endpoint rejection is a
separate native geometry finding.

The all-bot review is complete and the patrol/capture repairs are accepted from closed evidence
in `magmaw-development-fc8caa430d`. An isolated300-second Elemental calibration is
being prepared to separate class mechanics from encounter losses. Existing map0
assets are present, but the current map669-only asset closure lacks their selected
contract; no closure check will be bypassed. No coefficient change is admitted.

The current batch contains deferred post-exit receipt binding (three tests, Sol
approved), the hook approach's route-derived floor identity (producer/native
admission regression passed, Sol approved), and generic selected-map admission
from the existing audited asset inventory (128 affected tests passed, Sol approved). The latter
reuses the existing map 0 data; 606 independent offline navmesh copies passed
content and mode readback. It does not change native terrain or pathing.

Closed fc evidence is published through
`artifacts/cata_raid_program/magmaw_development_fc8caa430d_20260908.tar.gz.dvc`.
The 28,003,017-byte archive passed fresh remote reconstruction and hash verification;
exact raw/log/archive duplicates were evicted after all readers completed.

## Earlier result: capture repaired, canary stopped during Chainwielder

Source `fa34580f2f4930fe9e31ec1fd80215df4aaf6a6e` built and verified, then the
canonical watchdog stopped the route at Chainwielder for repeated failed decisions.
Magmaw was not reached. All ten bots survived and cleanup passed; post-run build
identity verified. Native formation and vehicle-exit acceptance remain pending.

The capture repair is accepted for this run: active nonterminal deltas started
before combat, retained833/833 final native events, and report no gaps, conflicts
or transport rejection. Evidence demultiplexing passed. The closed result remains
`gameplay_failure` / `repeated_decision_watchdog`; no boss-clear or DPS claim.

Chainwielder totals:3,609,026 hostile damage,46,870.468 DPS and7,650.610 HPS over
77 active callback seconds. The136.812-second all-event span is a different clock.
There were3,148 decisions and zero deaths. Trace review proves patrol pull
authority re-entered after accepted combat and globally suppressed offense when
the mob moved outside its initial anchor radius. A shared, episode-scoped patrol
handoff repair is approved for implementation. It preserves prefight safety and
does not re-stage on later movement or a transient victim-role change.
The patrol implementation passed22 focused checks and independent Sol review.
Five stale source-reader failures were repaired at their actual split owners;
all6 authority checks now pass without weakening their predicates.
A separate watchdog review found11 owned Blood damage events missing from its
stale trace-based progress inputs. The controller repair passes the real
accepted-chunk/capture/watchdog replay with7 remaining failures, plus43 affected
checks and independent Sol approval. Limits remain unchanged.
All reviews are complete. Closed evidence is published through
`artifacts/cata_raid_program/magmaw_development_fa34580f2f_20260908.tar.gz.dvc`.
The8,849,274-byte archive passed fresh remote reconstruction and hash verification;
exact raw/log/archive duplicates were evicted. Proceed with the approved batch.

## Earlier result: native Magmaw kill, capture falsely rejected

Source `88d35c0421af4ddecf4ead56dde84fb45ae44ff6` completed native Magmaw 10N
with all ten bots surviving the boss. Five casualties occurred during Drudges;
all recovered before the boss. Cleanup passed, worldserver exited zero, and
post-run build identity verified. No server is running.

Boss aggregates: 29,045,514 hostile damage, 127,953.806 DPS and 18,146.260 HPS
over 227 active callback seconds. The 273.504-second event span includes
non-damage time and is not an exact WCL engage-to-kill comparison. Native boss
death is accepted separately from the capture's `infrastructure_abort`.

The abort is one evidence-demux rejection at capture row97. Row96 advanced the
route to generation3/node2 while retaining the previous strategy; row97 supplied
the matching native strategy transition. The validator prematurely consumed the
route advancement. The bounded Astra low repair passed independent Sol review and replay of all
987 retained rows. Unexplained strategy changes remain rejected.

Incremental capture also bound only after terminal foundation acceptance and
missed event sequences1..6707. The final full aggregate is authoritative, but
only4098/10805 detailed events survived. Active-admission binding is repaired and
independently approved with29 focused checks using actual nonterminal native
statuses through the real completion predicate. Failure finalization preserves
that admitted identity. This repair has not yet run live.

The closed all-actor review accepts first-exit Affliction reconciliation followed
by native UA/Haunt/Shadow Bolt submissions and landings. A later receipt772
completed, but its binding was discarded while the prior sampled receipt was
still pending. Astra repaired that race; independent Sol review approved the pending-receipt regression.
Elemental repeatedly alternated successful outward range movement and inward
formation movement: its minimum12-yard profile conflicts with the8-yard
ordinary support anchor. The formation repair now observes the exact configured
filler range and abstains from incompatible ordinary restoration. Missing range
facts preserve existing healer formation. New regressions pass and final independent
Sol review approved the amended formation behavior. One older movement-intent assertion also fails against
the original restore implementation and is recorded separately.
Boss DPS by spec: Affliction28,739.780; fixed Fire26,177.176; hook Fire20,762.643;
Marksmanship20,320.727; Elemental10,244.555. No coefficient tuning is justified
without matching effective stats and cadence. Overall DPS remains unresolved.

The four-repair batch is independently approved for one combined build and
bounded native validation. Closed88 evidence is published through
`artifacts/cata_raid_program/magmaw_development_88d35c0421_20260908.tar.gz.dvc`.
The25,689,125-byte archive passed fresh remote reconstruction and hash verification.
Exact raw/log/archive duplicates were evicted; compact all-actor and implementation
reviews remain. The earlier86 evidence is also remotely verified and evicted.

## Earlier result: reviewed batch failed the Magmaw canary

Source: `86d37c0a449d19b1123d65c6caf5d52691626527`.
The combined build passed and the canonical Magmaw 10N development capture
closed as `semantic_stall`. There was no boss kill. Twelve casualties were
recorded: two in trash and ten during the boss pull. All ten bots recovered,
but the post-wipe roster did not resume progress. Cleanup passed, worldserver
exited zero, and the post-run build receipt verified. No server is running.

The boss window reports 29,075,000 hostile damage, 67,616.279 DPS and
12,992.740 HPS over 430 active callback seconds (428 hostile-damage seconds).
Schema v3 retains 753,738 friendly/self damage separately. The 582.787-second
all-event span includes recovery and is not an exact WCL engage-to-kill clock.
This run does not accept overall performance or qualify the six-repair batch
as a whole. Individual repair acceptance and the earliest causal regression
are being reviewed from the closed evidence before another implementation.

The joined class/role review covers every actor. Combat facing preserved actual
native splines; exact DPS glyphs, friendly Holy Shock range, exercised generic
taunt ownership and hostile/friendly accounting are accepted. Moving Lightning
Bolt submission and path progress are proved, but landing remains unproved.
No Heroism was submitted in this run; Elemental died before the retained head
window. Earlier haste implementation acceptance does not establish this run's use.

The next proved runtime cause is server-controlled Player vehicle exit leaving
FALLING set after a completed native ground POINT receipt. Fire 30007 and
Affliction 30008 then repeatedly yield hardcasts despite finalized IDLE/MAX
motion and zero displacement. The generic receipt-bound
vehicle-exit repair and Elemental support-target minimum-range retreat are
implemented and independently approved. Native acceptance remains pending.
The vehicle repair contains no encounter entry predicate or broad movement
normalization. Hunter floor-path rejection
and missing healer decision-state joins remain explicit subsequent findings.

The detailed combat ring dropped 6,985 early events before the final capture.
Aggregate metrics remain available; some lethal-event joins do not. Incremental
event retention is implemented but independent review found incomplete-stream
acceptance and transfer-boundary defects. Astra low workers corrected the
existing changes, and independent Sol review approved the final implementation
after 32 focused checks passed. The six unrelated recurrence-fixture failures
share an admission boundary reproduced on clean source86 before capture. The final
full snapshot remains the aggregate DPS/HPS authority.
Closed evidence and reviews are published through
`artifacts/cata_raid_program/magmaw_development_86d37c0a44_20260908.tar.gz.dvc`.
The 39,094,953-byte archive passed fresh remote reconstruction and hash
verification. Exact raw/log/archive duplicates were evicted; compact reviews remain.
The native semantic-stall receipt is in `report.semantic_stall`; the separate
`terminal_failure.detected == false` does not mean the watchdog missed it.

## Earlier result: Heroism verified, roster performance unresolved

Source: `5a7e61f9ced99a77382f8a759b885dcd3f68a4b6`.
The Magmaw 10N development run cleared with cleanup and all ten bots recovered.
It recorded one trash death and one boss-fight death. Actor 30010 submitted
Heroism 32182 at 1788864414150 during the first selectable-head window and
observed its owner-cast aura at 1788864415151, without a duplicate submission.
Raid-wide recipient coverage and Exhaustion remain unobserved.

The report records 98,206.508 DPS and 16,876.141 HPS over 311 active damage
seconds. Inspection found 550,757 friendly/self damage included in its damage
total. Hostile-only damage is 29,991,467, or 96,435.585 DPS using the same
denominator. The measurement correction does not resolve the throughput gap.
Do not compare this active-second denominator as an exact WCL fight duration.

The active WCL reference xAhkN2y9YP3KRmnJ/fight 10 records 378,849.0 all-enemy
DPS and 369,013.6 boss-only DPS over 70.9s with 1 tank / 1 healer / 8 DPS.
Our roster remains 2 tanks / 3 healers / 5 DPS. Use its actual per-player
results, matching specs and observed casts; no rough 150k threshold applies.
Parallel reviews cover both Fire mages, Affliction, Elemental, Marksmanship,
both tanks and all healers. Shared defects receive one implementation owner.

Closed evidence and reviews are published at
[`magmaw_development_5a7e61f9ce_20260908.tar.gz.dvc`](../../artifacts/cata_raid_program/magmaw_development_5a7e61f9ce_20260908.tar.gz.dvc).
The 28,905,726-byte archive passed fresh-cache remote reconstruction and hash
verification; exact local raw payloads were evicted. Compact reviews remain in
the external run directory. No worldserver is running. The 300-second calibration
verification remains pending; this kill does not qualify heroic or training data.

The joined repair batch is independently approved for one build and canary:
combat facing preserves an active spline; native aura masks permit covered
moving casts; canonical DPS glyphs match the catalog; friendly casts delegate
range validation to the core; generic taunts preserve other-cohort-tank ownership;
and schema v3 separates friendly/self damage from hostile DPS and progress.
Forced facing was proved to replace the hunter's admitted hazard spline during
a simultaneous instant cast. A proposed downstream movement-flag normalizer
was held and removed from the implementation after that earlier cause was found.

Fifty combined class/runtime checks passed. Damage accounting passed 46 focused
checks, four progress checks and nine live-controller checks. Four status/cursor
checks passed after correcting an obsolete source-location assertion. Fixtures
prove their production seams and modeled transitions, not native vehicle behavior
or full encounter performance. The next live run must establish native acceptance
for each repaired edge and reassess every actor's DPS/HPS, deaths and movement.

## Earlier result: Elemental repair accepted, raid haste blocked

Source `226fa8857d23aa894a5d0be9929ddf70e7975a00` cleared Magmaw 10N with three
terminal statuses, cleanup complete, four trash deaths and zero boss-fight deaths.
All ten bots recovered. Originated party DPS rose 84,974.593 to 95,723.151;
HPS 20,206.545 over 325 active damage seconds. These scoring seconds are not a
strict WCL-equivalent engage-to-death duration. Raw callback DPS 229,813.151
contains transferred damage and must not be claimed as throughput.

Independent Sol review accepted native Lightning Bolt submission while Chain was
forbidden, followed 2.342s later by landed damage on the same target entry.
Direct Lightning Bolt events increased 4 to 11; Elemental DPS 5,579.518 to 9,270.637.
Exact cast-to-target GUID is unavailable after aggregation. Remaining cadence,
head targeting, moving filler and effective-stat parity remain unresolved.
Roster remains 2 tanks / 3 healers / 5 DPS; requested 2/2/6 has not been tested.

The first selectable-head observation 1788861562295 shows the assigned shaman
on 42347 and `blocked_spell_not_in_shaman_spellbook`. No haste submission or aura
followed. Persisted spell rows alone do not establish the runtime spellbook.
The active browser WCL report xAhkN2y9YP3KRmnJ/fight 10 lasts 70.9s and applies
Time Warp at 10.449–10.463s, removing it 50.456–50.457s. That reference does not
prove head-window timing. Our requested strategy remains burst on first head.

Closed evidence and the all-bot review are published at
[`magmaw_development_226fa8857d_20260908.tar.gz.dvc`](../../artifacts/cata_raid_program/magmaw_development_226fa8857d_20260908.tar.gz.dvc).
The 27,520,648-byte archive passed fresh-cache remote reconstruction and hash
verification. Exact local raw payloads were evicted after independent review.
Calibration category accounting is repaired and built at d3298f73f1, but its
300s live calibration is deferred for this higher-impact raid-haste edge.

Ten focused checks cover runtime spell variants, canonical/shard provisioning,
and offline verifier readiness. Independent Sol review approved both gameplay
changes and the preparation correction. Offline DVC verification now explicitly
allows valid incomplete loadouts while retaining false qualification readiness;
all payload, artifact and database validation failures still fail. Generated
routes/gear bindings were refreshed; the equipment profile bytes are unchanged.

## Earlier result: corrected-gear Magmaw development clear, 2026-09-08

Source `48c42063461eafe111c8f6ee930fa81a5bdb75b3` completed the canonical
10-player normal Magmaw route after replacing the invalid heuristic gear and
binding both Fire mages to the promoted exact preset. The controller accepted
native Magmaw death and three terminal statuses, exited automatically with code
0, and verified zero remaining bots/leases. Postrun build verification passed.
The admitted identity is epoch `5977365002067371`, attempt 1, instance 2.

The roster remains 2 tanks, 3 healers and 5 DPS. There were two trash deaths and
four boss-fight deaths; all ten recovered before cleanup. The final report
records 33,649,939 originated damage and 84,974.593 DPS over 396 active damage
seconds, with 23,951.020 HPS. The broader 513.278-second report window includes
other events. Raw callback DPS of 200,514.298 includes transferred damage and
must not be claimed as actual player throughput. Overall performance remains
unresolved; this clear does not establish heroic/full-raid readiness or permit
training-data admission.

The generated gear and route stages are current in DVC. Two preparation
failures occurred before any server started: stale generated-gear asset
bindings, then a stale route-stage fixture dependency. The route regenerated
unchanged. Workflow instructions now require both asset and exact route-profile
preflight before building. Neither failure is a boss attempt.

Independent Sol review verified exact resolved/native gear-manifest equality
for all ten bots and unchanged admission/current identities. Item 55159 is
absent. Heuristic tank/healer equipment and gems have positive acquisition
sources and no permanent enchants; only the exact DPS presets retain their
per-slot enchants/reforges. These fallback loadouts are legitimate equipment,
not a claim of fully enchanted best-in-slot tank/healer setups.

Fixed-bait Fire mage 30006 landed 41 Fireball events at average 37.049 yards,
versus zero in the preceding run. Its corrected gear/range edge is accepted.
Party DPS fell from 94,830.092 to 84,974.593 across changed gear, duration,
movement and survival; this is not a controlled single-variable tuning result.
The next bounded work unit is Elemental candidate coverage. Actor 30010 landed
four Lightning Bolts and zero Lava Bursts. Repeated `no_valid_profile_action`
diagnostics show aura, range and enemy-count gates excluding the available
spells. Join exact target/aura/count/range observations to eligibility before
assigning a repair; this is not evidence for coefficient tuning. The four
boss-fight deaths and other actors' movement/cadence losses remain visible in
the all-bot review. Do not rerun Magmaw just to reproduce these retained traces.

The closed run, exact inputs/build receipts, preparation-failure corrections
and independent all-bot review are published at
[`magmaw_development_48c4206346_20260908.tar.gz.dvc`](../../artifacts/cata_raid_program/magmaw_development_48c4206346_20260908.tar.gz.dvc).
The 32,647,161-byte archive was reconstructed from remote into a fresh empty
cache and hash-verified. Exact archive duplicates and local raw logs were then
evicted; the adjacent publication receipt records the checks and member hashes.
Historical results below retain their original scope; the earlier
gear-attribution correction remains applicable.

## Earlier Magmaw development clear

Source `fc2061c40cd92c348e7f0f97ec9e06edd6257fae` completed the canonical
10-player normal Magmaw route with native boss death, zero casualties, three
accepted terminal statuses, automatic controller exit 0, and zero remaining
bots or leases. Identity binding, trace continuity, combat-log transport, and
cleanup all passed. This is a development clear, not heroic/full-raid
qualification or training-data admission.

The accepted report, exact run inputs, build verification, and independent
outcome review are retained through
[`magmaw_development_fc2061c40c_20260907.tar.gz.dvc`](../../artifacts/cata_raid_program/magmaw_development_fc2061c40c_20260907.tar.gz.dvc).
The adjacent publication receipt records remote download verification and exact
local payload eviction. Restore that payload through DVC when investigation
requires raw events.

## Latest performance iteration: hunter range cap repaired

Source `d5bf3b804a488f7a880a1e1a693541fc5b012d00` corrected the Marksmanship
profile's false 35-yard maximum to the native 40-yard shot ranges (45 for Kill
Shot). Priorities, coefficients, gear, formation geometry, and movement code
were unchanged. The executable SQL regression and affected APL tests passed;
independent review approved the repair before one verified build and live run.

The same 10-player normal route cleared with native boss death, three accepted
terminal statuses, controller exit 0, verified cleanup, and all ten bots alive.
One warlock trash death was recovered before Magmaw; no bot died during the
boss fight. Party DPS increased from 79,977.972 to 94,830.092 over 316 combat
seconds versus 396 in the baseline. HPS was 16,259.737 versus 16,803.215.
Hunter DPS increased from 3,096.018 to 18,722.421, with Auto Shot landed events
98 versus 18, Steady Shot 29 versus 2, and Chimera Shot 21 versus 6.

The DPS reviewer verified attacks beyond the old cap without hunter hook duty
or generic range-movement oscillation. This accepts a range-eligibility repair,
not full simulator parity or a native damage-coefficient change. The evidence,
including the separately attributable baseline DPS analysis, is retained at
[`magmaw_development_d5bf3b804a_20260908.tar.gz.dvc`](../../artifacts/cata_raid_program/magmaw_development_d5bf3b804a_20260908.tar.gz.dvc).
The adjacent publication receipt records remote verification and exact eviction.

Keep one dedicated rotation/DPS reviewer on every run and carry its first
proven mismatch into the next work unit. The next proven DPS edge is fire mage
30006: exposed-head diagnostics reject Living Bomb and Fireball at the fire
profile's 35-yard cap although both native spells allow 40 yards. Scope the
next repair to the affected fire profile/actions; retain Fire Blast's native
30-yard limit, all priorities, coefficients, and fixed-bait geometry. Elemental
shaman throughput remains a separate diagnostic tail, not a guessed tuning fix.

The bounded hunter repair is complete. Continue the wider raid program using the
existing shared-worldserver instance workflow. Check native script readiness
before assigning another boss. Do not reopen historical fixture-admission
requests without new contradictory evidence.

## All-bot and external reference review, 2026-09-08

The clear and hunter repair remain accepted; overall roster DPS is unresolved.
The actual roster is 2 tanks, 3 healers and 5 DPS. It has not tested the requested
2 tanks, 2 healers and 6 DPS composition. Reassembled originated damage is
29,966,309 over a first-to-last damage span of 316.048 seconds, or 94,815.689 DPS.
The existing integer-second score remains 94,830.092. Neither the damage span
nor the report's broader 353.207-second event window proves an exact native
engage-to-death boundary equivalent to WCL. Boss/head-only originated damage is
22,769,032; linked-target transfer and vulnerability accounting still need parity.

Previous browser history retained direct `classic.warcraftlogs.com/reports/`
links. Opening these reports and their summary, damage and casts views worked
in the connected browser. Generic rankings/API access failure must not be
treated as proof that direct reports are unavailable. Anonymous access was not
retested after the user signed in.

- [June 21 kill](https://classic.warcraftlogs.com/reports/wPJW8z1mAQnd6jZh?fight=1&type=summary):
  10-player normal, 9 actual players, 2/2/5, average ilvl 382.89, rounded 2:36,
  173,500.5 DPS summed from displayed actor rows, including adds and pets.
- [May 22 kill](https://classic.warcraftlogs.com/reports/ZynLKgBwCQYDtHRM?fight=24&type=damage-done&targetclass=Boss):
  9 players, 1/1/7, average ilvl 401.56, 67.7 seconds, 376,176.7 boss-only DPS.
- [June 22 kill](https://classic.warcraftlogs.com/reports/64qa7t3RFnAX9GVf?fight=15&type=summary):
  10 players, 1/1/8, average ilvl 403.90, 53.2 seconds, 497,890.5 DPS summed
  from displayed actor rows. Its Elemental shaman cast 24 Lightning Bolts and
  6 Lava Bursts; its Fire mage cast 22 Fireballs.
- [Affliction actor](https://classic.warcraftlogs.com/reports/xAhkN2y9YP3KRmnJ?fight=10&type=casts&source=10):
  ilvl 403, 70.9-second kill, 28 Shadow Bolts and 5 Haunts. Marksmanship's
  inspected Phase 4.5 normal rankings were private; Survival is not a substitute.

These examples make 200k a plausible direction, not an established acceptance
threshold. None matches the requested composition and frozen gear; short kills
amplify cooldown and head-window effects. Full buff/phase/pet normalization is
incomplete. The review separates WCL casts from native landed events.

All ten bots have DPS/HPS and role-specific findings in the separately published
[reference review](../../artifacts/cata_raid_program/dps_cross_reference_d5bf3b804a_20260908.tar.gz.dvc).
It includes normalized WCL observations, exact source bindings, simulator action
comparisons, the damage-window calculation and remaining evidence gaps.

Correction from resolved provisioning and native gear manifests: the original
review inferred equipment from base profile names and missed the WoWSims
overlays. Affliction, Marksmanship and Elemental match their exact equipment
transforms. Both Fire mages instead wore the heuristic set despite an exact
profile label. Current pre-mutation database readback confirms item 55159,
`Rough Approximation Healer Robe`, on both Fire mages and the Discipline priest.
The native DB2 really records its 2,793 intellect and 4,191 stamina. The previous
artifact remains immutable; its base-profile overlap counts and Affliction
robe attribution are superseded by this correction. Live effective-stat parity
is still unproven, so no coefficient conclusion follows.

Next gameplay repair remains the proven Fireball/Living Bomb range cap. The
Elemental bot's one landed Lightning Bolt and zero Lava Bursts are the largest
unresolved cadence lead; trace its first rejection before modifying its policy.
Verify the gear authority and regenerate matching simulations before numerical
class tuning. Preserve the all-bot review on every subsequent run, including
tank threat/defensives and healer duty rather than judging them by DPS alone.

## Player gear repair awaiting live validation

The provisioning sources now explicitly select the canonical WoWSims DPS gear
profiles. The regenerated BWD shards preserve those bindings, and materialization
rejects a canonical label paired with different resolved equipment. Fireball and
Living Bomb eligibility are corrected to their native 40-yard ranges; Fire
Blast retains its native 30-yard limit.

Heuristic fallback equipment and gems now require positive retained acquisition
records from the DVC-bound world item-source index. Client definitions and
reference-loot placeholders cannot establish acquisition. Unsupported permanent
enchants are zero; exact WoWSims per-slot enchants are preserved. The generated
fallback profiles have complete equipment and sourced gems. They are legitimate
fallback loadouts, not a claim of fully enchanted best-in-slot optimization.

Focused tests cover acquisition rejection, unresolved socket gems, resolved DPS
profile equality, canonical-label mismatches, the missing-profile fallback,
direct-module imports and validator gem-catalog evidence. The old Fire source
smoke test follows the extracted persistent-setup module. Its source check is
not native behavioral proof. The separate generic loot scoring gate remains
unmet for unenchanted fallback profiles and is not used to certify this canary.

Initial preparation at `e6bdbd44aa` stopped before worldserver start because
the generated-gear asset class still pinned the old payload. Refreshing only
that class's expected files/inventory and DVC provenance passed the full runtime
input verifier with no issues. Native client/map audit and extraction bindings
remain unchanged. Future generated-gear changes must run this check before
building or provisioning.

The next run must use the corrected gear and report all-bot DPS/HPS, native
gear manifests, boss death and cleanup. The prior clear used invalid fallback
gear and does not prove completion under this corrected setup.

The entries below are historical investigation records. Their old "next" steps,
uncompleted claims, and fixture-bank requirements are superseded by this result
and the current development-mode skill.

## Historical shared-instance and Magmaw work

The shared-cohort native kernel is implemented and independently approved.
Runtime input reconstruction, full worldserver build, and remote publication
have passed. The third live canary at `00db4bec77` passed the shared-instance
isolation fixture after the complete recovery-observation repair.
No boss clear, accepted gameplay repair, or ML-data admission is claimed.

## Native implementation

Checkpoint `7daa4e0cbd` implements two active cohorts with at most one map worker,
per-cohort update scopes, lease/attempt/map/instance callback ownership, and
cohort-scoped cleanup. Ambiguous, stale, and foreign ownership fail closed.
Inactive shutdown cleanup also respects current lease ownership. Start-wrapper
scope restoration and denial paths preserve the selected cohort and profile.

The worker command executor permits only addressed known verbs, verifies native
registration before dispatch, and guards exclusive serial calibration against
foreign active cohorts. Calibration identity binds the actual native capacity.
Capacity-two serial evidence requires recorded exclusivity checks. Synthetic
ownership probes remain explicitly non-live evidence.

`shared_instance_observation.py` checks exact native rosters and current member
instance IDs. Sequential observations alone do not prove simultaneous execution
or callback/stop isolation. The live validation must observe both cohorts
advancing, correctly attributed native events, and continued witness progress
after the other cohort stops.

Native validation included 20 focused fixtures, translation-unit syntax checks,
73 integration checks and 29 Phase 9 checks. Independent capacity/exclusivity
review ran 56 checks and approved the change. The full link passed at
`d82a1f88de`; the reviewed Python protocol repair at `06996cc142` passed an
incremental build and receipt verification before and after the live run.

## Runtime inputs: verified and published

The immutable historical inventory and extraction-negative fixture are unchanged.
The current input manifest now explicitly uses verified materialization, with
historical extraction origin recorded as unknown. No historical extractor
receipt was invented and no client-data extraction was needed.

The entire native DataDir matched all 40,976 pinned entries. The archive was
published, downloaded through a separate empty DVC cache, extracted on persistent
ext4 storage, and verified against the portable inventory. Only directory
allocation size is excluded from comparison; paths, types, modes, and every
file's size and SHA-256 remain exact. Physical source inventory is retained.

- Archive pointer: `dataset/runtime_assets/native_inputs_03cb01db0b.tar.dvc`
- Archive SHA-256: `75ee7707bfca455868fb62f74be3c4a6667b4f2142f9161cd1caa224a18e10f1`
- Archive DVC MD5: `b1020765779cbccba103b8873dfb8c2e`
- Archive size: 5,256,591,360 bytes
- Materialization pointer: `dataset/runtime_assets/native_inputs_03cb01db0b.materialization.json.dvc`
- Receipt SHA-256: `d1a1bfd6cc62bc0f54ab77104c0e6071cc7dddc8907f8033b675e47eef8fdaaf`
- Verification pointer: `dataset/runtime_assets/native_inputs_03cb01db0b.verification.json.dvc`
- Verification SHA-256: `593821756506251785a2599c5c7e7f6463b3f3b1850e7a3ebcda129afb70dcbd`
- Promoted input manifest SHA-256: `ece9fd1784638946bfc324832dc857560a0633c4f27eb82fb4f66515394892a7`
- Passing input snapshot: `c5f8b77f264d0d3235670ea5bf23a46b27a0b20f96361c4375d9b5508ef02ead`
- Portable inventory: 40,968 files, eight directories, 5,224,209,638 file bytes
- Portable inventory SHA-256: `e6cd916f71b2a9bfb63694dbca78dcf3a5e510f9b00d9489552ef72b87440597`

Both metadata payloads were separately fetched through another empty DVC cache
and matched their SHA-256 hashes. Targeted local and cloud DVC status were in
sync before eviction. The verified reconstruction tree, workspace archive, and
exact archive cache object were removed, recovering roughly 25 GB. Native
DataDir, the small metadata, and required independent source inputs remain.
A missing local archive after this cleanup is deliberate; restore it through its
DVC pointer when needed. No broad DVC garbage collection was performed.

Code checkpoints are `03cb01db0b` (materialization), `d7e0900671` (explicit
archive resume), `831af130aa` (archive publication checkpoint), and `d3d8b87c5e`
(portable directory comparison). Root's final focused suite passed 85 checks;
independent final review passed 97 read-only checks. Real remote reconstruction,
not these fixtures alone, established the production input proof.

## Causes of the input loop that were repaired

1. Source and native roots aliased the same eight MMAP files while requiring
   modes `0444` and `0664`. Their bytes matched throughout. Changing modes only
   transferred failures between consumers. The new preflight reports the root
   contradiction before reading assets; independent copies satisfy both.
2. A missing historical extraction receipt was treated as essential even though
   its producer only records caller-provided extraction metadata. Verified
   materialization now proves current reproducibility without inventing history.
3. `/dataset/*` hid newly generated `.dvc` pointers. Narrow pointer exceptions
   and explicit verified archive resume avoid repeating a completed capture.
4. Reconstruction in `/tmp` hit its tmpfs quota. Exact failed copies were
   cleaned; multi-GB reconstruction now uses persistent storage.
5. Directory `stat.st_size` made reconstruction dependent on filesystem layout.
   The portable comparison excludes only that allocation detail.

The first two publication failures were local pointer visibility and extraction
quota failures. Neither was a live bot attempt. Historical failing snapshot
`b6bc5ac7429957736b9a3a9e90ff58785c39bb53f9a3df004b2d209aa2aacdd7`
is superseded by the passing current input proof, not rewritten as success.

## Next bounded work

The concrete pair is frozen in
`experiments/configs/cata_shared_instance_fixture_v1.json`: Magmaw cohort
`bwd_magmaw_diagnostic_10n` (GUIDs 30001–30010) and Omnotron witness
`bwd_omnotron_diagnostic_10n` (GUIDs 30101–30110), both map 669, difficulty 0.
The fixture proves isolation only. It cannot certify either boss, predecessor
state, heroic progression, or training-data admission.

The shared driver must prove advancing native outgoing outcomes and decisions
in both instances while both are active, stop Magmaw, collect a fresh witness
baseline after that stop, and then prove further witness outcomes with the same
identity and retained movement evidence. It stops both addressed cohorts and
verifies cleanup. Its successful observation ends as typed `interruption`, not
an encounter clear.

The coordinator entry point is `tools.raid_program.run_shared_instance_canary`.
Run it from the frozen checkout with `--source`, the Git common `--repository`,
the verified `--build-receipt`, and a new external `--output` directory. It
derives the authenticated shared base config, verifies source/build/assets,
provisions and reads back the exact pair under the lifecycle lock, starts an
attached server, binds the responding native PID, drives the fixture, and closes
the owned server. No SOAP credential or single-boss Chainwielder overlay is used.

Preparation found and repaired another cross-cohort defect: provisioning a
subset still deleted the entire validation item GUID range. Item cleanup now
joins through selected character ownership, and allocation retains offsets from
the full frozen layout. The regression compares selected item IDs with the full
layout and exercises preservation of excluded inventory and item-instance rows.
An older test explicitly required the destructive global-range deletion; that
assertion now requires owned cleanup.

Combat exports now carry the generic epoch/attempt/profile identity already
present in status and trace. Diagnostic polling no longer overwrites last real
decision history for detached bots. Independent Sol static review approved
these native changes. Compilation and linking passed; the first live outcome
is recorded below and does not accept isolation.

The final independent Sol review approved the repaired driver and launch
helpers. The combined shared-instance, provisioning/readback and transport
suite passed 108 tests; the focused existing provisioning suite passed 36.
These include real-process executable replacement and SQL cleanup regressions,
but the two-cohort protocol fixtures are synthetic and do not certify live
isolation. A read-only database preflight found all 385 planned item IDs owned
by the selected cohort names, with no foreign or orphan collision.

The driver rejects reused cohort identities and ambiguous create ownership,
uses independent unfulfilled-cohort progress budgets, reconciles every visible
new combat suffix with outgoing aggregates, and anchors actual witness movement
receipts across the stop. The narrow combat reducer was implemented by a
Luna max worker and included in independent Sol review.

One coordinator owns
the shared binary, configuration, provisioning, console and server lifecycle.
Workers receive addressed cohort access only. Individual interruption must stop
that cohort and preserve the shared server and every other active instance.

The frozen checkout is
`/home/runiir/Games/trinity-shared-instance-validation-03cb01db0b/source`,
Git-clean at `06996cc142`. It retains the verified independent runtime inputs
and the built binary. The live launcher used its derived shared config and
successful build receipt, provisioned only the selected pair, and passed both
fresh database readbacks.

## First real canary

The run at `06996cc142` admitted both cohorts on one server epoch. Its first
complete observations showed Magmaw in native instance 13 and Omnotron in
instance 2, with disjoint group IDs and ten leases each. The baseline measured
Magmaw DPS/HPS 0/0 and witness DPS/HPS 0/11323. These are brief startup
measurements, not class calibration or encounter performance results.

Later witness status reported two deaths and diagnosis reported six alive
members. The driver stopped at `native_instance_identity_invalid`, with typed
termination `contamination`. Independent replay traced the rejection to status sequence 43: difficulty
readback became incomplete while ghosts were outside the raid during native
corpse recovery. Diagnosis sequence 44 retained exact frozen instance and
attempt-bound recovery for those ghosts. Native ownership allowed this state;
the Python validator did not. No cross-cohort ownership leak was observed.
The next repair recognizes only that exact native recovery state and preserves
the chained diagnostic reason. The failed run remains unchanged.
Both addressed cohorts were stopped, all leases were released, and the owned
worldserver exited with code 0. No witness-after-subject-stop proof was reached.

Before launch, a real protocol mismatch was repaired: successful native start
returns `botauto_status`, while the transport and its fake test expected
`botauto_start`. Native combat-log rejections also need prompt recognition
rather than waiting for chunk completion. Focused real-child transport tests
now cover these variants, including incomplete chunks. Independent Sol review
approved the repair; the shard skill now requires native handler-derived reply
fixtures. No native gameplay change was needed for this correction.

The closed run, raw console/command responses, exact config, provisioning SQL,
readbacks, and both build receipts were archived to
`artifacts/cata_raid_program/shared_instance_06996cc142_20260907.tar.gz.dvc`.
A fresh empty-cache remote download matched archive SHA-256
`cd7264c204d2305172879144231a32e6f8a094c66bc53a9360a9bd086053a35e`.
Targeted local and remote DVC status passed. The retained publication receipt
records the round trip. The run is closed and training-ineligible.

Then repair generic profile admission: `IsValidationProfileName` currently
accepts only ten-player normal Blackwing Descent. Heroic, 25-player and other
raid maps remain separate work. Route absent boss scripts to native encounter
implementation. Route matched-cadence damage defects to native class mechanics
and matched-damage cadence defects to role policy. Do not remain on Magmaw after
its current edge is accepted or replaced by a different proven blocker.

## Revised canary and next bounded repair

Commit `3490069d1c` recognizes native-authorized in-world ghost runback with
exact corpse, frozen-instance and recovery-attempt evidence. Its exact replay
and ownership negatives passed with the other focused checks (65 total), and
independent Sol review approved the change. Error reports now retain the
chained cause and precise pre-cleanup raw command sequence (`565a7f5a65`).

The revised run again admitted both instances, then stopped at raw sequence 44.
GUIDs 30102 and 30104 were temporarily `in_world=false` during
`released_ghost_observed`, while native `matches_cohort=true`, corpse presence,
locked map669/instance2 and attempt1 remained intact. The native ownership
predicate explicitly supports released ghosts through their corpses before its
ordinary in-world check. The Python observation still required in-world on
every poll, so it rejected this earlier transfer boundary. This is the second
recovery-observation failure, not evidence of foreign ownership or a boss clear.
Both cohorts released all leases and the worldserver exited normally.

The next work unit must cover release, worldport, runback, return and stable
in-instance observation together. It must distinguish a legitimate transient
observation from accepted progress and from a foreign identity; no dead or
absent member may fabricate the witness-continuation proof. Replay both closed
runs and all foreign/stale-ownership negatives before any further live attempt.
Do not repair these transitions by repeatedly launching Magmaw. The broad
recovery-observation recurrence count is two; changing sub-error labels must
not reset it.

The revised evidence is published at
`artifacts/cata_raid_program/shared_instance_3490069d1c_20260907.tar.gz.dvc`,
archive SHA-256 `b40acec9cceec76256e9e733a50660c41b807a654681cff62871a6cc88851a26`.
An empty-cache remote download matched; local/cloud status passed before exact
archive-copy eviction. Raw command/console data remains remote reconstructible.
Both runs remain training-ineligible. Class balance and boss fidelity cannot
be assessed from these short isolation failures.

## Recovery sequence revision

The validator now accepts temporary absence only during the three native
release/entrance transfer phases, with the same exact corpse, attempt, group,
roster and frozen-instance authority. In-instance ghosts remain attributable
through reclaim; a complete later difficulty diagnosis can supersede an earlier
incomplete status sample. Transfer GUIDs are retained in heartbeat evidence and
neither boundary of such a sample may certify outgoing progress. Both original
closed native failures are retained as exact field projections, with additional
release/runback/re-entry/reclaim sequence and foreign/stale negatives.

The focused suite passed 76 checks and independent Sol review approved this
revision. The next action is one incremental build and bounded isolation canary,
then the user's requested Magmaw completion attempt under the completion
watchdog. No boss clear or full isolation claim exists yet.

## Accepted shared-instance canary

The real run at `00db4bec77` passed the complete isolation fixture. Both cohorts
advanced in disjoint native instances (subject13, witness2) on one server epoch.
The subject recorded 610 decisions, two native events and 3,390 outgoing amount;
the witness recorded 214 decisions, 197 events and 411,867 outgoing amount before
the stop. After the subject stopped, the witness advanced from 253 to 316
decisions, 207 to 230 events and 467,573 to 595,903 outgoing amount under the
same identity. Actual movement evidence survived the scoped stop. No transfer
snapshot was used for progress proof. The witness had ten deaths; this fixture
does not certify its encounter behavior or DPS.

Both cohorts released their leases and the owned server exited0. The terminal
reason is `interruption` / `isolation_fixture_passed`, not a boss clear.
Post-run source/build receipt verification passed. DVC publication and a fresh
empty-cache remote download matched archive SHA-256
`2fa56493e659e87dff0540e1ae55d8e3a91c865f3045ab6d58e4ae3fb9b5a86a` at
`artifacts/cata_raid_program/shared_instance_00db4bec77_20260907.tar.gz.dvc`.
Local/cloud status passed and exact verified archive copies were evicted.
The two earlier recovery-observation failures remain retained, followed by this
passing verification; their recurrence history is not reset.

The user's next requested work is a real Magmaw completion attempt using the
existing single-boss completion-watchdog capture workflow, with its current
recurrence admission and exact roster/configuration. The isolation phase is
complete. Magmaw has not been killed and no ML data admission is claimed.

### Capture completion correction before Magmaw launch

The prepared 00db4bec77 Magmaw bundle was not launched. Independent review
found that Python accepted arrival at a partition's terminal node before the
boss died. Native route completion already requires confirmed boss death.
The capture acceptance repair requires native manifest completion, scoped
terminal evidence and matching terminal-boss death evidence. The historical
foundation arrival smoke keeps its original limited claim. All 266 capture and prestart-bundle tests pass, including arrival, wrong-boss
and stale-generation counterexamples. Acceptance uses the authenticated runtime
route suffix (three nodes) rather than the canonical four-node source route.
A production-bundle regression accepts generation 3 completion and rejects arrival.
Review and a refreshed source-bound build/admission precede the live attempt.
Magmaw remains uncompleted. Existing recurrence blockers require a diagnostic
fixture-expansion capture before ordinary gameplay admission.

The 20fed2e904 launch was rejected before worldserver startup by
`runtime_route_dvc_lineage_dirty`. Reproducing only `validation_scenarios`
changed no generated bytes; its lock still named an older common.py digest.
The lock is refreshed, and exact upstream report/cache hydration is required
in the frozen checkout. No live attempt or boss outcome occurred.

Independent Sol review approved the capture repair and the bounded regression
runner optimization. `--run-suite` now executes each fixed command once and
uses its actual in-memory results, rechecking source/config before evaluation.
External receipt verification still replays every command. All 48 ledger tests
pass, including real subprocess execution counts for passing and failing
fixtures, external replay, and preservation of latest-run decision attribution.

### Closed Magmaw diagnostic b0c7f38b0a

One worldserver ran one admitted Magmaw diagnostic (epoch 191320230607534,
instance 2, attempt 1). Chainwielder and Drudges cleared. The bots engaged
Magmaw, and the corrected acceptance predicate retained zero accepted statuses
at boss-node arrival. No native Magmaw death was observed.

The controller terminated at 624.311 seconds with `death_loop_watchdog`.
Inspection found that the watchdog counts distinct actors' first deaths toward
a route-wide loop limit. The terminal status has four deaths and six survivors;
this does not establish repeated recovery/death cycles. This is the next
validator repair, while the earlier gameplay mismatch is being diagnosed
independently. Keep the raw report's classification unchanged and annotate the
termination defect; do not relabel the attempt as a clear.

Magmaw combat analysis: 26,495,960 originated damage, 72,393.333 DPS and
21,364.022 HPS over 366 active damage seconds (384.101 elapsed encounter
seconds). Elapsed-window values are 68,981.752 DPS and 20,357.229 HPS.
Raw damage callbacks include transferred damage and must not be substituted
for originated damage. Both trash clears are retained as native terminal
evidence. All final telemetry channels, cleanup, server exit 0, and postrun
build verification passed.

Evidence: `artifacts/cata_raid_program/magmaw_b0c7f38b0a_20260907.tar.gz.dvc`.
The 26,026,682-byte archive reconstructed from remote into an empty cache with
SHA256 `133bbf8697ea8183701ae9b782ed34b2c3003dbdb0b5a61052401afab8d5dbad`.
Archive duplicates are evicted; raw evidence remains only during active causal
review. The run is not training-eligible or boss-clear qualifying.

## Reviewed repairs after the b0c7f38b0a attempt

The completion watchdog now counts canonical native death episodes per admitted actor and deduplicates native wipe generations. It rejects foreign attempt, route, and roster observations before updating cursors. Distinct first casualties no longer terminate a progressing pull as repeated death loops. Independent Sol review approved the repair; 40 watchdog tests and 48 recurrence tests passed. Existing diagnosis fixtures now use members of their declared roster.

Commit 4fbab0ce87 repairs fixed-baiter first contact by selecting the opposite checked lane endpoint immediately. Five policy tests and two directional integration tests passed, including GUID churn and unsafe-anchor cases; independent Sol review approved. Native pathing and floor rejection remain intact. Neither repair has live validation yet.

Next: build the reviewed source once, execute the 29-entry recurrence suite once, seal current configuration/route/provisioning, and run one bounded Magmaw completion attempt. The previous canary killed trash but did not kill Magmaw.

The first 29-entry admission suite on 272b596a07 passed 25 entries and rejected four entries that reuse two legacy arbitration tests. Their retained radial-state assertions conflicted with the approved fixed-lane contract. Both duplicated blocks now check exact opposite anchors, updated shared transition identity, stable GUID-churn behavior, and clearance. No production change was needed. Independent Sol review approved; the full arbitration file passed 13 tests and policy/directional checks passed seven. Run the full suite before the next build-receipt refresh.

## Closed b60350a657 Magmaw validation

Source b60350a6575ad494408bc81c937a5c9a47a9c1f2 passed all 29 admission entries, independent review, queued build verification, sealed route/configuration and exact roster readback. Chainwielder and Drudges cleared. Three first casualties recovered and the controller correctly continued. Hunter 30009 contact escapes reached the checked fixed endpoint through native submission; the former off-platform radial rejection was absent in the observed contact sequence. This is a positive submission proof, not full parasite-mechanic acceptance.

Magmaw was not killed. The first boss-route death was healer 30003; no exact lethal-event attribution was available. The pull collapsed and the roster recovered into another pull. Final boss-route aggregates span pulls and adds: 42,566,340 originated damage, 72,268.829 active DPS and 23,671.491 HPS. Boss HP was unavailable. Across recording windows there were 13 casualties and 15,301 decisions; the final pre-cleanup roster had nine alive.

At the 15-minute statistics-window boundary, run 31/autonomy_window_0 became run 32/autonomy_window_1 while server epoch 3980418384854960, attempt 1, instance 2 and route generation 3 remained unchanged. Native trace sequence counters reset. The watchdog's attempt-scoped cursor could consequently reject later events as old. The coordinator interrupted through the capture controller rather than allow an unreliable retry loop. Classification is infrastructure_abort/operator_interrupt, with no boss-clear or training claim. Cleanup verified zero bots/leases and absent worldserver, exit 0; post-run build receipt remained valid.

Evidence is remotely verified through a fresh empty-cache DVC download: `artifacts/cata_raid_program/magmaw_b60350a657_20260907.tar.gz.dvc`, SHA256 e15eb53e7bd93327add72f97c7629c21bbce6c3dfb50675e27d1508998a12c47. The archive includes compact babysitter and rollover evidence, raw/report/log bytes, build/config/route/provisioning bindings and the two rejected prelaunch suite records.

Next bounded dependency: preserve native trace continuity across statistics windows, retaining genuine stop/profile resets, with a compiled producer fixture and independent review. The existing source-shape test required the defective reset; replace that requirement with executable continuity coverage. Do not retry the old source. After that repair's live verification, investigate the first healer death from an attributable lethal-event join rather than guessing a class coefficient or relaxing movement safety.

The trace-continuity repair is now independently Sol-approved. Statistics-window rotation no longer invokes `ResetTraceStreams`; genuine stop/profile resets remain. A compiled test of the actual producer failed with the old reset restored and passed across two rotations with trace sequences, unexported rows, export cursors and planner receipts preserved. Seventeen focused tests and 48 ledger tests passed. This latest native repair has not yet been built into or exercised by a live canary. The next admission bank has 30 fixtures and retains the new occurrence without erasing prior failures. Published raw logs and obsolete prelaunch copies were evicted after exact member-hash verification; compact reports remain and the full archive can be hydrated for the healer investigation.

One unchanged retained Stage3 test depends on an old checkout with stale route payloads; its failure was reproduced against unmodified HEAD authorities. Current map 0 and 669 production admission both pass. Proceed with the reviewed batch and one native Magmaw run.
