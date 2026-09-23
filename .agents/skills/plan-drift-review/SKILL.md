---
name: plan-drift-review
description: Optional, never a required workflow stage. Check a worker or main orchestrator's active plan and next action against the parent objective, latest user direction, completed work and remaining requirements. Use only when explicitly asked to check drift. Does not implement repairs or launch live experiments.
---

# Review plan drift

Read the current conversation's objective and latest user direction first.
Distinguish an authorized change of focus from abandoning a parent requirement.
Do not restart an older task merely because a historical plan calls it next.

Collect the active plan and observed state: completed steps, open requirements,
the proposed next action, Git status/diff, latest relevant test/run receipts,
and the matching error-ledger entry. For this program, current state comes from
`raid_workloop resume` and `scoreboard verdict` (raid tuning playbook). Read only
the relevant ledger entries. Conversation instructions outrank
stale status documents; report conflicts rather than treating old text as authority.

Ask whether the next action advances the authorized plan, drops an unresolved
requirement, repeats a closed edge without new evidence, or claims more than the
observations establish. A needed blocker repair can be a valid dependency. Name
that dependency explicitly. Do not infer drift just from time spent or a failed run.

Use `tools.raid_program.worker_checkpoint` with `subject: orchestrator` and a
compact `goal_context` containing:

- `parent_objective` and `latest_user_direction`;
- `current_plan`, `completed_work`, and `remaining_requirements`;
- known blockers and prior retries when they affect the next action.

Map the next action to `proposed_change`; put the observed blocker in
`first_broken_edge`. Use `stage: plan` before work or `result` when reviewing
claims. Keep `acceptance_claim` explicit, including what remains unproved.
Use the existing task fields and CLI in
[`worker_checkpoints.md`](../../../docs/bot_raids/worker_checkpoints.md).
For read-only plan review, use empty changed-file and required-test lists;
do not invent a test requirement. Bind cited source excerpts to real files.
The main agent supplies the plan because a tool cannot reconstruct unstored
conversation intent from Git alone. Preserve unknown state explicitly.

Model advisors are not part of the workflow. Inspect current receipts and
source to adjudicate with the coordinator's own check.

Write short checkpoint fields: state each fact once, use actor IDs with concise
open requirements, and keep hashes/paths in evidence metadata. Do not retry an
oversized packet unchanged or silently truncate it.

Return one short verdict: aligned, drift found, or insufficient evidence. State
the exact divergence and the smallest correction, with any parked requirement
that must remain visible. If aligned, continue the active work. If drift is
proved, update the existing plan/status and continue the corrected next action.
Do not ask for permission again for already authorized work. Retain the model
responses and the coordinator verdict separately for later evaluation.

Use this checkpoint only on request, never after every tool call. The pre-commit hook checks staged code; this skill also catches
orchestrator drift that produces no code, such as repeating research or stopping
before the required live validation.
