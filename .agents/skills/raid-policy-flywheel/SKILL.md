---
name: raid-policy-flywheel
description: Admit, quarantine, transform, train, and evaluate one immutable batch of TrinityCore raid decision data for a safe learned bot policy. Use for telemetry schema checks, DVC/DVCLive dataset lifecycle, candidate-ranking datasets, hard-negative labeling, offline splits, shadow evaluation, replay comparison, and model-registry promotion. Do not use to change live gameplay logic, encounter scripts, class rotations, or capture an active run.
---

# Raid Policy Flywheel

Turn already-closed, attributable raid evidence into reproducible learning data. The deterministic priority system stays the teacher and safety envelope; the first learned policy ranks an existing valid candidate set rather than inventing actions.

## Required inputs

Read [references/dataset-admission.md](references/dataset-admission.md) before admitting data. Accept only a closed evidence batch handed off by `raid-evidence-lifecycle` with:

- exact Git and build identities;
- roster, route, encounter, mode, configuration, and run identities;
- capture manifest and terminal receipt;
- schema/version identity;
- explicit publication or local reconstruction state.

Never read a still-growing telemetry file as training input.

## Ownership boundary

Own one immutable batch or one model evaluation at a time. This skill may change dataset builders, schemas, quality gates, training/evaluation code, DVC metadata, and DVCLive experiment records. It must not:

- mutate or restart a live shard;
- alter class, boss, or route behavior to make labels easier;
- relabel infrastructure failures as gameplay failures;
- let a model bypass deterministic legality, safety, mechanic, or authority gates;
- promote a model from aggregate DPS/HPS alone.

## Flywheel loop

### 1. Verify batch identity

Fail closed if the terminal receipt, manifest, Git/build identity, roster, route, or schema is missing or contradictory. Hydrate only the exact DVC artifact required for this batch. Do not broaden the pull.

### 2. Build decision rows

Prefer the existing deterministic tools:

```bash
pixi run python tools/bot_ml/build_decision_dataset.py --help
pixi run python tools/bot_ml/validate_data_quality.py --help
```

Each row must preserve the observation, complete candidate set, deterministic masks/gates, relevance or priority features, selected candidate, native submission, rejection/completion, landed outcome, and role/mechanic outcome. Aggregate meters alone cannot train action arbitration.

WoWSims is a versioned reference or teacher signal for DPS cadence and expected output. It is not a source of live server outcomes and does not replace native spell legality or encounter context.

### 3. Partition before training

Assign every row to exactly one state:

- `admit`: attributable, player-like, complete decision/outcome chain;
- `hard_negative`: a legitimate candidate/action failed for a modeled gameplay reason;
- `quarantine`: identity, schema, script, route, synthetic-assistance, capture, or infrastructure defect;
- `holdout`: valid data reserved before tuning.

Keep quarantine records and reason counts, but never feed them into training or benchmark summaries.

Split by whole run/encounter/roster cohort as appropriate. Do not allow adjacent rows from the same decision sequence to leak across train and evaluation splits.

### 4. Train and compare reproducibly

Use repository tools through pixi:

```bash
pixi run python tools/bot_ml/train_policy_model.py --help
pixi run python tools/bot_ml/evaluate_policy_model.py --help
pixi run python tools/bot_ml/replay_compare_report.py --help
```

Commit code, schema, configs, and compact manifests to Git. Track large datasets and model artifacts with DVC and experiment metrics with DVCLive. Record feature schema, split manifest, seed, trainer config, input DVC hashes, and source commit.

Evaluation must include legality/mask violations, candidate-ranking quality, rejection-loop rate, action completion and landed-outcome rates, mechanic compliance, role metrics, and per-encounter regressions. Averages must not hide a failed boss or role.

### 5. Promote in stages

Promotion order is:

1. offline holdout;
2. native replay comparison against the deterministic policy;
3. live shadow scoring with no control authority;
4. bounded candidate-ranking experiment behind deterministic gates;
5. broader validation only after no-regression evidence.

Use `tools/bot_ml/register_policy_model.py` only after its stated gates pass. A learned score may reorder eligible actions; deterministic masks, native action checks, and encounter safety remain authoritative.

### 6. Publish and minimize disk

Checkpoint generated datasets, reports, and models with DVC. Run `dvc status` and `dvc push`, record successful remote publication, and evict only reconstructable local payloads under the evidence-retention rules. Never delete the only copy or an active batch.

## Completion gate

Return:

- admitted, hard-negative, holdout, and quarantine counts with reason codes;
- exact Git, DVC, schema, split, seed, and model identities;
- per-role and per-encounter evaluation, not only an aggregate score;
- comparison with the deterministic baseline;
- promotion state: `blocked`, `offline_only`, `shadow_ready`, or `bounded_control_ready`;
- the first failed gate and the next bounded owner when blocked.

Use the shared handoff contract from `raid-performance-loop/references/handoff-contract.md`.
