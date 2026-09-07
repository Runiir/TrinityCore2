# Raid program audit, 2026-09-05

This audit starts at Git `cbe661ec16e0291d34d170a4dde55eb970769b4b`.
It distinguishes code defects, workflow friction, and unproved gameplay behavior.
No new live raid result or model-training result is claimed.

## What is working

`pixi run python -m tools.raid_program.raid_workloop status` reports the frozen
25-player roster ready and all 16 DPS requests current in the promoted
self-provided WoWSims catalog. This checks the catalog's current projection;
it does not prove each Trinity spec meets that reference. The supported universe
is 24 roster modes, 23 required and one optional, rather than every spec in the
client. An explicit coverage policy must decide whether other specs are in scope.

The typed action arbiter has deterministic ordering, resource conflicts,
candidate deduplication, retry backoff, and separate submission/progress phases.
Retain it. The native bot `.cpp`, `.h`, and `.inl` files inspected are all below
1,000 lines. Existing recurrence, build identity, watchdog, and DVC machinery
should be reused; adding a second implementation of these contracts would add
another opportunity for disagreement.

## Why work repeats

1. In the last 100 commit subjects at the audit baseline, 59 contain
   `authoriz`. This is a measure of workflow traffic, not proof that every such
   commit was unnecessary. The active descriptor explicitly required stopping
   after one implementation commit and leaving the generic caller unresolved.
   This conflicts with the latest user's instruction to carry repairs through
   verification. Worker scope limits belong to the worker; the coordinator must
   continue with the next dependency under the existing user authorization.
2. The retained `cata_raid_magmaw_pre_gameplay_infrastructure_causal_summary_20260903.json`
   records four Stage3 attempts, all with zero bot decisions. Three never started
   a worldserver; one started it but admitted no bots. These attempts diagnose
   infrastructure, not class DPS or the current native gameplay repair.
3. The current asset verifier reports the complete missing set: ten offline
   DBC/DB2 files, three generated gear files, and an unpinned extraction receipt.
   Its additional four hash and two size mismatches are consequences of the
   missing inventories, not six independent gameplay defects. An optional
   caller gate let omission bypass this check entirely.
4. The proposed task architecture is only partially deployed. The generic
   `Decision/BotPersistentTask.h` defines state enums; the substantial task
   implementations and reconciliation currently live in Magmaw modules.
   `RunBotDecisionKernel` explicitly falls back to `RunLegacyBotDecision` when
   the validation kernel does not own the tick. The latter contains ordered
   handlers that choose work and execute side effects. Splitting those handlers
   into files has not removed their temporal and ownership coupling.
5. `Kernel::Observe` resets consecutive submission failures for committed work,
   including `Submitted`, while recording progress only for `Progressed` or
   `Completed`. That separation is useful, but a task owner must enforce its
   own outcome deadline. Backoff or an accepted intent alone cannot establish
   arrival, hazard escape, target ownership, or recovery. This is an architectural
   risk visible in source, not a newly proved cause of a particular live wipe.

## Repairs in this audit

- Make the existing runtime asset authority mandatory across the assigned
  bundle, capture, readback, composite-plan, live-validator, and route-child
  boundaries. Offline log reparsing is a separately typed operation. Tests must
  prove omission and mismatch reject before side effects. This does not invent
  extraction provenance or make the existing missing assets present.
- Shorten the coordinator entrypoint by moving detailed causal routing and
  recurrence procedures into linked references. Preserve their rules. Remove
  the nonexistent CLI model-script requirement for native collaboration;
  correct model-review effort; remove universal ten-player, six-shard, and
  Magmaw-specific rehearsal assumptions from the shard skill.
- Replace skill tests that require exact sentences with local reference checks.
  The old tests could certify wording but could not certify agent behavior.
  Executable native regression fixtures are retained.
- Stop silently selecting candidate zero when the observed action cannot be
  joined to exactly one recorded candidate. Explicit identity cannot fall back
  to a shared activity. Missing candidate sets and ambiguous identities are
  exported separately as quarantine, with their DVC output declared.
- Reject still-running experiment records from the decision builder's ordinary
  run filter, using the native `RecordRunStop` status and timestamp contract.
  This filter remains a necessary condition, not complete run provenance.
- Exclude flattened future outcomes, selected-action fields, and record IDs
  from `numeric_features`. Candidate scores no longer inherit the chosen
  action's scores or an outcome value. Retain outcomes for diagnosis and labels.

## Tests and iteration costs

A scan found 199 test files that read source text without recognizable native
execution. This is a heuristic inventory, not a count of worthless tests.
Line limits, registration, and forbidden dependencies are legitimate structural
checks. Assertions that a method name or telemetry string occurs in a file
cannot prove scheduling, movement, or landed outcomes. Keep those checks
labelled as structural and require executable boundary tests for gameplay claims.

The original 13-file counterexample already has a temporary-directory test
that fails with the entire missing set and passes after restoring the inputs.
Its separate retained-machine test describes a historical negative environment;
it cannot serve as a positive runtime-readiness gate.

`tools/bot_ml/run_live_bot_validation.py` was 8,074 lines at the audit baseline;
`run_wowsims_exact_references.py` was 6,451 and `review_rotation_mechanics.py`
4,606. Extract stable orchestration/transport/reporting boundaries with existing
behavioral coverage when touching those owners. Do not spend the next canary
cycle splitting files without reducing repeated work or proving a bug.

For fast iteration, use the focused production-boundary fixture before a
heavyweight build, then the retained fixtures adjacent to the changed contract.
Use the existing queued build and build/control compatibility verifier. Do not
rebuild a native binary solely because a reviewed status document changed.
Hydrate only declared dependencies and do not run broad `dvc repro` to satisfy
an unrelated missing output. Keep build, live validation, and publication as
separate observed results, joined by identity.

## Remaining work, in dependency order

1. Verify the propagation repair independently, then reconstruct the entire
   runtime closure in a fresh run root. The local client directory
   `/home/runiir/Games/Cataclysm-4.3.4.15595-enUS-x64` exists. That does not prove
   it produced existing `data/` bytes. Bind a real extraction/reconstruction
   operation and its input/extractor identities; do not backdate a receipt.
2. Run the current bounded production replay/canary only when asset, recurrence,
   source, build, and database gates pass. Close its evidence and route the
   current earliest mismatch. Do not reopen a latest-absent historical symptom.
   Leave Magmaw-specific repair work when the lifecycle edge is accepted or a
   different shared blocker is proved.
3. Migrate one trace-proved temporal ownership edge through observations, pure
   facts, assignment, persistent task, passive candidates, native execution,
   and outcome feedback. Reuse that shared contract for a second encounter
   before treating it as general. Test actor motion, observation gaps, safety
   preemption, retained submission, failed native execution, and task termination.
   No blanket priority reordering, tolerance changes, or bot-side Z steering.
4. Establish generic role acceptance records. `audit_role_efficiency.py` still
   contains spell groups keyed by Stonecore bot names; that is a diagnostic
   fixture, not all-roster healer/tank acceptance. Cover the charter's healing,
   mitigation, mana, threat, cooldown, movement, and preventable-death measures.
5. Complete the encounter catalog by evidence and difficulty. Status reports
   28 named raid encounters: 19 source-present but not runtime-validated, nine
   missing dedicated implementations, all 28 fidelity-blocked. The displayed
   raid catalog is not a complete dungeon/difficulty coverage matrix. Track
   those missing dimensions explicitly before claiming program completion.
6. Make ML batch admission consume verified closed-run manifests, not only
   `runtime_mode` and assistance flags. Join task/assignment, the full candidate
   set, actual native outcomes, and terminal/cleanup identity. Preserve valid
   failures as hard negatives, and quarantine infrastructure/identity defects.
   Preserve the new exclusions for unbounded semantic-memory features and the
   strict training/evaluation partition gates. No model was trained in this audit.
7. Define an actual-client observation/action contract before training for that
   target. Server-side snapshots may contain information the client adapter
   cannot observe. Separate observations from privileged labels, define client
   input timing and action acknowledgements, record actual-client episodes,
   and evaluate on held-out runs/encounters. Begin with shadow ranking under
   deterministic legality and safety. Server bot success alone does not certify
   the client-controlled policy.

These are evidence gates and implementation dependencies. Passing this audit's
unit tests does not mean Magmaw, all specs, all raids, or client control are done.

## Continuation and independent review, 2026-09-07

The first worker stopped at a provider usage limit before its final handoff.
Its landed files were inspected directly and tested. A separate Sol/high review
then returned NO-GO for live authority for two additional verified reasons:

- The proposed launch contract embeds the closure manifest digest, while that
  manifest pins both launch_contract.json and bundle_manifest.json. The resulting
  digest cycle cannot be produced deterministically. Metadata-only bundle tests
  did not exercise this production-shaped dependency graph.
- Compose merely copied closure arguments and could schedule configure/build
  with nonexistent manifest/data paths. Full prerequisite verification belonged
  before that expensive work.

The correction separates immutable input closure from generated bundle output
verification. The historical complete-directory snapshot remains historical
negative evidence. No current extraction identity is invented to make it pass.
Offline input-log parsing also now rejects live preparation and publication
flags before their side effects; an offline exemption cannot authorize DB writes.

A full ML-pipeline test run initially reported 32 failures. Twenty-six were
later-boundary tests that needed an explicit upstream asset-gate fixture after
closure became mandatory. The remaining six reproduced with baseline common
and decision-builder code restored in the test process. They exposed four
separate issues, repaired without weakening their acceptance predicates:

- An equipment SQL test counted the three native consumable item rows as gear.
  It now checks the exact 16 equipment payloads separately and accounts for the
  declared consumable rows.
- Elemental's action manifest omitted IDs 2894 and 51505 already present in its
  canonical target list. The manifest now matches that list exactly; no spell
  priorities, reference values, or gear identities changed.
- The native profile loader selects min_hostile_target_health_pct, but no SQL
  migration declared it. A forward/rollback pair now declares the disabled-by-
  default float column. These migrations have not been applied to a live DB.
  The static schema contract and its DVC dependency list cover the extension.
- The Phase7 synthetic positive record claimed a 15-yard target distance while
  its coordinates disagreed. The sample coordinates now agree; the existing
  negative geometry, distance, lane, and contamination tests are retained.

The Phase4 structural audit also counted exact occurrences of a C++ helper
rather than checking its allowed resource tags. It now checks the actual tag
set, including the existing soul_shard gate, and explicitly labels the result
structural_only. No static test is promoted to a live gameplay result.

Descriptor freshness now tolerates documentation-only descendant commits while
retaining source-handoff digest checks. Changes under source, tools, config, or
unknown paths still invalidate the descriptor, and live admission still requires
its independent clean-source/build identity. This removes a demonstrated source
of authorization-only commits without permitting stale native binaries.

The final independent review exposed further data defects. Final exported
semantic and fingerprint aggregates are now excluded from model inputs. The
native telemetry envelope combines activity choices with a possibly retained
combat mask; the dataset now admits the uniquely matched activity group and
quarantines the unsupported combat group. Quality checking, teacher selection,
and ranking use run, bot, decision, and domain identity. Training no longer
falls back to evaluation rows, evaluation no longer falls back to training rows,
and feature selection uses the training partition only. Regression fixtures
cover native mixed masks, cross-run ID collisions, future aggregate changes,
and missing observed partitions.

This does not yet establish native feature parity. The generic numeric feature
filter still exposes fields whose names or availability differ from the native
activity model's feature map. A native-parity allowlist and held-out adapter
comparison remain required before shadow/assist promotion. Actual-client
features need a separate observation contract.

Verification before the final caller integration passed 714 integration tests
and 162 asset tests. The later ML review repairs passed 36 focused tests. Tests
use temporary outputs; no new experiment batch, model, native build, server,
or database mutation occurred. DVC status returned successfully with 576 changed
stage/artifact entries, compared with 574 at baseline. These include pre-existing
absent outputs and changed source dependencies. No broad hydration, reproduction,
or artifact publication was performed to make unrelated status entries green.

The parent launchers now carry the asset tuple through Phase6 live soak, Phase8
calibration, Phase9 planning, DPS acceptance, and the Make entrypoint. The generic
multi-map shell plan defers required machine paths to environment bindings and
uses each scenario's own map ID. Missing bindings fail before launch; arbitrary
scenario strings are still shell-quoted. Map zero remains valid. The Make target
uses prepared inputs and no longer configures, touches the DB, or builds before
admission. Its changed source digest is repinned in the existing derivation
contract; the test-configs recipe and derived runtime bytes remain unchanged.

Additional test repairs remove the assumption that Magmaw must always be the
active work unit, remove exact wording checks for the ML split description, and
read the current calibration/semantic modules for structural guards. The
historical materialized Phase8 fixture still fails its meaningful freshness
check. Its embedded target-catalog digest is 46a79c46..., while the current
catalog is 89263d95...; embedded Affliction and Demonology action lists differ.
Neither file was changed in this audit. The counterexample is retained and
queued for reference reconciliation, without overriding the current promoted
simulator catalog or silently promoting a regenerated historical fixture.

The final combined suite ran 1,119 tests: 1,105 passed and 14 failed. Thirteen
failures came from the added derived-config boundary suite's obsolete setup;
its asset admission and source-build snapshot inputs are now explicit, and all
23 tests in that suite passed on the focused rerun. This leaves 1,118 passing
checks across the combined run and rerun, with the one historical fixture
freshness failure retained. No live readiness claim follows from these tests.
All four edited skills passed packaging validation. Final DVC status returned
successfully with the same 576 changed stage/artifact entries.
