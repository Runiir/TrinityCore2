# Phase 04 Progress

## Current milestone

Milestone 11 complete for the local/headless V1 path. Live DB-backed quest smoke remains an optional stronger validation path, not a hard blocker for the current serverless smoke.

## Completed

- Milestone 1: active quest state is exposed through `playerbot quest objective|status <quest_id>`.
- Milestone 2: quest objective progress is extracted for kill/gameobject and item collection objectives.
- Milestone 3: NPC-style quest accept/turn-in hooks exist through `playerbot quest accept <quest_id>` and `playerbot quest turn_in <quest_id>`.
- Milestone 4: V1 gameobject/static interaction credit hook exists through `playerbot quest interact <quest_id> [entry]`.
- Milestone 5: V1 use-item/collection progress hook exists through `playerbot quest use_item <quest_id> [item_id]`.
- Milestone 6: deterministic simple quest planner path added to the headless experiment runner: accept, travel, kill/interact/use, return, turn in.
- Milestone 7: quest JSONL frames are recorded with `domain=quest`, `subdomain=quest_objective`, task/state/policy/action/outcome fields matching the Phase 04 schema.
- Milestone 8: quest metadata/vocab and objective schema files added.
- Milestone 9: simple kill quest smoke config added and verified.
- Milestone 10: collect/interact quest smoke config added for local/headless use.
- Milestone 11: quest metrics generated and recomputed by tests.

## Changed files

- `src/server/scripts/Commands/cs_healerbot.cpp`
- `experiments/run_experiment.py`
- `experiments/configs/headless_simple_kill_quest_smoke_001.json`
- `experiments/configs/headless_collect_interact_quest_smoke_001.json`
- `tests/test_ml_pipeline.py`
- `ml/vocab/quest_vocab.json`
- `ml/schemas/quest_objective.schema.json`
- `params.yaml`
- `dvclive/params.yaml`
- `dvc.yaml`
- `dvc.lock`

## Verification log

- `pixi run pytest tests/test_ml_pipeline.py` passed: 4 tests.
- `cmake --build build --target worldserver -j2` passed.
- `pixi run python experiments/run_experiment.py experiments/configs/headless_simple_kill_quest_smoke_001.json --local` passed:
  - generated `dataset/raw/run_000010/frames.jsonl`
  - generated `experiments/runs/run_000010/quest_metrics.json`
  - `quest_completion_success=true`
  - `quest_frame_count=17`
  - `deaths_per_quest=0`
  - `invalid_action_rate=0.0`
- `pixi run dvc repro capture` passed with the quest smoke and generated DVC-tracked `run_000011`.
- `pixi run dvc repro` passed for capture/preprocess/train/evaluate.
- `pixi run dvc push` pushed updated artifacts.
- `pixi run dvc status` reports: `Data and pipelines are up to date.`

## Blockers / assumptions

- The C++ quest command path uses existing player quest APIs and applies quest accept/reward/progress checks to the command owner/headless owner selected by `owner <name|guid>`. This is compatible with RA/SOAP and avoids adding a new HTTP service.
- The server command surface provides V1 interaction hooks, but the verified quest completion smoke is local/headless. A live DB-backed in-world quest run requires a prepared owner/bot, questgiver/objective spawns, and suitable quest data in the configured world DB.
- `playerbot quest interact` uses kill-credit style progress for static interaction V1 cases; scripted, phased, escort, vehicle, and timed quests remain out of Phase 04 scope.

## Next step

For stronger validation, prepare a real simple quest in the world DB and run the same `headless_simple_kill_quest_smoke_001` flow through RA/SOAP instead of the local adapter.
