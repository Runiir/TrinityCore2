# Bounded specialist work contract

Use this contract for every delegated raid specialist task. The user's latest
instruction always wins.

## Lock scope before acting

Write a compact scope lock containing:

- the immutable evidence path or exact source state;
- a compact ordered causal receipt that labels material claims `verified`,
  `refuted`, or `unproven` and cites the observation for each label;
- one candidate first-broken edge, its first observed downstream state mutation,
  the failure postcondition, and one implementation hypothesis;
- the correlation keys that join that candidate to the mutation, such as actor,
  attempt or mechanic generation, candidate/receipt ID, and native execution ID;
  when the trace cannot supply that join, label the causal link `unproven`;
- the owned behavior and expected observable change;
- the production boundary that the focused fixture must cross, including the
  expected fail-before and pass-after observations;
- allowed files or directories;
- explicitly excluded adjacent lanes and mutations;
- one focused validation command, plus any explicitly assigned build or live
  run;
- terminal conditions for success, failed verification, and out-of-scope
  handoff.

Record pre-existing dirty files and leave them untouched. Read-only inspection
outside the owned files is allowed only to resolve the admitted edge.

## Stay inside the lock

- Implement one hypothesis. Do not fix a newly discovered adjacent problem.
  Return its evidence and owning specialist instead.
- Do not regenerate DVC stages, build, provision, start or stop servers, mutate
  databases, publish evidence, or clean artifacts unless the scope lock assigns
  that action.
- Run the focused validation once. If the patch itself causes a focused failure,
  permit one correction cycle and rerun it. An unrelated or pre-existing failure
  is a handoff, not permission for repository-wide repair.
- Do not run broad discovery, a full test suite, repeated live canaries, or a
  second optimization after the expected signal passes.
- If the evidence disproves the hypothesis or identifies another owner, stop
  without a speculative patch.
- Preserve cross-lane ownership for raid cooldowns. A role unit may tag and
  submit a native cooldown candidate; shared runtime owns the default
  trash/regroup/pre-pull reservation; an encounter unit may expose only the
  reviewed boss phase that releases it; shard architecture validates the
  resulting bag item, cast, aura, target, and timing receipts. Do not duplicate
  the reservation or release policy in a class rotation or route fixture.
- Treat an admission receipt as a mutation boundary. Gear, talents, glyphs,
  pet row/spellbook/autocast state, roster leases, group identity, difficulty,
  map, and instance identity must reach their declared state before the
  receipt commits. After commit, decision and route code may observe them but
  must not repair or normalize them. A legitimate native gameplay transition
  must be represented explicitly in the receipt contract before it is allowed;
  never silence an identity-drift diagnostic to accommodate a late mutation.
- Keep each receipt-bound observer and canonicalizer in one shared production
  owner. Do not copy pet, gear, roster, or instance identity logic into
  calibration, route, and runtime functions. If multiple consumers need it,
  extract a value-only helper and test all consumers against the same result.
- Treat priority-queue candidates as deferred work. A submitter may return
  before `Candidate::Attempt` runs, so its callable must explicitly capture
  every value it owns and may reference only state whose lifetime spans queue
  resolution. Do not use blanket `[&]` captures in deferred candidates. When
  touching a submitter, audit sibling candidates in that submitter and keep a
  source-level lifetime guard in the focused regression suite; a later stack
  layout change must not be able to resurrect dangling-capture behavior.
- Separate stable identity from native lifecycle state. A pet row, owner,
  entry, and persisted spellbook/autocast are identity; alive, summoned,
  in-world, current victim, and combat references are lifecycle. Death,
  dismissal, revive, summon, release, and worldport need typed recovery facts,
  not a rewritten receipt or a misleading identity-drift reason.

## Prove the causal edge and fixture boundary

An immutable handoff fixes the assignment and evidence identity. It does not
make its causal interpretation true. Verify its material claims against the
bounded trace and production source before editing, and preserve contradictory
claims as `refuted` or `unproven` instead of silently replacing them.

Classify the ordered observations before naming the first-broken edge:

- A `contained rejection` reaches no native submission and causes no observed
  downstream control or world-state change. Diagnostic fields alone do not make
  it causal unless a later decision consumes them.
- The `first state-infecting edge` is the earliest observed wrong admission,
  submission, or mutation that a later owner consumes on the path to failure.
- A `downstream symptom` reflects an earlier mutation without introducing the
  first wrong state.
- A `terminal watchdog` classifies and stops the run. It is not the causal edge
  unless its own mutation caused the failure being investigated.

Time order alone does not prove causality. If no downstream mutation is
observed, return an evidence or telemetry work unit instead of a production
fix.

An earlier candidate and a later mutation are not a causal chain merely because
they share an actor or occur close together. Name a `first state-infecting edge`
only when an observed owner-to-owner receipt joins the candidate, its native
execution, and the consumed mutation. Without that join, keep it as an
`unproven suspected edge` and add the missing correlation telemetry before any
gameplay edit.

A focused fixture must execute every production owner implicated by the
hypothesis and observe the required outcome. A helper unit test may prove a
local predicate but cannot certify a production fix. For native movement or
recovery, the fixture must reach the real admission and native-submission path,
observe the resulting generator, spline, or lifecycle transition, span enough
ticks to distinguish submission from progress, and assert the required arrival,
reclaim, rejoin, or safe-position postcondition. The recorded counterexample
must fail before the fix and pass after it. If the production boundary or exact
mechanism is not observable, expand the fixture or telemetry first; do not
recommend build or canary.

When the hypothesis depends on map geometry, MMAP, collision, DBC, database, or
world lifecycle state, the fixture must bind and execute those real production
dependencies. Injected path proofs, preconstructed successful observations,
mock generators, or source-shape assertions may test a local predicate, but
cannot stand in for the environment-bound boundary or authorize implementation.

## Return a bounded handoff

Report the scope lock, exact changed files, decisive before/after signal, test
command and result, a claim ledger with `verified`, `refuted`, and `unproven`
entries, untouched dirty files, and the next owner if any. Changed files must be
a subset of the declared ownership. The coordinator must reject and split a
handoff that crosses the lock, even when its extra changes appear useful.
