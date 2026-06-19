# Quest/Profession Lane Progress

## 2026-06-19

- Added data-driven planner manifests for quest hub batches, quest route edges, unsupported quest fallbacks, service visit plans, recipe acquisition plans, material plans, and crafting surfaces.
- Extended world-planner validation with staged gates for quest chains, fallback coverage, cross-zone routing, class/profession trainer visits, all-profession recipe acquisition, material planning, and crafting surfaces.
- Added `tools.bot_ml.build_quest_profession_reports` plus `pixi run bot-quest-profession-report` and a DVC metrics stage at `quest_profession_report` for no-server staged report generation from planner manifests.
- Updated focused tests in `tests/test_ml_pipeline.py` and bot_ml README workflow documentation.

Verification:

- `pixi run pytest tests/test_ml_pipeline.py::test_bot_ml_workflow_has_pixi_tasks_and_documented_dvc_steps tests/test_ml_pipeline.py::test_world_planner_builder_derives_hubs_clusters_services_and_travel tests/test_ml_pipeline.py::test_world_planner_validation_report_marks_covered_and_missing_gates tests/test_ml_pipeline.py::test_quest_profession_report_builds_without_live_server` passed: 4 passed, 1 warning from `dvclive`/`pynvml`.
- Temporary command smoke passed: `pixi run bot-world-planner --world-dir /tmp/.../world --output-dir /tmp/.../planner` then `pixi run bot-quest-profession-report --planner-dir /tmp/.../planner --report /tmp/.../report.json` produced `bot_quest_profession_report_v1` with 15 passed, 0 failed, `all_passed=true`.
- Integration rerun: `pixi run pytest tests/test_autonomy_pipeline_smoke.py tests/test_ml_pipeline.py` passed with 96 tests and 1 `dvclive`/`pynvml` warning.
- `pixi run dvc repro quest_profession_report` and `pixi run dvc repro world_planner_validate` completed and updated `dvc.lock`. The local sparse planner dataset intentionally leaves the generated quest/profession metrics report at 1 passed, 14 failed until real planner rows are present.
- `pixi run dvc status` completed. Only `live_validation_combined` remains stale from the integration-owned `tools/bot_ml/run_live_bot_validation.py` dependency drift.

Blockers:

- Full quest/profession gate success still requires populated world planner manifests with actual quest batches, cross-zone route edges, class trainer visits, recipe/material rows, and repair/vendor coverage.
