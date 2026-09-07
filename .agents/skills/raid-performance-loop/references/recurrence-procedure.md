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

Before launching a live canary, persist its exact suite admission snapshot in
the run record: source/config identity, suite-receipt hash, and every fixture
ID with its positive revision. Do not rely on a `/tmp` receipt or active-work
descriptor as the only copy. The evaluator must treat those admitted revisions
as passes before that run, so rerunning the same revision after a recurrence
cannot masquerade as fixture expansion.

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

When a live recurrence or its evidence review proves a retained production
fixture's boundary insufficient, do not mark the replacement revision pending
or passed before its evidence exists. Declare one target-bound replacement-
evidence request with the fixture ID, current and next revisions, previously
observed causal signature, and required production boundary. This also applies
when the inadequate fixture was first added after the occurrence and therefore
is not yet listed as invalidated. The request may admit only an observation-
only `fixture_expansion_replay`; build, gameplay canary, and gameplay mutation
remain closed. Seal the request into the suite manifest and recurrence
admission, then promote the incremented fixture revision only after the
captured production evidence satisfies the boundary.

Treat a recurrence after a passing fixture as proof that the fixture covered
the wrong boundary. Stop live canaries for that signature, preserve the old
fixture, and add a replay at the first missing policy-to-native-outcome edge.

A reviewed fixture quarantine must be represented in the executable ledger,
not only in a handoff. Keep the fixture, occurrence history, failed status, and
deferred production-boundary request, but mark its admission scope as
`quarantined`. The evaluator may then exclude it from build and gameplay-canary
admission without reporting it as passed. Quarantine is appropriate only when
an independent review shows that the missing boundary is low value for the
current gameplay decision and names the condition that would make it relevant
again. It must continue to block any claim that directly depends on that
boundary.

Avoid a build/metadata/rebuild loop. When the exact clean source is ready for
its first live verification, one tracked descriptor should conditionally admit
the current recurrence suite, one configure/build if needed, and exactly one
no-retry completion-watchdog canary. Do not commit a build-only completion
descriptor and then require another commit before the canary when that commit
would invalidate the binary receipt. If a later control-only commit must reuse
an older binary, require an explicit two-identity verifier: the binary remains
bound to its build commit, the workflow remains bound to the current clean
control commit, the build commit is an ancestor, and every intervening path is
on a narrow reviewed control-plane allowlist. Any native, dependency, CMake, or
unknown path change requires a new build.
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

Before promoting the replacement, name the causal invariant and enumerate the
adjacent execution variants that can reach it. The fixture must exercise that
equivalence class at the final policy-to-native outcome boundary, not only the
single path type or coordinate tuple seen in the latest run. For movement this
normally includes complete versus incomplete native paths, retained versus new
submissions, plausible same-floor probes, unrelated lower-geometry probes, and
a legitimate cross-floor rejection. Missing one of these variants keeps the
signature open and blocks another live canary.

For native-path recurrence, require separate evidence that a complete rejected
primary path cannot launch a progressive-local fallback and that an incomplete
same-floor path can still use the bounded fallback when otherwise admissible.
Also require retained-route consumers to reject post-construction cross-floor
actor drift. If the standalone test environment cannot initialize Map, MMAP,
MotionMaster, and world ticks, helper tests may admit a build but cannot promote
the fixture: route one admission-sealed, observation-only worldserver replay
that injects the exact intent through the production planner and records native
launch, progress, rejection, and terminal outcome.

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

For the Magmaw diagnostic, evaluator output is not live authority by itself.
After fresh provisioning creates the exact runtime config and route manifest,
seal them with the clean source, verified build receipt/binary, ledger,
decision, and suite receipt:

```bash
pixi run python -m tools.raid_program.recurrence_admission create \
  --worktree <clean-worktree> --binary <worldserver> \
  --build-receipt <verified-build-receipt.json> \
  --runtime-config <worldserver.validation.conf> \
  --route-manifest <validation_route_manifest.json> \
  --ledger <recurrence-ledger.json> --decision <recurrence-decision.json> \
  --suite-receipt <suite-receipt.json> --output <run>/recurrence-admission.json
```

Pass that file and its SHA-256 to the capture with
`--recurrence-admission` and `--recurrence-admission-sha256`. The capture
re-verifies every bound byte before spawning a worldserver. Missing, stale,
dirty, failing, invalidated, or identity-mismatched admission is terminal
preflight evidence; never bypass it with an older descriptor or `/tmp` result.

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

Aggregate class or resolver labels cannot authorize a gameplay patch by
themselves. Require the specialist handoff to retain actor, target, full
actor-target geometry, movement state, profile identity, and bounded
per-candidate rejection reasons. If target selection succeeded but native
availability failed because encounter movement put the actor out of range,
split target ownership from encounter positioning and repair the positioning
edge first.

For fixed mechanic assignments, the contract must state both who owns the
mechanic movement and what non-owners do. Reject a repair that gives the fixed
team a lane but still lets non-owners enter a generic fallback for the same
hazard. Tests must include owner and non-owner actors with simultaneous hazards
so a nearer low-priority hazard cannot mask a lethal one.

Route acceptance requires two consecutive completed clears in which every
known signature is explicitly `absent`. Passing a focused test or one clean
canary makes a repair provisional; it does not erase its recurrence history.

Use the words `implemented`, `fixture-green`, `build-admitted`,
`canary-provisional`, and `closed` as distinct states. Never call a blocker
fixed before it is `closed`. A live recurrence immediately demotes every later
state for that signature to `quarantined`, invalidates the latest retained
fixture revision, and revokes any outstanding build or canary authorization.
Record that demotion in the ledger and active work-unit descriptor before
reviewing another patch or launching another run. This rule applies even when
the recurrence is less frequent, affects fewer actors, or appears after clean
intervening runs; improvement is not absence.

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

Conversely, a checkpoint/verifier failure is not automatically a movement
failure. When the correlated receipt shows a complete accepted path, live
generator/spline identity, same-floor decreasing progress, and arrival, route
the first broken edge to the evidence predicate that rejected those facts.
Compare requested X/Y/Z with the planner-selected terrain endpoint separately;
bit-exact requested-Z equality is invalid when the bounded, floor-valid native
projection differs. Do not dispatch route, MMAP, priority, or movement changes
for that post-hoc false rejection.

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
