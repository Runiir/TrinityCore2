# Run 000033 Progress Summary

## Scope

Continued from run 000032 / commit `be7ab16dfa`, focused on Blackwing Descent 10N uninterrupted route validation and raid evidence scoring.

## Worker Routing

No worker or reviewer Codex sessions were launched in this pass. The changes were scoped enough for the orchestrator to implement and validate directly.

## Implementation

- Added durable live-validation evidence counters to `BotWorldStatus` and `.botexp summary` for role assignments, group/raid formation, target priority, interrupts, healer assignments, tank positioning, regrouping, recovery, and instance reset evidence.
- Emitted validation cohort formation and role-assignment trace events once per bot when the validation group/raid is formed.
- Counted raid telemetry events such as `raid_role_assignment`, `raid_interrupt`, `raid_healer_cooldown`, `raid_position_anchor`, `raid_boss_action`, `raid_add_wave`, and `raid_wipe` into the summary evidence counters.
- Extended `tools/bot_ml/run_live_bot_validation.py` and `tools/bot_ml/build_validation_scenario_manifests.py` so route manifests and live reports recognize the raid telemetry action names.
- Rebuilt validation scenario manifests with `pixi run bot-validation-scenarios`.

## Validation

- `pixi run pytest tests/test_ml_pipeline.py -k "group_mechanic_evidence or summary_only_raid_evidence_after_trace_rolloff or phase08_server_raid_telemetry_surface"`
- `cmake --build build --target worldserver -j$(nproc)`
- `pixi run bot-live-validate --validation-scenario-id blackwing_descent_10n --validation-scenario-dir dataset/validation_scenarios --validation-route-manifest --duration-policy completion-watchdog --observe-sec 300 --timeout-sec 900 --reset-bot-pool --bot-pool-tag test_account --apply-validation-provisioning --output-dir artifacts/live_validation_instances/blackwing_descent_uninterrupted_full_clear_r1`

## Live Evidence

`artifacts/live_validation_instances/blackwing_descent_uninterrupted_full_clear_r1/report.json` failed as final evidence:

- `completion_reason`: `machine_failure_predicate`
- `acceptable_final_evidence`: `false`
- `failure_labels`: `["validation_route_death_loop"]`
- `final_evidence_rejections`: `["not_all_stages_passed", "failure_labels_present"]`
- `validation_route_manifest_complete`: `0`
- `boss_kill_evidence`: `0`
- `kills`: `1`
- `trash_pulls`: `125`
- `validation_route_segment_advance`: `1`
- `active_bots` / `target_bots`: `10` / `10`

The prior `bot_lifecycle_not_loaded` blocker is no longer present. Evidence counters now populate from summary and trace: `role_assignments=10`, `raid_formation=20`, `target_priority=69`, `tank_positioning=96`, `regrouping=47`, and `recovery=34`. The next blocker is runtime behavior: bots loop/die around the entry trash route after one trash kill and one segment advance, with repeated `validation_route_stuck_anchor_focus_reset`, `guardrail_repath`, and `validation_route_death_loop`.

## DVC

- Added `artifacts/live_validation_instances/blackwing_descent_uninterrupted_full_clear_r1.dvc`.
- DVC push/status were run at the end of the pass; see orchestrator final JSON for exact result summary.

## Checklist

Updated the remaining BWD checklist entries (`raid_trash`, `raid_boss`, `full_blackwing_descent_clear`) to point at `artifacts/live_validation_instances/blackwing_descent_uninterrupted_full_clear_r1/report.json` with the current failure label `validation_route_death_loop,scenario_clear_not_complete,missing_required_evidence,failure_labels_present`.

## Next Handoff

Continue from run 000033 after the commit for this pass. Inspect `artifacts/live_validation_instances/blackwing_descent_uninterrupted_full_clear_r1/report.json` and `worldserver_output.log`. The BWD uninterrupted run now has 10 loaded bots and working raid evidence counters, but it fails during entry trash with `validation_route_death_loop`: one trash kill, one route segment advance, repeated `validation_route_stuck_anchor_focus_reset`, `guardrail_repath`, and deaths before any boss engagement. Repair the entry trash route progression/recovery so the manifest advances cleanly from entry trash to Magmaw without looping at the old anchor/focus, then rerun long-budget BWD route validation (`--observe-sec 300 --timeout-sec 900`). Use pixi for Python commands, DVC-add/push any new artifacts, run `pixi run dvc status`, and update checklist/progress files before committing.
