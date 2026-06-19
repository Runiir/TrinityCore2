# Lane 6 ML Data Progress

## 2026-06-19

- Consolidated the offline policy dataset around `teacher_policy_candidate_v1`.
- Candidate rows now carry explicit candidate masks, chosen actions, domains, reward/outcome labels, trace fields, and failure labels.
- Joined `bot_memory_decision_fingerprints` into decision building and filter repeated teacher loops from imitation with `repeated_decision_loop` and `repeated_failed_decision_loop`.
- Kept failed/unsafe rows as negative outcome evidence while setting `imitate_teacher=0`.
- Added data-quality checks for contract version, domains, candidate masks, chosen masks, and loop-filter invariants.
- Added runtime fail-closed metadata to train/evaluate/register outputs: `control_eligible=false` and `runtime_ml_control=disabled_until_shadow_assist_replay_validation_beats_teacher`.
- Added DVC stages for `bot_ml_build_decisions`, `bot_ml_validate`, `bot_ml_train`, `bot_ml_evaluate`, and `bot_ml_register`.
- Integration fixed fallback candidate counts and duplicate-activity chosen-label ambiguity; chosen matching now uses candidate id first and emits exactly one observed row.
- Added a tiny DVC-tracked raw telemetry fixture at `dataset/bot_ml/raw.dvc` so the ML DVC chain is reproducible without a live DB export.

Verification:

- `pixi run pytest tests/test_ml_pipeline.py -k 'bot_ml_decision_builder or bot_ml_data_quality or bot_ml_numeric_features or policy_model'`: passed with 8 tests and 1 `dvclive`/`pynvml` warning.
- `pixi run dvc repro bot_ml_register` completed through build/train/evaluate/register on the raw fixture. Evaluation remains fail-closed with `accepted=false`, `control_eligible=false`, `eval_rows=1`.
- `pixi run dvc repro bot_ml_validate` completed with `ok=true`, 2 decisions, 2 chosen rows, and zero contract errors.
- `pixi run dvc repro validation_run_status quest_profession_report world_planner_validate` completed after shared `common.py` changed.
- `pixi run dvc status` reports data and pipelines up to date.

Blockers:

- Real `bot-ml-export` requires a live characters DB URL.
- The fixture is only a reproducibility smoke input; real ML readiness still requires live exported telemetry from a characters DB.

Post-commit note:

- Runtime ML control remains disabled until shadow/assist/replay validation beats the heuristic teacher.
