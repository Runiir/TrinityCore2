# World Planner Lane Progress

## 2026-06-19

- Commit: `b0652a649d` (`Extend world planner manifests`).
- Branch: `bot-autonomy/lane-world-planner`.
- Changed files:
  - `tools/bot_ml/extract_world_knowledge.py`
  - `tools/bot_ml/build_world_planner_manifests.py`
  - `tools/bot_ml/validate_world_planner.py`
  - `tests/test_ml_pipeline.py`
  - `docs/bot_autonomy_progress/world-planner.md`
- Tests:
  - `pixi run pytest tests/test_ml_pipeline.py -k 'world_knowledge_cli or world_knowledge_extractor or world_planner_builder or world_planner_validation'` passed, 4 selected.
  - `pixi run pytest tests/test_ml_pipeline.py` ran with 74 passed and 6 failed. Failures are outside the owned world-planner code path and require missing local config/generated artifacts or DB connectivity: `trinity-worldserver-test.conf`, MySQL `172.20.0.2:3306`, validation gear/provisioning datasets, and metadata JSON files.
  - Direct offline pipeline completed:
    - `pixi run python -m tools.bot_ml.extract_world_knowledge --output-dir dataset/world_knowledge`
    - `pixi run python -m tools.bot_ml.build_world_planner_manifests --world-dir dataset/world_knowledge --output-dir dataset/world_planner`
    - `pixi run python -m tools.bot_ml.validate_world_planner --planner-dir dataset/world_planner --validation-scenario-dir dataset/validation_scenarios --live-scenario-report-dir dataset/live_validation_scenario_reports_built --report dataset/world_validation/planner_report.json`
- Worldserver/ports: not started; no ports allocated.
- DVC:
  - `pixi run dvc repro world_planner_validate` was run twice.
  - First run failed rebuilding `world_knowledge` because `trinity-worldserver-test.conf` is absent.
  - After adding DB-unavailable fallback manifests, the second run failed before the target stage while DVC verified unrelated missing live-validation `.dvc` data source directories, starting with `dataset/live_validation_scenarios/blackwing_descent_10n/01_entry_trash`.
  - `pixi run dvc pull ... -v` failed because the local cache lacks the locked artifacts and the configured S3 remote requires credentials: `Unable to locate credentials`.
  - `pixi run dvc status` shows world-planner outputs generated locally but `not in cache`, plus many unrelated validation/live artifacts also missing from cache.
- Latest diagnostic summary:
  - Offline extraction wrote 18 world-knowledge manifest files with `extraction_status.mode=empty_db_unavailable`.
  - Planner builder wrote 18 planner manifest files.
  - Validator wrote `dataset/world_validation/planner_report.json` with `passed=0`, `failed=15`, `total=15`, `all_passed=false` because the lane has no DB-backed/generated world rows and no validation scenario/live report datasets materialized.
  - Validation report now includes deterministic `dataset_inputs` evidence with source paths, existence, row counts, and hashes.
- Blockers:
  - `trinity-worldserver-test.conf` is not present in this lane, so DB-backed extraction cannot run from the default DVC command.
  - DVC remote `s3://artifacts/trinity-cata` cannot be pulled in this environment without credentials.
  - Locked validation/live DVC artifacts are not available in local cache.
- Downstream trigger status:
  - Schema and tests are ready for downstream planner/profession/loot consumers.
  - Full validation remains blocked until DB access or DVC artifacts are materialized, then `pixi run dvc repro world_planner_validate` should be rerun and the generated DVC outputs pushed.
