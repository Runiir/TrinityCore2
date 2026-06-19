# Combat-Loot Lane Progress

## 2026-06-19

- Added checked-in Cataclysm 4.3.4 action/proficiency spell manifest at `experiments/configs/cata_434_action_profiles.json`.
- Added checked-in combat-loot profile manifest at `experiments/configs/cata_434_combat_loot_profiles.json` covering class/spec archetypes, stat weights, consumable metadata, smart-loot validation surfaces, and BiS/source reporting scaffolds.
- Added `tools.bot_ml.validation_profile_manifests` loader helpers with stable manifest hashes.
- Wired validation provisioning to load action/proficiency spells from the action profile manifest and record the manifest identity in generated reports/manifests.
- Wired validation gear profile generation to load stat weights and class/spec archetypes from the combat-loot manifest, annotate selected equipment with manifest hashes, and emit profile-level stat weights, average item levels, source counts, and BiS/source reports.
- Improved smart-loot validation reporting with selected equipment counts, source counts, stat-weight manifest hashes, and readiness evidence.
- Made hotfix item fetch fallback to local DB2 items when the hotfix database is unavailable and local DB2 data exists.
- Updated DVC stage deps and `tools/bot_ml/README.md` for the new manifests.

Validation run:

- `pixi run pytest tests/test_ml_pipeline.py -k 'validation_gear_profiles_can_complete_slots_from_item_rows or validation_provisioning_generates_reproducible_sql_and_readiness or cata_action_profile or combat_loot_profile or validation_provisioning_applies_gear_profiles'` passed: 5 passed.
- `pixi run pytest tests/test_ml_pipeline.py -k 'validation_gear_profiles or validation_provisioning or cata_action_profile or combat_loot_profile'` partially blocked: local DB2 files and generated validation datasets are absent in this sparse lane; tests requiring `data/dbc/enUS` and `dataset/validation_gear_profiles` failed.
- `pixi run pytest tests/test_autonomy_pipeline_smoke.py::test_quest_first_portfolio_routing_surface` failed on pre-existing C++ contract expectation `teacherAssistAuthoritativeFocus` absent from `BotWorldPopulationMgr.cpp`; no C++ files were changed in this lane.
- `pixi run bot-validation-gear --config experiments/configs/validation_provisioning_cata_001.json --output-dir dataset/validation_gear_profiles` blocked because `trinity-worldserver-test.conf` and `data/dbc/enUS` are not present.
- `pixi run dvc status` completed and reports many missing cached outs/deps in this worktree, including `data/dbc/enUS/*`, `dataset/validation_gear_profiles`, and `dataset/validation_provisioning`.

Next unblockers:

- Materialize DVC inputs/outputs for `data/dbc/enUS`, `dataset/validation_gear_profiles`, and `dataset/validation_provisioning`, or provide a local `trinity-worldserver-test.conf` plus DB2 files.
- Re-run `pixi run bot-validation-gear`, `pixi run bot-validation-provisioning`, `pixi run bot-validation-provisioning-verify`, and the full profile/loot pytest selection after the DVC cache is present.
