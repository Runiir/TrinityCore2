You are a scoped inspection worker for run 000022 in /home/runiir/Games/trinity-cata.

Context:
- Previous commit 40509c5475 added validation-route activation diagnostics and target-entry fallback.
- artifacts/live_validation_instances/stonecore_corborus_route_target_assist_r10/report.json briefly showed boss_engagement_actions=2 and kills=3, but final report is still incomplete with boss_kill_evidence=0 and repeated boss_route_no_focus_activation_already_applied / hold-anchor no-focus.
- The likely bug is that the configured boss target/focus is not persisted/resolved after activation fallback, so followers return to anchor hold instead of assisting an authoritative route focus. There may also be evidence aggregation loss from trace-window truncation.

Task:
1. Inspect BotWorldPopulationMgr validation route focus lifecycle and tools/bot_ml/run_live_bot_validation.py evidence aggregation.
2. Do not edit files.
3. Produce a concise recommendation with exact functions/files/line areas and any focused tests that should change.

Return only your findings and proposed fix.
