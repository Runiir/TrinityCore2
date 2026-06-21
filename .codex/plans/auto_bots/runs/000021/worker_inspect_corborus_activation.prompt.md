You are a medium-complexity inspection worker for TrinityCore bot autonomy run 000021.

Context:
- Repo: /home/runiir/Games/trinity-cata
- Previous commit: b343719d31
- Blocker artifact: artifacts/live_validation_instances/stonecore_corborus_route_target_assist_r8/report.json
- Live report shows validation_route_activation_attempts=0, boss_engagement_actions=0, boss_kill_evidence=0, and repeated advance_to_boss_route_no_focus.
- Previous pass added no-focus activation ordering and a target-entry fallback, but live behavior still did not record activation or unavailable telemetry.

Task:
1. Do not modify files.
2. Inspect BotWorldPopulationMgr and related validation route config loading/generation code.
3. Explain why TryValidationRouteObjective can record advance_to_boss_route_no_focus without recording either activation attempts or boss_route_no_focus_activation_unavailable.
4. Identify the smallest useful diagnostic or code fix the orchestrator should apply next.
5. Include exact file/function references and any tests that should be run.

Return a concise technical report only.
