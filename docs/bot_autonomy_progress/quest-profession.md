# Quest/Profession Lane Progress

## 2026-06-19

- Added data-driven planner manifests for quest hub batches, quest route edges, unsupported quest fallbacks, service visit plans, recipe acquisition plans, material plans, and crafting surfaces.
- Extended world-planner validation with staged gates for quest chains, fallback coverage, cross-zone routing, class/profession trainer visits, all-profession recipe acquisition, material planning, and crafting surfaces.
- Added `tools.bot_ml.build_quest_profession_reports` plus `pixi run bot-quest-profession-report` and a DVC metrics stage at `quest_profession_report` for no-server staged report generation from planner manifests.
- Updated focused tests in `tests/test_ml_pipeline.py` and bot_ml README workflow documentation.

Verification:

- `pixi run pytest tests/test_ml_pipeline.py::test_bot_ml_workflow_has_pixi_tasks_and_documented_dvc_steps tests/test_ml_pipeline.py::test_world_planner_builder_derives_hubs_clusters_services_and_travel tests/test_ml_pipeline.py::test_world_planner_validation_report_marks_covered_and_missing_gates tests/test_ml_pipeline.py::test_quest_profession_report_builds_without_live_server` passed: 4 passed, 1 warning from `dvclive`/`pynvml`.
- Temporary command smoke passed: `pixi run bot-world-planner --world-dir /tmp/.../world --output-dir /tmp/.../planner` then `pixi run bot-quest-profession-report --planner-dir /tmp/.../planner --report /tmp/.../report.json` produced `bot_quest_profession_report_v1` with 15 passed, 0 failed, `all_passed=true`.
- Full `pixi run pytest tests/test_ml_pipeline.py` was attempted and had unrelated local prerequisite failures: missing `trinity-worldserver-test.conf`, missing/uncached DVC datasets, missing DBC metadata, and unreachable hotfix DB `172.20.0.2`.
- `pixi run dvc status` completed. It reports this lane's modified planner/report deps and deleted or uncached shared DVC outs such as `dataset/world_knowledge`, `dataset/world_planner`, `dataset/validation_scenarios`, DBC files, and live validation artifacts.

Blockers:

- No local DVC data/cache for generated datasets in this worktree, so the new `quest_profession_report` DVC stage could not be reproduced against real `dataset/world_planner`.
- No new repo-local DVC artifact was generated to push; run `pixi run dvc pull` or regenerate the missing datasets before `pixi run dvc repro quest_profession_report` and `pixi run dvc push`.
