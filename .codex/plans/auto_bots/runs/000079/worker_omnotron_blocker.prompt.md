You are a worker Codex session for TrinityCore bot autonomy run 000079.

Goal: debug and fix the Blackwing Descent full-clear blocker at the `03_omnotron_defense_system` validation segment without weakening safety criteria.

Context:
- Repo: `/home/runiir/Games/trinity-cata`
- Starting commit for this run: `8d2b095e1c`
- Orchestrator validation artifact:
  - `artifacts/live_validation_instances/blackwing_descent_uninterrupted_full_clear_r4/report.json`
  - `artifacts/live_validation_instances/blackwing_descent_uninterrupted_full_clear_r4/03_omnotron_defense_system/report.json`
- `r4` segment outcomes:
  - `01_entry_trash`: `route_segment_complete`, 2 kills, 17 trash pulls, 79 route actions, no failure labels.
  - `02_magmaw`: `route_segment_complete`, 4 boss kill evidence, 71 route actions, no failure labels.
  - `03_omnotron_defense_system`: failed route sequence with `validation_route_death_loop`.
- Omnotron evidence:
  - 10 active bots.
  - 15 boss kill evidence, 6 kills, 135 validation route actions.
  - 14 deaths and 14 resurrection/recovery events.
  - 0 interrupts even though the route requires `interrupts`.
  - result counts include repeated `target_seen_dead`, `target_seen_not_attackable`, `boss_route_script_target_blocked_teacher_assist`, `validation_route_wrong_map`, and `search_after_activation_no_focus`.

Constraints:
- Use pixi for Python tasks.
- Do not enable runtime ML control.
- Do not just relax `validation_route_death_loop` or route completion to accept unsafe evidence.
- Prefer data-driven route/mechanic/config fixes or generic planner/executor fixes over encounter-specific branches.
- If you change code/config, add focused tests and run relevant validation where feasible.
- Do not commit; leave changes for orchestrator review.

Suggested investigation:
1. Inspect `tools/bot_ml/run_live_bot_validation.py` route-sequence and failure-label logic around `route_segment_complete`, `validation_failure_labels`, and route evidence counting.
2. Inspect `src/server/game/Bots/BotWorldPopulationMgr.cpp` route boss activation/recovery, interrupt evidence, target switching, wrong-map recovery, and death-loop handling.
3. Inspect Omnotron route data in `dataset/validation_scenarios/validation_routes.jsonl` and any generated scenario reports.
4. Determine whether the correct fix is:
   - route/mechanic profile data for Omnotron council members and interrupt/target-switch expectations,
   - generic validation-route focus recovery for council/multi-unit bosses,
   - bot survival/positioning/recovery behavior,
   - validation evidence counting,
   - or a combination.
5. Implement the smallest defensible fix that preserves the safety requirement that full BWD evidence must not include death loops.
6. Run focused tests via pixi and, if practical, a focused Omnotron validation segment with a long enough budget.

Return a concise final message with files changed, tests/validation run, evidence paths, and remaining blockers.
