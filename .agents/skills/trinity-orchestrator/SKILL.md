---
name: trinity-orchestrator
description: Own broad requests such as implement boss bots through diagnosis, repair workers, builds and live validation. Use for encounter-wide implementation and optimization, not only explicit orchestration requests.
---

# Trinity orchestrator

Own the broad encounter objective from selection through repair, independent review,
build, live validation, assessment, publication, and cleanup. A specialist result is
an intermediate receipt; it does not transfer coordinator ownership or close the
parent objective.

## Startup and progress authority

First inspect `git worktree list --porcelain`, use the checkout holding `master`,
read its `AGENTS.md` and applicable skills, and verify the saved
`coordinator_worktree`. Preserve unrelated dirty work. Do not build an old or
detached checkout, copy task state between worktrees, or mutate a live frozen
checkout.

For a request naming a boss and difficulty, run:

```text
pixi run python -m tools.raid_program.raid_workloop start "<request>"
```

For a fresh tab with an already selected program, run
`pixi run python -m tools.raid_program.raid_workloop resume` in the coordinator
checkout. Read the returned source bindings, owner skill, `unit.next_action`, and
`latest_assessment` when present, then execute the returned stage. `--preview`
is for read-only inspection. Missing research, scripts, rosters, references, or
exact runtime configuration are work items; initialization is not live readiness.
Never switch away from a claimed or unclosed operation, copy normal-mode acceptance
into heroic, or choose an unrelated patch because its fixture passes.

After every transition execute the next returned step. Before ending an
implementation/resume turn, run `resume`; continue while the parent objective is
open unless the user explicitly stopped or limited the task or a demonstrated
external blocker prevents authorized work. Assessment, publication, routing,
worker completion, and canary results are not stopping boundaries. The saved
development graph is authoritative; historical prose must not restart measurements.
Follow [development_graph.md](../../../docs/bot_raids/development_graph.md) and
reconcile controller/build ownership before launch. These commands do not start a
background worker or replace native admission checks.

Use `workflow_step advance --receipt <path> --dry-run`, then the same command
without `--dry-run`, under `pixi run python -m tools.raid_program`. For a claimed
step include its explicit `--owner`. The helper derives revision, unit, hashes
and token and calls the real reducer atomically. Do not hand-copy those fields
or retry a rejected transition unchanged. Build plans need a frozen build/resource
policy; a role-calibration policy is a different input and is rejected at planning.
Use `workflow_build refs` and `snapshot` for receipt inputs and owned files.

## Evidence and objective discipline

Keep class calibration shared across bosses and encounter validation specific to
each boss/difficulty. Consult
[class and encounter validation](../raid-performance-loop/references/class-and-encounter-validation.md)
before another dummy run or tank DPS work unit. New encounter work alone does not
invalidate class qualification. Require explicit compatibility for changed builds.

Use existing commands first. For admission and saved-task questions, use the
focused `evidence_view admission` and `evidence_view task` views; read their
command/output details in [evidence-views.md](../raid-rotation-review/references/evidence-views.md).
Then use selected, narrow queries. Read only the matching error-ledger entry and
current status; keep full payloads outside model context and never dump graph
history or generated datasets. Missing evidence remains unknown and routes to a
bounded capture task.

Keep the user's objective and every actor requirement visible. Correct stale status
in place, retain unresolved actor rows after an accepted repair or improved raid
total, and route the next action automatically. Do not substitute an authorization
document, ledger entry, proposed repair, or final handoff for authorized work.
Use the error ledger before dispatch/retry, carry its error ID, evidence, rejected
approaches, and affected callers, and update that entry when the result changes.

## Workers and review

Work directly by default. Delegate one bounded implementation when useful; multiple
implementation workers require explicit user authorization and disjoint ownership.
Do not use nested workers; worker prompts say to work directly without launching
another model or subprocess agent. Use a separate independent reviewer for risky
runtime/encounter changes. A worker freezes its owned files until a new edit
assignment; the reviewer hashes them and records the separate session ID and report
as `reviewer_session_id` and `review_report`. A worker cannot claim approval
before that verdict.
Import the actual separate session's final JSON with `review_execution`; changing
a reviewer label in a coordinator-written receipt is not independent review.
The report must contain its verdict and exact file hashes. Reuse unchanged
approval explicitly; changed files need another review. Provider advice cannot
substitute for this execution proof.

Use `gpt-5.6-luna` with `reasoning_effort: max` for implementation, causal
diagnosis, architecture, and independent review, following the current user
preference. Jev/Laya judgments are advisory. Keep deterministic checks separate,
send the reviewer exact immutable evidence and one hypothesis, and preserve
contradictory or missing evidence. For a DPS repair, require the existing
[damage-loss accounting](../raid-rotation-review/references/post-run-dps-review.md#account-for-the-dps-loss-before-selecting-a-repair)
before dispatch; raw deltas and model agreement do not authorize native tuning.
Keep handoffs short: one proven edge, exact evidence/file locations, owned files,
counterexample, focused command, and acceptance.

## Execution and handoff

Use the repair order: cheap preflight, affected behavioral tests, independent
review, one coordinator-owned build, bounded canonical capture, publication/cleanup,
then the next repair. Use the detailed [engineering and runtime rules](references/engineering-and-runtime.md)
for telemetry, identity, native include, build-queue, resource, and retry invariants.
Use the existing [bounded work-unit contract](../raid-performance-loop/references/bounded-work-unit-contract.md)
and [handoff contract](../raid-performance-loop/references/handoff-contract.md) when
dispatching. Python runs through Pixi; code/configuration belongs in Git; generated
evidence belongs in DVC.
