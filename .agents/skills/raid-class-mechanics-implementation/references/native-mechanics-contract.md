# Native class-mechanics contract

This lane starts after action selection is already credible. Its unit of work
is one native outcome edge, not a whole specialization.

## Required evidence

The work unit must identify:

- exact WoWSims request, result, ComputeStats, source revision, and binary;
- exact Trinity commit, binary receipt, profile generation, actor, target, and
  closed calibration report;
- identical gear and comparable scoring-start owner/pet effective stats;
- action-share, cast-start, and landed-event cadence ratios;
- owner, primary-pet, and total damage ratios;
- the spell or pet event whose damage per event is wrong.

Damage per event is meaningful only for the same semantic event. Do not compare
a channel start with a tick, a DoT application with all periodic ticks, a
primary pet with all guardians, or an aggregate over different durations.

## Allowed implementation surfaces

- core spell damage/healing and aura calculation;
- class spell scripts and proc handlers;
- talent and glyph modifiers;
- rating/stat conversion or application;
- pet owner-stat inheritance and primary-pet spell/melee outcomes;
- canonical spell data or database bindings when their source is pinned.

Priority buckets, trigger conditions, movement, target selection, and pet
commands belong to `raid-role-implementation`. Encounter state machines belong
to `raid-encounter-implementation`.

## One-fix rule

State one falsifiable hypothesis and the metric it should move. Make one patch,
one coordinator-admitted build, and one matched verification. A failed
verification ends the work unit and returns its evidence to the coordinator.

Never derive a blanket multiplier as:

```text
wowsims_total_dps / trinity_total_dps
```

That ratio mixes cadence, primary-pet and guardian output, crit variance,
periodic event counts, and native coefficients. Repair the first proven native
edge instead.
