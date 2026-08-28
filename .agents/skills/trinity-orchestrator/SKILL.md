---
name: trinity-orchestrator
description: Repo-scoped, quota-aware orchestration workflow for TrinityCore bot autonomy and experiment work, including bounded non-recursive delegation, worker task complexity routing, and model tier selection.
---

# Trinity Orchestrator

Use this skill when acting as the prompt-driven orchestrator for bot autonomy or experiment work in this TrinityCore repository.

## Workflow

1. Read the user goal, current daemon state, checklist, prior artifacts, and git status snapshot before deciding the next action.
2. Work directly by default. Create or resume a worker only when one bounded worker materially improves the result; the daemon does not auto-launch workers.
3. Before creating a worker, classify the worker task complexity as `simple`, `medium`, or `large`.
4. Run `scripts/check-openai-models.sh` once per orchestration pass before selecting or launching OpenAI-backed workers. Do not guess a replacement name when a required model is missing. Run `scripts/check-openai-models.sh --smoke` after proxy/auth/model-routing changes or when a model returns errors.
5. Choose the best worker model for the complete bounded task from `worker_model_catalog`; consider ambiguity, difficulty, repetition, required polish, latency, and usage cost. Treat `worker_model_tiers` as defaults, not restrictions.
   - Under Claude Code with CLIProxyAPI, pass the exact OpenAI model ID directly: `gpt-5.6-luna` for `simple`, `gpt-5.6-terra` for `medium`, and `gpt-5.6-sol` for `large`. Do not create or depend on Claude model aliases.
   - Run workers sequentially by default. Parallel workers require an explicit user request and disjoint tasks; always collect and review every result before integration.
6. Record worker complexity, model, reasoning effort, and evidence paths in progress summaries when the tier choice is relevant.
7. Keep worker tasks scoped, review results before merging, and run repository validation when behavior changes.
   Every worker must follow
   [../raid-performance-loop/references/bounded-work-unit-contract.md](../raid-performance-loop/references/bounded-work-unit-contract.md).
   Put its immutable input, one hypothesis, owned files, excluded lanes, one
   focused validation command, and terminal handoff conditions in the prompt.
   An adjacent finding is a new work unit, never an implicit scope expansion.
   Require one material-gate receipt within 60 seconds and every 60 seconds
   thereafter. Request status after the first missed receipt and interrupt
   after the second consecutive miss. After two failed command attempts on the
   same edge, require a compact failed handoff instead of more retries or
   broader optimization.
8. Commit experiment code/configs to git, checkpoint generated data/artifacts with DVC, then run `dvc status` and `dvc push` after future experiments that produce artifacts.
9. For every new or existing worktree used for experiments, verify DVC remote credentials before `dvc pull`, `dvc repro`, or `dvc push`: compare `pixi run dvc config --list` against the main repository worktree with secrets redacted, and copy/recreate `.dvc/config.local` from the main worktree when the worktree is missing the local remote credentials. Never commit `.dvc/config.local`.
10. Before exiting every pass, update the current run status/progress artifacts with what changed, evidence paths, validation outcomes, blockers, and the exact next handoff prompt for the next fresh agent.
11. Before exiting every pass, inspect `git status --short`, commit coherent finished changes and useful status/progress updates, checkpoint generated artifacts with DVC, run `dvc status`, run `dvc push` when artifacts were produced, and leave the worktree clean except for explicitly protected pre-existing user changes.

## Approved Plan Execution

When the user supplies or points to an approved implementation plan and asks to execute or continue it:

1. Treat the plan as authorization to work. Do not enter Plan mode, invoke plan-mode tools, rewrite the plan before acting, or ask for approval merely to start.
2. Inspect current status and evidence, identify the first incomplete phase, and keep exactly that phase active.
3. Implement and validate the active phase until its gate passes or a genuine external/new-authority blocker is reached. Do not work ahead into later phases.
4. At a passing phase gate, update status and handoff artifacts, commit coherent code/config changes, complete required DVC publication, and continue automatically with the next incomplete phase.
5. Do not end the run merely because a phase completed. Stop only when the full approved plan is complete, the user asks to pause, or progress requires new authority or an external-state change.
6. After context compaction or session resumption, continue from the recorded active phase and evidence paths rather than restarting discovery or planning.

## Mandatory Delegation Guard

Apply these rules unless the user explicitly requests a different worker budget:

1. Use one worker at most by default. A second worker is allowed only to verify a concrete uncertainty identified by the first worker or the root. Never infer more workers from task breadth.
2. Never interpret a list of classes, specs, files, review angles, failure categories, phases, or experiments as a request for one worker per item. One owner handles the whole bounded pass and organizes the output internally.
3. Do not launch workers for overlapping questions or files. Before launching, record the purpose, exact scope, model, expected output, and why existing results do not already cover it.
4. Worker nesting depth is one. Every worker prompt must include: **“Work directly. Do not invoke the Agent, Skill, Workflow, or Team tools. Do not launch another model or subprocess agent.”**
5. Neither the root nor a worker may invoke fan-out skills such as `code-review`, `simplify`, or `deep-research` unless the user explicitly requests multi-agent fan-out. Do not use a generic review prompt that can trigger those skills. Perform one consolidated checklist directly instead.
6. Consolidate changed-line correctness, removed behavior, cross-file contracts, reuse, simplification, efficiency, conventions, and tests into one review pass. Use the optional second worker only for one unresolved high-risk finding, not for another full review.
7. On the first `429`, usage-limit, cooldown, unknown-model/provider, or context-limit error, stop launching and retrying workers. Cancel redundant queued work, preserve completed results, and write the handoff.
8. Use exact OpenAI model IDs for every worker. Never use `opus`, `sonnet`, `haiku`, `fable`, or an omitted/default model.
9. Keep only one phase gate or bounded task active at a time. For an approved multi-phase execution plan, validate and checkpoint the active phase, then continue automatically with the next incomplete phase; do not re-enter Plan mode at phase boundaries.

If the harness cannot prevent a worker from delegating or invoking fan-out skills, do the task in the root session instead of launching that worker.

## Worker Complexity

- `simple`: near-instant, scoped edits, inspections, or small test updates with limited blast radius.
- `medium`: normal implementation tasks that require several files, local tests, or moderate debugging.
- `large`: broad, ambiguous, high-risk, or long-running investigations and changes.

## Model Selection

Use the lowest-cost model and reasoning effort that can reliably complete the task. Current model characteristics:

Use the exact current OpenAI model IDs directly through CLIProxyAPI. Do not add an alias mapping or substitute generic names such as `gpt-5.6`, `sol`, `terra`, or `luna`.

| Model | Intelligence | Taste | Cost | Best use |
| --- | --- | --- | --- | --- |
| `gpt-5.6-sol` | 9 | 8 | 8 | Complex, ambiguous, difficult, or high-value work |
| `gpt-5.6-terra` | 8 | 6 | 7 | Everyday implementation, debugging, and tool use |
| `gpt-5.6-luna` | 6 | 5 | 5 | Specific, repeatable, high-volume structured work |
| `gpt-5.3-codex-spark` | 5 | 4 | 4 | Near-instant, tightly scoped coding iteration |

Default roles:

| Role | Model | Reasoning |
| --- | --- | --- |
| Orchestrator | `gpt-5.6-sol` | `high` |
| Reviewer | `gpt-5.6-sol` | `medium` |
| Worker | `gpt-5.6-terra` | `medium` |

Default worker routing:

| Complexity | Model | Reasoning |
| --- | --- | --- |
| `simple` | `gpt-5.3-codex-spark` | `low` |
| `medium` | `gpt-5.6-terra` | `medium` |
| `large` | `gpt-5.6-sol` | `high` |
