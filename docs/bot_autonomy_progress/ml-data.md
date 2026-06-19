# Lane 6 ML Data Progress

## 2026-06-19

- Consolidated the offline policy dataset around `teacher_policy_candidate_v1`.
- Candidate rows now carry explicit candidate masks, chosen actions, domains, reward/outcome labels, trace fields, and failure labels.
- Joined `bot_memory_decision_fingerprints` into decision building and filter repeated teacher loops from imitation with `repeated_decision_loop` and `repeated_failed_decision_loop`.
- Kept failed/unsafe rows as negative outcome evidence while setting `imitate_teacher=0`.
- Added data-quality checks for contract version, domains, candidate masks, chosen masks, and loop-filter invariants.
- Added runtime fail-closed metadata to train/evaluate/register outputs: `control_eligible=false` and `runtime_ml_control=disabled_until_shadow_assist_replay_validation_beats_teacher`.
- Added DVC stages for `bot_ml_build_decisions`, `bot_ml_validate`, `bot_ml_train`, `bot_ml_evaluate`, and `bot_ml_register`.

Verification:

- `pixi run pytest tests/test_ml_pipeline.py -k "bot_ml"`: passed, 9 tests.
- `pixi run pytest tests/test_ml_pipeline.py`: 73 passed, 8 failed. Failures are environmental/pre-existing in this lane: missing `trinity-worldserver-test.conf`, unreachable hotfix DB at `172.20.0.2`, missing validation provisioning artifacts, and missing `dataset/metadata` files.
- `pixi run bot-ml-export --output-dir dataset/bot_ml/raw`: blocked because `--database-url` is required for DB export.
- Synthetic raw telemetry smoke:
  - `pixi run bot-ml-build-decisions --input-dir dataset/bot_ml/raw --output dataset/bot_ml/decision_dataset.jsonl --manifest dataset/bot_ml/decision_dataset_manifest.json`: passed.
  - `pixi run bot-ml-validate --dataset dataset/bot_ml/decision_dataset.jsonl --report dataset/bot_ml/data_quality.json`: passed.
  - `pixi run bot-ml-train --dataset dataset/bot_ml/decision_dataset.jsonl --model models/bot_policy/policy_model.json --model-dir models/bot_policy/artifacts --backend linear_baseline`: passed.
  - `pixi run bot-ml-evaluate --dataset dataset/bot_ml/decision_dataset.jsonl --model models/bot_policy/policy_model.json --metrics evaluations/bot_policy/metrics.json --diagnostics evaluations/bot_policy/diagnostics.json --min-eval-rows 1 --max-stuck-rate 1 --max-failure-rate 1`: passed, `accepted=false`, `control_eligible=false`.
  - `pixi run bot-ml-register --model models/bot_policy/policy_model.json --metrics evaluations/bot_policy/metrics.json --diagnostics evaluations/bot_policy/diagnostics.json --sql-output models/bot_policy/register_model.sql`: passed, `accepted=false`, `control_eligible=false`.
- `pixi run dvc status`: completed. New ML stages show modified generated outs from the synthetic smoke; existing lane status also reports many missing/not-in-cache validation artifacts and datasets.

Blockers:

- Real `bot-ml-export` requires a live characters DB URL.
- Full validation tests require generated configs/artifacts and local DBC/hotfix data that are absent or unreachable in this lane.

Post-commit note:

- Implementation committed as `28ade05756` with source/config/docs/tests only. Generated synthetic dataset, model, DVCLive, and register artifacts were left as local DVC/ignored outputs and were not committed to Git.
