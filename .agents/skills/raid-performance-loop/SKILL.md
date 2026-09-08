---
name: raid-performance-loop
description: Coordinate bounded raid and class repairs, join specialist results, and continue through live validation until the user's objective is achieved.
---

# Raid performance loop

Read the current result at the top of
[`shared_worldserver_workflow_20260907.md`](../../../docs/bot_raids/shared_worldserver_workflow_20260907.md)
before choosing work; its historical entries do not override the current result.

Use one repair loop: inspect the failed run, identify the earliest actionable mismatch,
repair it, test the affected behavior, review risky changes, build, run, and close evidence.
A worker or attempt ending does not end the user's task. Continue automatically after
passing checks. Stop unchanged retries at ten occurrences of the same first-broken edge,
write the causal summary, and change the hypothesis or architecture before resuming.

## Development runs

Use the existing capture controller's development mode with a canonical scenario/profile.
Require attributable clean source, verified binary/configuration, exact roster/readback,
runtime assets, a completion watchdog, native outcomes, and cleanup. Run cheap metadata
checks and affected behavioral tests before building. Execute overlapping tests once.
Do not require historical fixture-expansion requests, a full qualification suite, or a
new authorization/handoff document for each development attempt. Historical ledgers are
investigation records, not the development launch authority.

Keep one compact current issue/run summary: observed failure, source, repair, relevant
tests/review, live result, evidence pointer, and next action. Generated capture receipts
are the evidence; do not transcribe their fields into multiple handoff documents.
A development clear requires real native boss death but does not qualify a full raid,
validate every mechanic, or admit training data.

## Qualification

Use the full required regression/roster/reference and evidence checks when promoting a
boss, full raid, class calibration, or training dataset. Legacy sealed fixture replay
remains available when specifically testing that fixture. Consult the existing references
only for the qualification or specialist boundary actually being exercised.

## Route the repair

- Cadence, targeting, resources, healing choices: raid-role-implementation.
- Matching gear/stats/cadence with wrong event damage: raid-class-mechanics-implementation.
- Unknown encounter facts: raid-encounter-research; native scripts: raid-encounter-implementation.
- Shared task, movement submission, recovery, or lifecycle failures: raid-bot-runtime-implementation.
- Reference generation: raid-wowsims-reference; evidence/cleanup: raid-evidence-lifecycle.

Class tuning requires exact current WoWSims reference and gear/effective-stat comparison.
Use the promoted catalog, never an obsolete embedded DPS value. Movement-only work does
not require a new simulator run. Missing evidence is a bounded capture task, not a reason
to guess coefficients. Dummy calibration alone uses exactly 300 scoring seconds.

Keep typed arbitration and persistent tasks. Native pathing owns terrain; no bot Z
steering, teleportation, global tolerance relaxation, or encounter MMAP workaround.

## Workers

Assign one dedicated `raid-rotation-review` owner to the DPS side of every raid,
dungeon, or calibration attempt, including successful clears. Use Sol high for
this causal review. The reviewer follows that skill's post-run review mode,
reads the closed diagnostics before raw payload eviction, and returns a compact
per-spec breakdown plus one next repair or precisely missing observation.
Carry that finding into the next implementation packet and compare the repaired
edge on the next run. Keep this review separate from boss-completion acceptance;
a throughput finding does not erase a valid kill. Do not tune coefficients from
an aggregate raid DPS number or rerun a boss merely to regenerate available data.

Give one owner the evidence, one hypothesis, production files plus directly affected
tests, forbidden changes, command, and expected outcome. Include all affected callers
before dispatch. Use Luna max for exact narrow implementation, Sol high for ambiguous
causal diagnosis and independent review of risky runtime/encounter changes. Work directly
when delegation would add more coordination than useful work. Serialize builds, shared
server ownership, provisioning, and DVC publication. Independent reads may overlap.
