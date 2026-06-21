Continue from run 000078. The `raid_boss` checklist item is accepted with `artifacts/live_validation_instances/bwd_magmaw_force_terminal_r2/report.json`: Magmaw route segment completed with 10 active bots, `boss_kill_evidence=2`, `validation_route_actions=76`, no failure labels, and no death loop. Full BWD clear remains `needs_followup`.

Next, run or debug the full Blackwing Descent route sequence using the generated validation plan with long budget, preferably:

`pixi run bot-live-validate --duration-policy completion-watchdog --apply-validation-provisioning --reset-bot-pool --bot-pool-tag blackwing_descent_10n --keep-bot-pool-position --heartbeat-sec 30 --no-progress-window-sec 180 --max-repeated-decision-count 20 --max-death-loop-count 3 --timeout-sec 900 --observe-sec 300 --validation-scenario-id blackwing_descent_10n --output-dir artifacts/live_validation_instances/blackwing_descent_uninterrupted_full_clear_r3 --validation-route-sequence`

If it fails, inspect the first failing segment report under that output directory and compare route config fields in `.botauto diagnose all` against the route manifest. Keep `runtime_ml_control` disabled until uninterrupted full-clear evidence is clean.
