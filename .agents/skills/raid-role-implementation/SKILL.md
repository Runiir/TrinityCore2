---
name: raid-role-implementation
description: Implement and tune one Trinity-Cata DPS, tank, or healer behavior work unit using exact WoWSims or role-harness evidence and the Playerbots-style priority/action model. Use for class/spec action profiles, triggers, gates, priorities, prerequisites, alternatives, cooldown/resource logic, pet/form/stance behavior, target selection, role efficiency, or a first-broken policy-to-native-outcome edge. Do not use for generating WoWSims denominators, researching boss values, scripting native bosses, or training ML policies.
---

# Raid Role Implementation

Own one class family or one exact role failure. Do not own the simulator,
encounter source, live server, or evidence publisher.

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

Parameter differences such as target distance are dimensions to normalize, not
reasons to abandon the whole diagnostic. Compare unaffected actions and signals
directly; isolate or exclude actions whose eligibility changes with the
parameter. Require a matched rerun before changing those parameter-sensitive
actions or making a total-DPS acceptance claim. Stop only when the proposed code
change depends on the missing exact reference or when no attributable runtime
signal remains.

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

Stop at the first missing edge:

```text
observation -> candidate -> hard gates -> priority/resources -> movement/authority
            -> native submission -> completion -> landed effect -> role outcome
```

If the break is boss authority, route ownership, native script timing, or
reference identity, return it to the owning specialist instead of compensating
inside the class rotation.

## Implement the smallest policy change

Follow [references/priority-action-contract.md](references/priority-action-contract.md).
Change one trigger, typed gate, priority, resource claim, prerequisite,
alternative, target selector, or observed-state transition. Preserve ordinary
native spell legality and game outcomes.

Do not tune from final DPS alone. A diagnostic-only edit needs one observed
first-broken edge and one metric expected to move; run one before/after check
and stop. Permit at most one implementation plus one matched verification run
for the bounded work unit. If the same first-broken edge remains, report it and
hand it back to its owning layer rather than entering an optimization loop.
Never manufacture a proc, aura, resource, threat state, target, cast success,
heal demand, or boss outcome.

## Validate by role

Run focused unit/replay checks first. Use `queued_build.py` for every native
heavyweight build. Then run one deterministic role window:

- DPS: current reference ratio, active/elapsed DPS, action mix, landed/attempted
  ratio, resource capping/starvation, cooldown/proc uptime, movement/range loss,
  target correctness, and pet contribution. For pet specs, separate pet
  alive/target uptime, action or landed-event cadence, and damage per event; do
  not change pet priority when cadence matches but damage per event does not.
  Return that case to `raid-class-mechanics-implementation` with the exact
  owner/pet stat and event ratios.
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
