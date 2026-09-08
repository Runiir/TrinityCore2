---
name: raid-evidence-lifecycle
description: Capture attributable raid diagnostics, verify run identity and cleanup, and publish closed evidence through DVC.
---

# Raid evidence lifecycle

## Before a development run

Use the existing controller with a canonical scenario/profile and --development-run.
Keep a clean frozen source checkout, verified build receipt/binary hash, configuration,
route, roster/gear/consumables, runtime asset identity and fresh database readback.
Reject conflicting fixture overlays. Development runs do not need the historical
recurrence/fixture-expansion admission system; they remain qualification/training-ineligible.
Do not create additional receipt schemas or handoff files when existing outputs suffice.
For qualification or explicit sealed fixture replay, retain their existing stricter checks.

Verify cheap configuration and affected behavioral tests before a build. Reuse verified
assets and binaries when their relevant inputs have not changed. Do not repeatedly hydrate
large inputs. cache:false DVC outputs need exact locked-byte reproduction/copy, not dvc pull.
Use independent files where source and runtime permissions differ; never flip aliased modes.

Provision the exact cohort and read back native-loadable identities, roster, equipment,
consumables, positions, and group/instance/corpse state. Serialize mutation of the shared
worldserver and database. One cohort's cleanup must preserve other active instances.

## Capture and classify

Retain native bytes and bind scenario, server epoch, cohort, attempt, roster and route.
Use status heartbeats with delta trace and slower diagnosis; force final diagnostics at
material failure/termination. Statistics-window rotation must preserve attempt-scoped
trace identity. Count repeated actor death episodes or unique native wipes separately
from first casualties. Activity, repeated decisions, or endpoint submission alone is not
semantic progress.

Run until native clear or a typed stall, repeated decision, death loop, infrastructure
loss, contamination, or interruption. Only isolated dummy calibration has a 300-second
scoring window. An emergency wall-clock limit is never success.

Boss completion requires matching native route/node/generation and confirmed boss death.
Arrival, trash clear, fixture success, or high damage totals do not prove boss completion.
Retain DPS/HPS, movement, decisions, deaths, route progress, and first causal mismatch
separately from the terminal reason. Report missing boss HP or lethal joins honestly.
Do not treat synthetic observations or add-inclusive damage as boss-health evidence.

Interrupt through the controller so it stops the owned cohort, obtains final evidence,
checks zero bots/leases, and shuts down its owned server safely. Preserve interruption as
such. Only the shared-server owner may stop the whole worldserver.

## Close, publish, continue

Before publication/eviction, give the assigned DPS reviewer the closed report,
native combat aggregates, decision/diagnosis traces, exact roster and reference
identities. Include its compact review with the run's evidence. A later review
of an already-published run is a separately attributable analysis artifact;
do not rewrite the original accepted report or archive.

Use one compact report plus the generated receipts. Commit code/configuration to Git.
Publish immutable raw/report/log/receipt data through DVC, run targeted dvc status and
dvc push, and verify the remote bytes with an empty-cache reconstruction. Preserve
pointer visibility and enough space for transport; never print private credentials.
Evict exact verified duplicate payloads after diagnosis/review, retaining compact evidence
and the remote reconstruction path. No broad DVC GC or unrelated worktree deletion.

Do not admit development, stale, contaminated, unclassified, synthetic-only or incomplete
runs to training. Full qualification retains complete attribution and independent outcome
verification. A closed failed run routes the next repair; it is not the end of the user's
program. Continue without asking again for already-authorized work.
