# Resume raid development

Run from the mainline coordinator checkout, `/home/runiir/Games/trinity-cata` on
`master`. For another tab/worktree, inspect `git worktree list --porcelain`; the
saved `coordinator_worktree` must agree. Never copy an older state file over
current progress.

The normal request is "implement <boss> <mode> bots", also on a new tab:

```sh
pixi run python -m tools.raid_program.raid_workloop start "implement magmaw 25hc bots"
pixi run python -m tools.raid_program.raid_workloop resume   # continue the selected scenario
```

`start` resolves boss and 10N/10HC/25N/25HC from the strategy catalog. A matching
saved scenario resumes unchanged; a new one is initialized from requested-mode
inputs (see below). `--preview` inspects without selecting; `--expect` binds to
an observed state SHA256. Neither command launches a server, build or agent.

The primary agent stays coordinator; `owner_skill` names only the bounded
specialist. Output includes the parent objective, current unit and stage, its
`tier` (remaining/skipped steps), the `finish_line`, open requirements,
`reusable_build`, `latest_assessment` and a state hash. After each step execute
the next returned stage. Publication or routing is not completion; stop only for
explicit user limits or a demonstrated external blocker.

State lives in `experiments/configs/cata_raid_active_work_unit_v1.json` under
`development_graph`. Legacy fields outside it are historical context. For
diagnosis use the [compact evidence CLI](../../.agents/skills/raid-rotation-review/references/evidence-views.md);
keep full evidence on disk/DVC, not in model context.

## Finish line

Each scenario has a numeric target at
`experiments/configs/raid_targets/<raid>_<mode>_<boss>.json` (schema
`raid_target_v1`, e.g. `blackwing_descent_10n_magmaw`): per-actor mean kill DPS
over the required kills at least 0.95 x the median matched WCL DPS for the spec,
and no boss-window deaths. The scoreboard turns a labelled batch of kills into a
`raid_target_verdict_v1`.

- An actor requirement (`actor_<id>`) is accepted only when its verdict row is `pass`.
- An encounter requirement (one with `needs_all_actors`, e.g. `magmaw_10n`,
  `encounter_performance`) is accepted only when the overall verdict is `pass`.
- `no_reference`, `insufficient_kills` and `fail` keep the requirement open.
  `no_reference` is missing reference work, never acceptance.
- Free-form actor reviews, dummy calibrations and raid totals cannot close these
  requirements. Other requirements keep the reviewed repair assessment.

Accepting requirements records a compact verdict on each one (verdict file
reference, label, kills, status, ratio(s)). Lawful behavior is unchanged: no
coefficient tuning, external buffs, pre-applied debuffs or DTR allowance.

A missing target file is open work: new scenarios get a `raid_target`
requirement (in the first unit) and resume prefixes the next action with it.

## Risk tiers

A unit's `risk_tier` (set by `route` on the unit, or by the plan) fixes its steps:

| Tier | Use for | Steps after `implement` |
| --- | --- | --- |
| `profile` | rotation/profile, SQL data, config | `validate -> assess -> publish` (+ `build` only if needed, see below) |
| `class_native` | class/spec C++ under `src/server/game/Bots` | `review -> build -> validate -> assess -> publish` |
| `shared_runtime` | shared bot runtime, action arbitration, harness/validation tooling | `review -> build -> smoke -> validate -> assess -> publish` |

Units without a tier (all saved history) are `class_native`, which is exactly the
pre-tier flow. Skipped steps need no receipt. Plan-drift review and model advice
are never steps.

A unit whose own diff (plan base to tested commit) touches a native path (`src/`,
`dep/`, `cmake/`, CMake files) is at least `class_native`: the tests transition
raises a `profile` plan to `class_native` (review and build required) and resume
shows `tier.tier_raised`. A non-native `profile` unit skips `build` when the plan
cites `reuse_build` (a recorded build adapter or the queued-build receipt of the
binary on disk) that verifies under the plan policy and no native path changed
between that build and the tested commit. Otherwise it builds without review and
resume shows `tier.build_reason`. An unverifiable `reuse_build` is rejected at
plan time. `smoke` records one watchdog-bounded kill of the program encounter on
the new build before the measurement batch; a failed smoke is reworked.

A `profile` unit is 8 revisions and 5 receipts: plan, claim + tests, claim + run,
assessment (citing the verdict), claim + publication, then `route`.

## Record a step

Producer outputs stay unchanged. A small JSON adapter records the coordinator's
interpretation and links original receipts by SHA256. Every adapter has
`authority=coordinator_attestation`, `kind`, `unit_id`, `producer` and a nonempty
`evidence` list of `{"path", "sha256"}`. Adapter booleans are attestations; the
graph checks hashes, identity and prerequisites, not native truth.

| Stage | Kind | Required fields |
| --- | --- | --- |
| diagnose | plan | full `base_commit`, hypothesis, owned_files, forbidden_changes, acceptance_conditions, required_test_commands, policy, validation_identity; optional `risk_tier`, `reuse_build` (profile), `worker_context`, `supporting_review`, `advice` |
| implement | tests | file_hashes for every owned file, tests with command/exit_status |
| review | review | file_hashes, verdict=approved, reviewer_session_id and hash-bound review_report from a separate session |
| build | build | file_hashes, source_commit, binary_sha256, build_receipt, policy |
| smoke | smoke | build_identity, attempt_id, server_epoch, closed/cleanup_verified=true, scenario_kind=raid, clock=completion_watchdog, encounter, terminal_reason=clear |
| validate | run | build_identity, attempt_id, server_epoch, closed/cleanup_verified=true, terminal_reason, scenario_kind, validation_identity; `scoreboard_label` for verdict acceptance |
| assess | assessment | attempt_id, encounter_clear, accepted_requirements, and either `verdict` or the legacy baseline/comparison/actor_reviews/repair_accepted/performance_accepted |
| publish | publication | dvc_status_checked, dvc_push_completed, remote_verified, cleanup_verified, all true |

The plan's `validation_identity` binds scenario_kind, roster and runtime_profile;
a raid adds route and the program encounter, a dummy adds actor_id, spec and
reference. Runs must match it and the policy must match the build's.

Raid runs use `clock=completion_watchdog` and never a fixed success timer. Dummy
calibration uses `terminal_reason=measurement_complete`, `scoring_ms=300000`.
Failed or interrupted runs are closed and assessed without inventing a window.

Verdict assessment: run the labelled batch, then

```sh
pixi run python -m tools.raid_program.graph_acceptance verdict --label <scoreboard_label>
```

It evaluates the active scenario, writes the verdict under
`artifacts/cata_raid_program/verdicts/` and lists `acceptable_unit_requirements`.
Cite its `{path, sha256}` as `verdict`. The graph requires the run's
`scoreboard_label`, the program scenario and an identical fresh recomputation.
Accepting a non-verdict requirement in the same adapter needs `repair_accepted=true`.
Legacy assessments (no verdict) keep their gates, including the 95% dummy DPS gate
for `performance_accepted`. Requirements close only at publication, only inside
the bounded unit.

Example event (take values from resume):

```json
{"revision": 0, "unit_id": "magmaw:balance_self_setup_01", "action": "advance",
 "receipt": {"path": "artifacts/current-plan.json", "sha256": "ACTUAL_SHA256"}}
```

```sh
pixi run python -m tools.raid_program.workflow_step advance --receipt <adapter.json> --dry-run
pixi run python -m tools.raid_program.workflow_step advance --receipt <adapter.json> --owner <claim owner>
# or: raid_workloop advance --event /abs/event.json --expect STATE_SHA256
```

Writes take a Git-common-dir lock, compare the prior state hash and replace
atomically. A stale tab must resume. Commit state with code; publish adapters and
evidence through DVC; never edit a published receipt.

## Claims

Before executing implement, build, smoke, validate or publish, submit
`{"action": "claim", "revision": N, "unit_id": "...", "owner": "tab-name"}`. Put
`claim_token` in the completion event and `operation_id` in its adapter. A second
tab cannot claim the same operation and must inspect the owner's worker, build,
controller and DVC state rather than relaunch.

`release` (or claimed `rework`) needs a hash-bound reconciliation with
operation_id, ownership_checked=true, active_operation=false,
completed_operation=false and reusable_receipt_found=false. A completed operation
is recorded with `advance`, never released and repeated; for validation the graph
also searches the compact receipt directory for a closed run of this operation.

A completed run can be recorded after unrelated source changes:

```sh
pixi run python -m tools.raid_program.workflow_step advance \
  --receipt <original-run.json> --owner <original-owner> --recorded-source --dry-run
```

It verifies the committed launch snapshot and closes the run as historical
evidence only: no current-source repair/performance acceptance. Units that reused
a build cannot use this path.

## Build once across progress commits

```sh
pixi run python -m tools.raid_program.workflow_build preflight   # before claiming build
pixi run python -m tools.raid_program.workflow_build run          # after claiming and committing
pixi run python -m tools.raid_program.workflow_build finish       # completed build, interrupted handoff
```

`preflight` checks the reviewed policy and validation references (for dummy
calibration also the WoWSims binding); the build claim repeats it. `run` executes
policy-derived configure/build through the queue with no intervening Git writes,
stops on failure without retry, and returns the exact CAS-bound `next_command`.
`finish` verifies an existing queue result and never compiles.

Runners accept the canonical build receipt for a clean descendant commit when
only coordination paths changed: the active graph JSON, AGENTS.md, Markdown under
docs or skills, JSON under `artifacts/cata_raid_program/`, and newly added adjacent
DVC pointers/ignore lines there. Source, tools, configuration, references and
policy changes need a new build. Executables and symlinks never qualify.

## Tests and worker packets

Commit the implementation, then run the declared tests:

```sh
pixi run python -m tools.raid_program.workflow_step tests \
  --owner <claim owner> --producer <implementer session> --behavior-command '<declared command>'
```

It runs every declared command with timeouts, stores full output as artifacts
and returns the CAS-bound advance command only on success. A narrower passing
subset cannot replace the declared suite. `workflow_step amend-tests --file
tests/... --command ... --reason ...` adds a necessary test dependency during
implement without rebasing; production changes after tests need rework.

Source binding is checked at plan admission and implementation claim. `route`
starts the new unit from current HEAD; `rework` keeps the old base so a rejected
patch cannot hide in a new baseline. A separately reviewed workflow repair
(Python/tests/configs/pre-commit hook only) can join a paused unit through
`supporting_review`/`refresh_support`; native files and selected inputs cannot.

A plan may carry `worker_context` (`kind`, `question`, `decision`,
`counterexample`, a real `fixture`, and `native_behavior` line/hash excerpts of at
most 80 lines; observation work adds `observation_decision`). Then

```sh
pixi run python -m tools.raid_program.workflow_step packet --output /tmp/worker-packet.json
```

builds a packet (context <= 6KB, packet <= 10KB, never truncated) for the worker.

## Jev/Laya and retries

Jev (hosted) and Laya (local) are optional advisory tools; neither gates a
transition or can be a producer or acceptance receipt. Their use here is choosing
between the top two ranked damage gaps: ask Jev, with Laya shadowing Jev on the
same packet so their signal can be compared. An offline or context-rejected Laya
is recorded as not reviewed, never as a vote. After the measurement, log both
picks against the scoreboard delta:

```sh
pixi run python -m tools.raid_program.jev_outcomes append --unit <id> \
  --candidate <gap1> --candidate <gap2> --jev-pick <gap> --laya-pick <gap> --chosen <gap> \
  --label-before <label> --label-after <label> --party-delta <dps> --actor-delta <dps>
pixi run python -m tools.raid_program.jev_outcomes summary
```

Records go to `artifacts/cata_raid_program/jev_pick_outcomes.jsonl`; omit a pick
for a model that was not run. An optional `advice` object in a plan/tests adapter
may hold `jev` and/or `laya` entries, each with `status` (`reviewed` plus receipt,
or `not_reviewed` plus reason) and the coordinator's `adjudication`.

Rework (`action=rework`, reason, receipt) and every closed run that accepts no
requirement increment the edge's failure counter. At ten, `route` needs a
hash-bound `causal_summary` and a different edge. `recent_attempts` and
`failure_counts_by_edge` show history across unit renames.

At route submit `action=route`, reason and a new `unit` (unique id, edge, open
requirements, next_action, optional owner_skill and risk_tier). Route to the
largest remaining verdict gap. `action=complete` is rejected while any
requirement is open; scope changes come from the user and are committed.

## Scenario initialization and preservation

One active scenario plus a `parked_scenarios` map share the state file. Switching
parks the full prior state; reselecting restores it; nothing is rerun. Claimed
operations and open validate/assess/publish stages block switching.

A new scenario binds requested-mode research, native source, roster, simulator
reference catalogs and the raid target pointer. 25-player modes use all frozen
25 slots; a missing exact 10-player roster yields visibly unassigned slots, never
a guessed composition or another difficulty's actors. Requirements (all open):
encounter research, native script, roster setup, role references, runtime
scenario, assignments, raid target (if missing), every actor, and encounter
performance. Findings from another size/difficulty are context, not acceptance.
Changed bound inputs appear in `changed_bootstrap_sources`.

## Limits and history

The graph is a resumable coordination layer with no execution authority. Native
validators, the canonical controller's identity checks and independent review of
class/shared code remain authoritative. Workflow tests are synthetic fixtures;
build-verifier and review-session checks are mocked there and tested separately.

Earlier control-plane validation bundles (2026-09-20):
`development_graph_20260920`, `scenario_bootstrap_20260920`,
`workflow_build_repair_20260920`, `plain_request_continuation_20260920`
(`artifacts/cata_raid_program/<name>.tar.gz.dvc`). The script-readiness hash
mismatch in `test_script_readiness_uses_source_tree_identity` (recorded
`0855911a...` vs current `df4c8ee5...`) predates this workflow and remains open.
