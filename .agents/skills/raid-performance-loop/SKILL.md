---
name: raid-performance-loop
description: Coordinate the Trinity-Cata raid performance program by inspecting deterministic readiness, selecting bounded specialist work units, assigning non-overlapping ownership, and joining handoffs. Use for raid-program orchestration, deciding what class/boss/reference/data task should run next, splitting work across agents, or preventing one agent from owning WoWSims, class rotations, boss research, boss implementation, live validation, and ML data at once. Do not use this skill to implement gameplay behavior itself.
---

# Raid Performance Loop

Act only as the coordinator. Keep specialist context and file ownership separate.

## Inspect the control plane

Run:

```bash
pixi run python -m tools.raid_program.raid_workloop status
```

Treat `required_next_work_unit` as authoritative. If the active-work-unit
descriptor is stale, stop before assigning gameplay work
and repair that descriptor from the latest immutable handoff.

Then emit an exact work unit when needed:

```bash
pixi run python -m tools.raid_program.raid_workloop spec fire_mage
pixi run python -m tools.raid_program.raid_workloop boss blackwing_descent magmaw --mode 25H
```

Do not treat a stale WoWSims value, source-present boss, dossier, diagnostic
shard, or old DVC batch as a passing gate.

Keep validation clocks explicit in every work unit. Only isolated
training-dummy DPS throughput calibration owns an exact 300-second scoring
window. Raid and dungeon work units must use completion-watchdog execution and
terminate on normal clear or typed semantic/no-progress, repeated-decision,
death-loop, infrastructure, contamination, or interruption evidence. An
emergency wall-clock expiry never passes a route.

For a DPS work unit, inspect the rotation-review gate before assigning a role
implementation owner. The exact simulator and Trinity inputs must have the same
gear identity, and the comparison record must report:

```text
gear_parity.status = match
effective_stat_parity.status = match
dps_tuning_gate.tuning_admitted = true
```

Total-DPS claims additionally require
`total_dps_comparison_gate.comparison_admitted = true`. Consumable mismatch
fails that total-DPS gate without invalidating unaffected trace-only signals.

`insufficient_data` routes to one bounded reference or capture work unit.
`mismatch` routes to the owner of setup, stat application, or pet inheritance at
the reported first-broken edge. Neither result may be retried as rotation tuning,
and neither permits the coordinator to stop or restart the worldserver.

Bind every DPS claim to one reference class. Use `self_provided_baseline` as a
one-sided minimum floor with no upper rejection bound. It includes only effects
the frozen player can provide through its own setup and normal actions. Require
per-spec inventory provisioning and native use of the exact flask, food,
pre-pot, combat potion, racial, and profession actions selected by the request.
Use `controlled_live_parity` for exact cast, cadence, stat, and damage diagnosis.
Keep `upstream_full_throughput` as a duration-bound capability/UI cross-check.
Differences among these values are expected and do not block trace-only review.
A missing class blocks only its own acceptance claim.
The current work unit's catalog projection is authoritative for current versus
stale classification. Embedded metadata in an older runtime report remains
capture-time provenance and cannot override `accepted_dps_reference_class` or a
`current_accepted` catalog classification.

Use deterministic routing for an `insufficient_data` result:

- missing WoWSims ComputeStats -> `raid-wowsims-reference`;
- missing Trinity `scoring_start_stats` in a closed report ->
  `raid-shard-architecture` for one capture-only canary that preserves the
  existing worldserver lifecycle, followed by `raid-rotation-review`;
- a malformed comparison artifact -> `raid-rotation-review`.

When WoWSims reports `workspace_state=remote_requires_hydration`, run the
commands from `required_hydration_work_unit` exactly. This is materialization
of an already promoted reference, not reference regeneration and not a class
fix. The normal sequence is:

```bash
pixi run python -m tools.raid_program.wowsims_reference_workspace hydrate
pixi run python -m tools.raid_program.raid_workloop status
```

After the bounded reference/review work finishes, run the emitted exact
`evict_after_use` command. Never replace it with broad DVC garbage collection.

The completed comparison is `failed` when one of these data gates does not
pass. Do not classify it as `blocked` unless authority or an external input is
actually unavailable.

## Route work to one specialist owner

| Work unit | Required specialist skill | Owner output |
| --- | --- | --- |
| Exact simulator input or DPS denominator | `raid-wowsims-reference` | current promoted value plus reconstruction receipt |
| DPS, tank, or healer policy behavior | `raid-role-implementation` | one fixed first-broken edge plus role-harness evidence |
| Native class, spell, stat, or pet outcome | `raid-class-mechanics-implementation` | one fixed damage/stat edge plus coordinator build receipt |
| Shared bot movement, recovery, lifecycle, or native submission | `raid-bot-runtime-implementation` | one fixed shared runtime edge plus replay and runtime-verification plan |
| Online boss strategy and numeric claims | `raid-encounter-research` | reviewed dossier, mechanic contract, and value ledger |
| Native boss/instance/DB implementation | `raid-encounter-implementation` | replay-tested native change and build receipt |
| Closed decision data or learned ranker | `raid-policy-flywheel` | admitted/quarantined batch and evaluation |
| Rotation discrepancy review | `raid-rotation-review` | attributable comparison; no implementation ownership |
| Shard construction and live coordination | `raid-shard-architecture` | exact shard identity and verified handoff |
| Live observation | `raid-boss-babysitter` | read-only decisive observations |
| Publication and eviction | `raid-evidence-lifecycle` | DVC publication/reconstruction/cleanup proof |

Use `trinity-orchestrator` for model selection and worker limits. Give each
worker exactly one specialist skill and one work-unit JSON. Require the worker
to work directly without launching nested agents.

Require a compact material-gate receipt within 60 seconds of dispatch and at
least every 60 seconds while work continues: current gate, command or process
identity, decisive evidence path, and next expected edge. A worker may make at
most two failed command attempts on the same edge before returning a failed
handoff. After the first missed receipt, request status without interrupting.
After the second consecutive miss, interrupt and request the bounded handoff;
do not let silence expand into repository discovery or an optimization loop.

Treat an empty final message as a missed receipt: verify what actually landed
with `git status`/`git diff` and your own test run before accepting or
rejecting the unit. Reject any fix handoff that (a) did not execute its tests,
(b) threads a field that no real closed artifact contains, or (c) inverts
non-applicable predicates instead of skipping them. When one worker proves a
fix requires native changes or a new capture, stop that lane; do not redispatch
the same tools-side unit against the same edge.

## Parallelize only disjoint lanes

Parallel work is useful across these boundaries:

- one WoWSims reference cohort and one boss research packet;
- one class-family implementation and research for a different boss;
- analysis of an immutable closed batch and source work that cannot alter it.

Serialize these shared mutations:

- native heavyweight builds through `queued_build.py`;
- worldserver console, provisioning, roster leases, and canonical run state;
- canonical DVC publication and eviction;
- edits to a shared action profile, instance script, or encounter contract.

Do not assign one agent per spec, source, review angle, or telemetry category.
Use one owner per class family, boss, reference cohort, or closed batch.

## Join gates, not prose

Accept a specialist result only when its handoff follows
[references/handoff-contract.md](references/handoff-contract.md). Review hashes,
first-broken edge, validation result, and next dependency. Reject claims based
only on tests, source presence, a copied profile, engagement, or raw DPS/HPS.
For DPS tuning, also reject a handoff that omits exact gear identity or the
effective-stat parity result. Equal cast ratios with different damage are a stat
or native-outcome diagnostic until this gate passes; they are not permission to
keep optimizing the priority queue.

Before stopping, update the governing status/handoff artifact, commit coherent
code/config, and apply the required DVC lifecycle. Never let the coordinator
silently implement a specialist's failed work unit.

For one-spec canaries, classify the closed comparison with:

```bash
pixi run python -m tools.bot_ml.spec_canary_gate \
  --review /path/to/rotation-review.json \
  --spec affliction_warlock \
  --reference-class self_provided_baseline \
  --output /tmp/affliction-canary-decision.json
```

The decision emits at most one capture/review/fix work unit. On the matched
verification, pass `--fixes-used 1`; a remaining mismatch then terminates as
`fix_budget_exhausted`. Route cast mix, cadence, pet uptime, or pet event
cadence to `raid-role-implementation`. Route matching cadence with wrong owner
or primary-pet damage per event to `raid-class-mechanics-implementation`.
When the selected denominator is `self_provided_baseline`, accept
`runtime_dps >= reference_dps`; never fail a canary merely for exceeding the
baseline. Before that comparison, require exact consumable parity. Provision
the per-spec items and retain one successful native pre-pot use before combat
plus one successful native combat-potion use during the scoring window when
both are configured.
