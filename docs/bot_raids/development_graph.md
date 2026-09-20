# Resume raid development

Run from the current mainline coordinator checkout, `/home/runiir/Games/trinity-cata`
on `master` (relocated 2026-09-20). For another tab/worktree, inspect
`git worktree list --porcelain` and read that checkout's AGENTS.md first.
The saved `coordinator_worktree` must agree. Preserve side-branch work; do not
copy an older state file over current progress.

For a broad "implement boss bots" request, the primary agent owns the full loop.
Use the coordinator skills before choosing a bounded specialist; an implementation
handoff is not completion of the parent task. `start` selects work and the agent
then executes `unit.next_action`. This tool does not keep an agent running or
prevent it from replying early. Fresh-agent execution must be evaluated separately
from selector/graph fixture tests.

Select the requested encounter:

```sh
pixi run python -m tools.raid_program.raid_workloop start "implement magmaw 25hc bots"
```

`start` resolves the boss from the strategy catalog and normalizes 10N/10HC/25N/25HC
(including "25-player heroic"). A matching saved scenario resumes unchanged.
A new scenario binds its requested-mode research, native source, roster and class
reference catalogs. No server or database is changed. Unknown bosses, unsupported
modes, missing difficulty and conflicting requests fail without changing progress.
For structured calls, use `start magmaw --mode 25hc --raid blackwing_descent`.
`--preview` inspects inputs without selecting anything; `--expect` optionally
binds a selection to the state SHA256 observed by the caller.

To continue whichever scenario is already selected:

```sh
pixi run python -m tools.raid_program.raid_workloop resume
```

This is the entry point for continuation without a new encounter/difficulty. It returns the parent
objective, current bounded task, stage, every open requirement, completed
measurements, retained receipts and a state hash. Read the referenced evidence
and specialist skill before implementing. The saved state is
`experiments/configs/cata_raid_active_work_unit_v1.json`, under `development_graph`.
Its state owns task progress; historical handoffs provide context. The legacy
fields outside it are historical compatibility data, not separate acceptance.

The graph is:

`diagnose -> implement -> review -> build -> validate -> assess -> publish -> route`

From route, select another open requirement or finish when every requirement is
accepted. Passing tests, getting a kill or accepting one repair does not finish
the parent objective. Magmaw's five 50ec measurements are already recorded;
reference comparability and all ten actors' encounter acceptance remain open.

This command does not run an agent, build or server in the background. The
coordinator executes the existing tools for the current stage. Reuse verified
receipts; do not relaunch because a tab changed. Before a build/run, inspect
queued_build and the controller's actual ownership/attempt receipts. Graph file
locking prevents conflicting updates to this state, not concurrent server
launches. The existing build/server locks remain authoritative. Pick one
coordinator checkout; do not fork independent progress files across worktrees.

## Scenario initialization and preservation

The same atomic state file holds one active scenario and a `parked_scenarios`
map of inactive scenario states. Switching parks the full prior state, including
its accepted work, receipts, counters, claims history and completed measurements.
Reselecting restores it; no completed experiment is rerun by the initializer.
There is no duplicate active copy to reconcile. Claimed operations and unresolved
validate/assess/publish stages block switching until the current lifecycle closes.
The state lock and compare-before-write protect selection and ordinary transitions.

For 25-player requests, initialization uses all slots from the frozen 25-player
roster, preserving duplicate specs and recording logical slot IDs. Native GUID
binding, exact gear/setup readback and encounter assignments remain work. It never
reuses the ten Magmaw diagnostic GUIDs as a 25-player raid. Existing explicit
Blackwing Descent 10N shards retain their declared roster/profile/route. Where an
exact ten-player roster is absent, ten visibly unassigned slots and a roster task
are created; the initializer does not guess an encounter composition.

Simulator references bind the current self-provided request catalog, provider
revision and request/source-contract hashes. No embedded historical DPS number is
promoted. Missing DPS requests and tank/healer role diagnostics stay explicit.
DVC hydration, exact gear comparison and native readback remain required before
using references to tune damage. A catalog row is not a live-ready bot.

Each scenario retains requirements for encounter research, native script, exact
roster/setup, role references, runtime scenario, assignments, every actor, and
final encounter performance. Missing native scripts route to the research contract
and implementation work. Missing exact-mode runtime scenarios require the shard
specialist; a normal-mode route is never relabeled heroic. Initial acceptance is
false for all requirements, even when a script or contract file exists. Findings
in another size/difficulty are context, not inherited validation or DPS baselines.

`resume` includes the bound catalogs, their source hashes, owner skill, current
encounter and parked scenario IDs. Changed bound source files are reported in
`changed_bootstrap_sources`; reselecting does not silently overwrite the prior
snapshot or erase progress. Reconcile changed authority before using that input.
The bootstrap snapshot is provenance; later plans bind the actual reviewed runtime
and reference inputs through the ordinary graph receipts.

Initialization does not promise an automatic successful raid. The agent continues
from the first unresolved dependency using the existing specialist and review
workflow. It is a general entry point for catalog-supported encounters, including
ones whose scripts have not been implemented yet.

## Record a step

Keep existing producer outputs unchanged. A small JSON adapter records the
coordinator's interpretation and links original receipts with SHA256. Paths
are relative to the repository; hydrate DVC data only when a transition needs
its contents. Historical references may point to evicted payloads after closure.
Resume never repeats a run simply because that payload was evicted.

Every adapter requires `authority=coordinator_attestation`, `kind`, `unit_id`,
`producer` and a nonempty `evidence`
list of `{ "path": "...", "sha256": "..." }`. The graph checks these bytes.
It does not independently rerun tests or infer native correctness from a hash.
The coordinator must read and interpret the source evidence. Adapter booleans
are explicit attestations, not cryptographic proof or a model's verdict.

| Current stage | Adapter kind | Required additional fields |
| --- | --- | --- |
| diagnose | plan | full Git base_commit, hypothesis, owned_files, forbidden_changes, acceptance_conditions, required_test_commands, policy reference, validation_identity, advice |
| implement | tests | file_hashes for every owned file, tests containing command/exit_status, advice |
| review | review | file_hashes, verdict=approved; producer differs from implementer |
| build | build | file_hashes, source_commit, binary_sha256, build_receipt and exact policy references |
| validate | run | build_identity matching source_commit/binary_sha256; attempt_id, server_epoch, closed=true, cleanup_verified=true, terminal_reason, scenario_kind, validation_identity |
| assess | assessment | attempt_id, baseline, comparison, actor_reviews, separate encounter_clear/repair_accepted/performance_accepted, accepted_requirements |
| publish | publication | dvc_status_checked, dvc_push_completed, remote_verified, cleanup_verified, all true |

The plan's `validation_identity` binds scenario_kind, roster and runtime_profile
file references. For a raid it also includes route and encounter (raid/boss/mode)
matching the saved program. For a dummy it includes actor_id, spec and a reference
file reference. Run adapters must match that complete reviewed identity. The
plan's policy reference must also match the build adapter's policy exactly.
These adapter identities are checked alongside the canonical controller's own
native identity admission; copying expected values is not a native observation.

For raid runs, `clock` must be `completion_watchdog`. Successful dummy runs use
`terminal_reason=measurement_complete`, `scoring_ms=300000`. Failed/interrupted
runs can be closed without manufacturing a successful scoring window.

`actor_reviews` maps every roster actor to either
`{"status":"reviewed","receipt":{...}}` or
`{"status":"not_exercised","reason":"..."}`. An actor requirement also needs that row to contain `accepted=true`.
An isolated dummy review must
explicitly leave unexercised raid actors open. Performance acceptance also needs
`baseline_matched=true` and `unexplained_material_decline=false`, with the actual
comparison retained. Include exact DPS/HPS, activity, body/add damage, switch
latency, survival and phase/duty coverage in that comparison. The graph does
not invent an acceptable WCL delta or turn incomparable runs into matches.
Requirements close only after publication. It cannot accept requirements outside
the bounded unit, and raid/performance requirements retain their extra gates.

Before executing implementation, build, validation or publication, submit a
claim event using the current revision and state hash:

```json
{"revision": 1, "unit_id": "magmaw:balance_self_setup_01", "action": "claim", "owner": "coordinator-tab-name"}
```

Use the same advance CLI below. It returns the new revision/state hash and
`claim.token`/`claim.operation_id`. Include `claim_token` in the completion event
and `operation_id` in its receipt adapter. A second tab cannot claim the same
operation. A new tab must inspect the owner's worker/build/controller/DVC state;
never launch merely because an operation has no completion adapter yet.

To transfer an abandoned claim, use `action=release`, its claim_token and a
hash-bound reconciliation receipt with operation_id, ownership_checked=true,
active_operation=false, completed_operation=false and reusable_receipt_found=false.
If a completed operation has a receipt, record it with advance; do not release
the claim and repeat it. Release does not imply failure or completion. It does
not expire by elapsed time. Claimed rework also requires reconciliation.
The canonical coordinator worktree is bound in saved state; another worktree
must use that checkout rather than fork progress. Moving it is an explicit
coordinator migration in Git after reconciling outstanding ownership.

Plan binds the full base commit. A failed review retains its source baseline across rework; a new plan cannot
relabel unreviewed code as accepted baseline. Commit implementation before recording tests;
review/build check the actual source delta against owned files, including files
omitted from the adapter. Progress JSON, docs, skills and evidence are control
data excluded from that source delta. Native/config/tool/test code is included.
Record graph changes and commit before queued_build so its normal clean-source
admission still applies. Its existing verifier checks the original build
receipt with the exact policy, source identity and output binary. Workflow tests
mock valid native build verification and separately reject fabricated receipts;
they do not claim a native compilation occurred.

Example unclaimed plan completion event (take current values from resume):

```json
{
  "revision": 0,
  "unit_id": "magmaw:balance_self_setup_01",
  "action": "advance",
  "receipt": {"path": "artifacts/current-plan.json", "sha256": "ACTUAL_SHA256"}
}
```

```sh
pixi run python -m tools.raid_program.raid_workloop advance \
  --event /absolute/path/event.json --expect STATE_SHA256_FROM_RESUME
```

Each accepted event is retained in the same JSON history. Writes use an advisory
Git-common-directory lock, compare the entire prior state's hash, and replace
atomically. A stale tab must resume and reassess; never silently overwrite.
Commit updated state with code/configuration. Publish generated adapters and
source evidence through DVC. Do not edit a published receipt to fit new code.

## Jev/Laya and retries

At plan and result, use the existing
[worker checkpoints](worker_checkpoints.md). `advice` records both `jev` and
`laya`. Each entry has `status=reviewed`, a receipt reference and coordinator
`adjudication`; service/context failures use `status=not_reviewed`, `reason`
and the coordinator's alternative review. A model failure is visible without
blocking unrelated work. Model outputs cannot replace the independent approving
reviewer. The graph never interprets model confidence as acceptance.

Use `plan-drift-review` when switching work units or when requested. Review the
parent objective and all open requirements returned by resume, not just the
selected class. No per-tool model polling.

Before build, rejected work returns with `action=rework`, revision, unit_id,
reason and a receipt reference. Each failed rework or closed run accepting no requirement increments the
current edge's counter. A closed live failure passes through assessment and publication before
routing. At ten failures, route requires a hash-bound causal_summary and a
changed causal hypothesis; unchanged retries are rejected.

At route, submit `action=route`, reason and a new `unit` with unique id, edge,
nonempty open requirements and next_action. To finish, submit `action=complete`.
Completion is rejected while any requirement is open. Scope changes come from
explicit user direction and must update the objective/requirements transparently
in Git; do not erase outstanding requirements to obtain a completion verdict.

## Verification and limits

The focused tests exercise the real CLI in a fresh process after saved steps,
stale concurrent writers, code/receipt changes, missing tests/review, wrong
build/attempt identity, dummy/raid clocks, incomplete publication and retry
limits. They are synthetic workflow fixtures, not raid or class evidence.

This is a resumable coordination layer. Correctness still depends on the
existing native validators and independent review of actual evidence. It has
no autonomous execution authority, and does not replace source/build/runtime
identity checks in the canonical live controller.

Validated on 2026-09-20: 36 workflow tests and 44 related workloop/checkpoint
checks passed. Independent review approved this control-plane scope. The full
related suite also exposed a pre-existing boss-script readiness hash mismatch:
recorded `0855911a...` versus current `df4c8ee5...`. Running the unchanged HEAD
implementation against unchanged native files reproduced it. The targeted
80-test rerun explicitly deselected that one test; no audit claim was weakened
or silently refreshed. Reconcile the underlying encounter audit before relying
on its readiness result.

Hosted Jev reviewed the plan and result. Local Laya refused connections at both
checkpoints and remains not reviewed; independent review covered this change.
The evidence bundle is
`artifacts/cata_raid_program/development_graph_20260920.tar.gz.dvc`.
It contains tests, independent review, resume output, baseline-failure proof,
and exact model requests/responses. These are development records and are not
eligible for native raid-policy training. No new build or live raid was run.

## Scenario initializer validation (2026-09-20)

The catalog dry run initialized all 110 declared boss/mode combinations. A real
CLI round trip selected Magmaw 25H with 25 frozen slots, reselected it without
changing the state hash, then restored the existing Magmaw 10N state and its five
completed measurements exactly. The 25H task remains parked for later selection.
No native build, server, raid or training-data admission ran.

The related suite passed 112 tests. One existing source-readiness audit mismatch
(`test_script_readiness_uses_source_tree_identity`) was excluded; its unchanged
baseline failure is retained, not reclassified as passing. Independent review,
model advice/dispositions, test output and CLI receipts are published at
`artifacts/cata_raid_program/scenario_bootstrap_20260920.tar.gz.dvc`.
Local Laya was unavailable; Jev advice did not substitute for independent review.
