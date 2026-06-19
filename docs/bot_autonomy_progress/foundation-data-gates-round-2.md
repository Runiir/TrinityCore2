# Foundation Data Gates Round 2

Current date: 2026-06-19

## Latest Commit

- Commit: `e5fb60d111` (`Fail on empty DB-backed planner artifacts`).
- Lane: `audit-data-gates`
- Branch: `bot-autonomy/lane-audit-data-gates-round-2`, fast-forwarded into `master`.

## Changed Files

- `tools/bot_ml/extract_world_knowledge.py`
- `tools/bot_ml/build_world_planner_manifests.py`
- `tools/bot_ml/validate_world_planner.py`
- `tests/test_ml_pipeline.py`
- `dvc.lock`

## Claimed Behavior

- World knowledge extraction fails hard when the configured DB cannot be read unless `--allow-offline-reuse` is explicitly supplied.
- Offline reuse requires a complete existing manifest set and nonempty required DB-backed manifests.
- Planner manifest generation rejects empty required world inputs and empty required planner outputs.
- Planner validation writes an `input_contract` with required DB-backed manifest status and exits nonzero when required planner inputs are empty.
- The DVC graph now checkpoints regenerated nonempty DB-backed world/planner artifacts instead of the stale empty fallback outputs.

## Data Evidence

- `dataset/world_knowledge/manifest.json`: `extraction_status.mode=database`, `ok=true`.
- Required world manifests have no empty required files; notable counts include `quests=14991`, `quest_objectives=14627`, `npc_services=3570`, `item_sources=593661`, `travel=1472`, and `zones=262`.
- `dataset/world_planner/manifest.json`: `quest_hubs=3507`, `quest_chains=9307`, `objective_clusters=2550`, `service_index=3570`, `item_source_index=24240`, `material_source_index=24240`, and `travel_edges=1472`.
- `dataset/world_validation/planner_report.json`: `input_contract.ok=true`, `empty_required_db_backed_planner_manifests=[]`, `passed=20`, `failed=2`, `total=22`.
- `dataset/quest_profession_reports/report.json`: `all_passed=true`, `passed=15`, `failed=0`.

## Verification

- `pixi run pytest tests/test_ml_pipeline.py -q`: passed, 96 passed, 1 existing `pynvml` deprecation warning.
- `pixi run pytest -q`: passed, 110 passed, 1 existing `pynvml` deprecation warning.
- `cmake --build build --target worldserver -j"$(nproc)"`: passed.
- `pixi run dvc repro world_planner_validate`: passed and updated `dvc.lock`.
- `pixi run dvc repro quest_profession_report`: passed and updated `dvc.lock`.
- `pixi run dvc status`: data and pipelines are up to date.
- `pixi run dvc push`: pushed 32 files.
- `pixi run dvc status -c`: cache and remote `object` are in sync.

## Reviewer Acceptance

- Reviewer accepted amended commit `e5fb60d111c79188c107099ef729ae809c7324d8`.
- Reviewer independently verified clean git status, clean DVC status, remote cache sync, nonempty required row counts, `input_contract.ok=true`, quest/profession report pass status, and the full `tests/test_ml_pipeline.py` suite.

## Remaining Gates

- Natural uninterrupted Stonecore 5N and Blackwing Descent 10N full-clear evidence remains absent; existing strong route/segment evidence is not accepted as final full-clear proof.
