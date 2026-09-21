# Workflow repair and DPS acceptance

The stopped agent made real progress, but repeated bookkeeping failures delayed
the next measurement. A role-calibration JSON was accepted as a build policy
until build preparation. Hand-written event hashes and reviewer labels produced
further rework. An omitted observation duration could stop calibration immediately;
300 wall seconds could contain only 285 scored seconds after warmup.

The repaired path checks frozen build-policy commands during planning. Use
`pixi run python -m tools.raid_program.workflow_step advance --receipt <path>
--dry-run`, then repeat without `--dry-run`. A claimed operation requires its
explicit `--owner`. The helper derives the event revision, unit and file hashes
and uses the graph's atomic transition. It does not invent test results or reviews.

`review_execution` imports the actual independent session's final JSON response.
The response contains `verdict`, `file_hashes` and `findings`, with optional `tests`
and `limits`. Its compact report binds the session's retained prefix and final
response. Renaming a coordinator's report is insufficient. Changed reviewed
files require a new review. A stopped implementation may use `refresh_support`
with a reviewed support patch and reconciled operation; its native source base,
owned files, hypothesis and open requirements remain intact. Tests must run again.

Isolated calibration without an explicit observation probe now follows native
completion. Warmup is separate from the exact 300-second scoring window. A clock
timeout or disconnected transport cannot qualify a result. Explicit short probes
remain diagnostic. Raid and dungeon runs still use their completion watchdog.

## Numerical gate

Policy `all_spec_role_calibration_policy_v3.json` requires at least 95% of each
DPS actor's current promoted self-provided WoWSims reference. Both former 75%
and 85% thresholds are now 95%. Historical policies remain available to interpret
historical evidence; they cannot waive current graph acceptance.

Use `pixi run python -m tools.raid_program.dps_gate --help` to make a packet from
the retained run receipt and its native report or archive member. Attach the
returned packet reference as `dps_calibration` in the actor review. The graph
recomputes damage over 300 seconds, checks run/report identity, resolves current
promoted simulator files and runs the existing setup-admission comparison.
The calibration must match the currently validated source and binary; an older
passing run cannot qualify a newer build. Tank/healer reference thresholds stay
under their existing role policy and cannot substitute for DPS qualification.
Missing evidence, a role-only result or an approval flag cannot replace this.

A roughly 1,000 DPS Dragonwrath difference may explain part of the remaining gap.
It does not reduce the denominator or add another allowance below 95%. Passing
this numerical gate does not certify raid mechanics, WCL agreement, or every
cast's correctness. Keep repair, performance and encounter-clear outcomes separate.

The latest retained Balance measurement is 30,881.98 DPS against 35,447.59,
about 87.12%. Its 95% target is 33,675.21. This workflow patch does not recover
that missing damage or accept Magmaw. Every DPS and encounter requirement stays open.

## Validation boundary

Tests exercise production graph transitions, bound damage recomputation, policy
preflight and calibration transport behavior with fake external transports.
The focused suite passed 245 tests, with 3 skipped. After the final raw-policy
compatibility fix, all 42 raw-evidence tests passed. That fix allows equal hard
and optimization thresholds; the former strict inequality rejected the new 95%
policy. The earlier 245-test receipt retains its original source hashes. Independent clock review
caught an explicit-probe acceptance bug, which was fixed and re-reviewed.
They do not establish native class or encounter correctness. The existing
`test_script_readiness_uses_source_tree_identity` failure remains: the retained
boss-script audit hash begins `0855911a`, while current source begins `df4c8ee5`.
Updating the receipt without reviewing the script would conceal that mismatch.

Two broader `test_ml_pipeline.py` checks also fail against unchanged tests and
scenario inputs: `test_validation_scenario_manifests_link_routes_mechanics_and_provisioning`
reports the Chainwielder trash route's `patrol_future_sources` gap, and
`test_bwd_magmaw_preserves_boss_source_and_uses_db_ground_anchor` expects the older
v1 mechanic contract while the retained config uses v2 and explicit area-damage
allowlists. These remain separate route/contract work, not evidence of a repaired raid.
An earlier failure in `test_calibration_chunk_capture` passes in the final focused
suite; it was checked again rather than dropped from the selection.

Hosted Jev supported the scope but found the plan-only evidence insufficient for
acceptance. Local Laya returned weak support with no truncation. Actual test and
independent-review receipts govern this workflow change, not either model score.
