# Autonomy Data Engine v2

## Phase 1: runtime truth repair

Status: implementation complete; live Stonecore gate not yet passed.

Changed:

- Trash liveness is independent from target selectability, evade state, and path availability.
- Trash nodes require observed engagement and verified cluster clearance; `expected_alive_count` is descriptive only.
- Boss nodes require a naturally dead target. Validation force damage, forced death, and teacher completion were removed.
- Route terminals and boss kills are scoped by exact node and generation in runtime traces and report aggregation.
- Stuck recovery requires progress after the latest stuck or target-loss event.
- Full-clear and segment reports reject unscoped counters, stale nodes, forced assistance, missing terminals, and missing per-boss kills.
- Pytest ignores `generated/orchestrator_worktrees`.

Worker routing:

- C++ runtime truth: large/high-risk.
- Python evidence/report truth: large/high-risk.
- Manifest and pytest discovery: medium.
- Strict fixture migration and independent evidence review: medium and large/high-risk.
- The collaboration API did not expose per-worker model selection; workers used the platform-provided Codex model.

Verification:

- `pixi run pytest -q`: 239 passed.
- Fresh `cmake --build build --target worldserver -- -j2`: passed from Phase 1 commit `c80c6e26cd`.
- DVC remote credentials match the main worktree; `pixi run dvc status` was recorded and reports pre-existing missing-cache drift plus the changed validation stages.
- No experiment or live-run artifacts were produced, so no DVC checkpoint or push was required.

Next handoff:

Run the generated uninterrupted Stonecore manifest from the exact Phase 1 `HEAD` with `--observe-sec 300 --timeout-sec 900`. Accept no prior Stonecore evidence. Inspect `.botauto diagnose all` and `.botauto trace all 64`. Continue repairing deterministic teacher behavior until 10 consecutive clears show five bots in the original instance, four exact node/generation-scoped real boss kills, a terminal for every route node, zero forced/teacher completion, zero false terminals, and zero unresolved stuck states. Do not start Phase 2 until that gate passes.
