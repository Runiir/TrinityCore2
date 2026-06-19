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
- Integration tightened the manifest loader defaults so action/combat profile manifests resolve from the repo root even when commands run from another working directory.
- `pixi run dvc repro validation_provisioning_verify` completed through `validation_gear`, `validation_provisioning`, and `validation_provisioning_verify`; the generated verifier report has `all_passed=true`, `provisioning_all_ready=true`, 1829 enchantments, 827 gems, and 903 gem properties.
- `pixi run dvc repro validation_scenarios` completed after regenerated provisioning reports.
- `pixi run dvc status` completed. Only `live_validation_combined` remains stale from the integration-owned `tools/bot_ml/run_live_bot_validation.py` dependency drift.

Next unblockers:

- Run the full integration pytest and C++ build after remaining lane merges.
