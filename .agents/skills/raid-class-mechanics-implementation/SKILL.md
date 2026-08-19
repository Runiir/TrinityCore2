---
name: raid-class-mechanics-implementation
description: Repair one trace-backed native Trinity-Cata class-mechanics mismatch. Use for effective-stat application, pet stat inheritance, spell coefficients, aura/talent/glyph modifiers, proc outcomes, primary-pet damage per event, and other core outcomes. Damage tuning requires matching gear, effective stats, and cadence; stat/inheritance repair requires exact gear and attributable runtime stats. Do not use for priority queues, simulator references, boss scripts, live shard control, or repeated DPS optimization.
---

# Raid Class Mechanics Implementation

Own one trace-backed native outcome edge. Keep policy selection, simulator
generation, live process ownership, and evidence publication outside this work
unit.

## Admit only a mechanics failure

Read [references/native-mechanics-contract.md](references/native-mechanics-contract.md).
Require one immutable rotation review or spec-canary decision and admit exactly
one of these modes.

For `stat_application_or_pet_inheritance`:

```text
gear_parity.status = match
scoring-start owner/pet stats = runtime-attributable
effective_stat_parity.status = mismatch
first_broken_edge = stat_application or pet_stat_inheritance
dps_tuning_gate.tuning_admitted = false
```

This mode repairs only the first stat/inheritance edge. Cast mix and cadence
need only be usable enough to attribute the scoring-start snapshot; remeasure
them after stat parity is restored. It must not change coefficients or tune DPS.

For `damage_outcome`:

```text
gear_parity.status = match
effective_stat_parity.status = match
dps_tuning_gate.tuning_admitted = true
cast mix and landed-event cadence = within policy
first_broken_edge = native_class_damage_model or native_pet_damage_model
```

In `damage_outcome`, wrong owner or pet cadence, target uptime, action
selection, resources, range, or rejections returns the work unit to
`raid-role-implementation`.
Missing runtime attribution belongs to a capture-only
`raid-shard-architecture` work unit. Never compensate for missing evidence with
a coefficient change.

## Prove the exact broken outcome

Bind the Trinity commit/binary, WoWSims request/result/ComputeStats hashes,
gear manifest, owner and pet scoring-start stats, calibration actor and target,
spell identity, and duration. Separate:

- owner damage from primary-pet and guardian damage;
- action/cast starts from landed damage events;
- direct hits from periodic ticks and triggered child spells;
- primary-pet event cadence from damage per event;
- static spell data from talent, glyph, aura, target-debuff, and pet-inheritance
  modifiers.

Locate the first native function or data edge that disagrees with the pinned
reference. Use repository spell data, client data, or pinned WoWSims source as
evidence; do not invent a coefficient from the final DPS gap.

## Make one bounded repair

Change the smallest native spell, aura, stat, proc, or pet-inheritance edge
that explains the measured discrepancy. Preserve normal spell legality and the
priority/action model. Do not add hidden damage multipliers, simulator-only
auras, synthetic procs, or calibration-specific gameplay branches.

Permit one implementation attempt in the admitted mode. Run focused unit/replay tests, then request
one heavyweight build through `queued_build.py`. Hand the resulting binary and
receipt to `raid-shard-architecture`; this skill must not start, stop, restart,
or attach to a worldserver.

## Verify once and stop

Use one matched calibration window. A stat/inheritance repair passes when gear
still matches and the affected effective stats enter the declared parity
envelope; the coordinator then re-runs cadence and damage classification. A
damage-outcome repair passes only when gear and effective stats still match,
cadence remains within policy, and the affected owner/pet damage-per-event plus
total DPS enter the declared acceptance envelope.
If the same edge remains after that verification, return a failed handoff with
the observed ratios and no new patch proposal. Do not search or tune again.

Return the input hashes, first-broken edge, hypothesis, changed files, focused
tests, coordinator build receipt, before/after owner and pet signals, and next
dependency.
