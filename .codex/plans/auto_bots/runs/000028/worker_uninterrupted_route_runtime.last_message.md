Implemented the scoped Python-side first step and wrote the worker handoff to:

`.codex/plans/auto_bots/runs/000028/worker_uninterrupted_route_runtime.last_message.md`

Changed:
- `tools/bot_ml/run_live_bot_validation.py`
- `tools/bot_ml/build_live_scenario_reports.py`
- `tests/test_ml_pipeline.py`

Tests run:
- `pixi run pytest tests/test_ml_pipeline.py -k 'route_manifest_dry_run or manifest_backed_uninterrupted_clear or counts_stonecore_summary_boss_kills or route_sequence_dry_run or aggregates_segmented_raid_progress_without_full_clear'`
- `pixi run python -m py_compile tools/bot_ml/run_live_bot_validation.py tools/bot_ml/build_live_scenario_reports.py`

No commit made. Remaining blocker is C++ runtime support: `BotWorldPopulationMgr` still needs to consume the manifest and advance route nodes in one worldserver process.