---
name: raid-role-implementation
description: Implement and tune one Trinity-Cata DPS, tank, or healer behavior work unit using exact WoWSims or role-harness evidence and the Playerbots-style priority/action model. Use for class/spec action profiles, triggers, gates, priorities, prerequisites, alternatives, cooldown/resource logic, pet/form/stance behavior, target selection, role efficiency, or a first-broken policy-to-native-outcome edge. Do not use for generating WoWSims denominators, researching boss values, scripting native bosses, or training ML policies.
---

# Raid Role Implementation

Own one class family or one exact role failure. Do not own the simulator,
encounter source, live server, or evidence publisher.

A tank damage assignment needs a damage/cadence comparison against matched WCL
or a compatible class reference, not only threat or survival qualification.
Use the coordinator's ranked loss review and preserve mitigation while repairing
damage delivery. Measuring and keeping or reverting a change follows the
[raid tuning playbook](../raid-tuning-playbook/SKILL.md).

For an assigned read-only tank or healer review, use the supplied run context
and relevant `references/tank-review-notes.md` or `healer-review-notes.md` when
present. Return a causal repair packet before implementation. Shared encounter
or movement failures remain owned by the coordinator's single assigned worker.

Before inspection or editing, apply
[the bounded work-unit contract](../raid-performance-loop/references/bounded-work-unit-contract.md).
Lock one policy hypothesis, owned class/profile files, excluded native
mechanics/encounter/shard lanes, and one focused validation. A useful adjacent
fix is a new handoff, not part of this role patch.

## Admit the work unit

Use the coordinator's bounded packet when it already contains the exact trace,
current reference identity, owned files, affected callers and verification
commands. Do not repeat completed diagnosis or load a second specialist skill
to reconstruct that packet. For a healer/tank result, use the compact gate/metric
projection in [tool-call examples](../raid-rotation-review/references/evidence-views.md#tool-call-examples).
Do not dump `raw_runtime_status` to find a metric already exposed by the evaluator.
When the work uses a WoWSims reference (spec status, benchmark states,
reference classes, stat parity), first read
[WoWSims comparison rules](references/wowsims-comparison.md).

Compare only hashes with the same explicit field name; catalog file, canonical
JSON, target-catalog, and receipt hashes are different identities. Treat
`wowsims_source_relative_apl` as relative to the pinned WoWSims checkout, not
the Trinity worktree. For tanks and healers, require the role-harness contract.
Record the Trinity commit, profile generation/hash, actor/target,
gear/talents/glyphs, route/scenario, and evidence identity.

Translate reference terms through the native producer and consumer before
choosing a gate. Aura charges and stack amount are distinct native values;
a simulator's "stacks" label does not identify the server accessor. Fixtures
must preserve that distinction, and relevant inherited/nonvirtual accessors,
instead of flattening them into a convenient successful stub.

For proc-driven spell variants, require the actual native aura effect and
replacement identity in the packet. A made-up cast-time modifier can prove a
helper works while leaving the real override unreachable. The regression must
exercise the observed native mechanism through eligibility and execution;
retain the requested action identity separately when resolving its native form.

Use the supplied rotation review; request only the evidence missing for this
repair. A rotation, priority or cadence change measured by the playbook's raid
batch needs no WoWSims parity. A claim based on a WoWSims comparison, or a
change to damage behavior, needs the stat-parity gates in the WoWSims
comparison rules; never compensate for a stat mismatch with priorities or
coefficients.

Stop at the first missing edge:

```text
observation -> candidate -> hard gates -> priority/resources -> movement/authority
            -> native submission -> completion -> landed effect -> role outcome
```

Keep preference separate from legality. Do not disable a safe filler just to
make category-coverage expectations match an AoE rotation. Check adjacent
enemy counts and the case where the preferred action is forbidden, on cooldown
or otherwise unavailable. Preserve a legal fallback through existing candidate
priorities; never relax encounter safety to make the preferred action execute.
When a historical migration caused the trace failure, inspect its stated reason
and affected validation before calling the live database drifted.

Treat aggregate resolver labels as summaries, not causes. Before changing a
healer profile or priority, retain the target, actor-to-target distance, LOS,
movement/instant-only state, profile identity, and every relevant spell's
rejection reason. A correct priority target does not prove that any heal is
executable. If the selected target is outside the legal range because an
encounter movement policy displaced the healer, return the repair to the
encounter owner instead of adding a spell, priority, or range exception.

For equivalent faction or class abilities, resolve the actor's actual known
spell and carry that identity through submission and outcome observation.
Verify legitimate spell provisioning separately; empty persisted spell rows
do not prove a transient bot's runtime spellbook. A regression must exercise
the supported variants, not require the old implementation's hardcoded ID.

For setup selection repairs, follow both selection and already-ready checks.
Exercise missing setup, an existing wrong setup, and an existing correct setup
through the actual owner. Changing the preferred spell alone can leave the
old state accepted forever. Keep native effect acceptance separate from a
stubbed selector test.

If the break is boss authority, route ownership, native script timing, or
reference identity, return it to the owning specialist instead of compensating
inside the class rotation.

Class and role policies do not compute terrain height or issue vertical
movement. They may emit class mobility or ordinary movement candidates toward a
logical encounter/route destination, but native pathing owns the traversed Z.
Return wrong-floor, path-generation, or missing movement-progress evidence to
`raid-bot-runtime-implementation`; do not compensate with spell priority,
teleportation, or a height offset.

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

Name one observed first-broken edge and the metric expected to move; the
playbook's batch measurement decides keep or revert. Never manufacture a proc,
aura, resource, threat state, target, cast success, heal demand, or boss outcome.

A blocker that reappears after a clean run keeps its original error-ledger ID;
a clean intervening run does not reset an intermittent failure. A recurrent
role or pet blocker invalidates the previously passing fixture.
Replace it with a higher revision that executes the exact observed state and
fails against the pre-fix behavior; source-text assertions and configuration
presence checks are insufficient. For persistent pet autocast, separately
prove setup identity, native per-tick target eligibility, and suppression of a
redundant beneficial recast while preserving ordinary offensive autocast. Keep
the regression permanently. Development runs require the affected behavioral
tests at the reviewed source identity; the entire bank belongs to qualification.

## Validate by role

Run focused unit/replay checks first; raid measurement follows the playbook.
Tank/healer harnesses use their declared demand contracts. Diagnose with these
role metrics:

- DPS: ratio to target and encounter-window DPS (playbook definitions), action mix, landed/attempted
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

### Scoped action permission

When admitting one spell through a scoped area policy, trace the caller that
constructs the general `forbidArea` flag. A resolver-only test can pass while
that caller has disabled protection for every other candidate. Exercise the
actual caller with the allowed spell and an unrelated area spell, then the
resolver and both native executor checks. Preserve native secondary targets;
policy permission must not become a custom spell target filter.
