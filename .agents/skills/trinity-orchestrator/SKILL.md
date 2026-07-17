---
name: trinity-orchestrator
description: Repo-scoped orchestration workflow for TrinityCore bot autonomy and experiment work, including worker task complexity routing and model tier selection.
---

# Trinity Orchestrator

Use this skill when acting as the prompt-driven orchestrator for bot autonomy or experiment work in this TrinityCore repository.

## Workflow

1. Read the user goal, current daemon state, checklist, prior artifacts, and git status snapshot before deciding the next action.
2. Decide whether to work directly or create/resume a worker Codex session. The daemon does not auto-launch workers.
3. Before creating a worker, classify the worker task complexity as `simple`, `medium`, or `large`.
4. Run `scripts/check-openai-models.sh` once per orchestration pass before selecting or launching OpenAI-backed workers. Do not guess a replacement name when a required model is missing. Run `scripts/check-openai-models.sh --smoke` after proxy/auth/model-routing changes or when a model returns errors.
5. Choose the best worker model for the task from `worker_model_catalog`; consider ambiguity, difficulty, repetition, required polish, latency, and usage cost. Treat `worker_model_tiers` as defaults, not restrictions.
   - Under Claude Code with CLIProxyAPI, pass the exact OpenAI model ID directly: `gpt-5.6-luna` for `simple`, `gpt-5.6-terra` for `medium`, and `gpt-5.6-sol` for `large`. Do not create or depend on Claude model aliases.
   - Use `run_in_background: true` for independent parallel workers. Keep dependent work foregrounded, and always collect and review every worker result before integration.
6. Record worker complexity, model, reasoning effort, and evidence paths in progress summaries when the tier choice is relevant.
7. Keep worker tasks scoped, review results before merging, and run repository validation when behavior changes.
8. Commit experiment code/configs to git, checkpoint generated data/artifacts with DVC, then run `dvc status` and `dvc push` after future experiments that produce artifacts.
9. For every new or existing worktree used for experiments, verify DVC remote credentials before `dvc pull`, `dvc repro`, or `dvc push`: compare `pixi run dvc config --list` against the main repository worktree with secrets redacted, and copy/recreate `.dvc/config.local` from the main worktree when the worktree is missing the local remote credentials. Never commit `.dvc/config.local`.
10. Before exiting every pass, update the current run status/progress artifacts with what changed, evidence paths, validation outcomes, blockers, and the exact next handoff prompt for the next fresh agent.
11. Before exiting every pass, inspect `git status --short`, commit coherent finished changes and useful status/progress updates, checkpoint generated artifacts with DVC, run `dvc status`, run `dvc push` when artifacts were produced, and leave the worktree clean except for explicitly protected pre-existing user changes.

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
