---
name: raid-performance-loop
description: Coordinate bounded raid and class repairs, join specialist results, and continue through live validation until the user's objective is achieved.
---

# Raid performance loop

Read the current result at the top of
[`shared_worldserver_workflow_20260907.md`](../../../docs/bot_raids/shared_worldserver_workflow_20260907.md)
before choosing work; its historical entries do not override the current result.
Use the matching entry in the [error ledger](../../../docs/bot_raids/error_ledger.md)
to retain failed assumptions and distinguish implementation, review, build and
live acceptance. Update it after each bounded attempt rather than creating a
new narrative history. A passing DPS threshold does not prove declared
professions or enchant applicability; read back the selected actor's actual
requirements. Normal native load/save transformations must also be reconciled
before requiring a persisted identity on the next launch.

Keep the active-work-unit status consistent with that result. When a repair is
accepted, replace its active edge with the newly observed edge; do not leave
workers' status commands pointing to an already-fixed failure. Historical
receipts stay immutable. A stale status is metadata to correct, not a reason
to repeat an accepted experiment.

When closing a run, update the linked workflow's latest-run paragraph and the
active ledger edge together, including failures before the boss. Preserve the
last successful baseline under its own label. An isolated boss experiment may
answer a research question, but skipping failed trash does not resolve or
validate that route regression.
For route-wide survival comparisons, count retained death events in the same
attempt and route window; final watchdog counters may reset at a node change.
Trash wipes are not automatic rejection when native recovery regroups the
cohort and route progress resumes. Evaluate death, release, runback, resurrection,
regroup and resumed progress separately; prioritize a stalled recovery over
eliminating every casualty. Keep the watchdog's death-loop and stall limits.
Bind the recovery entrance in the first route's immutable admission receipt;
an executor fallback must not differ from the identity required by its tracker.
Source map zero is a valid map, not a missing entrance when the trigger is set.

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
When a stat gap matches a passive multiplier, verify the learned spellbook and
native aura ledger before changing coefficients or retrying unchanged role code.
Catalog SQL generation does not prove an existing calibration actor was updated.
Trace the actual launch's provisioning path and require selected-actor spellbook
readback before starting a window intended to validate a learned passive.

When repairing self-provided calibration admission, inspect both player and target
aura rules at reset and during scoring in the same work unit. Presence alone does
not prove an external buff or debuff: retain native caster ownership and reject
foreign, mixed or unknown sources. Cover the corresponding owned class effects
in both consumers before rebuilding. Preserve native consumable receipts and the
self-baseline return before fixture aura writers; do not invent cast provenance.
Follow the observed row through its Python projection and final role gate too.
Serialize the failing spec's actual fixture row into that consumer; a different
spec's passing row cannot validate the repaired path.

Keep typed arbitration and persistent tasks. Native pathing owns terrain; no bot Z
steering, teleportation, global tolerance relaxation, or encounter MMAP workaround.

## Workers

When several represented classes or roles underperform, use the
[parallel role review](references/parallel-role-review.md) requested by the
coordinator. One reviewer can cover duplicate bots of the same spec. Keep one
overall reviewer responsible for attribution and joining shared failures.

Assign one dedicated `raid-rotation-review` owner to the DPS side of every raid,
dungeon, or calibration attempt, including successful clears. Use Sol high for
this causal review. The reviewer follows that skill's post-run review mode,
reads the closed diagnostics before raw payload eviction, and returns a compact
all-bot DPS/HPS breakdown, per-DPS-actor WoWSims and Warcraft Logs comparisons,
and a ranked list of losses before choosing one next repair or missing
observation. A repair acceptance is not overall roster-performance acceptance;
keep unresolved actors visible. Record actual versus requested composition and
use matching DPS denominators for external comparisons.
Carry that finding into the next implementation packet and compare the repaired
edge on the next run. Keep this review separate from boss-completion acceptance;
a throughput finding does not erase a valid kill. Do not tune coefficients from
an aggregate raid DPS number or rerun a boss merely to regenerate available data.

Give one owner the evidence, one hypothesis, production files plus directly affected
tests, forbidden changes, command, and expected outcome. Include all affected callers
before dispatch. When a header adds a native type or constant, include its defining
header in the owning scope; an extracted fixture that supplies stub declarations
does not verify the real include chain. Label observed facts separately from inferred event ordering. A new
admission predicate must be supported by the trace or by the production contract;
do not require an unobserved intermediate state merely to make a fixture pass.
Exercise the actual caller and each valid ordering when asynchronous submission,
observation and native execution can occur on different ticks.
For profile migrations, test native storage semantics, including FLOAT precision;
SQLite replay alone does not prove a MySQL predicate matches. Read back the intended
rows after native updates and before the encounter. An applied migration receipt
with zero affected rows does not prove the repair was installed.
After regenerating routes, refresh the `validation_routes` inventory and DVC
binding in the runtime asset manifests, preserve other asset classes, normalize
route file modes to the declared 0644, and verify closure before building.
Use Luna max for exact narrow implementation, Sol high for ambiguous
causal diagnosis and independent review of risky runtime/encounter changes. Work directly
when delegation would add more coordination than useful work. Serialize builds, shared
server ownership, provisioning, and DVC publication. Independent reads may overlap.
Use `followup_task` for every new edit, investigation, or review assignment,
including assignments to an agent that appears active. Reserve `send_message`
for clarifications to its existing task. This avoids a completion race: queued
messages do not resume an idle worker. The coordinator owns review dispatch;
a worker saying "sent for review" does not prove that the reviewer started.
Check reviewer state before waiting on its result.
