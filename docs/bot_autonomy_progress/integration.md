# Integration Progress

Current date: 2026-06-19

## Latest Integration Pass

- Commit `0feb46ff36` merged `master` artifact pointers into `bot-autonomy/integration`.
- Commit `6cc510aed9` resolved the `evaluations/bot_policy` and `artifacts/bot_policy_dvclive` ownership overlap by making those output directories DVC-owned instead of git-tracked internally.
- `pixi run pytest tests/test_autonomy_pipeline_smoke.py tests/test_ml_pipeline.py`: passed, 105 passed, 1 `dvclive`/`pynvml` warning.
- `pixi run dvc status`: passed, data and pipelines are up to date.
- `pixi run dvc push`: passed, everything is up to date.
- No worldserver process was started in this pass; no live instance ports were allocated.

## Baseline Fixes

- Branch: `bot-autonomy/integration`
- Preserved pre-existing local changes: untracked BWD artifact directories remain untracked; the prior validation-route C++ range tweak is included in the integration-owned runtime fix.
- Added `teacherAssistAuthoritativeFocus` validation-route assist handling, boss-route teacher-assist recovery telemetry, and wider boss search ranges.
- Hardened gear profile item loading so local DB2/DBC rows are still usable when the optional hotfix MySQL endpoint is unreachable.
- Added `bot-lane-configs` with deterministic lane ports for lanes 0-6.
- Added live-validation config template fallback for clean worktrees without `trinity-worldserver-test.conf`.

## Verification

- `pixi run pytest tests/test_autonomy_pipeline_smoke.py::test_quest_first_portfolio_routing_surface tests/test_ml_pipeline.py::test_validation_gear_profiles_complete_from_local_db2_files tests/test_ml_pipeline.py::test_validation_provisioning_verifier_accepts_generated_payloads`: passed, 3 passed, 1 warning.
- `pixi run pytest tests/test_autonomy_pipeline_smoke.py tests/test_ml_pipeline.py`: passed, 94 passed, 1 warning.
- `pixi run bot-lane-configs --lane 0 --dry-run`: passed with lane 0 ports `18085/18086/13443/17878`.
- `pixi run bot-lane-configs --dry-run`: passed for lanes 0-6 with the planned `+100` port allocation.
- `cmake --build build --target worldserver -j2`: passed.
- `pixi run dvc status`: reports stale stages for `validation_gear`, `validation_provisioning_verify`, `live_scenario_reports`, and `live_validation_combined` because committed tool dependencies changed; no new generated artifacts were checkpointed or pushed.

## Lane Review State

- `runtime-recovery` commit `1e5871156d`: blocked by reviewer due malformed decision-fingerprint metadata JSON and no C++ build.
- `quest-profession` commit `0e2e3e278b`: blocked by reviewer due false-positive `cross_zone_routing` and `class_skill_visit` gates plus DVC lock gap.
- `combat-loot` commit `b3c5a3a0d6`: blocked by reviewer due failing smoke test on its branch, merge regression against the hotfix DB fallback, cwd-fragile manifest loading, and DVC lock drift.
- `group-validation` commit `5642c74362`: blocked by reviewer due stale/missing DVC artifacts and evidence-incomplete runs still being eligible for clear/training labels.
- `foundation` commits `6bf8300752`, `8fbee85646`: partially integrated manually; fake offline gear/enchant catalog intentionally not merged.
- `world-planner` commits `b0652a649d`, `539323fa89`: blocked by reviewer due stale DVC world-planner outputs/lock, incomplete-manifest fallback being marked successful, and `vendor_repair` passing without actual repair coverage.
- `ml-data` commits `28ade05756`, `6071062c81`: blocked by reviewer due fallback candidate count mismatch, duplicate-activity chosen-label ambiguity, and new ML DVC stages lacking lock/checkpointed outputs.
