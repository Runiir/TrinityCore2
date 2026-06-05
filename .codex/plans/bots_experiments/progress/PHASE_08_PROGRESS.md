# Phase 08 Progress

## Current milestone

Phase 08 implementation complete pending user review.

## Completed

- Milestone 1: Added raid module domain schema at `ml/schemas/raid_module.schema.json`.
- Milestone 2: Extended mechanic family metadata with raid families: `tank_swap`, `raid_wide_aoe`, `assigned_soak`, `interrupt_rotation`, `dispel_rotation`, `healer_cooldown_assignment`, `add_wave`, `boss_immunity`, `phase_transition`, and `enrage_timer`.
- Milestone 3: Added assignment scheduler skeleton in `ml/raid/scheduler.py` for tank swaps, interrupt rotations, healer cooldowns, soaks, subgroup movement, and add target switching.
- Milestone 4: Implemented deterministic headless tank swap raid module frames.
- Milestone 5: Implemented deterministic headless raid-wide AoE cooldown module frames.
- Milestone 6: Implemented deterministic headless interrupt rotation module frames.
- Milestone 7: Implemented deterministic headless stack/spread movement module frames.
- Milestone 8: Implemented deterministic headless add-wave target-switch module frames.
- Milestone 9: Added raid metrics in `ml/raid/metrics.py`.
- Milestone 10: Added headless local smoke configs for all required raid modules.

## Changed files

- `dataset/metadata/mechanic_families.json`
- `experiments/configs/raid_add_wave_target_switch.json`
- `experiments/configs/raid_aoe_cooldown_rotation.json`
- `experiments/configs/raid_interrupt_rotation.json`
- `experiments/configs/raid_stack_spread_basic.json`
- `experiments/configs/raid_tank_swap_basic.json`
- `experiments/run_experiment.py`
- `ml/raid/__init__.py`
- `ml/raid/frames.py`
- `ml/raid/metrics.py`
- `ml/raid/scheduler.py`
- `ml/schemas/raid_module.schema.json`
- `tests/test_ml_pipeline.py`

## Verification log

- `pixi run pytest tests/test_ml_pipeline.py` passed: 13 tests.
- `python -m json.tool dataset/metadata/mechanic_families.json >/dev/null && python -m json.tool ml/schemas/raid_module.schema.json >/dev/null` passed.
- `pixi run dvc status` completed and reported `experiments/run_experiment.py` as a changed dependency for the `capture` stage. No generated dataset artifacts were created in the repo by the smoke tests; pytest used temporary run/raw directories.

## Blockers / assumptions

- No hard blockers.
- Raid modules are deterministic local/headless smoke modules. They do not alter real player/server behavior and are intended to provide schema, scheduler, frame, and metric surfaces before full raid boss automation.

## Next step

Review and commit the Phase 08 code/config changes. If repo-tracked experiment artifacts are generated later, run `pixi run dvc status` and `pixi run dvc push` to sync the DVC remote.
