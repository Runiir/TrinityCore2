# Dedicated post-run DPS review

Own the DPS diagnosis for one closed run. Read the report and existing combat
aggregates first; request only missing trace/reference payloads from the
coordinator. Work directly, without nested workers. Do not change gameplay,
launch a server, generate new simulator references, or publish/evict evidence.

Read those inputs through [evidence-views.md](evidence-views.md): compare retained
runs/references first, then query the selected actor/spell/interval. The commands
compute differences locally and keep raw logs out of routine model context.

Bind the review to the report hash, source/binary, server epoch, attempt, cohort,
instance, route node/generation, roster, and promoted reference catalog. State
which comparisons are admitted and which lack setup/stat parity. A valid boss
clear remains valid even when the DPS review identifies inefficiency.

Resolve gear through the actual provisioning pipeline, including explicit bot
equipment and WoWSims overlays. Use the run's native `gear_manifest` and bound
inventory readback for comparison. A class name or base profile is not evidence
of equipped items. Item-level limits and name filters do not prove player
obtainability; retain the approved acquisition/preset source. Correct a prior
misattribution with attributable supplemental analysis, preserving the original.

Start with the complete roster, including every tank, healer, DPS, and owned
pet. Record actual and requested tank/healer/DPS counts; never silently compare
a 2/3/5 run with a 2/2/6 target or change the frozen roster to fit a benchmark.
Report DPS and HPS for every bot. Review tanks' offensive uptime alongside
threat/defensives and healers' damage opportunities alongside healing, mana,
and preventable deaths. A low healer DPS number alone is not a defect.

In the bot timeline, `activity.active_seconds` counts absolute one-second
buckets with effective healing or originated hostile damage, including pet/DoT
tails. It is not offensive or cast/GCD uptime. Use
`fresh_attack_active_seconds` for buckets with owner non-pet direct hostile
impacts, and the separately named submission/outage fields for their stated
boundaries. Neither bucket count measures time spent casting. Legacy captures
mislabel the enclosing `metric_scope`; preserve their numbers and correct the
interpretation instead of treating a healing-only actor as actively attacking.

For every DPS actor and spec, report available evidence for:

- Originated damage and DPS using the same encounter denominator for every
  actor; distinguish boss, required adds, incidental targets, and pet damage.
- Landed events and damage per event by spell; call them cast counts only when
  native cast/submission evidence actually supports that measurement.
- Eligible action cadence, idle/backoff episodes, target switches, range/LOS,
  movement, mechanic assignments, and opportunities to cast while moving.
- Cooldowns, profession/racial actions, food/flask/potion outcomes, resource
  gates, and pet cadence/target uptime when captured.
- Exact promoted WoWSims APL, result action mix/cadence, pet contribution,
  cooldowns, resources, and effective-stat/setup comparison. Do not stop at
  quoting a simulator DPS total. Record missing inputs per actor rather than
  omitting the actor. The promoted catalog supersedes embedded DPS figures.
- Warcraft Logs comparison to identified Cataclysm kills. Retain report URL/code,
  fight and actor IDs, date/patch, difficulty, raid size/composition, gear tier,
  kill duration, buffs, target filters, head/vulnerability phases, and the DPS
  denominator. Use several comparable strong kills when available, avoiding
  a single padded/outlier parse. Normalize observed spell mix, casts per minute,
  active casting, pets, cooldown/potion timings and target damage into the
  compact review; retain observations separately from inferred recommendations.
  Check retained report URLs and previous research/browser history before
  declaring an access blocker. Direct report pages may work when rankings or
  API access do not. If login/API/report access is unavailable, record the attempted source and
  exact blocker. Do not call the Warcraft Logs comparison complete or invent
  a benchmark from snippets. Continue comparisons supported by local evidence.

Party damage may include tanks, pets, adds, encounter-attributed effects and
redirected damage. Use the existing originated-damage accounting rather than
summing raw mirrored events. Use complete fight elapsed time for comparisons
with Warcraft Logs when its
DPS uses that denominator. Preserve the existing scored/active-second number
as a separately named metric; never compare it directly to elapsed-time DPS.
State whether transfers between linked targets are deduplicated and whether
pets and adds are included. A spell's moving-event fraction is not the actor's
movement uptime; a DOT ticking while
moving does not prove a lost hard cast. Boss vulnerability phases also prevent
direct damage-per-event comparison with an unmodified dummy reference.

For missing actions, inspect full diagnose snapshots before declaring candidate
telemetry absent. `snapshot.policy.valid_action_mask_json.actions` retains each
spell's eligibility, rejection reason and score; `chosen_action_json` retains the
resolver choice. Join them with `snapshot.combat_attempt`, native outcomes and
matching attempt/route/decision timestamps. Check evaluation purpose and
selector filters: passive range previews in older builds can overwrite the
execution mask with a different, never-submitted choice. A melee fallback can overwrite the
failed spell in the compact attempt summary. Compact trace rows alone do not
establish that a spell was never selected or that a new observer is needed.

Trace the largest suspicious loss through observation, eligible candidates,
selected candidate, resource claims, native submission, and landed outcome.
Distinguish established defects, plausible leads, and unavailable evidence.
Give each actor an explicit finding: proven defect, plausible loss requiring
one observation, no defect found in inspected evidence, or not yet reviewed.
Rank improvements across the roster before selecting one bounded implementation;
"one repair per iteration" does not mean "review only one bot."
Do not estimate recoverable DPS by subtracting an unmatched simulator total.

## Account for the DPS loss before selecting a repair

For a DPS optimization task, add this accounting to the existing `dps_review.json`
before handing off an implementation. Reuse retained reports and simulator
results; no new logger, simulator run or live canary is required for this step.
A visible APL difference alone is not a quantified performance cause.

1. Join the native report with the pinned request, aggregate result, ComputeStats
   and relevant debug timeline. Bind actor, window, target filters, owner/pet
   attribution and setup. A normalized review with `runtime=null`, missing stats
   or rejected comparison gates cannot establish matched damage or cadence.
   Restore/join retained inputs first; keep trace-only findings within their scope.
2. Produce a signed table by spell/effect and owner/pet: native/reference damage
   and DPS, ordinary cast starts, hits, crits, ticks, triggered copies, damage per
   comparable event, and limitations. Use matched scoring windows or describe
   encounter/phase/duty normalization. Losses and native gains must reconcile to
   total reference-minus-native DPS, including a numeric unattributed residual.
   Unknown attribution is not zero missing damage.
3. Separate player actions from passive/triggered copies before comparing cadence.
   Preserve simulator ActionID tags and native trigger provenance. For example,
   pinned WoWSims Dragonwrath copies use tag 71086: they contribute damage, not
   extra player casts or GCDs. Verify producer semantics for other tags. Keep
   copies, DoT ticks, AoE impacts and pet actions out of ordinary cast counts;
   unknown native provenance remains unclassified rather than assumed ordinary.
4. For the largest losses, separate event-count from damage-per-event differences.
   Check class-state/phase coverage, DoT refreshes, buff snapshots, cooldowns,
   pets, misses and crit/proc variation as relevant. Account for casting/channel/
   GCD time, waits, movement, target loss and duties without overlapping intervals.
   A damage-event gap is not automatically idle time; fewer casts do not prove
   why time was lost.
5. Rank apparent losses separately from proven recoverable gains. For the selected
   repair, give a bounded net DPS estimate or justified bound, its supporting
   observations, damage/time sacrificed to the replacement, uncertainty, and the
   strongest conflicting evidence. Do not sum overlapping gains. Two extra
   instant casts cannot alone explain many seconds of missing filler without
   another measured mechanism.

Use a compact row shape such as:

| Component / owner / event kind | Native DPS | Reference DPS | Signed gap | Count / size evidence | Cause status | Next check |
| --- | ---: | ---: | ---: | --- | --- | --- |

Keep `proven`, `hypothesis`, `expected duty/setup effect` and `unknown` distinct.
Arithmetic reconciliation is required; proving every cause is not. If the selected
gain cannot be bounded, return a diagnosis task with the missing join/observation
instead of guessing an implementation. A small correctness repair can still be
justified explicitly, but cannot stand in for closing the main DPS gap. Tank and
healer throughput remains subordinate to their role obligations.

After a decline, compare with the identified prior baseline and reconcile changed
component damage first. Inspect retained event/crit/proc variation before blaming
a single-run difference on code. Use a bounded matched repeat only if uncertainty
cannot be resolved offline. Revert or replace a change when controlled evidence
establishes regression; preserve unrelated repairs. Matching cast totals or a
passing behavior fixture does not establish a performance improvement.

The reviewer checks joined inputs, event classification, reconciled totals and
the repair estimate before approving a DPS optimization patch. Optionally send Jev/Laya the
largest signed gaps, unknown residual, selected estimate and acceptance limits;
agreement with a prose hypothesis does not explain the loss.

## Select the next work unit

Rank large unexplained component differences separately from small proven bugs.
Join duty/vehicle/safety intervals before labeling a cast gap avoidable; union
overlaps and retain unknown boundaries. Assignment time is not automatically
zero-casting time. Never divide total damage, including DoT/pet tails, by
duty-free seconds. Compare body/head/add mix, phase exposure, buffs and spell
aliases before attributing cadence or hit-size differences to code. Report
stronger native components too: they can mask deficits or expose accounting and
mechanics problems. A familiar small defect must not displace a larger unresolved
signal merely because its implementation is ready.

For a compact first comparison, normalize visible WCL component DPS into reviewed
actor/selector records, retain the source tables, then join the existing timeline:
`pixi run python -m tools.raid_program.evidence_view compare --current report.timeline.json
--wcl references.json --actor ACTOR`. This reuses `rank_raid_damage_gaps` and ranks apparent
differences, not recoverable gains. Bind duty annotations to the exact timeline
identity; record missing phase/stat/duty parity and the next discriminating check.

Return one compact `dps_review.json` and a short readable summary alongside the
run. Reuse existing rotation-review output for exact spec comparisons. Include
the per-actor findings, reference/measurement limitations, and the highest-value
bounded next work unit with its counterexample, production callers, owned files,
forbidden changes, focused test, and next-run acceptance condition.

Close the review once the all-bot table, repaired-edge verdict, available
reference comparisons and one bounded next task are recorded. Reuse retained
normalized references and existing report aggregates. Do not delay a proven
canary's publication to build a bespoke analyzer, expand a dossier or solve
the next repair. If causality is unresolved, return a diagnosis task with the
exact trace and missing join; do not invent implementation files or a fix.
The coordinator may package a compact reviewer response into the run's evidence.

Route cadence/priority/resource/pet-policy defects to role implementation;
shared arbitration/movement/target-ownership defects to runtime implementation;
matching setup/stats/cadence with incorrect event damage to native class
mechanics. Missing parity data means request that observation, not guess a
coefficient. Exact dummy calibration lasts 300 seconds; raid runs remain
completion-watchdog driven.

Keep three conclusions separate: encounter clear, acceptance of this repair,
and overall roster performance. A kill or one improved actor does not establish
that all bots meet their performance targets. State which actors and external
comparisons remain unresolved, and derive any aggregate target from the actual
composition and matched evidence rather than installing an arbitrary DPS gate.

On the next run, compare the repaired edge, per-actor output and clear/survival
outcomes against the prior review. Admit only the improvement actually observed.
Choose one next actionable loss; do not reopen repaired lifecycle failures or
require a new documentation/authorization chain for ordinary tuning iterations.


## Compact local-Jev and Luna handoff

Use [the local shadow commands](../../../../docs/bot_raids/local_jev_shadow.md)
after native closure. Do not send the entire group packet to the 8 GiB local
service. Keep the exact per-actor inputs, responses and model revision. Local
confidence or agreement with hosted Jev is not evidence that a repair is right.
Run deterministic checks on predicted assignment/repair eligibility. Preserve
contradictory predictions as diagnostic negatives pending adjudication; do not
execute them or silently discard them.

Before dispatch, keep a single all-roster table with DPS/HPS, known duties,
reference availability, the largest component differences and unresolved edges.
For same-spec peers, decompose the total gap by spell and owner/pet using the
same native interval. Check setup and assignment differences before treating
that gap as recoverable. Native rejection reasons can establish a blocked
spell; its missing damage does not establish the amount a repair will recover.

Send a Luna max worker one short packet, linked to existing receipts:

1. Mode: diagnosis or implementation; exact error-ledger ID and first broken edge.
2. Frozen code/source, run/report hash, actor/target/spell and the decisive rows.
3. At most one hypothesis, including the strongest conflicting observation.
4. Exact owned production/test files and affected callers. If those are not
   known, dispatch diagnosis, not a guessed implementation.
5. Forbidden changes: other specs, coefficients without parity, global safety
   bypasses, altered boss values, teleport/Z steering, metrics/denominators.
6. One production-path counterexample, required Pixi test command, and expected
   native submission/landed outcome. A string assertion is insufficient.
7. Acceptance: clear, intended behavior, and all-roster performance are separate.
   Coordinator owns the single reviewed build/watchdog run and DVC publication.

Worker returns changed files, test result, proven behavior and unknowns. It
must not launch another worker or a live server. Reuse existing references;
request the exact missing observation once. At the next run review the whole
roster again, without reopening previously accepted edges.
