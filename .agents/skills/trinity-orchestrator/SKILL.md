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
4. Select the worker model tier from the daemon's `worker_model_tiers` config.
5. Record worker complexity, model, reasoning effort, and evidence paths in progress summaries when the tier choice is relevant.
6. Keep worker tasks scoped, review results before merging, and run repository validation when behavior changes.
7. Commit experiment code/configs to git, checkpoint generated data/artifacts with DVC, then run `dvc status` and `dvc push` after future experiments that produce artifacts.
8. For every new or existing worktree used for experiments, verify DVC remote credentials before `dvc pull`, `dvc repro`, or `dvc push`: compare `pixi run dvc config --list` against the main repository worktree with secrets redacted, and copy/recreate `.dvc/config.local` from the main worktree when the worktree is missing the local remote credentials. Never commit `.dvc/config.local`.
9. Before exiting every pass, update the current run status/progress artifacts with what changed, evidence paths, validation outcomes, blockers, and the exact next handoff prompt for the next fresh agent.
10. Before exiting every pass, inspect `git status --short`, commit coherent finished changes and useful status/progress updates, checkpoint generated artifacts with DVC, run `dvc status`, run `dvc push` when artifacts were produced, and leave the worktree clean except for explicitly protected pre-existing user changes.

## Worker Complexity

- `simple`: near-instant, scoped edits, inspections, or small test updates with limited blast radius.
- `medium`: normal implementation tasks that require several files, local tests, or moderate debugging.
- `large`: broad, ambiguous, high-risk, or long-running investigations and changes.

## Worker Model Tiers

Use these defaults unless the active daemon config overrides them:

| Complexity | Model | Reasoning |
| --- | --- | --- |
| `simple` | `gpt-5.3-codex-spark` | `low` |
| `medium` | `gpt-5.5` | `medium` |
| `large` | `gpt-5.5` | `high` |

If a configured tier is missing or invalid, fall back to `worker_model` and `worker_reasoning_effort`.
