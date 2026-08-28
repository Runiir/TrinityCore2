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

Change the smallest shared transition, gate, owner token, or native-action
edge that explains the evidence. Preserve ordinary player movement, corpse
release, graveyard, entrance, resurrection, spell, threat, and encounter
rules. Never teleport, manufacture a wipe, revive, force a target, or mutate a
boss outcome.

Extract or reuse a deterministic C++ transition boundary when practical. Add
focused tests for the recorded counterexample and nearby valid states. A
source-shape test alone does not confirm native behavior.

For set-and-forget native movement, distinguish the short arbitration lease
from the native generator it admitted. A lease may expire exactly at the next
decision cadence while the receipt-bound `MotionMaster` path is still active.
Do not make observation, progress, or one-shot recovery predicates depend on
`ExpiresAtMs > nowMs` unless the action itself requires a currently valid
lease. Bind them instead to the recorded owner, attempt/wipe/route scope,
destination, traversal mode, and observed native path state. Test the exact
lease-expiry boundary at `nowMs == ExpiresAtMs`, plus one tick before and one
tick after; a source-shape assertion is not enough.

Use the queued build coordinator for every native build. Return a runtime
verification plan to `raid-shard-architecture`; that coordinator runs at most
one matched completion-watchdog shard. If the same edge remains, return a
failed handoff. Do not add another hypothesis or tune adjacent policies.

Use the shared handoff contract from
`raid-performance-loop/references/handoff-contract.md`. Report the exact
before/after edge, changed files, tests, build receipt, runtime verdict, and
next owner.
