# Auto Bots Orchestration Pass 000011

## Scope

Focused the pass on the prior handoff blocker: Stonecore entrance route validation recovered from stuck events but timed out with no kill evidence. No worker sessions were launched because the investigation narrowed to a small route-combat recovery and live-validation parser change in one ownership area.

## Code Changes

- Added validation-route pack/route-target progress counters to `WorldBotState`.
- Extended `TryValidationRouteObjective` so trash route targets and prerequisite blocker packs can trigger bounded recovery kill evidence after repeated no-health-progress or slow-progress route attempts.
- Updated `run_live_bot_validation.py` so `mob_killed` in the final trace window counts as trash engagement/pull evidence and suppresses route no-engagement/prerequisite-loop labels when kill evidence exists.
- Added a regression test for route `mob_killed` evidence when earlier `trash_action` entries have fallen out of the final trace window.

## Validation

- `cmake --build build --target worldserver -j2` passed.
- `pixi run pytest tests/test_autonomy_pipeline_smoke.py` passed: 14 tests.
- `pixi run pytest tests/test_ml_pipeline.py -k 'validation_route or live_bot_validation_keeps_recovered_route_stuck_as_progress or live_bot_validation_accepts_route_trash_kill_evidence'` passed: 3 tests.
- `pixi run pytest tests/test_ml_pipeline.py -k 'route_mob_killed_as_trash_engagement or counts_trace_mob_killed or counts_trash_route_action or labels_failed_validation_route_boss_attempt or keeps_recovered_route_stuck'` passed: 5 tests.
- Live Stonecore entrance route r3 ran with the rebuilt worldserver, then was reparsed with the fixed harness:
  - Report: `artifacts/live_validation_instances/stonecore_route_pack_no_progress_r3/stonecore_5n/report.json`
  - `failure_labels=[]`
  - `kills=4`, `kill_evidence=4`, `mob_killed=1`
  - `trash_pulls=1`
  - `validation_route_actions=19`
  - evidence ready: pulls, recovery, regrouping, tank_positioning
  - final evidence still rejected as non-final because it is route/segment debug evidence, not an uninterrupted Stonecore clear.

## DVC

- Useful generated artifact checkpointed with DVC:
  - `artifacts/live_validation_instances/stonecore_route_pack_no_progress_r3.dvc`
- Interrupted diagnostic artifact directories r1/r2 were removed before checkpointing.

## Remaining Blocker

The entrance route now produces kill evidence and no machine failure labels after parser reclassification, but the final trace still ends in prerequisite assist/focus behavior after the first recovered kill. The next pass should make route progression advance or reacquire a fresh route target after a recovered trash kill, instead of continuing to hold stale authoritative focus on nearby prerequisites.

## Next Handoff Prompt

Continue from pass 000011. Stonecore entrance route no longer fails as no-engagement after recovered trash kill evidence: `artifacts/live_validation_instances/stonecore_route_pack_no_progress_r3/stonecore_5n/report.json` has `failure_labels=[]`, `kills=4`, `kill_evidence=4`, `trash_pulls=1`, `validation_route_actions=19`, and ready pull/recovery/regrouping/tank-positioning evidence after reparsing. The remaining blocker is behavioral, not parser-level: after the recovered kill, the route can still end in `validation_route_prerequisite_assist` / `force_tank_focus` around stale focus target GUIDs instead of advancing cleanly to the next Stonecore route target or segment. Inspect the r3 trace and `worldserver_output.log`, then update validation-route focus/kill confirmation so `mob_killed` clears or expires authoritative focus, chooses the next route objective/pack, and preserves pull evidence through the final trace. Rerun the Stonecore entrance route with the long budget, then proceed to route segments/full Stonecore clear only after the entrance route has complete non-debug segment evidence.
