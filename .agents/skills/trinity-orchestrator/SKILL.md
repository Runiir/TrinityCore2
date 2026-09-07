---
name: trinity-orchestrator
description: Coordinate TrinityCore repair workers and serialized builds/live experiments with minimal handoff overhead.
---

# Trinity orchestrator

Use the user's current objective and the latest compact run evidence. Correct stale
status in place; do not stop to produce authorization-only documents. Finish the requested
objective across worker and attempt boundaries. An agent finishing or a canary exposing
a new bug means route the next action, not return control to the user.

Work directly by default. Delegate one bounded implementation when useful; use a second
agent for independent review of risky runtime/encounter changes. Multiple implementation
workers require explicit user authorization and disjoint ownership. No nested workers.
Worker prompts include: "Work directly. Do not launch another model or subprocess agent."

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
