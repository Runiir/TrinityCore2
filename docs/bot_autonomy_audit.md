# Bot Autonomy Audit

Current date: 2026-06-19

## Implemented

- `BotWorldPopulationMgr` owns always-on/manual bot population, spawn/resume placement, safe-position memory, visible POI memory, danger zones, failed path memory, death recovery, quest hub sweeping, simple quest objective execution, objective bucket selection, combat decisions, replay records, policy model shadow/assist scoring, telemetry clips, and `.botauto debug/diagnose/trace`.
- `BotLongTermProgressionBrain` scores broad activities and simple gear upgrades from item level, role-ish stat weights, gold, level, and cooking skill.
- `BotClassSpecActionProfileStore` builds static Cataclysm-like fallback spell profiles per class, candidate masks, chosen-action JSON, and profile embeddings.
- `BotRoleSaturationPolicy` evaluates healer/tank/DPS balance mode from group health, mana, threat, encounter pressure, and learned outcome stats.
- `BotEncounterMechanicCatalog` classifies generic mechanic families such as interrupts, tank busters, ground danger, adds, raid AoE, and wipe risk.
- Telemetry and replay capture write canonical `BotDatasetEvent` JSON into `experiment_bot_*` tables, clips, clip frames, replay records, and semantic outcome stats.
- `tools/bot_ml` can export tables, build candidate-level decision datasets, validate quality, train/evaluate/register portable policy models, compare replays, and log with DVCLive.
- DVC/DVCLive are configured through `pixi`, `dvc.yaml`, `params.yaml`, and `tools/bot_ml/README.md`.
- Headless smoke configs exist for movement, combat, simple quests, cooking, autonomous loop, 5-man trash, dungeon segment labels, and several raid mechanic modules.
- Lane config generation is implemented through `pixi run bot-lane-configs`, with isolated world/instance/SOAP/RA ports following the lane `+100` formula. Lane 0 uses `18085/18086/13443/17878` and output root `generated/bot_autonomy_lanes/foundation`.

## Scaffold Or Partial

- Quest autonomy supports nearby quest givers, accepting multiple hub quests, simple kill/collect/gameobject/spell objectives, turn-ins, basic chain detection, POI/objective routing, and geographic objective buckets. It is not yet a full world router.
- Dungeon and raid logic exposes role assignment, mechanic telemetry, route labels, generic mechanic responses, and long-window segmented boss-route validation for Stonecore and Blackwing Descent. Full uninterrupted entrance-to-final-boss clears are still not proven end to end.
- Profession logic is mostly policy/telemetry and cooking smoke coverage. Full profession recipe/material/trainer/vendor/drop/discovery/daily-cooldown planning is missing.
- Combat action profiles are in C++ static tables, not external manifests/embeddings loaded from data. They cover core action categories but not complete 4.3.4 rotations, glyphs, gems, enchants, consumables, BiS manifests, or class/spec-specific encounter responses.
- Smart loot has gear upgrade scoring and telemetry concepts, but group roll integration and full class/spec gear profiles are incomplete.
- Persistent memory covers POIs, failed paths, danger zones, safe positions, objective clusters, recipe sources, material sources, daily cooldowns, transport usage, and repeated decision fingerprints as first-class tables. Runtime producers exist for POIs, paths, danger, safe positions, objective-cluster outcomes, visible vendor/trainer recipe-source discovery, visible objective-object material-source discovery, and decision fingerprints; cooldown/transport producers are still partial.
- Diagnostics report current action, diagnosis code, decision snapshot, trace entries, active quest cluster, cooldown counts, and decision fingerprint repeat/failure counters. Recovery attempts and validation status still need to be expanded into a stable machine-readable schema.
- Mechanic metadata files exist as scaffold JSON for families, spell mechanics, role responses, boss timelines, and embedding vocabulary. Only mechanic families are currently populated.

## Missing Foundation

- Current worktree DVC/cache state is incomplete for world knowledge, planner manifests, validation gear/provisioning artifacts, validation scenarios, live-validation reports, and model training outputs. The code paths exist, but the generated artifacts are missing locally until DVC cache or source DB/DBC inputs are restored.
- Hierarchical planning from long-term goals to zone/instance routes, objective clusters, and execution actions.
- Loop guardrails for repeated quest choices, target churn, idle loops, dungeon/raid/profession loops, and repeated failed recovery decisions. Decision fingerprints are now persisted for loop analysis, but recovery policy still needs to consume them consistently.
- Automatic recovery policy that blacklists objectives/paths temporarily, switches clusters, returns to safe points, repairs/restocks/trains, regroups, resets instances, or fails validation with a reason.
- Live-server verification that generated validation gear enchant IDs, gem payloads, and prepared characters load cleanly remains missing in this worktree.
- End-to-end validation scripts for full Stonecore and Blackwing Descent with pass/fail reports and DVC-managed artifacts.

## New In This Audit Pass

- Added `tools.bot_ml.extract_world_knowledge` and the `pixi run bot-world-knowledge` task.
- The extractor emits `dataset/world_knowledge/{quests,quest_objectives,npc_services,item_sources,travel,zones}.jsonl` plus `manifest.json`.
- Added `tools.bot_ml.build_world_planner_manifests` and the `pixi run bot-world-planner` task.
- The planner builder emits `dataset/world_planner/{quest_hubs,quest_chains,objective_clusters,service_index,item_source_index,travel_edges}.jsonl` plus `manifest.json`.
- Added `tools.bot_ml.validate_world_planner` and the `pixi run bot-world-validate` task.
- The validator emits `dataset/world_validation/planner_report.json` with pass/fail evidence for staged gates from movement smoke through full Blackwing Descent.
- Added DVC stages `world_knowledge`, `world_planner`, and `world_planner_validate`; the validation report is now emitted as `dataset/world_validation/planner_report.json`.
- The local configured world DB extraction produced 3,507 quest hubs, 9,307 quest-chain rows, 2,550 objective clusters, 3,473 service-index rows, 24,240 item-source-index rows, and 1,472 travel edges.
- The world planner validation report currently passes 12/15 staged gates and keeps `full_stonecore_clear`, `raid_boss`, and `full_blackwing_descent_clear` failing until route/mechanic manifests, prepared gear, and live reports exist.
- Added `tools.bot_ml.run_live_bot_validation`, `pixi run bot-live-validate`, and `make bot-live-validate`.
- The live harness pipes `.botauto status`, `.botauto diagnose all`, `.botauto trace all 20`, `.botexp summary`, and `server exit` into `worldserver`, then writes `dataset/live_validation/report.json`.
- Added `tools.bot_ml.build_validation_provisioning`, `pixi run bot-validation-provisioning`, DVC stage `validation_provisioning`, and `experiments/configs/validation_provisioning_cata_001.json`.
- The validation provisioning generator writes `account_commands.txt`, `provision_accounts.sql`, `provision_characters.sql`, `manifest.json`, and `report.json` for a Stonecore 5-player roster and Blackwing Descent 10-player roster. It provisions max-level characters, role coverage, skills, glyphs, consumables, bot-pool entries, instance start positions, and generated equipment payloads. `provision_accounts.sql` creates only missing validation accounts with deterministic Trinity SRP6 credentials and does not overwrite existing account passwords.
- Added `tools.bot_ml.validate_validation_provisioning`, `pixi run bot-validation-provisioning-verify`, and DVC stage `validation_provisioning_verify`. The verifier checks generated enchant/gem payloads against DBC data and can run a DB preflight for auth/characters schema compatibility plus missing validation accounts.
- Added `tools.bot_ml.build_validation_gear_profiles`, `pixi run bot-validation-gear`, and DVC stage `validation_gear`.
- The gear profile builder reads Cataclysm `Item.db2`/`Item-sparse.db2`, `SpellItemEnchantment.dbc`, and `GemProperties.dbc` client data plus hotfix overrides from `HotfixDatabaseInfo`, applies class/spec role stat weights, writes `dataset/validation_gear_profiles/{profiles,report,manifest}.json`, and feeds generated equipment into validation provisioning.
- Gear profile loading now preserves local DB2/DBC item rows when the optional hotfix MySQL database is unavailable. It does not fabricate item, enchant, or gem IDs; real DB2/DBC-backed artifact generation is still required for full validation evidence.
- Live validation dry-run config generation now falls back to repo config templates when `trinity-worldserver-test.conf` is absent from the worktree.
- Validation-route no-progress recovery now exposes `validation_route_teacher_assist` telemetry and bounded teacher damage for blocked route prerequisites, plus explicit authoritative-focus assist labels for boss-route smoke diagnostics.
- DB2/DBC-backed gear now completes all required equipment slots for the 13 validation class/spec profiles. `dataset/validation_gear_profiles/report.json` reports `all_equipment_slots_complete=true`, `all_gemmed=true`, `all_enchanted=true`, `complete_equipment_profiles=13`, 208 selected client DB2 items, and 208 encoded permanent enchants. Socket gems are selected through `GemProperties.dbc` socket-color masks and encoded into the socket enchantment fields. The provisioning report now shows `all_ready=true` for both Stonecore and Blackwing Descent prepared rosters. Enchant applicability is still explicitly marked `enchant_applicability_verified_by_server=false` until a live worldserver load validates the generated enchant IDs on equipped items.
- Added `bot_memory_objective_clusters`, `bot_memory_recipe_sources`, `bot_memory_material_sources`, `bot_memory_daily_cooldowns`, `bot_memory_transport_usage`, and `bot_memory_decision_fingerprints`.
- `RecordDecision` now writes repeated decision fingerprints so loop/stuck behavior can be labeled and filtered before ML training.
- `RecordQuestEvent` now writes objective-cluster outcome memory before experiment-run filtering so always-on autonomy can remember completed, failed, and temporarily blacklisted quest clusters.
- Visible POI scans now also populate vendor/trainer recipe-source memory and objective-object material-source memory for later reconciliation with extracted manifests.
- `.botauto diagnose`/debug snapshots now expose active quest cluster, cooldown counts, and decision fingerprint repeat/failure counters.
- The manifest contracts are deliberately data-driven so C++/Python planners can consume extracted world state instead of hardcoded behavior.

## Validation Status

- `pixi run pytest tests/test_autonomy_pipeline_smoke.py tests/test_ml_pipeline.py`: 94 passed, 1 warning.
- `pixi run bot-lane-configs --lane 0 --dry-run`: passed; generated manifest reports world `18085`, instance `18086`, RA `13443`, SOAP `17878`, output root `generated/bot_autonomy_lanes/foundation`.
- `cmake --build build --target worldserver -j2`: passed.
- `pixi run dvc repro world_planner_validate`: passed and updated `dvc.lock`.
- `pixi run dvc repro validation_gear`: passed via `pixi run dvc repro validation_provisioning` and updated `dvc.lock`.
- `pixi run dvc repro validation_provisioning`: passed and updated `dvc.lock`.
- `pixi run dvc repro validation_provisioning_verify`: passed and updated `dvc.lock`; payload verification reports 1,829 usable enchantments, 903 gem properties, and 827 gem catalog entries.
- Applied generated `dataset/validation_provisioning/provision_accounts.sql` and `provision_characters.sql` to the configured local auth/characters DB. `pixi run bot-validation-provisioning-verify --check-db --require-applied` now passes with 15/15 validation accounts and 15/15 validation characters present.
- A first SOAP live-validation attempt against the already-running worldserver proved SOAP access and parsed `.botauto status`, but showed that process was stale and lacked `.botauto diagnose`/`.botauto trace`.
- Stopped the stale worldserver through SOAP, reran live validation against the current binary, then added stricter live gate evidence so spawn-only traces and idle diagnoses no longer pass smoke gates.
- Ran an observed SOAP validation window with `--observe-sec 45` and checkpointed the parsed report with DVC at `artifacts/live_validation.dvc`. This short window is a smoke diagnostic only; boss-route validation must use the generated run-plan budget or equivalent `--observe-sec 300 --timeout-sec 900`.
- The current observed live report shows 5 active autonomy bots, 5 machine-readable diagnoses, 7 trace entries, non-spawn actions `vendor_repair_train`, `travel_to_quest_hub`, and `use_quest_object`, plus no live command errors. The stricter staged report passes 3/15 gates (`movement_smoke`, `trainer_visit`, `vendor_repair`). It still fails kill, quest progress, quest hub batching, profession recipe, material farming, smart loot, Stonecore, and Blackwing Descent gates because those outcomes are not yet proven by live telemetry.
- `pixi run dvc status`: reports broad missing-cache/missing-output drift for world knowledge, planner, validation gear/provisioning, validation scenarios, live-validation reports, capture/preprocess/train/evaluate, and artifact `.dvc` outputs. Tool dependency changes in this lane also mark validation gear/provisioning verification and live-scenario report stages stale.
- `pixi run dvc push`: attempted after artifact generation, but failed because the configured endpoint `http://192.168.111.161:9000/artifacts/trinity-cata` was unreachable.
- Long-window segmented boss-route validation now has DVC-managed strong teacher evidence for all Stonecore and Blackwing Descent boss segments, and the built scenario reports pass both scenario-level boss/full-clear gates. This proves scripted boss-route coverage, not yet a natural uninterrupted clear from entrance to completion.
- The live validation harness is available and now produces partial live autonomy reports plus prepared dungeon/raid boss-route reports, but broader questing, profession, loot, and natural full-clear autonomy still need stronger live evidence.

## Next Implementation Order

1. Run `pixi run bot-world-knowledge`, `pixi run bot-world-planner`, and `pixi run bot-world-validate` against the local world DB and checkpoint `dataset/world_knowledge` plus `dataset/world_planner` with DVC.
2. Run `make bot-live-validate` and checkpoint `dataset/live_validation` with DVC once the report is meaningful.
3. Add C++/runtime planner consumers for the manifests: quest hub graph, objective cluster graph, trainer/vendor/repair lookup, travel graph, and item/material source lookup.
4. Add runtime producers/consumers for objective-cluster completion, recipe/material/farming/transport/cooldown memory.
5. Expand `.botauto diagnose` and `.botauto trace` to include hierarchical planner state, loop counters, recovery attempts, and validation state.
6. Externalize class/spec action, gear, loot, profession, dungeon route, and raid mechanic profiles into versioned manifests.
7. Add staged live validation reports for the required smoke, dungeon, and raid gates.
