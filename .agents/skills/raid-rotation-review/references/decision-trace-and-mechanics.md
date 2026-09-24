# Decision trace, mechanics, and reporting

Read this reference after parity gates pass or when reviewing a policy, candidate,
movement, native outcome, route obligation, or report. It complements the common
translation model.

## Trace the first broken edge

Include decision complexity when traces show conflicting owners, oscillation, repeated
decisions, or opaque fallback. Measure the current CCN of the functions involved
before acting. Split only when the effective decision graph loses overlapping ownership or
branches. Moving branches into helpers while calling all of them preserves
complexity. Prefer independent typed candidates, explicit resource claims, stable
intent reasons, and traces for admission, rejection, execution, and outcome.
Priority arbitration remains the decision boundary; movement is a separate
set-and-forget execution concern.

For each suspicious spell or mechanic, reconstruct:

```text
source policy
  -> observed player/target/encounter state
  -> candidate and executable gates
  -> priority/resource arbitration
  -> movement or mechanic preemption
  -> native request submission
  -> core outcome
  -> landed effect/damage/progress
```

Stop at the first missing or contradictory edge. Range, LOS, route authority,
setup, resource ownership, or a higher-priority mechanic can be the actual defect.
A profile row or selected target is insufficient until an eligible candidate reaches
native submission and a landed effect.

Before changing bucket or score values, inspect setup and multi-target branches that
return before normal ranking. Replay the actual setup-to-resolver path with an
eligible competing action; preserve legitimate prepull and target setup when
removing a bypass. Use native target classification and loaded flags, not display
rank or an encounter-specific entry list.

Deduplicate replayed trace rows by actor and native sequence. Keep submissions,
primary impacts, periodic ticks, triggered effects, and per-target AoE impacts
separate; event counts are not cast counts. A no-impact interval can contain an
instant action or required movement. Join native terminal outcomes before calling a
missing impact a failed cast or idle time.

Inspect counter producers before trusting labels. In the DPS/tank calibration
collector, `action_attempts` counts valid selections even when the outcome is
casting, global cooldown, or no action; it is not cast-start count. Use per-spell
`decision_timeline` rows with `result=ok` for successful submissions, retain
excluded outcomes separately, and distinguish submission from landing.

Do not treat aggregate reasons such as `no_trained_heal` or
`no_instant_heal_while_moving` as the first broken edge. Join exact actor/target,
distance, LOS, movement, profile identity, and per-spell rejection mask. Verify
geometry in full 3D when the runtime gate does. Inspect profile gates in
`BotClassSpecActionProfile.{h,cpp}`, context/movement/mechanics/telemetry in
`BotWorldPopulationMgr.cpp`, priority/resource conflicts in
`BotActionArbiter.h`, `BotNativeActionIntent.h`, and
`BotMeleeAutoAttackIntent.h`, and route obligations in manifests and
`BotEncounterMechanicCatalog`. Relevant evidence includes
`action_attempts`, `spell_damage`, `last_action_rejections`,
`last_chosen_action`, `combat_attempt`, and `decision_kernel`.

## Compare rotation behavior

Compare setup and initial resources; player, pet, poison, form, presence, stance,
seal, totem, and autoattack state; exact priority and tie-breaking; proc, owned
aura/disease/DOT, stack, duration, resource/rune/combo-point, target-health,
target-count, cooldown, and cast-time predicates; range/LOS, movement,
target-selection, area/multidot, and pet-command semantics; waits, strict
sequences, item actions, unsupported simulator-only actions, and absent-state
numeric semantics. Compare observed action/failure/rejection distribution, uptime,
resource starvation/capping, movement loss, and off-target effects.

For pet specs bind owner and pet separately: pet identity, alive/target uptime,
action or landed-event counts, per-event damage, and damage share. A matching share
can hide uniformly low output; low absolute pet damage does not prove idle AI when
event cadence matches. After a closed bounded spec canary, run
`tools.bot_ml.spec_canary_gate`; event-cadence failures route to
`raid-role-implementation`, matching-cadence damage failures to
`raid-class-mechanics-implementation`, and the gate never authorizes repeated
tuning.

WoWSims aggregate metrics cover all iterations, while debug logs/timelines normally
cover only the first. Compare distributions separately from ordered events and
preserve log line order for equal displayed timestamps. An APL leaf with no Trinity
observation/gate is a coverage gap. A Trinity heuristic with no simulator analogue
is an intentional divergence until player-like rationale and evidence are recorded.
A static profile dump has no live candidate score: same-bucket ordering is
unresolved without runtime candidate evidence; bucket differences and observed
score/tie-break facts are the evidence.

## Route and encounter mechanics

Do not treat a fixed 300-second observation as a raid/dungeon completion gate; it is
only isolated training-dummy calibration. Inspect the complete watchdog attempt and
typed terminal reason: normal clear, semantic/no-progress stall, repeated decisions,
excessive death loops, infrastructure loss, contamination, or interruption.

Map every route obligation to typed observation, candidate, resource claim, native
action, and terminal/completion observation. Hazard/mechanic movement preempts
ordinary movement at declared priority without owning unrelated GCD/cast resources.
Ordinary DPS continues when resources are independent and pauses only for observed
safety/authority. Target switches, interrupts, dispels, cooldowns, tank swaps,
recovery, and interactions retain exact actor/target/attempt/route identity.
Retryable rejection falls through or retries with bounded diagnostics. A repeated
fail loop terminates attributable evidence for investigation, while dungeon
execution has no arbitrary overall time cap.

WoWSims does not model route pathing or boss-script authority. Use it for class
action semantics and controlled encounter inputs, then review route/script
observations in Trinity.

## Findings and handoff

Lead with the first broken edge and one concrete counterexample. Include severity
and issue type (correctness, liveness, evidence, or tuning), exact spec/node/actor/
target and source hashes, WoWSims policy plus Trinity code/profile/trace paths,
expected versus observed predicate/action/outcome, comparison impact, smallest
player-like fix, and static/non-ledger/live verification.

Never recommend direct state manufacture, forced target/cast success, teleportation,
scoring-time health/resource refill, or denominator-derived tuning. Prefer typed
observations, candidates, native requests, and later outcome receipts. A pinned
reference contract and a production-evaluator counterexample can establish a policy
defect before its live frequency is visible; do not require an observation-only
build solely to admit that repair. Keep native frequency, DPS cost, and improvement
claims unproven until measured; this does not justify coefficient tuning,
missing-reference assumptions, or fabricated outcomes.

A raid result above the self-buffed dummy reference neither excludes a shared class
defect nor establishes parity. Raid buffs, head modifiers, adds, and duties change
that comparison. Require matched stats and event/cadence evidence before accepting
or rejecting a mechanics hypothesis.
