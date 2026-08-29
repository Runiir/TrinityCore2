---
name: raid-role-implementation
description: Implement and tune one Trinity-Cata DPS, tank, or healer behavior work unit using exact WoWSims or role-harness evidence and the Playerbots-style priority/action model. Use for class/spec action profiles, triggers, gates, priorities, prerequisites, alternatives, cooldown/resource logic, pet/form/stance behavior, target selection, role efficiency, or a first-broken policy-to-native-outcome edge. Do not use for generating WoWSims denominators, researching boss values, scripting native bosses, or training ML policies.
---

# Raid Role Implementation

Own one class family or one exact role failure. Do not own the simulator,
encounter source, live server, or evidence publisher.

Before inspection or editing, apply
[the bounded work-unit contract](../raid-performance-loop/references/bounded-work-unit-contract.md).
Lock one policy hypothesis, owned class/profile files, excluded native
mechanics/encounter/shard lanes, and one focused validation. A useful adjacent
fix is a new handoff, not part of this role patch.

## Admit the work unit

Run:

```bash
pixi run python -m tools.raid_program.raid_workloop spec <spec>
```

For DPS, interpret `benchmark.state=blocked_exact_reference` as an acceptance
gate, not a blanket diagnostic stop. Hand the exact denominator to
`raid-wowsims-reference` and copy `benchmark.required_reference_work_unit`
verbatim: reference promotion is one atomic 16-spec cohort, never a per-spec
work unit. While that work is pending, a bounded `diagnostic_only` class work
unit may still implement one trace-backed mismatch in cast mix, cast cadence,
failed/rejected actions, priority order, DoT or buff uptime, resources, or pet
execution. It must not use stale DPS as a tuning target, claim a simulator DPS
ratio, or promote the result.

If `benchmark.state=hydrate_exact_reference`, do not hand off generation and
do not edit the role. Return the emitted `required_hydration_work_unit` to the
coordinator. After its hydrate-and-verify command passes, rerun the same spec
work unit and proceed from the now-local promoted reference.

Parameter differences such as target distance are dimensions to normalize, not
reasons to abandon the whole diagnostic. Compare unaffected actions and signals
directly; isolate or exclude actions whose eligibility changes with the
parameter. Require a matched rerun before changing those parameter-sensitive
actions or making a total-DPS acceptance claim. Stop only when the proposed code
change depends on the missing exact reference or when no attributable runtime
signal remains.

Read `benchmark.reference_class_policy` before using a DPS number. A
`self_provided_baseline` is a one-sided floor, so exceeding it passes and is not
an overtuning failure. Use `controlled_live_parity` for action ratios and
damage-per-event diagnosis. Never compare Trinity against a UI or full-preset
number whose race, professions, consumes, external buffs/debuffs, duration,
variation, distance, or target differs. Such a difference narrows the usable
signals; it does not halt the whole work unit.

Compare only hashes with the same explicit field name; catalog file, canonical
JSON, target-catalog, and receipt hashes are different identities. Treat
`wowsims_source_relative_apl` as relative to the pinned WoWSims checkout, not
the Trinity worktree. For tanks and healers, require the role-harness contract.
Record the Trinity commit, profile generation/hash, actor/target,
gear/talents/glyphs, route/scenario, and evidence identity.

Load `raid-rotation-review` and produce the normalized comparison before
editing. For DPS, require its `gear_parity.status` and
`effective_stat_parity.status` to be `match`, and require
`dps_tuning_gate.tuning_admitted` to be true before changing rotations or damage
behavior.
Gear-manifest equality alone is not enough. A stat mismatch belongs to setup,
core stat application, or pet inheritance; an `insufficient_data` result needs
a scoring-start recapture or bound WoWSims stat artifact. Return that boundary
instead of compensating with priorities, coefficients, or repeated search.

For a `self_provided_baseline`, `effective_stat_parity.status=match` may include
explicit `favorable` checks where a monotonic Trinity throughput stat is above
the simulator minimum. A lower stat, gear drift, or secondary-rating drift is
still a blocker.

Stop at the first missing edge:

```text
observation -> candidate -> hard gates -> priority/resources -> movement/authority
            -> native submission -> completion -> landed effect -> role outcome
```

If the break is boss authority, route ownership, native script timing, or
reference identity, return it to the owning specialist instead of compensating
inside the class rotation.

## Implement the smallest policy change

If the policy lives in a high-CCN decision function, reduce the decision graph
as part of the bounded repair. The 2026-08-28 native bot audit found 45
functions above CCN 100, with a maximum of 464. Do not merely move branches
into helpers and call every helper from the same monolithic decision. Give an
extracted class/spec or pet concern one typed candidate, explicit gates,
resource claims, stable reason text, and an observable outcome. Preserve the
shared priority queue and keep movement ownership separate from the DPS,
healer, or tank decision. Measure the touched function before and after and
keep every C/C++ source and header below 1,000 lines.

Follow [references/priority-action-contract.md](references/priority-action-contract.md).
Change one trigger, typed gate, priority, resource claim, prerequisite,
alternative, target selector, or observed-state transition. Preserve ordinary
native spell legality and game outcomes.

Candidates are deferred until the shared kernel resolves. Role code must use
explicit lifetime-safe captures for `Candidate::Attempt`; never use blanket
`[&]` in a submitter that returns before resolution. If a role trace crashes or
changes nondeterministically inside `Kernel::Resolve`, return the shared
lifetime repair to `raid-bot-runtime-implementation` rather than compensating
with class priorities.

For long offensive cooldowns, guardians, combat potions, and Bloodlust, own
only the class-correct native candidate, semantic category/tags, prerequisites,
and alternatives. Do not encode trash-versus-boss route policy or an encounter
release phase in a class rotation. Shared reservation belongs to
`raid-bot-runtime-implementation`; boss-phase release belongs to
`raid-encounter-implementation`. Emergency defensive and healing cooldowns are
not withheld merely because the current route node is trash.

Pet autocast configuration is persistent setup, not a combat-priority action.
Declare the class-correct initial autocast state for provisioning/admission;
after the receipt commits, role code may issue ordinary pet attack/follow and
rank pet actions but must not toggle receipt-bound autocast or rewrite the pet
spellbook. Return late setup to `raid-bot-runtime-implementation` with the
identity-drift reason rather than suppressing the receipt check.

If a role change triggers a terminal receipt failure, inspect whether the role
candidate wrote frozen setup state before changing priorities or the
validator. A high-signal identity terminal can be the consequence of an
unrelated class action. The role repair is complete only when its candidate
uses normal combat or lifecycle state and leaves gear, talents/glyphs, group,
map/instance, roster lease, and persistent-pet identity untouched.

Do not tune from final DPS alone. A diagnostic-only edit needs one observed
first-broken edge and one metric expected to move; run one before/after check
and stop. Permit at most one implementation plus one matched verification run
for the bounded work unit. If the same first-broken edge remains, report it and
hand it back to its owning layer rather than entering an optimization loop.
Never manufacture a proc, aura, resource, threat state, target, cast success,
heal demand, or boss outcome.

Before calling a previously observed role blocker fixed, consult the active
route recurrence ledger. A clean intervening canary does not reset an
intermittent candidate, pet, target, or movement-authority failure. Reappearance
uses the existing causal signature and increments it once for that run. At ten
occurrences, return the accumulated evidence for architecture review instead of
adding another class-policy branch.

## Validate by role

Run focused unit/replay checks first. Use `queued_build.py` for every native
heavyweight build. Then run one deterministic role window. Only an isolated
training-dummy DPS throughput check uses the exact 300-second scoring window;
tank/healer harnesses use their declared demand contracts, and raid/dungeon
checks use completion watchdogs rather than a fixed 300-second timer:

- DPS: current reference ratio, active/elapsed DPS, action mix, landed/attempted
  ratio, resource capping/starvation, cooldown/proc uptime, movement/range loss,
  target correctness, and pet contribution. For pet specs, separate pet
  alive/target uptime, action or landed-event cadence, and damage per event; do
  not change pet priority when cadence matches but damage per event does not.
  Return that case to `raid-class-mechanics-implementation` with the exact
  owner/pet stat and event ratios.
  Provision the exact per-spec flask, food, pre-pot, and combat potion as real
  inventory items. Teach the policy to use them through native item actions.
  Require a successful pre-pot before combat, a successful potion during
  combat, item-count changes, and the expected auras. A fixture-added aura is
  not consumable-use evidence. If consumable execution differs, report that
  first edge or regenerate a condition-matched reference before interpreting
  total DPS.
- Tank: threat retention and healer exposure, snap/add threat, taunt/interrupt,
  mitigation and defensive coverage, spike size, survival, action validity, and
  useful damage.
- Healer: delivered demand, deaths/health floor, effective healing and absorbs,
  overheal, mana slope/time-to-OOM, response latency, triage accuracy, dispels,
  cooldown periods, idle-under-demand, and cast failures.

Evaluate captured metrics with:

```bash
pixi run python -m tools.bot_ml.role_calibration_harness \
  --input <role-record.json> --output <evaluation.json>
```

Use a script-ready boss shard only to test an encounter-dependent behavior.
Pass live coordination to `raid-shard-architecture` and publication to
`raid-evidence-lifecycle`.

Return one before/after first-broken edge, changed files, focused tests, role
metrics, evidence paths, and the next dependency. Do not broaden the patch to
another class family or boss.
