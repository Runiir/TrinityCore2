# Jev/Laya checkpoints for bounded workers

Use the existing worker assignment as the authority. Jev/Laya check a proposed
change against that assignment and its evidence. They do not create a new plan,
approve native behavior, or replace the independent reviewer.

Check twice: after the worker identifies its proposed repair, and after it
returns the diff and test receipts. Read-only investigation can continue while
a checkpoint is evaluated. Do not poll the models on every tool call or ask
them repeatedly until they agree.

The coordinator supplies the objective, first broken edge, owned files,
forbidden changes and acceptance conditions. The worker supplies its proposed
change and cited evidence. At the result checkpoint include the actual diff,
test commands/results and explicit outstanding validation. Keep observations,
hypotheses and claims separate. A confident worker summary is not evidence.

`tools.raid_program.worker_checkpoint` reuses the existing local and hosted
clients. File ownership, required test receipts and cited artifact hashes are
checked directly. The models answer separate questions about scope, support
for the proposed repair, and support for an acceptance claim. They can answer
`insufficient_evidence`. No answer automatically accepts or executes a change.

Keep evidence excerpts compact enough for the deployed Laya checkpoint's
1,024-token context and 256-token question/options budget. Keep long hashes and
artifact provenance outside model state. A rejected or truncated request is a
failed observation, never a favorable vote. Give both providers the same facts.
The coordinator examines disagreement, unsupported assertions and missing
evidence, then sends one concrete correction to the worker. Service failure
routes to the existing reviewer; it does not halt unrelated work or request
user approval. A justified scope change updates the assignment explicitly.

For example, the Fire dummy task is to prevent two owners from using the combat
potion. A patch that excludes the fixture-owned potion from the ordinary
calibration resolver can satisfy that task. Globally removing raid potions or
changing the count to conceal an extra use does not. The Survival task requires
preserving legitimate racial actions; deleting Blood Fury to fit a reference
that omitted it violates the objective even if that makes a validator pass.

Retain requests, raw responses, resolved models, source hashes, latency and
coordinator adjudication separately. A prediction is not a label. Evaluate
missed drift, false alarms and useful corrections on held-out real work units
before granting any model autonomous gate authority. Group related tasks and
their counterfactuals together when splitting future data. Counterfactual test
packets are development fixtures, not native raid training evidence.

## Pre-commit use

The repository hook at `.githooks/pre-commit` runs
`pixi run --frozen python -m tools.raid_program.worker_precommit`. It reads the
current coordinator-authored task from `git rev-parse --git-path worker-task.json`,
captures the actual staged diff and file list, and retains the index tree,
source HEAD and task/diff hashes. Unstaged work is excluded. An index change
during review invalidates the result. The hook prints each model's choice,
probability and confidence separately, with a path to the complete receipts.
HEAD and the original task bytes are also rechecked before returning.

Use it for one commit without changing hooks in the other ongoing worktrees:

```sh
git -c core.hooksPath=.githooks commit
```

For an explicit checkpoint or an API key stored outside this worktree:

```sh
pixi run python -m tools.raid_program.worker_precommit \
  --task /absolute/path/to/current-task.json \
  --env-file /absolute/path/to/jev.env --backend both
```

The task contains `task_id`, `objective`, `first_broken_edge`, `allowed_files`,
`forbidden_changes`, `acceptance_conditions`, `observations`, `proposed_change`,
`acceptance_claim`, `required_test_commands`, `tests`, and `evidence_excerpts`.
Each test supplies its exact `command` and observed `exit_status`; each evidence
entry supplies `id`, `path`, `sha256` and a short `excerpt`. The coordinator
defines required tests; workers cannot omit one by listing only a passing test.
The hook supplies `stage`, `changed_files` and their observed source itself.
Test commands and exit values are reported receipts, not independent execution
proof. A test run against unstaged code does not validate the staged tree.
The coordinator must check that binding before accepting the repair.

This is an advisory semantic review. Definite staged-file ownership and required
test failures block; model answers never automatically approve or reject a
commit. Missing task, provider failure and context overflow are visibly
**not reviewed**. A successful Git commit is not task acceptance. A model score
is the probability of its supplied classification, not a code-quality percentage.
Large diffs may exceed local Laya's context; retain that rejection and use the
coordinator review rather than silently truncating code. Install no global hook.

## Research basis

Reviewed 2026-09-19:

- [TypeSafe's building guide](https://docs.typesafe.ai/concepts/how-to-build-with-system-one)
  recommends code-owned control flow and narrow independent questions.
- [State guidance](https://docs.typesafe.ai/concepts/state) recommends named
  fields and explicit relationships between the facts being compared.
- [Citation checking](https://docs.typesafe.ai/cookbooks/citation_check) separates
  exact source checks from semantic support checks. Apply that separation to
  worker evidence instead of asking a model to verify hashes or command exits.
- [Confidence](https://docs.typesafe.ai/confidence) requires thresholds evaluated
  for the actual task. A concentrated distribution does not prove a patch works.
- [Jev's documented limitations](https://docs.typesafe.ai/model-jaggedness/jev-1.13)
  include numeric precision, indirect reasoning and distracting context. Compute
  DPS, durations, counts and identity equality in code; send their observed
  meaning alongside the specific rule and proposed change.
- [Laya's source documentation](https://github.com/NandhaKishorM/laya) describes
  task-specific fine-tuning, limited context and calibration limitations.
  Its benchmark does not establish reliability on this repository's repairs.

Keep this worker-steering dataset separate from the existing per-bot diagnosis
in [local_jev_shadow.md](local_jev_shadow.md). One judges development decisions;
the other inspects native bot behavior.

## Initial pilot limitations

The 2026-09-19 pilot retained the actual Luna test overclaim, a bounded claim
control, and the rejected Blood Fury deletion proposal. The first question
wording let both models accept a claim that manually assigned test counters
proved native accounting. One explicit question correction distinguished
asserted expected values from executing the claimed production path. Jev then
flagged that overclaim and the racial-deletion scope violation; Laya still
missed both important judgments and reported low confidence. The bounded
claim was retained separately from full-task acceptance.

These examples confirm an existing coordinator/reviewer finding; they do not
show a new model-discovered fix, measure held-out accuracy, or justify an
automatic score threshold. Retain the failed first query alongside the later
one. Coordinator adjudication remains necessary, especially for Laya.

The orchestrator check also retained its latest user direction and remaining
class requirements. Jev supported the real current plan and rejected a separate
counterfactual that abandoned those requirements and declared completion.
Laya missed the counterfactual's scope and completion errors. That contrast is
a development check, not a measured production detection rate.
