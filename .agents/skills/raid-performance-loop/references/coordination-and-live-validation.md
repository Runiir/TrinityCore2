# Coordination and live-validation details

Read this reference for run closure, recovery interpretation, development versus
qualification, specialist dispatch, or route/build handoffs. The tuning loop,
metrics and thresholds are in the raid tuning playbook; startup and saved-task
continuation are owned by `trinity-orchestrator`.

## Route runs and closure

Preserve failures in trash or pre-boss route nodes. An isolated boss experiment
can answer a research question, but skipping failed trash does not resolve or
validate the route regression. Historical receipts are immutable; correct stale
metadata in place.

For a fresh instance, use the generated scenario-level command with
`--validation-route-manifest`, without segment/node selectors. It executes the
declared entrance, trash and boss nodes on one worldserver. Selecting a later
segment does not clear its predecessors; retained bot positions and descriptive
prerequisite metadata are not proof of a prepared instance. The launch tool
rejects these slices before asset checks/provisioning. A boss-only experiment
requires a separately admitted scenario with verified instance prerequisites.
If a previously working pull fails, compare the actual generated manifest and
start state with the successful run before changing native target policy.

For route-wide survival, count retained death events in the same attempt and route
window; final watchdog counters may reset at a node change. A trash wipe is not
automatic rejection when native recovery regroups the cohort and route progress
resumes. Evaluate death, release, runback, resurrection, regroup, and resumed
progress separately, and prioritize stalled recovery over eliminating every
casualty. Keep watchdog death-loop and stall limits.

Bind the recovery entrance in the first route's immutable admission receipt. An
executor fallback must not differ from the identity required by its tracker. Map
zero is valid when the trigger is set. An accepted optional recovery gate does not
prove recovery occurred: read its required flag and full-route lifecycle events.
Distinguish partial casualties, a full wipe, and an unexercised branch; final boss
counters can omit trash deaths.

## Development and qualification boundaries

Use the existing capture controller's development mode with a canonical
scenario/profile. Require attributable clean source, verified binary/configuration,
exact roster/readback, runtime assets, a completion watchdog, native outcomes, and
cleanup. Run cheap metadata checks and affected behavioral tests before building;
execute overlapping tests once. Do not require historical fixture expansion, a full
qualification suite, or a new authorization document for each development attempt.
Historical ledgers are investigation records, not launch authority. A development
clear requires real native boss death but does not qualify a full raid, every
mechanic, or training data.

Promotion of a boss, full raid, class calibration, or training dataset uses the full
required regression, roster, reference, and evidence checks. Legacy sealed fixture
replay remains available when specifically testing that fixture. Load only the
qualification or specialist reference needed for the current boundary.

For startup/lifecycle questions, prefer the shortest attributable observation and
verify that the diagnostic is enabled and reaches its consumer. A short probe has
no accepted DPS result. If a repair leaves the same symptom, inspect the missing
causal boundary and earlier speculative changes before stacking gameplay patches.
Separate setup/admission failures from completed measurements.

## Exact admission and class-routing rules

WoWSims-based class tuning (native damage, coefficients, stat math) requires the
current promoted WoWSims reference plus gear and effective stat comparison. The
promoted catalog is authoritative; obsolete embedded DPS values are not.
Movement-only work does not need a new simulator run. Missing evidence is a
capture task, never a reason to guess coefficients.

If a stat gap resembles a passive multiplier, verify the learned spellbook and
native aura ledger before changing coefficients or retrying unchanged role code.
Catalog SQL generation does not prove a calibration actor was updated. Trace the
actual launch provisioning path and read back the selected actor's spellbook before
a window intended to validate a learned passive.

For self-provided calibration admission, inspect player and target aura rules at
reset and during scoring in the same work unit. Presence alone does not establish
external buff/debuff provenance: retain native caster ownership and reject foreign,
mixed, or unknown sources. Cover owned class effects in both consumers before
rebuilding. Preserve native consumable receipts and the self-baseline return before
fixture aura writers; never invent cast provenance. Follow the observed row through
its Python projection and final role gate, and serialize the failing spec's actual
fixture row; another spec's passing row cannot validate it.

Keep typed arbitration and persistent tasks.

## Actor review details

A `no_action` resolution or wait is not a failed native cast. Keep it separate
from submission and terminal failures. Label healing totals and HPS denominators:
retained encounter aggregates may include post-death healing, while exact run HPS
uses healing through native death. The comparison baseline is the last kept
scoreboard label (raid tuning playbook, step f).

When several roles underperform, use the parallel-role reference. One reviewer can
cover duplicate same-spec bots, but one overall reviewer must join shared failures.
Do not tune coefficients from aggregate raid DPS or rerun solely to regenerate
available data.

## Dispatch, storage, and build details

Give one owner exact evidence, one hypothesis, production files plus directly
affected tests and callers, forbidden changes, command, and expected outcome.
When a header adds a native type/constant, include its defining header; a fixture
stub does not verify the real include chain. Label observed facts separately from
inferred ordering. An admission predicate needs a trace or production contract,
not an unobserved intermediate state invented for a fixture. Exercise the real
caller and each valid ordering when asynchronous submission, observation, and
native execution occur on different ticks.

For profile migrations, test native storage semantics including FLOAT precision;
SQLite replay does not prove a MySQL predicate. Read back intended rows after native
updates and before the encounter. A zero-row migration receipt does not prove the
repair was installed.

After route regeneration, refresh the `validation_routes` inventory and DVC
binding in runtime asset manifests, preserve other asset classes, normalize route
file modes to declared 0644, and verify closure before building. Serialize builds,
shared server ownership, provisioning, and DVC publication. Independent reads may
overlap.

Use `followup_task` for every new edit, investigation, or review assignment,
including an apparently active agent; reserve `send_message` for clarification
inside an existing task. The coordinator owns review dispatch, and a worker saying
it sent work for review does not prove the reviewer started. Check reviewer state
before waiting.
