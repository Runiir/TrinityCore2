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
