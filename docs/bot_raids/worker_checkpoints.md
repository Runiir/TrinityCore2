# Jev/Laya checkpoints for bounded workers

Worker scope is checked deterministically. Jev (hosted) and Laya (local) are
optional advisory tools: neither is a required step, neither gates a transition
or commit, and neither replaces the independent reviewer. Laya shadows Jev on the
same packet so their signal can be compared; an offline Laya or a rejected packet
is recorded as **not reviewed**, never as a vote. When they choose between the top
two damage gaps, both picks go into the outcome log (`jev_outcomes`, see
[development_graph.md](development_graph.md)). Plan-drift review is never a
required step.

## Pre-commit hook

Enable with `git config core.hooksPath .githooks` (or `git -c
core.hooksPath=.githooks commit` for one commit). The hook runs the C/C++ module
size check, then `tools.raid_program.worker_precommit`:

- **Worker task contract present** (`git rev-parse --git-path worker-task.json`,
  or `--task`): staged files outside `allowed_files` block the commit. Otherwise
  the staged diff (never unstaged edits) is captured with its index tree, HEAD and
  task hash; missing/failed required test receipts or wrong cited artifact hashes
  block, as does a concurrent index, HEAD or task change.
- **No task contract** (normal coordinator commits): silent, except inside the
  active graph unit. During `implement`, staged code outside the unit's owned or
  supporting files prints one warning (its tests/review binding would fail).
  During `review`, `build`, `smoke` or `validate`, staged code prints a warning
  with the unit's tier and remaining steps, because it invalidates the recorded
  tests/build. Coordination files (graph state, docs, skills, JSON evidence) never
  warn. Warnings do not block.

The default hook makes no model call. `--model-advice` (with `--backend
local|hosted|both`, `--env-file`) opts in to one non-blocking Jev/Laya review of
the staged checkpoint and prints each model's choice, probability and confidence.

The task contract contains `task_id`, `objective`, `first_broken_edge`,
`allowed_files`, `forbidden_changes`, `acceptance_conditions`, `observations`,
`proposed_change`, `acceptance_claim`, `required_test_commands`, `tests`
(`command`, `exit_status`) and `evidence_excerpts` (`id`, `path`, `sha256`,
`excerpt`). The coordinator defines required tests; a worker cannot omit one.
Reported results are receipts, not proof they ran on the staged tree; the graph's
`workflow_step tests` runner is the executed record. A commit is not acceptance.

## Model packets

`tools.raid_program.worker_checkpoint` reuses the local Laya and hosted Jev
clients. Code checks file ownership, test receipts and cited hashes; the models
answer separate scope, evidence and claim questions and may answer
`insufficient_evidence`. Give both models the same compact facts (about 600 tokens
of state, each fact once; hashes and paths stay in `evidence_excerpts` metadata).
Laya's local adapter returns HTTP 422 `context_budget_exceeded` when a question
would truncate: that is not reviewed, not a service outage. Shorten wording once
without dropping constraints, or record Laya as not reviewed; never retry the
unchanged packet. Retain requests, responses, latency and the coordinator's
adjudication; a prediction is not a label.

## Judging actor changes

Actor progress is judged from scoreboard verdicts: compare a batch's per-actor
ratios and deaths with the previous label for the same scenario, roster and gear.
Review every exercised actor so a raid-total gain cannot hide one actor's loss;
keep tank threat/mitigation and healer survival/mana duties next to throughput.
Compute deltas in code. Example scope violation: deleting a legitimate racial
(Blood Fury) so a validator passes violates the objective even if it turns green.
