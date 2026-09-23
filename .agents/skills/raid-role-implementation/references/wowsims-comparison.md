# WoWSims comparison rules for role work

Read this only when a role work unit uses a WoWSims reference. A rotation,
priority or cadence change measured by the raid tuning playbook's batch needs
none of it.

When current spec/reference status is missing, run:

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

A claim based on a WoWSims comparison, or a change to damage behavior, requires
`gear_parity.status` and `effective_stat_parity.status` to be `match` and
`dps_tuning_gate.tuning_admitted` to be true. A trace-backed legality or
candidate-coverage repair may proceed without numerical stat parity when its
correctness does not depend on those stats; keep its acceptance limited to the
repaired edge. Gear-manifest equality alone is not enough. A stat mismatch belongs to setup,
core stat application, or pet inheritance; an `insufficient_data` result needs
a scoring-start recapture or bound WoWSims stat artifact. Return that boundary
instead of compensating with priorities, coefficients, or repeated search.

For a `self_provided_baseline`, `effective_stat_parity.status=match` may include
explicit `favorable` checks where a monotonic Trinity throughput stat is above
the simulator minimum. A lower stat, gear drift, or secondary-rating drift is
still a blocker.
