# Integration Progress

Current date: 2026-06-19

## Baseline Fixes

- Branch: `bot-autonomy/integration`
- Preserved pre-existing local changes: untracked BWD artifact directories remain untracked; the prior validation-route C++ range tweak is included in the integration-owned runtime fix.
- Added `teacherAssistAuthoritativeFocus` validation-route assist handling, boss-route teacher-assist recovery telemetry, and wider boss search ranges.
- Hardened gear profile item loading so local DB2/DBC rows are still usable when the optional hotfix MySQL endpoint is unreachable.
- Added `bot-lane-configs` with deterministic lane ports for lanes 0-6.
- Added live-validation config template fallback for clean worktrees without `trinity-worldserver-test.conf`.

## Verification

- `pixi run pytest tests/test_autonomy_pipeline_smoke.py::test_quest_first_portfolio_routing_surface tests/test_ml_pipeline.py::test_validation_gear_profiles_complete_from_local_db2_files tests/test_ml_pipeline.py::test_validation_provisioning_verifier_accepts_generated_payloads`: passed, 3 passed, 1 warning.
- `pixi run bot-lane-configs --lane 0 --dry-run`: passed with lane 0 ports `18085/18086/13443/17878`.

## Lane Review State

- `runtime-recovery` commit `1e5871156d`: blocked by reviewer due malformed decision-fingerprint metadata JSON and no C++ build.
- `quest-profession` commit `0e2e3e278b`: blocked by reviewer due false-positive `cross_zone_routing` and `class_skill_visit` gates plus DVC lock gap.
- `foundation` commits `6bf8300752`, `8fbee85646`: partially integrated manually; fake offline gear/enchant catalog intentionally not merged.
- `world-planner`, `combat-loot`, `group-validation`, and `ml-data`: pending review/integration.
