# Jev/Laya checkpoints for bounded workers

Use the existing worker assignment as the authority. Jev/Laya check a proposed
change against that assignment and its evidence. They do not create a new plan,
approve native behavior, or replace the independent reviewer.

These legacy scope/claim checks are optional. Do not require plan/result model
checkpoints or run model calls automatically from pre-commit. For gameplay
improvements use [per-bot comparison advice](bot_improvement_advice.md), which
suggests a bounded investigation without authorizing or blocking work.
Do not poll the models on every tool call or ask repeatedly until they agree.

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

### Packet size and HTTP 422

Compose checkpoint fields for the model, with each fact stated once. Aim for
roughly 600 tokens of state to leave room for the questions; this is a writing
budget, not a tokenizer guarantee. Keep the full source artifacts and hashes in
`evidence_excerpts` metadata, which the packet builder excludes from model state.
Use short excerpts rather than repeating observations. List every open actor or
requirement by ID and a short description; preserve the parent objective, latest
direction, forbidden changes, acceptance limits, failures and unknowns. Send the
same compact facts to both providers. Do not clip strings or drop trailing actors
to fit. Large staged diffs may still require a narrower review.
The builder uses zero-based `allowed_files_indices` for changed paths already
listed in `allowed_files`, retains other paths explicitly, and references repeated
test commands with `required_test_commands_index`. Full paths/commands remain in
the checkpoint and deterministic checks; these references remove no facts.
The audit-only `task_id` also stays in the full receipt, outside model state.

See the two compact historical inputs in
[`checkpoint_examples.json`](../../experiments/configs/local_laya/checkpoint_examples.json)
for field length and structure. They are examples, not current task state.

The local adapter returns HTTP 422 with `context_budget_exceeded` when any
question would truncate instructions, options or state. The error includes
`state_tokens`, `state_budget` and `truncated_fields` for each question. This means
**not reviewed**. It is neither a model judgment nor a stopped service. Other 422
reasons, such as an invalid question or wrong model, need their own correction;
read the response body rather than assuming every 422 is a size failure.

Keep the rejected request and error receipt. Shorten repeated prose, then submit
one corrected packet and inspect its returned `token_budget`: every
`truncated_fields` list must be empty. If essential evidence still cannot fit,
record Laya as not reviewed and continue independent review. Do not retry the
unchanged packet, restart a healthy service, or treat hosted success as local
review. Provider errors are advisory-path failures; they never close a task.

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

## Per-bot baselines

Keep baseline state in Git/DVC and supply it with each model request. TypeSafe's
[state API](https://docs.typesafe.ai/concepts/state) evaluates the state provided
in that request; model memory is not the run ledger.

Reuse the existing actor acceptance table, hash-bound assessment `baseline` /
`comparison` receipts and per-actor `laya_packets.actor_packets` projections.
Do not create a second combat logger or duplicate raw timelines for this check.
Each actor comparison needs:

- Stable roster slot, spec/role, gear/setup and reference identities. Do not join
  different actors by name alone or silently compare a changed spec.
- The last accepted run for that actor and the current native observations:
  damage/healing, cadence, idle/failure intervals, deaths and mechanic execution.
- Shared encounter/mode, duration, phase/target coverage, buffs and assignments,
  including mandatory duties that explain an activity difference.
- Deltas calculated in code, comparator eligibility, and explicit unknowns.
  Keep exact receipt hashes outside the compact model state.

There are two references: the actor's last accepted behavior catches regression;
the matched WoWSims/WCL reference measures remaining work. Neither the latest
run nor the single highest DPS sample automatically becomes the accepted baseline.
Review every exercised actor independently so a raid-total gain cannot hide one
actor's loss. Keep tanks' mitigation/threat and healers' survival/mana obligations
alongside their throughput. Missing role metrics mean insufficient evidence.

Promote a better actor result after the matched comparison and separate review
accept its improvement, with survival, mechanic duties and other required metrics
preserved. Save a new immutable version referencing the prior baseline and its
promotion assessment; move only that actor's current pointer. Keep the previous
version in DVC. Other actors can retain baselines from different runs, so every
row carries its own run context. Those rows do not form a synthetic best-of raid
and their DPS must not be summed as an observed clear.

Supply the same compact comparison to Jev and Laya. Ask whether the observed
change is supported regression, expected context variation, supported improvement
or insufficient evidence. Code performs arithmetic and identity checks; the
models flag interpretation concerns. Model scores do not promote a baseline,
auto-revert a patch or authorize another run. Review unresolved findings against
native evidence, and retain both predictions plus the adjudication.

The parent-plan checkpoint remains separate: an actor can improve while the
orchestrator abandons other requirements. Send it the current plan, completed
work, recent attempts and remaining actors. This section defines how to use the
existing comparison/review path; it is not an automatic baseline-promotion service.

## Pre-commit use

The repository hook at `.githooks/pre-commit` runs
`pixi run --frozen python -m tools.raid_program.worker_precommit`. It reads the
current coordinator-authored task from `git rev-parse --git-path worker-task.json`,
captures the actual staged diff and file list, and retains the index tree,
source HEAD and task/diff hashes. Unstaged work is excluded. An index change
during review invalidates the result. The default hook makes no model calls.
With explicit `--model-advice`, it prints each model's choice, probability and
confidence separately, with a path to the complete receipts.
HEAD and the original task bytes are also rechecked before returning.

Use it for one commit without changing hooks in the other ongoing worktrees:

```sh
git -c core.hooksPath=.githooks commit
```

For an explicit checkpoint or an API key stored outside this worktree:

```sh
pixi run python -m tools.raid_program.worker_precommit \
  --task /absolute/path/to/current-task.json \
  --env-file /absolute/path/to/jev.env --backend both --model-advice
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
