---
name: trinity-orchestrator
description: Coordinate TrinityCore repair workers and serialized builds/live experiments with minimal handoff overhead.
---

# Trinity orchestrator

Use the [error ledger](../../../docs/bot_raids/error_ledger.md) before dispatch or
retry. Give workers the relevant error ID and its current evidence, rejected
approaches and affected callers. Update that entry when the result changes;
do not restart a closed edge or copy the ledger into another handoff document.

Use the user's current objective and the latest compact run evidence. Correct stale
status in place; do not stop to produce authorization-only documents. Finish the requested
objective across worker and attempt boundaries. An agent finishing or a canary exposing
a new bug means route the next action, not return control to the user.

Work directly by default. Delegate one bounded implementation when useful; use a second
agent for independent review of risky runtime/encounter changes. Multiple implementation
workers require explicit user authorization and disjoint ownership. No nested workers.
Worker prompts include: "Work directly. Do not launch another model or subprocess agent."

When replacing or resuming a worker, name the latest implementation review and
its unresolved findings explicitly. The worker must reconcile those findings
with the current diff before choosing more work; a directory of older reports
is not an adequate handoff. Preserve completed repairs and distinguish missing
live acceptance from an implementation defect. Honor the user's requested model
for the current experiment; the defaults below are not mandatory model choices.
For a critical regression, run its explicit pytest node ID or verify that the
focused selector actually collects it. A passing filtered suite is not evidence
for a new test whose name the filter excludes.

When splitting a native translation unit, preserve its prerequisite include order
and check file-local names if unity is enabled in the actual build receipt/cache;
a dormant CMake unity branch does not prove the active configuration. Extracted-body
fixtures do not compile that native include chain. In this core, Pet.h depends
on Common.h being available first; a plausible shortened include list can fail
after all behavioral fixtures pass. Keep native compilation a separate claim.

For retained telemetry changes, locate both full and delta serializers and test
the same native record through each. A field visible in a full snapshot can still
be lost after ring eviction if the delta export omits it.
When increasing decision or sampling frequency, test the resulting full-size
export through controller retention, parsing and final acceptance recomputation.
Incomplete transport is an infrastructure failure, not a class-tuning signal.
Complete transport does not prove that native diagnostic arrays are complete.
Check bounded producers across the full scoring window at the current cadence;
retain explicit attempted/retained/dropped receipts for a repaired loss path.
Keep diagnostic-loss rejection separate from the measured DPS/HPS result.
Permanent rejection regressions must run after raw evidence eviction. Use a small
repository-owned fixture for final acceptance; keep optional hydrated-payload
size checks separate and label skips explicitly. Bind historical regression fixtures
to their original reference and fixture authority, not the mutable current catalog.
A new catalog must not relabel old observations or break unrelated replay tests.

For mixed console JSON, identify the message type before interpreting shared
field names. A diagnostic `bots` array is not a status count. Preserve explicit
zero values and test newer inactive or malformed status after older readiness.

Review the actual launch-to-consumer path, including every identity used to select
the runtime actor and its inputs. For frozen-checkout admission, exercise the
complete preparation caller with default checkout data absent, including nested
gear loaders and both dry-run and apply paths. Offline reference validation uses
frozen authority; native preparation may use the actual configured, verified
DataDir. A fixture-loader-only test does not prove the launch binds its data root. Match each check to its observation time: prepull
readiness uses the scoring-start snapshot; consuming an item during combat does
not invalidate that earlier readiness. Return all known blocking findings together;
do not end the first review after checking only one identity field.

Use Luna max for exact narrow implementation with immutable evidence, owned production
and affected test files, one hypothesis, excluded changes, a focused command, and concrete
acceptance. Use Sol high for causal ambiguity, architecture, or independent risky-change
review. Do not interrupt a quiet worker arbitrarily. Send decisive new context; resume a
completed worker with followup_task, not a message that cannot start its next turn.

For development: cheap preflight -> affected behavioral tests -> review -> build ->
bounded canonical capture -> publish/cleanup -> next repair. Use existing commands and
one compact issue/run summary. Do not require repeated full-suite qualification, manual
fixture revision bookkeeping, or sealed movement checkpoints for ordinary development.
Full qualification and training promotion retain their specific checks.

Serialize heavyweight builds through queued_build, shared worldserver ownership,
provisioning, and DVC publication. Never mutate a live frozen checkout. Python uses pixi;
code/configuration use Git; generated evidence uses DVC. Reuse exact verified assets,
verify remote copies, and evict only exact duplicate payloads.

A real tool/account/resource failure may require external input; ordinary fixture,
configuration, implementation, and review failures should be repaired and execution
continued. At ten occurrences of the same first-broken edge, stop unchanged retries and
produce the causal summary before changing the hypothesis. Do not turn this into a
permanent program stop when a new bounded repair is available.
