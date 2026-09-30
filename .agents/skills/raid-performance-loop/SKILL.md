---
name: raid-performance-loop
description: Route a picked raid DPS gap, failed run or missing encounter prerequisite to the one specialist skill that owns it, and join the specialist result back into the tuning loop.
---

# Raid performance loop

The measure-change-measure loop, finish line, thresholds and risk tiers are in
[raid-tuning-playbook](../raid-tuning-playbook/SKILL.md); startup and graph
commands are in [trinity-orchestrator](../trinity-orchestrator/SKILL.md). This
skill decides who owns the next change.

## Find the first broken edge

Follow one actor's loss forward and stop at the first missing or contradictory edge:

`policy -> observed state -> candidate/gates -> arbitration/resources -> movement/authority -> native submission -> native outcome -> landed damage`

A spell existing in a profile does not make the rotation correct, and a low
number does not make it wrong when range, LOS, duty, setup or a mechanic is the
first failure. Keep reusable class calibration (dummy, shared across bosses)
separate from per-boss encounter validation.

## "Investigate before tuning" packets

A raid-program packet whose task says "Investigate before tuning" carries
blocking run-sanity findings. The last round's numbers for that boss are not
real yet, so find and fix the cause before any DPS change:

1. Triage each finding with the playbook's
   [sanity table](../raid-tuning-playbook/SKILL.md#sanity-findings-is-the-result-real),
   in its order.
2. Name the first broken edge for it, and route it with the table below.
   Stranded or idle bots are usually movement, range or encounter positioning,
   not rotation.
3. In the handoff, state the confirmed cause and its evidence (kill id, trace
   rows), and the observation the next run must show.

## Route to one owner

| Broken edge | Specialist skill |
| --- | --- |
| Cadence, priorities, resources, targeting, cooldowns, pets, healer/tank choices | `raid-role-implementation` |
| Native stats, coefficients, auras/procs, pet inheritance, damage per event | `raid-class-mechanics-implementation` |
| Shared movement, recovery, lifecycle, arbitration, native submission | `raid-bot-runtime-implementation` |
| Encounter facts, timers, spell values, strategy | `raid-encounter-research` |
| Native boss/instance script or DB binding | `raid-encounter-implementation` |
| Route manifests, rosters, provisioning, shard/live coordination | `raid-shard-architecture` |
| Exact WoWSims input or reference value | `raid-wowsims-reference` |
| Rotation discrepancy analysis (no implementation) | `raid-rotation-review` |
| Read-only observation of a started run | `raid-boss-babysitter` |
| Capture identity, publication and DVC cleanup | `raid-evidence-lifecycle` |
| Closed decision data or a learned ranker | `raid-policy-flywheel` |

Give the worker exactly one skill and one packet. The coordinator keeps the
parent objective; a specialist handoff is progress, not completion. When a fix
needs a native change or a new capture, stop that lane instead of approximating
it in tooling.

## References (read only when the question arises)

- [coordination-and-live-validation.md](references/coordination-and-live-validation.md):
  run closure, route-wide survival and death recovery, development versus qualification.
- [class-and-encounter-validation.md](references/class-and-encounter-validation.md):
  dummy calibration reuse and tank-damage review.
- [causal-routing.md](references/causal-routing.md): ambiguous ownership,
  persistent-task and movement slices, identity or detector alarms.
- [parallel-role-review.md](references/parallel-role-review.md): several roles
  underperform in the same run.
- [bounded-work-unit-contract.md](references/bounded-work-unit-contract.md) and
  [handoff-contract.md](references/handoff-contract.md): worker packet and handoff format.
- [recurrence-procedure.md](references/recurrence-procedure.md): only for an
  explicitly requested legacy sealed replay.
