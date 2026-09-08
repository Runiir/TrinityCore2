---
name: raid-bot-runtime-implementation
description: Repair one trace-backed shared Trinity-Cata bot-runtime edge such as movement arbitration, death recovery, instance rejoin, cohort lifecycle, candidate scheduling, native action submission, or cross-role execution control. Use when the failure is shared bot infrastructure rather than a class policy or encounter script. Do not use for class rotations, spell coefficients, boss mechanics, shard provisioning, or live server ownership.
---

# Raid bot runtime implementation

Own one shared policy-to-native-outcome edge. Do not own live shard control or
broaden the repair into a class, boss, or route redesign.

An encounter-local bot task or movement-intent producer also belongs here when
the proven mismatch is its retained state or logical destination and the native
boss script, class policy, and executor are behaving correctly. File location
alone does not assign a bot-policy defect to the native boss-script owner.
Keep that work unit confined to its encounter module and existing validated
destinations; it must not introduce universal encounter rules or relax native
pathing safeguards. No simulator reference is needed for a movement-only repair
that makes no damage, cadence, or stat-tuning claim.

Before inspection or editing, apply
[the bounded work-unit contract](../raid-performance-loop/references/bounded-work-unit-contract.md).
Declare one runtime hypothesis, owned files, excluded class/encounter/shard
lanes, and one focused validation. Stop and hand off immediately when the first
broken edge belongs elsewhere.

## Admit one exact edge

Use the coordinator's supplied bounded packet for this worker. A separate
in-flight primary work unit does not replace an explicitly assigned diagnostic
or validator repair. When no packet is supplied, obtain `required_next_work_unit`:

```bash
pixi run python -m tools.raid_program.raid_workloop status
```

Require a hash-bound closed report, exact source commit, typed first-broken
edge, and one implementation hypothesis. Shared examples include corpse
release/runback/rejoin, movement-owner arbitration, decision scheduling,
cohort lifecycle, native action submission, and completion observation.

Before accepting the named edge, classify the ordered observations with the
bounded contract. A rejected plan with no native submission and no later
control-state consumer is contained. An accepted or submitted plan may be the
first state-infecting edge, but its exact mechanism remains unproven until the
launched generator, spline, or recovery transition is observed. Later position,
death, recovery, or watchdog events are downstream symptoms unless they add the
first wrong state. Do not infer a launch, collision, or fall mechanism from a
later position alone. Require one correlated receipt chain from candidate and
native execution identity to the later consumed mutation. Actor identity and
timestamp proximity alone do not establish that chain.

For execution telemetry, inspect whether the executor re-resolves or mutates
the preview action and its output category. Attribute ordinary outcomes to the
final action, not a stale preview; retain preview attribution only for an
explicit preview-only return such as movement preparation. Test the actual
caller transition where preview A becomes executed B. A helper-only test can
pass while its caller still records the wrong action. Selected categories are
not successful categories until the corresponding native result succeeds.

Inspect native helper side effects before blaming arbitration. A facing call
can launch a new spline and replace already-admitted movement even when the
combat action is instant. Join the selected actions to native spline identity;
repair a proven producer before adding cleanup for its downstream stale state.

Return the work when the trace instead identifies:

- class priority, resource, pet, form, or stance policy: `raid-role-implementation`;
- stats, coefficients, inheritance, or landed damage: `raid-class-mechanics-implementation`;
- boss or instance state: `raid-encounter-implementation`;
- route identity, provisioning, or live coordination: `raid-shard-architecture`.

## Repair and verify

Check fixture values against the claimed predicate: an out-of-range case must
actually exceed its range, and an isolated LOS case must otherwise be in range.
Test names and inert flags do not prove boundary coverage or native behavior.

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

In Python runtime identity and scope validators, reject `bool` explicitly
before accepting integers or comparing numeric identity; `True == 1` and
`False == 0` must never satisfy an identity predicate. At each lifecycle state
boundary, review both boolean impostors and omitted/default fields.

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

Treat an execution-capability change during a retained task as its own traced
lifecycle edge. For cross-map corpse recovery, record flight eligibility before
and after the tick plus the retained owner, traversal mode, attempt/wipe/route
scope, destination, generator, spline, and physical progress. If eligibility
rises while an exact matching ground `Recovery/native_long_path` is retained,
invalidate only that retained path evidence and resubmit the same typed
destination once through the existing executor. Eligibility remaining true
must not restart movement. Do not alter X/Y/Z, fabricate height, relax MMAP or
floor admission, or move flight/gravity ownership into encounter policy. Cover
living, same-map, wrong-scope, indoor, transport, stale-episode, other-owner,
already-aerial, successful-progress, and bounded-no-progress cases.

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

For hazard-relative movement, bind the diagnostic to the acting bot, stable
hazard GUID and sampled hazard position, requested destination, planner-selected
endpoint, path/floor proof, and clearance change. Preserve a rejected hazard
receipt before another movement candidate from the same tick can replace the
actor's latest observation. Diagnostic-only metadata must not change ordinary
movement fingerprints, candidate identity, admission, or execution. Do not
authorize a path change from an unjoined rejection and later infection.

Apply that distinction in every downstream receipt/checkpoint verifier too,
not only in planner admission. Do not require bit-exact equality between the
requested Z and the planner-selected terrain Z after the planner has produced
a complete `ReachedRequested` proof with exact requested X/Y, a floor-valid
endpoint, and a vertical projection inside the shared endpoint-component
tolerance. Before classifying `planner_receipt_failed` as a planner or MMAP
failure, inspect the correlated receipt, MotionMaster/spline identity, and
physical progress samples. If the same receipt reaches its selected endpoint
on the same floor, repair the false evidence predicate; do not change movement,
global path tolerances, or route geometry. Keep adversarial coverage for
excessive Z projection, horizontal drift, wrong floor, incomplete/unaccepted
proofs, and actor/map/scope/candidate/receipt drift.

Also distinguish requested-destination reach from Detour end-polygon
projection. A complete polygon corridor can legitimately terminate at
`closestPointOnPolyBoundary` when the declared point is outside the final
walkable polygon. Require a typed point-path terminal result such as exact
request reached, projected end-poly reached, no steer target, corridor
exhausted, capacity, or failure; carry the resolved end-poly point separately.
Never infer projected reach from point count, `PATHFIND_NORMAL`, or a wider 3D
tolerance. A projected endpoint may prove native movement progress, but it is
not semantic arrival at the task's logical destination.

A complete primary path with an inadmissible endpoint is terminal for that
route attempt. Do not reinterpret it as permission to probe or launch a shorter
progressive-local fallback: completeness says the native planner resolved the
request, while endpoint or floor rejection says that resolved route is unsafe
or wrong. Progressive-local fallback is eligible only for an explicitly
incomplete primary path that still satisfies the shared floor and forbidden-path
guards. Cover both branches through the final planner selection boundary.

Movement producers must submit the destination's declared/navigation-floor Z,
not the actor's transient Z, when the destination came from a route-bound
anchor. Prove the recorded requested-versus-normalized endpoint deltas against
the strict shared endpoint gate. Do not loosen that gate to compensate for a
producer that discarded its destination floor.

Route construction is not the only floor-identity boundary. Every consumer of
a retained route—including waypoint advancement, arrival, remaining-route
safety, retry, and completion—must recheck the actor against the retained
navigation-floor anchor before changing state. Test post-retention actor Z drift
at the same X/Y as well as a nearby legitimate terrain offset; 2D proximity
alone must never advance or complete a route on another floor.

Apply that floor check before mutating semantic progress, not only before
declaring arrival. A same-X/Y actor on the wrong floor must not improve best
distance, refresh the no-progress clock, increment progress samples, or postpone
the original terminal deadline. Preserve ordinary terrain following: this is a
completion/progress proof and never a command to move vertically.

Initialize a fresh destination-bound native execution observation at every
selected movement-attempt boundary before calling an adapter that may reject
early. Null actors, unavailable sessions, and other pre-planner exits must
produce current unavailable evidence instead of inheriting the previous
attempt's receipt, endpoint, or submission state. Keep a negative replay with a
valid prior receipt followed by an early rejection and prove no prior evidence
is rebound under a new timestamp.

A successful wait, suppression, or consumable candidate can coexist with a
failed movement candidate in the same kernel resolution. Do not use the
top-level `ok` result as proof of progress. When the failed candidate repeats,
require both its typed reason and a full window with no observed movement
progress before terminating; retain a nearby replay where the same retry is
allowed while movement is advancing.

Treat directional mobility and route traversal as separate candidates.
Directional spells must claim movement, cast, and GCD resources, face through
ordinary player state, and use a normal non-triggered cast. Forward travel faces
toward the route point; backward travel faces away from it. The validated point
path remains submitted independently with a stable actor-based identity, so a
reserved, unknown, cooling-down, or rejected mobility spell leaves movement
eligible in the same kernel resolution. Prove that fallback through the real
arbiter, not only by testing the two actions separately.

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
source-shape or helper-only test does not confirm native behavior. Before
recommending build or canary, the focused fixture must enter through the
production planner/admission path, cross native submission, observe the actual
generator or spline over multiple ticks, and assert the required movement or
recovery postcondition. If the claim depends on map/MMAP, collision, DBC,
database, or world lifecycle state, use those initialized production
dependencies; a preconstructed path proof or mocked successful observation is
not the production fixture.

A compiled test that manually reconstructs a production admission or submission
adapter is still a parallel implementation and may remain green while runtime
drifts. Extract the smallest shared value-level production adapter, call it from
the real manager path, and link/call that same symbol from the compiled test.
Exercise the real arbiter with reordered producers, retryable high-priority
safety, hard-masked lower alternatives, unmapped mechanics, and rejected typed
bindings. Source-presence assertions may guard wiring, but they cannot be the
behavioral proof used to admit a build.

Trace every fixture claim through the production writer and the live consumer.
A test that manually copies a before snapshot into an after snapshot, manually
constructs a successful observation, or checks production calls only as source
text is synthetic even when it compiles C++. Likewise, a launch manifest field
is not enforced merely because bundle creation and verification agree on it:
the live scheduler must parse and reject every decisive predicate. Require one
negative test proving that the fixture cannot terminalize when the claimed
production prerequisite is absent. Do not retain a compatibility fallback as
an alternate success path when the receipt claims a single exact trigger.

Construct each deterministic lifecycle fixture from the native state
projection it claims to represent. Do not clone a later or terminal-state row
and mask fields to simulate an earlier acknowledgement or transition; that can
retain impossible state and hide omitted/default behavior.

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

Do not encode only the one native path shape that happened to fail. State the
causal invariant and cover its live equivalence class: complete and incomplete
paths, direct and retained submissions, plausible same-level floor samples,
implausible lower-geometry samples, and the nearest legitimate cross-floor
negative when those variants can reach the same decision. A later recurrence
through an untested adjacent path variant means the fixture was still too
narrow, even when the recorded coordinates themselves remain green.

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

`PlayerPetData::Active` is mutable lifecycle state: ordinary dismiss/save can
clear it without changing pet identity. Resolve the live pet's stable pet
number to its exact persisted row, then compare owner, pet ID, entry, admitted
spellbook, autocasts, and receipt hash. Never select an unrelated currently
active row as a substitute, and never include `Active` in immutable identity.

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

Keep task identity and semantic deadlines separate from candidate freshness.
An authoritative running task may renew the same candidate's short arbitration
lease without changing its generation, destination, or progress clock. Replay
a later tick past the original expiry with a competing lower-priority action;
prove native path retention as well as eventual termination of a true stall.

Report implementation, fixture, build, and live results separately. Development
uses the affected tests and a bounded native canary; full qualification has its
own criteria. A recurrence requires a corrected causal fixture before retrying
the same edge, not a new authorization or an unrelated historical test bank.

For event-owned encounter movement, retain a typed semantic transition in
addition to the short generic lease. Bind it to encounter/attempt and mechanic
generation, assigned actor, transition identity, direction, destination, and
committed/arrived state. Once admitted, observation churn, changing hazard
GUIDs/positions, ordinary lease expiry, or crossing a geometric midpoint must
not choose a new destination. A typed lethal-safety action may preempt it, but
the same transition resumes afterward. Retire it only on observed native
arrival, a later mechanic generation after arrival, or exact attempt reset.
Validate the full traversed corridor, not only endpoints.

Treat observed geometry as task input, not task identity. After a terminal
native rejection, ordinary actor motion, moving-hazard drift, or nearest-hazard
GUID churn inside the same mechanic wave must not silently increment the task
generation and retry forever. A persistent task may use one explicitly bounded,
distinct alternate route, then reaches a typed failed state and releases its
resources. Rearm only for a new stable mechanic wave or lifecycle scope. Add a
multi-tick replay with sub-yard actor and hazard movement after rejection;
exact-endpoint non-repetition alone is insufficient because it can hide
semantic task churn behind slightly different coordinates.

Treat reducer authority as task input, not task existence. Once an
authoritative threat or assignment creates an actor-keyed task, a later
temporarily stale, partial, or non-authoritative facts snapshot must transition
that same task to a typed `AwaitingAuthoritativeFacts` or suspended state. It
must not make the strategy return as though the task never existed. Retain the
actor, lifecycle, mechanic wave, deadline, and last semantic progress while
waiting; emit no unsafe candidate until authority is current, then resume the
same task identity. Trace `task_created`, `awaiting_facts`, `candidate_built`,
arbitration, native submission/progress, and `succeeded`/`infected`/`failed`
with one correlation key. Add a multi-tick counterexample where first contact
creates the task, the next snapshot loses authority, and a later authoritative
snapshot must emit the stable candidate before the lethal outcome.

When an encounter strategy uses ordered conditionals to choose one movement
before the action kernel sees alternatives, treat source order as an implicit
priority system. Migrate one mechanic vertically: normalized facts, sticky
raid assignment, persistent per-bot task, passive intent collection, existing
kernel, and exact action/native outcome feedback. Keep lethal safety as an
independent high-priority intent that suspends and later resumes the same task.
Do not build a generic framework from one encounter or replace the existing
arbiter. Use a default-off authority selector until the shadow task and legacy
candidate match for the same actor, lifecycle, destination, and resource
claims. Submission alone is never task progress; projected native reach keeps
the task running until position or another semantic postcondition proves
logical arrival.

Keep the layer questions disjoint: reducers answer what is true; coordinators
answer who owns the mechanic; persistent tasks own multi-tick progress and
deadlines; policies emit every currently eligible action; the arbiter chooses
compatible actions for this tick; executors report what actually started and
progressed. Do not let one ordered conditional chain perform several of those
jobs, and do not let a task preselect the one candidate the arbiter is allowed
to see.

Movement policy never commands a bot to move vertically. It selects a logical
destination and may carry the route anchor's Z only as floor identity. Native
`PathGenerator`, MMAP, `MotionMaster`, and the movement spline follow walkable
terrain and select the executed height. Never add per-tick Z steering, vertical
offset correction, a teleport, or a wider global tolerance to make an encounter
route pass. Verify requested X/Y, selected terrain endpoint, same-floor proof,
native progress, and semantic arrival as separate facts.

If that live signature recurs while the focused fixture passes, do not patch a
new helper or run another canary. First replace the incomplete fixture with a
multi-tick replay spanning selection, arbitration, semantic retention, native
submission/progress, preemption/resume, arrival, and reset. Preserve the old
counterexample and record any corrected expectation in the architecture
handoff.

Preserve the old counterexample and add the missing live boundary to the
affected behavioral tests. An unchanged passing replay does not explain a
recurrence. Development does not require fixture-expansion metadata or a
historical full-bank receipt; those belong to sealed replay and qualification.

The replay must cross the independent action owners implicated by the observed
failure. Include the competing candidate or native recovery caller that could
undo the repair. Do not require unrelated pet, class, or boss simulation in
every movement fixture; state which native outcomes still need live validation.

Return the reproduced failure, repair, and focused test result. The coordinator
owns live validation and continues after the bounded worker finishes. A native
boss kill proves a development clear; qualification uses its separate criteria.

Use the queued build coordinator for every native build. Return a runtime
verification plan to `raid-shard-architecture`; that coordinator runs at most
one matched completion-watchdog shard. If the same edge remains, return a
failed handoff. Do not add another hypothesis or tune adjacent policies.

Use the shared handoff contract from
`raid-performance-loop/references/handoff-contract.md`. Report the exact
before/after edge, changed files, tests, build receipt, runtime verdict, and
next owner.
