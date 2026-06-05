# Phase 09 Progress

## Current milestone

Milestone 11 complete for the local/headless V1 autonomous loop path.

## Completed

- Milestone 1: added autonomous high-level task schema at `ml/schemas/autonomous_task.schema.json`.
- Milestone 2: added deterministic task selection skeleton in `ml/autonomous/selector.py`.
- Milestone 3: integrated repair/vendor/restock preflight through the existing `playerbot vendor_trash` and `playerbot repair` command paths; the local adapter now tracks durability recovery.
- Milestone 4: integrated quest task invocation from the autonomous loop with bounded objective attempts and local kill objective progression.
- Milestone 5: integrated profession task invocation from the autonomous loop through `profession_score` and `craft`.
- Milestone 6: integrated dungeon task invocation from the autonomous loop through existing route step command primitives.
- Milestone 7: documented failure handling paths in `ml/autonomous/tasks.py` and emitted them in autonomous frames.
- Milestone 8: added a long-term progress store model in `ml/autonomous/progress.py` and included it in autonomous frames.
- Milestone 9: added autonomous loop frame emission to the headless experiment runner and a separate `autonomous_loop_<run>.jsonl` artifact.
- Milestone 10: added `experiments/configs/headless_autonomous_loop_smoke_001.json` and the `pixi run autonomous-smoke` task.
- Milestone 11: added `autonomous_metrics` with tasks/hour, recovery, stuck/death/manual-intervention/resource metrics, goal progress, and frames by domain.

## Changed files

- `experiments/run_experiment.py`
- `experiments/configs/headless_autonomous_loop_smoke_001.json`
- `ml/autonomous/__init__.py`
- `ml/autonomous/tasks.py`
- `ml/autonomous/selector.py`
- `ml/autonomous/progress.py`
- `ml/autonomous/frames.py`
- `ml/autonomous/metrics.py`
- `ml/schemas/autonomous_task.schema.json`
- `tests/test_ml_pipeline.py`
- `pixi.toml`
- `params.yaml`
- `dvclive/params.yaml`
- `dvc.yaml`
- `dvc.lock`
- `.codex/plans/bots_experiments/progress/PHASE_09_PROGRESS.md`

## Verification log

- 2026-06-05: `pixi run pytest tests/test_ml_pipeline.py::test_headless_autonomous_loop_smoke_records_frames_and_metrics -q` passed (`1 passed`, existing DVCLive/pynvml deprecation warning).
- 2026-06-05: `pixi run pytest tests/test_ml_pipeline.py -q` passed (`14 passed`, existing DVCLive/pynvml deprecation warning).
- 2026-06-05: `pixi run autonomous-smoke` passed and generated local `run_000022` with `autonomous_frame_count=6`, `tasks_completed=4`, `domain_tasks_invoked=["dungeon","profession","quest"]`, `manual_intervention_count=0`, and `progress_toward_selected_goal=1.0`.
- 2026-06-05: `pixi run dvc-repro` passed after pointing capture params at `headless_autonomous_loop_smoke_001`; generated DVC-managed `run_000023` with the same autonomous metrics.
- 2026-06-05: `pixi run dvc-status` reported `Data and pipelines are up to date.`
- 2026-06-05: `pixi run dvc-push` pushed `22 files`.
- 2026-06-05: `pixi run python -m py_compile experiments/run_experiment.py ml/autonomous/tasks.py ml/autonomous/selector.py ml/autonomous/progress.py ml/autonomous/frames.py ml/autonomous/metrics.py` passed.

## Blockers / assumptions

- The verified Phase 09 smoke is the local/headless adapter path, not a live DB-backed worldserver autonomous run.
- Live repair/vendor/restock, quest, profession, and dungeon steps depend on the same existing `.playerbot` command surfaces verified in previous phases; trainer/vendor reagent buying remains limited by normal in-world NPC interaction constraints documented in Phase 06.
- Raid task type is present in the schema and failure handling vocabulary, but the V1 autonomous smoke invokes quest, profession, and dungeon domains. Full raid autonomous scheduling remains a later integration target.

## Completion criteria audit

- Autonomous task schema exists: complete via `ml/schemas/autonomous_task.schema.json`.
- Task selector skeleton exists: complete via `ml/autonomous/selector.py` and test coverage.
- Preflight repair/vendor/restock exists or blockers documented: complete via autonomous `repair_and_restock` task and local smoke metrics.
- At least two domain tasks can be invoked from the autonomous loop: complete; smoke invokes `quest`, `profession`, and `dungeon`.
- Autonomous frames recorded: complete; `dataset/raw/run_000023/autonomous_loop_run_000023.jsonl` and canonical `frames.jsonl` contain autonomous frames.
- Failure handling paths documented/implemented: complete via `FAILURE_HANDLERS` and frame emission.
- General metrics generated: complete via `experiments/runs/run_000023/autonomous_metrics.json`.
- Headless autonomous smoke runs or blockers documented: complete via `pixi run autonomous-smoke` and DVC `run_000023`.
- Progress/docs updated: complete in this file.

## Next step

Phase 09 completion criteria are met for the requested headless autonomous loop implementation. Optional stronger validation is a live DB-backed worldserver autonomous run through SOAP/RA using the same config shape.
