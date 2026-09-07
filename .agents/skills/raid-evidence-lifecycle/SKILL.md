---
name: raid-evidence-lifecycle
description: Control, verify, publish, retain, and safely evict TrinityCore raid-experiment evidence. Use for capture-controller implementation, build receipts, provisioning/readback proof, telemetry demultiplexing, DVC publication, compact run summaries, disk minimization, or attribution audits. Do not load for a read-only live babysitter that only reports observations.
---

# Raid Evidence Lifecycle

Keep evidence independently reconstructible while retaining as little local data as possible.

## Establish admission proof

Before live execution, require:

- a retained clean source checkout at the exact sealed commit/tree, and require
  the launch contract to name that immutable path. Never use an advancing
  coordinator branch worktree as durable source identity. Verify from the path
  stored in the bundle after later control commits; `source_identity_mismatch`
  is a real lifecycle failure, not a summary-only mismatch;
- canonical generated JSON written by a serializer or `apply_patch`. Parse and
  canonically verify it before the next budgeted action, require a final `0a`
  byte, and reject literal terminal bytes `5c 6e`. Do not use shell output that
  writes `\\n` as data;

- an exact clean Git commit and tree;
- a successful gate-bearing build receipt whose request, admission, and completion identities are equal and clean;
- treat clean Git identity and porcelain as source proof only: they cannot
  detect concurrent mutation of ignored receipt-bound artifacts such as the
  CMake cache or built binary. Snapshot and compare those artifacts themselves
  before and after validation, and bind returned provenance to the final
  verified snapshot. Add deterministic callback/interleaving fixtures that
  mutate each ignored artifact during the gate. When preflight and launch are
  separate boundaries, repeat the artifact validation immediately before
  launch;
- the exact binary hash and generated config hash;
- an exact materialized DVC workspace for every runtime asset. A detached Git
  checkout does not update DVC outputs: run targeted `dvc pull`/`dvc checkout`
  against that commit's lock, require local and cloud status clean, then verify
  the runtime manifest's decisive node IDs and mechanic fields before
  provisioning;
- Detect contradictory requirements when source and runtime roots alias the
  same files before trying permission repairs. Use independent copies when
  their contracts require different modes; changing one shared file repeatedly
  cannot satisfy both contracts. Never hard-link copies with different modes.
- For existing native assets with unknown extraction history, do not invent
  extractor metadata or repeatedly search for an absent historical receipt.
  Use the explicit verified-materialization authority: exact input inventory,
  DVC content address, and reconstruction verified from the remote with an
  empty cache. Record historical extraction origin as unknown. This authority
  does not waive content, mode, or source-identity mismatches.
- Before archiving a large new payload, check that Git can retain its intended
  `.dvc` pointer. A broadly ignored data directory needs narrow exceptions for
  its pointer and DVC-generated `.gitignore`, while payloads remain ignored.
  If publication stops after capture, reuse the verified archive through the
  explicit resume path and repeat remote reconstruction; do not recapture
  unchanged inputs merely to get past a pointer-visibility failure.
- Put multi-GB reconstruction workspaces on persistent storage with room for
  the cache, downloaded archive, and extracted tree. Check that filesystem's
  capacity and quota; free space on the repository filesystem does not describe
  a separate `/tmp` tmpfs. Remove exact failed temporary copies before resuming.
- Compare reconstructed directory paths, types, and permissions, but not their
  filesystem allocation size (`stat.st_size`). File contents, sizes, hashes,
  and modes remain exact. Keep physical source readback separately from the
  portable reconstruction comparison, and preserve historical authorities.
- inspect the owning `dvc.yaml` stage before planning hydration. A lock-file
  hash does not mean an output is restorable: metrics or outputs declared with
  `cache: false` are intentionally not materialized by `dvc pull` or
  `dvc checkout`, even when an object with the same digest exists locally. For
  such an output, either reproduce the exact stage from its pinned dependencies
  or copy the exact bytes from a clean, lineage-matching workspace only after
  verifying the immutable checkout's `dvc.lock` digest and size, the source
  workspace's relevant DVC status, and the copied destination digest. Record
  which method was used and never retry checkout under a different spelling;
- deterministic provisioning application and verification against the source
  manifests/DBC inputs before strict readback. Do not assume a prior run left
  learned spells, consumable counts, or other mutable roster state pristine;
- Keep a canonical route catalog and a prepared runtime route manifest as
  distinct authenticated artifacts. Authenticate the DVC-owned JSONL catalog,
  then use the production selector to bind one scenario's ordered rows and
  output-object hash in a typed receipt. Never pass catalog JSONL directly to
  a single-object consumer or hand-convert it for a live shard.
- fresh DB readback of the exact roster, account linkage, positions, and zero group/instance/corpse/ghost residue.
- Keep launch authority separate from the fixture target. A route replay may
  require an authenticated runtime-profile overlay and a sealed predecessor
  checkpoint even when neither is the behavior under test. Verify and retain
  those auxiliary bindings without adding unrelated fixture targets; reject
  partial profile authority where only some of the manifest, overlay, or
  expected profile identity are present.
- Supply generated runtime-profile authority only for a fixture replay that
  actually uses a generated suffix manifest. A normal gameplay canary binds
  its canonical profile through the runtime config and route-manifest hashes;
  do not pass the canonical profile manifest as if it were an unsealed fixture
  overlay.
- Carry fixture quarantine through every downstream admission and prestart
  verifier. A quarantined fixture remains visible, invalidated, and ineligible
  as evidence for its own claim, but it must not be reinterpreted as a blocking
  fixture after the recurrence decision has admitted an unrelated gameplay
  canary. Recompute and reject any nonquarantined remainder instead of requiring
  every raw fixture-state list to be empty.
- native-loadable character identity: normalized 2–12-letter player names and `at_login == 0`; a digit or rename flag makes `Player::LoadFromDB` fail even when ordinary row equality passes.
- provisioning/reset SQL that freezes every native group containing an exact
  cohort member, including a foreign-leader group, and deletes in dependency
  order: `group_instance`, `group_member`, then `groups`. Interrupted servers
  can otherwise poison the next admission with persistent group identity.

Do not reuse a binary or receipt for changed native source. Do not accept stored `passed` booleans when the underlying rows cannot be reconstructed.

In Python evidence code, a leading underscore does not make a module name
private or non-rebindable; public constructors and helpers are equally
replaceable. Build and validate canonical evidence from function-local fixed
literals or semantics, or another lexical value the caller cannot rebind.
Validation must not derive its expectation by calling a replaceable exported
constructor or helper. Capture values that span a callback once before invoking
it--especially SQL statement identity--and use that captured value for both
execution and the receipt. Add adversarial fixtures that rebind schema, field,
and SQL globals plus public and underscore-prefixed helpers, then prove callback
execution and the receipt retain the same original canonical value.
At a Python evidence boundary that executes caller callbacks, capture the full
transitive dependency set as fixed lexical authority at definition/import time,
including builtins, container constructors, predicates, length/set operations,
and exception classes. Forward tests must inspect for module-lookup fallbacks or
adversarially shadow them through ordinary callback-driven module/global
rebinding; invasive closure mutation or reflection is outside this boundary.

## Capture an immutable lifecycle

These shutdown and persistence duties belong to the capture controller or coordinator, not a read-only babysitter.

- Retain raw command/output bytes first; normalize afterward.
- Treat an operator interrupt as a controlled infrastructure abort: issue the
  addressed native `botauto stop <cohort>` and final `botauto status <cohort>`.
  Only the shared-server lifecycle coordinator may issue `server exit` or
  terminate its child process group after all owned cohorts have been closed.
  Stopping an individual boss test must preserve other active instances.
  Preserve the partial raw log, normalized rows, cleanup observations,
  and final report; record `operator_interrupt` as the reason rather than
  emitting an uncaught traceback or calling the partial run successful.
- Bind every retained JSON row to scenario, cohort, server epoch, attempt, runtime profile/hash, strategy, assignment generation, exact roster hash, action, and capture sequence.
- Classify every row. Unknown, missing, cross-attempt, cross-roster, stale-profile, or forged wrapper identity fails closed.
- Require successful, fresh status, diagnose, and trace envelopes with exactly the frozen roster when the gate needs per-bot decisions.
- For a `calibration-only` class canary, derive measurement integrity from the
  scoped `combat_calibration` decision timeline, action attempts/successes,
  landed events, actor/target identity, and cleanup receipt. Zero global route
  bots or route trace entries are expected in this mode and are not themselves
  a rejection. Do not use this exception for a route or boss claim.
- Bind the selected DPS `reference_class` in the report. For a
  `self_provided_baseline`, retain the exact per-spec flask, food, pre-pot, and
  combat-potion item IDs, provisioning readback, pre/post item counts,
  successful native uses, and resulting auras. Require flask and food before
  scoring, one pre-pot before combat, one combat potion during scoring, and
  zero externally supplied raid buffs or pre-applied target debuffs. A directly
  installed aura is not a consumable-use receipt. For
  `controlled_live_parity`, retain the exact condition projection used by both
  sides. Reference-class differences do not invalidate trace-only evidence.
- Treat timing as part of evidence identity. The exact 300-second measurement
  window is valid only for an isolated training-dummy DPS calibration. Raid and
  dungeon captures must be completion-watchdog-driven and retain the typed
  terminal edge: normal clear, monotonic semantic/no-progress stall, repeated
  decisions, excessive death loops, infrastructure loss, contamination, or
  explicit interruption. An emergency wall-clock expiry is noncompletion.
- In a fixture-expansion capture, a verified typed fixture terminal is the
  terminal result even when ordinary gameplay-stability gates are false. Stop
  promptly, request the final evidence bundle, and classify the result as a
  non-successful fixture observation; do not wait for the generic semantic
  stall clock and do not relabel it as gameplay success or gameplay failure.
  Classify the complete received batch before stopping: admission/preflight
  infrastructure failure has first precedence, an already-proven gameplay
  failure has second precedence, and only then may the fixture terminal own
  the result. If the fixture terminal's forced evidence is incomplete,
  classify the run as an infrastructure abort while retaining the typed
  terminal. Do not apply that override to an already-proven gameplay failure:
  preserve its gameplay classification and mark its terminal evidence
  incomplete.
- For a sealed movement fixture, treat the generic controller hold as transport
  lifecycle only. Fixture success must come from the dedicated native response,
  never from a generic `ok`, `checkpoint_terminal`, or release receipt. Freeze
  wipe generation and instance identity from the stable native status pair and
  reject later status or terminal drift. Accept the core's normal abbreviated
  binary revision only when its native comparison proves it is a prefix of the
  exact 40-character source identity; do not assume the runtime revision itself
  is always 40 characters.
- Validate movement-fixture success against the producer's real accounting:
  exact actor/task/candidate/planner/spline identity, one queue/attempt/native
  submission, compiled task generations, finite same-floor logical arrival,
  and at least two decreasing same-floor samples. Total samples may include
  wrong-floor observations, but wrong-floor samples must never count as
  decreasing semantic progress. Keep failed dedicated stages as failed fixture
  observations even when the generic hold terminalizes cleanly.
- Reconstruct milestones from ordered native observations rather than trusting aggregate completion flags.
- Preserve both `first_broken_edge` and `terminal_edge` when they differ. A
  later admission receipt, identity, recovery, or watchdog failure must not
  overwrite the earlier gameplay action/outcome edge unless ordered evidence
  proves causality. Bind each claimed edge to its first timestamp, route and
  wipe generation, bot identity, native observation, and preceding submitted
  action.
- Treat a new loud failure after an unrelated change as an attribution audit,
  not an automatic regression verdict. Record the exact changed ownership
  lane, then classify every writer and observer of the failed value as
  pre-admission setup, stable value-only observation, transient lifecycle, or
  reporting. Duplicated observers and post-admission writers are evidence
  defects even when the final receipt is correctly fail-closed.
- Keep evidence invalidation separate from gameplay termination. A
  contamination, drift, or forbidden-target receipt may reject or quarantine
  the run without granting the observer authority to suppress unrelated
  healing, defense, current-pack offense, or native recovery. Report when the
  detector itself caused the later wipe, and retain both the observed edge and
  the detector-induced terminal edge.
- In uncapped mode, use channel-freshness and monotonic semantic-progress clocks. Activity churn, casting toggles, or changing victim GUIDs are not progress.
- Treat an authoritative terminal cohort action gate as a completion-watchdog
  terminal on the next heartbeat, and classify it before appending that
  heartbeat. Do not infer an unrecoverable terminal from `all_dead` plus an
  absent recovery field; require a native typed recovery-failed outcome and
  never override a proven clear. Preserve the final heartbeat, diagnosis,
  trace, combat log, bot cleanup, and server shutdown; do not wait for the
  broader semantic-stall clock after a terminal is proven.
- Inspect the resolved candidate set when a top-level decision reports `ok`.
  A successful wait or suppression lane does not erase a failed movement or
  interaction candidate in the same tick. After the configured repeated-action
  window and a matching no-native-progress interval, retain that candidate as
  the first broken edge and stop the capture; do not wait for the broader
  semantic-stall timeout.
- Keep controller admission predicates byte-for-byte semantic peers of the
  runtime gate. In particular, post-wipe ready-check orchestration must accept
  either the scoped boss-reset edge or the scoped native-hostile reset edge
  used for trash, require inactive hostiles, and bind attempt, wipe,
  assignment, route generation, and node identity. A missing required
  controller command is an infrastructure abort, not a gameplay failure.

## Separate evidence scopes

- Label synthetic mechanic smokes `synthetic_test_only_not_boss_fidelity`.
- Label predecessor saves as diagnostic assistance and noncertifying.
- Keep boss-shard, boss-script, native recovery, and canonical full-raid claims separate.
- Never promote engagement/wipe evidence into a kill, tactic, or observable-fidelity claim.
- Reaching a boss partition's final node is arrival, not completion. Require
  native manifest completion and terminal evidence; a boss clear also requires
  confirmed unit-death evidence matching the selected node, generation, and
  boss entry. Keep the historical foundation arrival smoke explicitly scoped.

## Diagnose before eviction

Preserve enough raw data to answer:

- what exact decision each bot made and why;
- which native script event, target, aura, summon, geometry, or phase was observed;
- whether the trained damage profile executed or was blocked;
- whether stuck/unstuck, CPU, log, or persistence hot paths distorted the run;
- whether cleanup returned bots, leases, groups, and processes to zero.

Retain low-cost process-resource samples (PID, monotonic timestamp, CPU ticks,
RSS bytes, and server identity) at a multi-second cadence. Do not extrapolate
parallel CPU/RAM capacity from screenshots or unretained `ps` observations.

The coordinator makes fixes and completes independent review before discarding diagnostic payloads. A babysitter only reports the decisive evidence.

For long uncapped runs, keep status as the inexpensive heartbeat and use
delta trace export plus a slower steady-state full diagnosis/trace cadence.
Material status edges must force an immediate diagnosis, and every stall,
error, or operator shutdown must force a fresh full diagnosis and trace delta.
This reduces output/CPU pressure without dropping decision evidence or
weakening freshness/demultiplexing gates.

When a causal join depends on one native receipt, retain that exact receipt
until its terminal outcome or explicit supersession has been published. Pin at
most one requested lifecycle per actor and include it inside the existing
bounded publication window. Do not raise global receipt/sample capacity or
enable broad high-frequency tracing to recover one missing join. The compact
extractor must join actor, intent fingerprint, planner result, native launch,
spline progress, and terminal outcome for the requested receipt, and must say
which fields remain unavailable.

For a rejected hazard movement, publish the rejection before a later candidate
in the same tick can overwrite an actor-level `Latest` slot. Include hazard GUID
and sampled position, requested and resolved endpoints, path/floor proof,
clearance delta, candidate/task generations, authority source, and typed
terminal reason. Z is floor evidence only; it is never a bot movement command.

## Publish and minimize disk

Publication and eviction belong to the coordinator/evidence curator, not the babysitter.

1. Write a compact tracked summary containing classification, exact identities, hashes, decisive findings, cleanup facts, and the next action.
2. Add the immutable raw/report/log/receipt/readback bundle through DVC.
   For long runs, record canonical uncompressed hashes first, then store a
   deterministic compressed representation only when the verifier can stream
   it and reproduce those hashes. Compression is not a substitute for row
   classification or raw-byte provenance.
3. Run the relevant `pixi run dvc status`, `pixi run dvc push`, and targeted cloud/status verification.
   For persistent directory outputs, also inspect `dvc status -v` and reconstruct
   generated bytes with the verifier; a terse/JSON status can hide a missing
   cache object or stale workspace payload.
4. Verify the tracked `.dvc` pointer, directory metadata, remote availability, file counts, sizes, and hashes.
   Keep stage outputs schema-clean: move ad-hoc apply/readback/verifier files
   outside a tracked output directory before reproduction so they cannot
   become accidental children of the stage object.
5. Evict the exact published workspace outputs and only cache children unique
   to that evidence object. Check whether a tracked DVC stage reuses each
   child; retain or immediately recommit shared stage objects so stage status
   remains clean. Record unique evicted and shared retained counts.
   Keep directory metadata needed for reconstruction.
6. Never use broad `dvc gc`, recursive cache deletion, or unresolved globs to save space.
7. Recheck process state, Git cleanliness, DVC status, and disk usage.

Historical evidence may remain remote-only. Hydrate it only when a new diagnosis or audit genuinely needs the bytes, then evict it again after use.

## Gate publication

A run is gate-bearing only when source/build/config/provisioning/runtime/roster/attempt identity is exact, all retained rows are classified and bound, required native outcomes are independently reconstructed, cleanup is observed, remote publication is verified, and no forbidden assistance or unresolved Critical/High finding remains.
