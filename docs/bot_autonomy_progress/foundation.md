# Foundation Lane Progress

Current date: 2026-06-19

## Latest Commit

- Commit: `6bf8300752` (`foundation: harden autonomy validation smoke fallbacks`).
- Lane: `foundation`
- Branch: `bot-autonomy/lane-foundation`

## Changed Files

- `src/server/game/Bots/BotWorldPopulationMgr.cpp`
- `tools/bot_ml/build_validation_gear_profiles.py`
- `tools/bot_ml/validate_validation_provisioning.py`
- `tools/bot_ml/run_live_bot_validation.py`
- `tools/bot_ml/generate_lane_configs.py`
- `pixi.toml`
- `dataset/metadata/{spell_mechanics,role_responses,boss_timelines,embedding_vocab}.json`
- `docs/bot_autonomy_audit.md`
- `docs/bot_autonomy_progress/foundation.md`

## Tests

- `pixi run pytest tests/test_autonomy_pipeline_smoke.py tests/test_ml_pipeline.py`: passed, 94 passed, 1 warning from `dvclive`/`pynvml`.
- `pixi run bot-lane-configs --lane 0 --dry-run`: passed. Lane 0 port allocation is world `18085`, instance `18086`, RA `13443`, SOAP `17878`; output root is `generated/bot_autonomy_lanes/foundation`.
- `pixi run dvc status`: completed with existing missing-cache/missing-output drift across world knowledge, validation, live-validation, capture/preprocess/train/evaluate, and artifact `.dvc` outputs. New code changes also mark `validation_gear`, `validation_provisioning_verify`, `live_scenario_reports`, and `live_validation_combined` stale because their tool dependencies changed.

## Diagnostic Summary

- Added the missing validation-route teacher-assist smoke surface around authoritative focus recovery and no-progress teacher assist.
- Gear profile generation now prefers DB2/DBC plus hotfix rows and keeps local DB2 item evidence usable when the optional hotfix MySQL database is unreachable.
- Provisioning verification can rebuild missing gear profiles in memory from the same fallback path, allowing payload smoke checks to pass without local DVC artifacts.
- Live validation dry-run config writing resolves missing relative base configs against repo templates.
- Lane config generation for lane 0 is available through `pixi run bot-lane-configs`.

## Blockers

- DVC outputs and cache entries for world knowledge, generated validation gear/provisioning, validation scenarios, live validation reports, and training artifacts are not present in this worktree.
- `data/dbc/enUS` is absent, so full DB2/DBC-backed artifact regeneration cannot be proven here; smoke tests exercise the offline fallback path.
- No `dvc push` was run because no generated DVC artifacts were produced in this lane pass.

## Downstream Triggers

- Integrator can consume the explicit `validation_route_teacher_assist` and authoritative-focus smoke surfaces.
- Validation/data lanes can rerun `pixi run dvc repro validation_gear validation_provisioning validation_provisioning_verify` when DB2/DBC and DVC cache are available.
- Runtime lanes can use `pixi run bot-lane-configs --lane 0` to materialize isolated lane 0 configs under `generated/bot_autonomy_lanes/foundation`.
