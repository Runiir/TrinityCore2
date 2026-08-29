---
name: raid-performance-loop
description: Coordinate the Trinity-Cata raid performance program by inspecting deterministic readiness, selecting bounded specialist work units, assigning non-overlapping ownership, and joining handoffs. Use for raid-program orchestration, deciding what class/boss/reference/data task should run next, splitting work across agents, or preventing one agent from owning WoWSims, class rotations, boss research, boss implementation, live validation, and ML data at once. Do not use this skill to implement gameplay behavior itself.
---

# Raid Performance Loop

Act only as the coordinator. Keep specialist context and file ownership separate.

## Inspect the control plane

Run:

```bash
pixi run python -m tools.raid_program.raid_workloop status
```

Treat `required_next_work_unit` as authoritative. If the active-work-unit
descriptor is stale, stop before assigning gameplay work
and repair that descriptor from the latest immutable handoff.

Then emit an exact work unit when needed:

```bash
pixi run python -m tools.raid_program.raid_workloop spec fire_mage
pixi run python -m tools.raid_program.raid_workloop boss blackwing_descent magmaw --mode 25H
```

Do not treat a stale WoWSims value, source-present boss, dossier, diagnostic
shard, or old DVC batch as a passing gate.

Keep validation clocks explicit in every work unit. Only isolated
training-dummy DPS throughput calibration owns an exact 300-second scoring
window. Raid and dungeon work units must use completion-watchdog execution and
terminate on normal clear or typed semantic/no-progress, repeated-decision,
death-loop, infrastructure, contamination, or interruption evidence. An
emergency wall-clock expiry never passes a route.

For a DPS work unit, inspect the rotation-review gate before assigning a role
implementation owner. The exact simulator and Trinity inputs must have the same
gear identity, and the comparison record must report:

```text
gear_parity.status = match
effective_stat_parity.status = match
dps_tuning_gate.tuning_admitted = true
```

Total-DPS claims additionally require
`total_dps_comparison_gate.comparison_admitted = true`. Consumable mismatch
fails that total-DPS gate without invalidating unaffected trace-only signals.

For `self_provided_baseline`, the reviewer's `match` may contain explicit
one-sided `favorable` throughput-stat checks. Do not reopen those as blockers;
lower stats, gear drift, and rating drift remain blocking mismatches.

`insufficient_data` routes to one bounded reference or capture work unit.
`mismatch` routes to the owner of setup, stat application, or pet inheritance at
the reported first-broken edge. Neither result may be retried as rotation tuning,
and neither permits the coordinator to stop or restart the worldserver.

Bind every DPS claim to one reference class. Use `self_provided_baseline` as a
one-sided minimum floor with no upper rejection bound. It includes only effects
the frozen player can provide through its own setup and normal actions. Require
per-spec inventory provisioning and native use of the exact flask, food,
pre-pot, combat potion, racial, and profession actions selected by the request.
Use `controlled_live_parity` for exact cast, cadence, stat, and damage diagnosis.
Keep `upstream_full_throughput` as a duration-bound capability/UI cross-check.
Differences among these values are expected and do not block trace-only review.
A missing class blocks only its own acceptance claim.
The current work unit's catalog projection is authoritative for current versus
stale classification. Embedded metadata in an older runtime report remains
capture-time provenance and cannot override `accepted_dps_reference_class` or a
`current_accepted` catalog classification.

Use deterministic routing for an `insufficient_data` result:

- missing WoWSims ComputeStats -> `raid-wowsims-reference`;
- missing Trinity `scoring_start_stats` in a closed report ->
  `raid-shard-architecture` for one capture-only canary that preserves the
  existing worldserver lifecycle, followed by `raid-rotation-review`;
- a malformed comparison artifact -> `raid-rotation-review`.

When WoWSims reports `workspace_state=remote_requires_hydration`, run the
commands from `required_hydration_work_unit` exactly. This is materialization
of an already promoted reference, not reference regeneration and not a class
fix. The normal sequence is:

```bash
pixi run python -m tools.raid_program.wowsims_reference_workspace hydrate
pixi run python -m tools.raid_program.raid_workloop status
```

After the bounded reference/review work finishes, run the emitted exact
`evict_after_use` command. Never replace it with broad DVC garbage collection.

The completed comparison is `failed` when one of these data gates does not
pass. Do not classify it as `blocked` unless authority or an external input is
actually unavailable.

## Route work to one specialist owner

Before dispatch, create the worker's scope lock using
[references/bounded-work-unit-contract.md](references/bounded-work-unit-contract.md).
Include that lock verbatim in the worker prompt. Reject changed files, commands,
or extra fixes outside it; useful adjacent findings become a new work unit.

Use decision complexity as a routing signal when a trace shows ownership
conflicts, oscillation, or opaque fallback behavior. The 2026-08-28 native bot
baseline was average CCN 15.80, p95 73, 45 functions above 100, and maximum
464. Re-measure before acting because the tree changes. Route one bounded
policy extraction to the specialist that owns the first broken edge. Do not
assign a generic cleanup or accept a refactor that only moves branches into
helpers. The handoff must preserve typed priority-queue candidates, explicit
resource claims, stable movement intents, and observable outcomes. Require
before/after CCN for touched high-risk functions and the repository's
sub-1,000-line C/C++ limit.

Treat a loud admission-identity failure after an unrelated gameplay change as
an ownership alarm, not automatically as the gameplay root cause. Before
dispatching a fix, list every writer and observer for the failed receipt field
and classify each as pre-admission setup, immutable identity observation, or
transient lifecycle. Route post-admission writers to the owning runtime layer;
route observers that mix identity with death, summon, worldport, target, or
combat state to a lifecycle repair. Require one authoritative value-only
observer for each receipt identity instead of accepting copied validators that
can disagree. Do not weaken the receipt or tune the encounter around its most
visible terminal reason.

Apply the same audit to non-identity detectors. Separate the component that
observes an invalidating event from the component that blocks the unsafe
native action, the component that owns continued gameplay, and the component
that rejects or quarantines certification. If one observation such as future
encounter contact, a rejected path, or a missing transient pet immediately
closes every action lane, route it as a shared-runtime ownership defect. Do not
let a useful high-signal diagnostic become the cause of the wipe it reports.

| Work unit | Required specialist skill | Owner output |
| --- | --- | --- |
| Exact simulator input or DPS denominator | `raid-wowsims-reference` | current promoted value plus reconstruction receipt |
| DPS, tank, or healer policy behavior | `raid-role-implementation` | one fixed first-broken edge plus role-harness evidence |
| Native class, spell, stat, or pet outcome | `raid-class-mechanics-implementation` | one fixed damage/stat edge plus coordinator build receipt |
| Shared bot movement, recovery, lifecycle, or native submission | `raid-bot-runtime-implementation` | one fixed shared runtime edge plus replay and runtime-verification plan |
| Online boss strategy and numeric claims | `raid-encounter-research` | reviewed dossier, mechanic contract, and value ledger |
| Native boss/instance/DB implementation | `raid-encounter-implementation` | replay-tested native change and build receipt |
| Closed decision data or learned ranker | `raid-policy-flywheel` | admitted/quarantined batch and evaluation |
| Rotation discrepancy review | `raid-rotation-review` | attributable comparison; no implementation ownership |
| Shard construction and live coordination | `raid-shard-architecture` | exact shard identity and verified handoff |
| Live observation | `raid-boss-babysitter` | read-only decisive observations |
| Publication and eviction | `raid-evidence-lifecycle` | DVC publication/reconstruction/cleanup proof |

Use `trinity-orchestrator` for model selection and worker limits. Give each
worker exactly one specialist skill and one work-unit JSON. Require the worker
to work directly without launching nested agents.

Do not impose an arbitrary prose-receipt deadline on a bounded worker. Quiet
inspection, compilation, and focused tests are normal. Track progress through
the worker state, owned-file diff, process identity, and requested evidence;
send a non-blocking steering message only when new decisive context would
shorten the task. Interrupt only when the worker crosses the scope lock, repeats
the same failed command twice, enters an unbounded optimization loop, or loses
its required process. Silence alone is never a terminal condition.

Require the final handoff to name the current gate, commands/processes,
decisive evidence paths, and next edge. A worker may make at most two failed
command attempts on the same edge before returning a failed handoff.

Treat an empty final message as a missed receipt: verify what actually landed
with `git status`/`git diff` and your own test run before accepting or
rejecting the unit. Reject any fix handoff that (a) did not execute its tests,
(b) threads a field that no real closed artifact contains, or (c) inverts
non-applicable predicates instead of skipping them. When one worker proves a
fix requires native changes or a new capture, stop that lane; do not redispatch
the same tools-side unit against the same edge.

## Preserve recurring blockers across runs

Maintain one causal-blocker recurrence ledger for the active route. Key a
blocker by the earliest causal edge, affected route stage, and owning layer;
never key it by a later watchdog, receipt, recovery, or shutdown symptom. Count
at most one occurrence of a signature per run after deduplicating repeated
trace snapshots.

Before creating or extending that ledger, audit the retained Git handoffs, DVC
pointers, compact reports, and prior canary summaries for the same invariant.
Import the lifetime history, including occurrences that predate the current
ledger and clean runs between failures. A newly added ledger row starts at the
historical count, not at one. Treat an omitted historical family as a migration
defect: stop canaries, repair the ledger and fixture coverage, and run the
evaluator before changing runtime code.

Insert the just-closed run into the recurrence ledger before accepting any
suite receipt, build receipt, or next-run authorization. Map every terminal
symptom to an existing causal or parent invariant first. A receipt generated
while the latest run is absent from the ledger is stale even when all listed
fixtures pass; it proves only that the incomplete manifest passed.

When several stage-specific failures all displace the same end-to-end owner,
retain their detail but count them under one parent invariant. For route
combat, an alive exact current-node target or persisted pack must outrank stale
anchors, regroup, retreat, previous/future targets, and generic fallback.
Cover that precedence with one transition replay that includes a valid current
target, a forbidden proposed target plus a valid current pack, and the true
no-focus case. A collection of source-shape assertions is not that replay.

Keep stage labels and terminal reasons as evidence under that one family. Do
not give `submission_inactive`, `no_progress`, `trigger_not_crossed`, reclaim,
or rejoin failures independent counters when they violate the same end-to-end
lifecycle invariant. A renamed or downstream symptom must inherit the family's
occurrence count and architecture stop.

Run the ledger evaluator before authorizing either a repair or another canary;
its `required_next_action` is a gate, not a report-only field. Every repaired
signature keeps its original counterexample as a deterministic regression
fixture. Do not delete, weaken, or replace that fixture when a later repair
changes the implementation or diagnostic vocabulary.

Treat a recurrence after a passing fixture as proof that the fixture covered
the wrong boundary. Stop live canaries for that signature, preserve the old
fixture, and add a replay at the first missing policy-to-native-outcome edge.
Rerunning the unchanged fixture after the failed run is not a repair. Every
fixture has a positive contract revision; increment it only when its exercised
boundary or counterexample materially expands. The recurrence evaluator must
keep the canary gate closed when a post-run pass has the same revision as the
last pre-recurrence pass, even if the Git source identity changed.
The replacement gate must include the recorded numeric counterexample and the
state transition that the route actually needs. A submitted or top-level
`ok` action is not progress unless its native postcondition changes. Require
the watchdog to terminate a known failed candidate hidden beneath successful
wait work after one no-progress window, while allowing the same retry during
observed movement progress.

Only a currently `occurred` signature is eligible for repair routing. An older
open signature whose latest assessed state is `absent` remains a provisional
acceptance gate, but it must not displace the causal edge that occurred in the
latest trace. If every open signature is latest-absent, run the next clean
full-route acceptance canary instead of reopening an old implementation.

An intervening successful action or run does not reset the count. Record one of
`occurred`, `absent`, or `not_exercised` for every known signature in each
closed canary. `absent` is closure evidence only when the relevant route was
fully exercised. A partial run, infrastructure exit, or missing observation is
`not_exercised`, not a pass. Evaluate the ledger with:

```bash
pixi run python -m tools.raid_program.blocker_recurrence_ledger \
  --ledger <route-blocker-ledger.json> \
  --source-identity <exact-source-id> \
  --config-identity <exact-route-config-id> \
  --suite-receipt <hash-bound-suite-receipt.json> \
  --output <recurrence-decision.json>
```

To create the receipt in the same gate, replace `--suite-receipt` with
`--run-suite <receipt-path> --boundary-run-id <known-run-id> --boundary
before|after`. The bounded runner executes each manifest argv without a shell,
captures return/timeout plus command and result hashes, writes the receipt, and
only then evaluates it.

An active route opts into the fail-closed `regression_bank` field (schema
`trinity_raid_regression_bank_v1`). Its append-only `fixture_history` and
`fixtures` manifest name every retained executable fixture, while each
`fixture_verifications`/`verifications` row records its exact source/config
identity, positive fixture revision, and boundary. The CLI requires an external clean-tree source identity
and config identity plus a `trinity_raid_regression_suite_receipt_v1` whose manifest hash and identity
match; editing the ledger's declared identity cannot manufacture a pass. The
Magmaw route's config identity is the `sha256:` digest of the canonical JSON
payload `{validation_scenario: scenarios[id=blackwing_descent_10n],
bwd_diagnostic_shard: {schema, canonical_roster, diagnostic_bot_count,
instance_identity_policy, shard[id=bwd_magmaw_diagnostic_10n]}}` from
`validation_scenarios_cata_001.json` and `cata_raid_bwd_diagnostic_shards_v1.json`;
the ledger itself is intentionally excluded. The
evaluator emits exact `missing_fixture_ids`, `stale_fixture_ids`,
`failing_fixture_ids`, `invalidated_fixture_ids`, and `canary_admitted`/`build_admitted`.
It also emits `missing_causal_signature_ids` when an occurred signature has no
retained fixture. Any missing, renamed/unbound, stale, failing, or
recurrence-invalidated fixture/signature blocks admission. Ledgers without
`regression_bank` retain pre-gate history and compatibility until explicitly
migrated.
`build_admitted` is the current full-bank gate; `canary_admitted` additionally
requires no ten-occurrence stop and a post-occurrence pass for the latest
occurred signature (an open-but-repaired signature is allowed); only
`acceptance_admitted` waits for the two completed clean clears.

Reappearance reopens the same blocker even after clean intervening runs. At ten
occurrences of one signature in the active investigation epoch, including
interleaved occurrences, stop implementation and new canaries. Return the ten
run identities, earliest causal receipts, attempted fixes, regressions, and
unchanged invariant to an architecture review before beginning a new explicit
epoch. Do not evade this gate by renaming the signature or counting a terminal
symptom instead.

When a later trace proves that a narrow signature is one instance of a shared
mechanism, create a parent signature and carry every attributable historical
occurrence into it. Changing the action owner, intent label, encounter phase,
or distance band does not create a fresh blocker when the same admission gate
and failure invariant are unchanged. Record the narrow signatures as
subsumed, retain their counts, and apply the occurrence limit to the parent
before authorizing another patch or canary.

Represent that relationship with `causal_signatures.<child>.parent`; the
deterministic evaluator rolls child occurrences into the parent once per run.
After a hash-bound architecture review, record
`architecture_reviewed_through_occurrence_count` and its evidence on every
reviewed child and parent. This preserves total history while counting only new
post-review recurrences toward the next architecture stop. Never add that
acknowledgement merely to unblock a run.

One action label must not represent different causal waits. Formation staging,
health recovery, pull ownership, path admission, and native execution need
distinct reasons in closed evidence. If old telemetry conflates them, classify
from the underlying candidate and native outcome, then repair the diagnostic;
renamed or ambiguous evidence cannot prove a signature `absent`.

Route acceptance requires two consecutive completed clears in which every
known signature is explicitly `absent`. Passing a focused test or one clean
canary makes a repair provisional; it does not erase its recurrence history.

When a live signature recurs while its retained fixture still passes, stop
runtime edits and new canaries: the fixture is invalid or incomplete. Expand
the same immutable counterexample through the missing full sequence of owner
selection, priority/resource arbitration, semantic transition identity,
native submission/path execution, and observed postcondition across multiple
ticks. A helper-only, source-shape, endpoint-only, or preconstructed-lease test
cannot certify that sequence. Counterexample expectations are append-only;
changing or deleting an earlier expectation requires a hash-bound architecture
review that preserves the old case and explains why its expectation was
wrong.

Submission is not an outcome. For native movement and recovery, an accepted
intent or retained lease proves only arbitration. The fixture and live receipt
must separately prove a live native generator, multi-tick position progress,
the required world/area-trigger transition, and the final reclaim/rejoin or
arrival postcondition. One successful bot or one successful run does not close
an intermittent family.

Record each promoted fixture pass in the signature's append-only
`fixture_verifications` list with its evidence path and exact boundary. Use
`passed_before_run_id` for a fixture qualified before an admitted run, and
`passed_after_run_id` when an expanded fixture qualifies a repair after a
closed recurrence. Run the recurrence evaluator after each change and after
the next run closes. If the same signature occurs after that boundary, the
evaluator must return `expand_invalid_retained_fixture`; this is a hard gate
against both another patch and another canary. Do not clear the gate by editing
the previous verification. Append a later verification only after the expanded
end-to-end fixture passes.

Maintain a compact permanent regression matrix for the active route. Each row
binds one causal signature to its original counterexample, current fixture,
owning layer, first causal observation, and the two-clear acceptance state.
Run every row adjacent to a touched shared contract. A fix for a later row is
not admissible if it breaks an earlier row, even when the latest live trace did
not exercise that earlier mechanic.

Treat a later failure in an already-cleared stage as a regression audit, not a
fresh optimization opportunity. Compare the first causal edge with retained
counterexamples and inspect adjacent module contracts for contradictory
predicates. In particular, raid preparation has one strict order: durable
flask/food setup, health and encounter formation, short-lived pre-pot, then
the designated pull. Do not let an arbitrary boss-distance proxy override an
encounter's declared max-range formation, and do not let consumable readiness
silently become a second movement or pull-ownership policy.

## Parallelize only disjoint lanes

Parallel work is useful across these boundaries:

- one WoWSims reference cohort and one boss research packet;
- one class-family implementation and research for a different boss;
- analysis of an immutable closed batch and source work that cannot alter it.

Serialize these shared mutations:

- native heavyweight builds through `queued_build.py`;
- worldserver console, provisioning, roster leases, and canonical run state;
- canonical DVC publication and eviction;
- edits to a shared action profile, instance script, or encounter contract.

Do not assign one agent per spec, source, review angle, or telemetry category.
Use one owner per class family, boss, reference cohort, or closed batch.

## Join gates, not prose

Accept a specialist result only when its handoff follows
[references/handoff-contract.md](references/handoff-contract.md). Review hashes,
first-broken edge, validation result, and next dependency. Reject claims based
only on tests, source presence, a copied profile, engagement, or raw DPS/HPS.
For DPS tuning, also reject a handoff that omits exact gear identity or the
effective-stat parity result. Equal cast ratios with different damage are a stat
or native-outcome diagnostic until this gate passes; they are not permission to
keep optimizing the priority queue.

Before stopping, update the governing status/handoff artifact, commit coherent
code/config, and apply the required DVC lifecycle. Never let the coordinator
silently implement a specialist's failed work unit.

Route from the compact report and verified specialist handoff. Do not hand a
worker a multi-megabyte raw trace for open-ended reading. When one exact event
must be confirmed, use a streaming bounded extractor that filters the requested
action/result and deduplicates by `(bot_guid, sequence)`; pass the resulting
small receipt to the routing worker. A completed report plus an absent owned
worldserver is terminal evidence for the observation worker, not a reason to
keep polling.

For one-spec canaries, classify the closed comparison with:

```bash
pixi run python -m tools.bot_ml.spec_canary_gate \
  --review /path/to/rotation-review.json \
  --spec affliction_warlock \
  --reference-class self_provided_baseline \
  --output /tmp/affliction-canary-decision.json
```

The decision emits at most one capture/review/fix work unit. On the matched
verification, pass `--fixes-used 1`; a remaining mismatch then terminates that
specialist work unit as `fix_budget_exhausted`. It does not complete or block
the spec program. Close the attempt, preserve its before/after evidence, run a
fresh comparison, and route the newly observed first-broken edge to its owning
specialist. Do not redispatch the failed hypothesis or let one worker tune it
again. Continue this diagnose, bounded-repair, matched-verification sequence
until the spec passes its acceptance contract or a genuine external authority
or infrastructure dependency is unavailable. A report that only establishes
that the bot still fails is a routing receipt, not the requested outcome.

Route cast mix, cadence, pet uptime, or pet event
cadence to `raid-role-implementation`. Route matching cadence with wrong owner
or primary-pet damage per event to `raid-class-mechanics-implementation`.
When the selected denominator is `self_provided_baseline`, accept
`runtime_dps >= reference_dps`; never fail a canary merely for exceeding the
baseline. Before that comparison, require exact consumable parity. Provision
the per-spec items and retain one successful native pre-pot use before combat
plus one successful native combat-potion use during the scoring window when
both are configured.
