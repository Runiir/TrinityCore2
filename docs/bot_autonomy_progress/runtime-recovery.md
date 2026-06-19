# Runtime Recovery Progress

## 2026-06-19

- Added runtime loop guardrail state for repeated decision fingerprints, idle/wander repetition, and target churn in `BotWorldPopulationMgr`.
- Added conservative runtime recovery action: clear current target/quest target, stop combat, repath to a nearby collision position, emit `loop_guardrail_triggered`, and rate-limit recovery with a cooldown.
- Extended persistent decision fingerprint metadata and decision replay failure snapshots with loop counters, guardrail action/reason, and last recovery mode/result.
- Extended `.botauto diagnose` and `.botauto trace` machine-readable output with loop/recovery counters while preserving `.botauto debug`'s existing `diagnosis` object.
- Added diagnosis codes for `repeated_decision_loop`, `idle_loop_guardrail`, and `target_churn_loop`.
- Verification:
  - `pixi run pytest tests/test_autonomy_pipeline_smoke.py::test_botauto_diagnosis_and_trace_surface tests/test_autonomy_pipeline_smoke.py::test_recovery_smoke_records_death_recovery_without_center_fallback_unless_enabled tests/test_autonomy_pipeline_smoke.py::test_extended_bot_memory_schema_and_decision_fingerprint_surface -q` passed.
  - Full `pixi run pytest tests/test_autonomy_pipeline_smoke.py -q` has an unrelated existing failure: `test_quest_first_portfolio_routing_surface` expects `teacherAssistAuthoritativeFocus`, which is absent in this lane.
  - `cmake --build build --target worldserver -j2` could not run because `build/` does not exist in this worktree.
  - Scripted worldserver diagnose/trace smoke could not run because the `worldserver` binary under `build/src/server/worldserver/` is unavailable without a build tree.
  - `pixi run dvc status` completed; it reports many existing missing/not-in-cache datasets and artifacts, with no new generated DVC artifacts from this change.
