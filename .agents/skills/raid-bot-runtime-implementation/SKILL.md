---
name: raid-bot-runtime-implementation
description: Repair one trace-backed shared Trinity-Cata bot-runtime edge such as movement arbitration, death recovery, instance rejoin, cohort lifecycle, candidate scheduling, native action submission, or cross-role execution control. Use when the failure is shared bot infrastructure rather than a class policy or encounter script. Do not use for class rotations, spell coefficients, boss mechanics, shard provisioning, or live server ownership.
---

# Raid bot runtime implementation

Own one shared policy-to-native-outcome edge. Do not own live shard control or
broaden the repair into a class, boss, or route redesign.

Before inspection or editing, apply
[the bounded work-unit contract](../raid-performance-loop/references/bounded-work-unit-contract.md).
Declare one runtime hypothesis, owned files, excluded class/encounter/shard
lanes, and one focused validation. Stop and hand off immediately when the first
broken edge belongs elsewhere.

## Admit one exact edge

Start from `required_next_work_unit`:

```bash
pixi run python -m tools.raid_program.raid_workloop status
```

Require a hash-bound closed report, exact source commit, typed first-broken
edge, and one implementation hypothesis. Shared examples include corpse
release/runback/rejoin, movement-owner arbitration, decision scheduling,
cohort lifecycle, native action submission, and completion observation.

Return the work when the trace instead identifies:

- class priority, resource, pet, form, or stance policy: `raid-role-implementation`;
- stats, coefficients, inheritance, or landed damage: `raid-class-mechanics-implementation`;
- boss or instance state: `raid-encounter-implementation`;
- route identity, provisioning, or live coordination: `raid-shard-architecture`.

## Repair and verify

Treat decision complexity as a runtime risk, not as a diagnosis by itself. The
2026-08-28 native bot audit found a heavy tail: 45 functions above CCN 100 and
a maximum of 464. When the broken edge is inside a high-CCN function, measure
it before and after. Extract one independent policy owner that submits a typed
candidate with explicit resource claims and a reason. Do not move the same
branch tree into helpers that are all still called unconditionally. Preserve
movement as a set-and-forget intent, keep action selection in the priority
queue, and trace ownership, admission, execution, and outcome boundaries.
Accept the refactor only when the effective decision graph or ownership
overlap shrinks. Keep every C/C++ source and header below 1,000 lines.

The action kernel resolves candidates after submitter helpers return. Treat
every `Candidate::Attempt` as deferred: capture owned values explicitly and
reference only the update context or other state that provably outlives
resolution. Blanket `[&]` capture is forbidden in deferred submitters because
an unrelated stack-layout change can expose old undefined behavior as an
intermittent regression. When a trace enters a candidate lambda through
`Kernel::Resolve`, audit every sibling candidate in that submitter, replace
implicit captures with explicit lifetime-safe captures, and add a source-level
guard that prevents the unsafe form from returning. Keep a compiled behavior
test for the original transition as well; the source guard proves lifetime
shape, not gameplay correctness.

An unrelated rebuild that exposes an older failure usually changed timing; it
does not make the newest patch the cause. Trace the first admitted owner and
native outcome before inspecting the latest diff. Treat missing or default
metadata conservatively: a null action, absent profile result, unregistered pack
GUID, temporarily unavailable pet, or stale route target must not bypass a
safety, identity, or cleanup invariant. Test the missing/default case and the
nearby explicit valid case. Search for the same bypass shape at adjacent
ownership boundaries, but report each additional finding as a separate bounded
work unit instead of widening the current repair.

Change the smallest shared transition, gate, owner token, or native-action
edge that explains the evidence. Preserve ordinary player movement, corpse
release, graveyard, entrance, resurrection, spell, threat, and encounter
rules. Never teleport, manufacture a wipe, revive, force a target, or mutate a
boss outcome.

For dead-player movement, distinguish policy admission, native generator
creation, spline activity, coordinate progress, entrance/worldport, corpse
reclaim, and roster rejoin in both traces and tests. Do not report a void
MotionMaster call as committed movement without verifying that the expected
generator exists and its spline is active. Prefer the ordinary persistent
playerbot point generator; if flight is authorized, carry flight/gravity as
scoped execution state instead of substituting a short-lived generic spline.
Expose current/active motion type, spline-finalized state, flight/gravity
flags, actual position, requested destination, and exact recovery episode.

For shared movement admission, do not repair one owner or distance band at a
time when route, combat-range, hazard, and mechanic receipts fail at the same
native path or floor-proof gate. Define the invariant once below the owners,
preserve strict vertical/future-pack guards, and test the recorded owners
against the same deterministic proof. If the parent causal signature reaches
the route recurrence limit, return an architecture review with no edit and no
live rerun.

Keep destination identity separate from native floor normalization. A complete
path may preserve the requested horizontal endpoint while MMAP resolves its Z
to the walkable polygon. Use explicit bounded horizontal and vertical evidence
plus endpoint-floor validity; do not collapse those facts into one unexplained
3D tolerance. Retain the exact rejected endpoint deltas as a compiled
counterexample and serialize both components for future traces.

Movement producers must submit the destination's declared/navigation-floor Z,
not the actor's transient Z, when the destination came from a route-bound
anchor. Prove the recorded requested-versus-normalized endpoint deltas against
the strict shared endpoint gate. Do not loosen that gate to compensate for a
producer that discarded its destination floor.

A successful wait, suppression, or consumable candidate can coexist with a
failed movement candidate in the same kernel resolution. Do not use the
top-level `ok` result as proof of progress. When the failed candidate repeats,
require both its typed reason and a full window with no observed movement
progress before terminating; retain a nearby replay where the same retry is
allowed while movement is advancing.

Shared raid cooldown reservation belongs here only when it is class-agnostic:
reserve offensive cooldowns, offensive guardians, combat potions, and
Bloodlust during trash, regroup, and boss staging, while leaving emergency
tank/healer survival actions available. Consume semantic category/tags from
the role candidate and an explicit release fact from the encounter contract;
do not add class spell lists, choose the best boss phase, provision items, or
run the shard in this work unit.

For shared pre-pull execution, keep durable setup, encounter staging, and
short-lived effects as separate states. The invariant is flask/food first,
then full-health and encounter-owned formation, then every admitted member's
ordinary native pre-pot use, then the designated pull. A generic distance
threshold must not contradict an encounter-owned max-range bait position.
When one member cannot satisfy a stage, emit that member and exact predicate;
never let the first member's short aura expire behind an unexplained cohort
wait or collapse the condition into a generic `prepull_failed` loop.

Extract or reuse a deterministic C++ transition boundary when practical. Add
focused tests for the recorded counterexample and nearby valid states. A
source-shape test alone does not confirm native behavior.

When a live blocker reappears after its retained fixture passed, treat that
fixture revision as invalidated. Before editing the runtime, add an executable
value-level counterexample using the recorded trace inputs and prove it fails
against the pre-fix behavior. Increment the existing fixture revision; do not
rename, remove, weaken, or replace its causal signature. The repaired fixture
must exercise the final admission/selection result, not merely a helper in
isolation, and include adjacent rejection cases for other owners, cross-floor
movement, non-progress, or forbidden native path flags as applicable. A new
live canary is forbidden until this revised fixture and the complete retained
regression bank pass at one clean committed identity.

Before changing a live decision path, inventory every state it mutates and
compare that list with the active admission receipt. Receipt-bound pet
spellbook/autocast, gear, talents/glyphs, roster leases, group/difficulty, and
map/instance state are pre-admission setup, not route recovery. Runtime after
admission is observation-only for those identities. Move required setup before
receipt commit and preserve the drift failure; do not weaken, refresh, or
rewrite the receipt after actions start.

Enforce one setup owner before admission and zero gameplay writers afterward
for every receipt field. Search all writers, not only the function named by the
terminal reason. A route, encounter, class, movement, recovery, or pet helper
that changes a receipt field after admission is a cross-domain ownership bug,
even when its local intent is harmless. Add a focused counterexample proving
the unrelated action leaves the frozen field unchanged. Keep the terminal
receipt check as evidence, but diagnose the illegal writer as the first broken
edge.

Search for duplicate identity observers before adding another local check.
The 2026-08-28 audit found `ObserveActiveOrdinaryHunterPet` duplicated across
six validation/calibration translation units. A bounded repair should reuse one
shared value-only observer when that duplication touches the admitted edge;
do not broaden an unrelated repair into a repository-wide cleanup.

Keep observation, immediate safety mitigation, gameplay authority, and
certification verdict as four distinct owners. A detector may record or
quarantine future-encounter contamination, identity drift, path rejection, or
another invalidating condition. It must not also suppress unrelated healing,
defense, current-target offense, or native corpse recovery unless ordered
evidence proves those actions are unsafe. In particular, do not turn a
protected-target observation into a cohort-wide terminal hold while the owned
trash target is still alive. Block the forbidden target or splash at native
submission, retain the first evidence edge for certification, and allow the
ordinary runtime to survive, reset, or recover. Audit every call to a shared
terminal latch as an ownership boundary, not merely as a reason-code branch.

Resolve current-route combat authority before generic regroup or fallback.
If an exact current target is valid, preserve it. If the proposed target is
stale or belongs to another encounter while an alive persisted current-pack
target exists, recover the persisted target. Only the absence of both permits
`hold_anchor_no_focus`. Keep this as one explicit precedence table and replay
all three states; do not add another local target chooser or a renamed hold
reason.

Do not reuse one decision/action reason for different predicates. A health
hold, formation wait, pull-owner wait, movement rejection, and recovery attempt
must remain distinguishable in the candidate receipt. When a live trace exposes
an ambiguous label, repair the reason at the policy-to-runtime boundary and add
a focused fixture before using that label in recurrence or acceptance logic.

Do not make an immutable identity observer also require transient liveness.
For ordinary pets, reconcile the stable owner/pet row/entry/persisted
spellbook separately from alive, summoned, in-world, target, and combat state.
The latter belongs to a typed native pet lifecycle/recovery edge. Use distinct
reason codes so a dead or temporarily unsummoned pet cannot masquerade as
spellbook identity drift and permanently close an otherwise recoverable raid.
Apply the same split to group membership versus corpse worldports, roster
identity versus active participation, and initial map/instance identity versus
typed native recovery transit.

Persistent setup may run after admission only for a typed native lifecycle
transition that restores the same admitted identity. It must not choose a new
pet row, spellbook/autocast state, gear item, talent, or glyph. Report spec,
talent, glyph, and role-composition failures with separate reason codes so a
frozen-identity mismatch cannot be misrouted as ordinary roster composition.

For set-and-forget native movement, distinguish the short arbitration lease
from the native generator it admitted. A lease may expire exactly at the next
decision cadence while the receipt-bound `MotionMaster` path is still active.
Do not make observation, progress, or one-shot recovery predicates depend on
`ExpiresAtMs > nowMs` unless the action itself requires a currently valid
lease. Bind them instead to the recorded owner, attempt/wipe/route scope,
destination, traversal mode, and observed native path state. Test the exact
lease-expiry boundary at `nowMs == ExpiresAtMs`, plus one tick before and one
tick after; a source-shape assertion is not enough.

Keep repair state names exact: `implemented`, `fixture-green`,
`build-admitted`, and `canary-provisional` are not `closed`. Never report a
blocker as fixed until two consecutive full current-standard clears explicitly
mark its signature absent. If it reappears at any later state, immediately
quarantine that signature, invalidate the newest retained fixture revision,
and revoke outstanding build/canary authorization before reading or editing
another runtime edge. A smaller affected cohort is improvement, not absence.

For event-owned encounter movement, retain a typed semantic transition in
addition to the short generic lease. Bind it to encounter/attempt and mechanic
generation, assigned actor, transition identity, direction, destination, and
committed/arrived state. Once admitted, observation churn, changing hazard
GUIDs/positions, ordinary lease expiry, or crossing a geometric midpoint must
not choose a new destination. A typed lethal-safety action may preempt it, but
the same transition resumes afterward. Retire it only on observed native
arrival, a later mechanic generation after arrival, or exact attempt reset.
Validate the full traversed corridor, not only endpoints.

If that live signature recurs while the focused fixture passes, do not patch a
new helper or run another canary. First replace the incomplete fixture with a
multi-tick replay spanning selection, arbitration, semantic retention, native
submission/progress, preemption/resume, arrival, and reset. Preserve the old
counterexample and record any corrected expectation in the architecture
handoff.

An unchanged replay rerun after the recurrence is not fixture expansion. Keep
the old fixture and its revision, add the missing live boundary, then increment
the fixture-contract revision. The recurrence gate must reject a same-revision
post-run pass regardless of a newer source commit or another green result.

The replay must cross every independent action owner implicated by the live
counterexample. For encounter movement plus class combat, execute encounter
assignment, immutable combat constraints, class-action filtering, priority and
resource arbitration, native movement, persistent pet/area effects, hostile
threat or victim selection, and the observed lethal postcondition in one
compiled sequence. A strategy-only target assertion cannot prove that a later
class resolver, pet, totem, autoattack, or area spell obeys the assignment.

Before handing back a repaired fixture, append its evidence with
`passed_after_run_id` bound to the closed recurrence that caused the expansion,
then run the ledger evaluator. The only admissible result is the
fixture-expansion gate cleared for that signature; the coordinator still owns
the single matched canary and two-clear acceptance.

Use the queued build coordinator for every native build. Return a runtime
verification plan to `raid-shard-architecture`; that coordinator runs at most
one matched completion-watchdog shard. If the same edge remains, return a
failed handoff. Do not add another hypothesis or tune adjacent policies.

Use the shared handoff contract from
`raid-performance-loop/references/handoff-contract.md`. Report the exact
before/after edge, changed files, tests, build receipt, runtime verdict, and
next owner.
