# All-specialization Stonecore execution continuation

## Authority and purpose

This document is the continuation contract for the approved program in `.codex/plans/all_class_sc_plan.md`. It is not a replacement design exercise and is not a request to enter Plan mode. Execute it directly from commit `482e84b68d878822513a8fbc12811b5a385851f6` on branch `all-spec-stonecore-execution`.

Phases 0-8 are complete. Phase 9, `pairwise_matrix_and_serial_stonecore_canaries`, is the only active phase. The commit above is an in-progress checkpoint, not a Phase 9 completion. Phases 10-12 remain blocked until every Phase 9 gate and the mandatory independent review pass.

The immediate objective is to resolve the rerun127 Feral-tank role-quality failure using immutable evidence, run a passing current-identity canary 2, complete serial canaries 3-8, close the Phase 9 pairwise/evidence contract, and obtain independent `gpt-5.6-sol` high-reasoning approval. After that gate passes, continue automatically through Phases 10-12.

## Locked program decisions

- Cover exactly 31 Cataclysm targets: 4 tanks, 5 healers, and 22 DPS.
- Treat `feral_druid_tank` and `feral_druid_dps` as distinct targets.
- Keep `unholy_death_knight` as the preferred Death Knight DPS specialization and continue optimizing it.
- Use only parties containing exactly 1 tank, 1 healer, and 3 DPS.
- Keep explicit SQL/rule profiles as runtime authority. Generic ML remains offline/shadow-only.
- Preserve the 75% individual calibration hard floor and 80% optimization target. No aggregate may conceal an individual failure.
- Preserve true `300 +/- 5` second scored qualification windows where applicable.
- Certify Stonecore only through a strict uninterrupted current-identity clear of the complete 14-node route.
- Do not use teleport, teacher/forced completion, route weakening, stale identity, instance substitution, missing terminal nodes, or acceptance-policy relaxation to manufacture a pass.
- Keep `MaxActiveCohorts = 1` throughout Phase 9. Establish serial correctness and isolation before concurrency.
- Only one operator may mutate the live worldserver and only one publisher may mutate canonical DVC state.
- Use Pixi for Python. Use DVC/DVCLive for generated evidence. Commit experiment code/configuration to Git and checkpoint data through DVC.
- Publish, remotely verify, and locally evict raw evidence after every closed batch. Never use broad `dvc gc`.
- Never print credentials, include the SOAP environment in artifacts, or commit `.dvc/config.local`.

## Current repository and runtime checkpoint

- Git branch: `all-spec-stonecore-execution`.
- Checkpoint commit: `482e84b68d878822513a8fbc12811b5a385851f6`.
- Git-visible worktree state at checkpoint: clean, zero untracked files.
- No serial operator is active.
- No Phase 9 worldserver is active. The last exact unit is inactive.
- The Phase 9 matrix, independent verifier, evidence-identity builder, deterministic run-plan builder, serial operator, SQL migrations, runtime changes, and audit changes are committed.
- Program status authority: `experiments/configs/all_spec_stonecore_program_status_v1.json`.
- Original full program authority: `.codex/plans/all_class_sc_plan.md`.

Generated Phase 9 history through rerun127 is stored at:

- Pointer: `artifacts/all_spec_program/phase9_generated_history_through_rerun127_20260802.tar.zst.dvc`
- DVC MD5: `9cb8af3f7a26e34e46d2100db7dd0356`
- Size: 5,525,534 bytes
- Archive SHA-256 before eviction: `f2339ae066cf6b2647c196b7e0785fa076d433edd66fce8719de9f67bc5a4b25`
- Remote publication: verified before local eviction
- Local expanded Phase 9 folders, archive payload, hydrated raw/compact payloads, and batch-local cache: evicted

Repository-wide `dvc push` uploaded nine additional objects and reported two older objects missing both locally and remotely:

- `24b9d133fe3fe1b6f253e500c266562f.dir`: stale locked `dataset/all_spec_phase1_catalogs` object. Regenerate it from the current DVC stage during dependency reconciliation.
- `c67ee8935753b8ceccbdddbafdfebe.dir`: legacy 1.8 GiB `stonecore_strict_repair_run_053` object. Treat this historical pointer as unavailable unless another verified source is found.

Neither missing object is the Phase 9 history archive or rerun127 publication.

## Phase 9 deterministic matrix contract

The committed matrix is not an aspirational draft. Its offline construction currently records:

- Canonical targets: 31
- Candidate constrained compositions: 30,800
- Selected covering-array compositions: 85
- Required unordered pairs: 449
- Covered required pairs: 449
- Uncovered required pairs: 0
- Structurally excluded pairs: 47
- Tank-healer: 20 required / 20 covered
- Tank-DPS: 88 required / 88 covered
- Healer-DPS: 110 required / 110 covered
- Compatible DPS-DPS: 231 required / 231 covered
- Excluded tank-tank: 6
- Excluded healer-healer: 10
- Excluded self-pairs: 31
- Policy-incompatible pairs: none in the current policy
- Serial canaries: 8
- Serial target union: all 31 targets

Identity hashes:

- Matrix: `bac3a937ced4063f4c20267812ab621044373fb3e42a620a66e3a75d8fe64921`
- Pair universe: `b40d215ba4929b721c411e977c4c72a750bb64474eb589994cd89d58748d19e1`
- Selected composition set: `0e9edff5d37cf4fcdf68107cfcbf882a8f92a5e2aa40e16024b4eaad5ef02a76`
- Representation: `69a2420b5b8d0a95fa060b353bf4e3b72270be04935e0131c56dccf00ef9e54e`
- Serial canary set: `5e3e76e5001e9d4a5383f4534f8fa1eaf3a8dc97cf7d063a0361d4a3ae675fd7`

The generator orders candidates by tank, healer, and canonically sorted DPS triple; greedily selects maximum uncovered gain; breaks ties by minimum member representation and lexical order; and reverse-prunes redundant rows. The independent verifier must reconstruct targets, pairs, exclusions, coverage, mappings, and representation without trusting stored pass booleans or pair lists.

The offline counts above do not complete Phase 9. The DVC contract must be reproduced under the final inputs, all eight serial rows must pass live, evidence must be current and remotely verified, and independent architecture/evidence approval must be recorded.

## Pinned eight-row serial canary set

| Row | Composition | Tank | Healer | DPS 1 | DPS 2 | DPS 3 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `stonecore_phase9_065_e33ae8a3db04` | Blood DK | Restoration Shaman | Affliction Warlock | Beast Mastery Hunter | Shadow Priest |
| 2 | `stonecore_phase9_006_6893daf98698` | Feral Druid tank | Discipline Priest | Fury Warrior | Marksmanship Hunter | Retribution Paladin |
| 3 | `stonecore_phase9_083_5d0c65765654` | Protection Paladin | Holy Priest | Arcane Mage | Assassination Rogue | Fire Mage |
| 4 | `stonecore_phase9_004_3904746e5810` | Protection Warrior | Restoration Druid | Elemental Shaman | Enhancement Shaman | Feral Druid DPS |
| 5 | `stonecore_phase9_077_59bcbc0d6019` | Blood DK | Holy Paladin | Balance Druid | Frost DK | Survival Hunter |
| 6 | `stonecore_phase9_082_d421aa6b815f` | Feral Druid tank | Holy Paladin | Beast Mastery Hunter | Destruction Warlock | Frost Mage |
| 7 | `stonecore_phase9_075_743d591b7ee4` | Protection Paladin | Restoration Shaman | Combat Rogue | Elemental Shaman | Unholy DK |
| 8 | `stonecore_phase9_084_137e606f60b7` | Protection Warrior | Restoration Druid | Arms Warrior | Demonology Warlock | Subtlety Rogue |

Every tank appears exactly twice. Every healer appears once or twice. Every DPS appears once or twice. Blood and Feral rows include native Hunter Misdirection support because Azil can activate simultaneous follower waves beyond one self-centered pickup radius.

Do not alter the matrix, row order, party membership, target aliases, route, timeouts, or acceptance policy merely to avoid a runtime failure. A justified change is allowed only after evidence proves the contract itself is wrong; such a change invalidates all live evidence and requires a fresh identity and regenerated plan.

## Active failure: rerun127 canary 2

Exact party:

- `feral_druid_tank`
- `discipline_priest`
- `fury_warrior`
- `marksmanship_hunter`
- `retribution_paladin`

Closed-batch facts already established:

- Exact party verified
- Evidence/runtime identity matched
- Operator session closed normally
- Cleanup completed
- Publication remotely verified
- Local raw payload evicted
- Publication receipt SHA-256: `2e176b912ece0f45918a14d06e9509030f5800b0b2d4006da7613e3d272f6769`
- Final gate failure: `role_quality:Feraltank:healer_target_exposure`

Do not infer from the summary alone that route, threat retention, or every other role-quality subgate passed. Reconstruct those facts from immutable evidence. The task is to determine whether healer exposure represents real Feral threat loss, delayed/sparse area pickup, stale hostile ownership, bad target selection, hazard/path displacement, healer proximity/aggro behavior, Misdirection timing, or incorrect identity-scoped audit attribution.

### Required diagnosis dimensions

Reconstruct a single time-aligned sequence containing:

- Every hostile GUID observed during the scored route and the intervals in which it was alive, engaged, owned by the party, owned by the Feral tank, or targeting the healer.
- Feral all-hostile retention numerator/denominator and identity scope, including when mobs enter or leave the eligible set.
- Healer exposure count, dwell, longest continuous interval, and target transitions.
- Threat-margin samples for tank versus healer and tank versus each DPS.
- Growl/taunt attempts and results.
- Swipe, Thrash if applicable, Demoralizing Roar, Maul, Mangle, Lacerate, and any rule-profile threat action, including legality/rejection reasons.
- Misdirection acquisition, cast, target, transfer window, and expiration.
- Pull boundaries, simultaneous add-wave arrivals, pack density, target swaps, strict-area classifications, and any mobs outside the tank's effective radius.
- Hazard exit/re-entry, tactical retreat, recovery mode, route movement, partial/unreachable paths, line-of-sight, facing, range, and downtime from threat actions.
- Tank/healer death, resurrection, combat-resurrection, stale combat, or audit-window transitions.
- Server epoch, process, profile generation/content hash, route hash, matrix hash, attempt ID, party/cohort/instance IDs, and batch identity attached to every accepted fact.

### Hypotheses and falsifiers

1. **True initial/add-wave pickup failure.** Supported if eligible hostiles target the healer before the Feral establishes any meaningful threat and the expected bounded area/taunt actions were legal and available. Falsified if the tank owned them throughout and only the audit attributed exposure incorrectly.
2. **Threat retention decay after initial pickup.** Supported if tank ownership is first established, then threat margin collapses during action downtime, target fixation, movement, or cooldown gaps. Falsified if the hostile was never owned or was structurally outside the eligible retention set.
3. **Hazard/path recovery caused combat-action starvation.** Supported by a time-aligned movement/recovery interval preceding threat loss. Falsified if normal threat cadence continued and margins still collapsed.
4. **Misdirection support failed or targeted the wrong identity.** Supported by missing transfer, wrong target, rejected cast, or a transfer window that excludes add activation. Falsified by verified threat transfer to the current Feral identity before exposure.
5. **Audit scope or denominator is wrong.** Supported only if raw events prove the audit counted dead, unengaged, another-identity, pre-window, post-window, non-party-owned, or otherwise ineligible hostiles. Fix the audit only when the runtime behavior is correct and the attribution error is independently reproducible.
6. **Healer behavior is the primary cause.** Supported if the healer creates legitimate threat before tank pickup or leaves the bounded party position while the tank behavior remains correct. Do not hide this by relaxing the tank gate; correct the responsible rule/profile/runtime behavior.

Write a compact diagnosis that states which hypotheses were tested, the evidence rows/time ranges used, the accepted causal chain, rejected alternatives, and why the proposed correction is the smallest safe one. Hash the diagnosis and place it in rerun127's retained evidence before capture validation and re-eviction.

## Minimal hydration and low-disk diagnosis protocol

1. Verify `.dvc/config.local` exists, is ignored, and provides the same redacted remote configuration as the main worktree. Never display secret values.
2. Pull only `artifacts/all_spec_program/phase9_generated_history_through_rerun127_20260802.tar.zst.dvc`.
3. Verify the DVC MD5, size, and archive SHA-256 listed above.
4. Extract only the rerun127 subtree into its original repository-relative path. Do not expand all 118 historical folders.
5. Read retained summaries, receipt, final manifest, report, combat analysis, operator state/log, run plan, and identity manifest first.
6. Pull rerun127 raw/compact pointers only when those retained artifacts cannot answer a named uncertainty.
7. Before accepting the capture, independently verify exact party, identity, closure, cleanup, receipt, remote verification, raw part count, raw event-row count, compact row count, and bundle hashes.
8. Write and hash the diagnosis, run the established capture validator, and confirm remote evidence again.
9. Delete the hydrated raw/compact workspaces, exact cache objects, extracted rerun127 subtree, local archive payload, and exact archive cache object only after verification. Retain the `.dvc` pointer and committed compact handoff facts.

If a push, content check, receipt check, or remote status fails, retain the affected local payload and stop cleanup for that batch. Do not compensate with broad DVC garbage collection.

## Correction contract

The preferred correction target is real Feral tank threat retention. Valid small corrections include a bounded change to action priority/cadence, target selection, area-threat eligibility, taunt selection, Misdirection integration, or a proven audit attribution bug. The correction must preserve:

- Strict route semantics and full 14-node evidence.
- Current-identity and uninterrupted-attempt requirements.
- Feral all-hostile retention threshold of at least 0.90.
- Healer exposure and dwell gates.
- Existing legality, cooldown, range, facing, resource, and ownership checks.
- Cohort/party/instance isolation.
- No teacher/teleport/forced completion path.

Do not add a one-off Stonecore completion hack, target a hard-coded rerun identity, suppress healer exposure events, remove eligible mobs from the denominator without a structural rule, or globally inflate threat without checking other tanks and DPS behavior.

Review the change across the runtime action resolver, rule profile/SQL, threat telemetry, role-quality audit, identity manifest, provisioning, and DVC dependencies. Batch source changes coherently; do not layer speculative fixes between unexamined reruns.

## Identity invalidation matrix

Create a fresh evidence identity and discard earlier live acceptance whenever any of these change:

- C++ source or worldserver binary
- SQL action/profile migration or live profile generation
- Acceptance, audit, threat-retention, exposure, dwell, timeout, or route policy
- Candidate provisioning, talents, glyphs, gear, consumables, pets, spellbook, or pool membership
- Worldserver configuration, schema, database snapshot, route manifest, matrix, row membership, scenario, or command sequence
- Server process/epoch, instance identity, session fingerprint, or external evidence component

A diagnosis or report-only change does not invalidate evidence if it cannot affect runtime facts or acceptance. Diagnostic login/logout and provisioning inspection do mutate candidate state; reprovision before authoritative evidence.

## Fresh runtime and canary 2 protocol

1. Confirm no worldserver or serial operator is active.
2. Implement the smallest correction and record its source/config/SQL scope.
3. Build `worldserver` through the established host build surface. Do not run tests or typechecks; validate runtime behavior through the actual worldserver surface.
4. Reapply deterministic `all_spec_candidate_pool` provisioning and verify exact party availability, aliases, talents, glyphs, gear, pets, rule profiles, and no stale leases/groups/instances.
5. Start one worldserver with `MaxActiveCohorts = 1` and one operator owner.
6. Capture a fresh composite evidence identity after the final binary, config, database, schema, profile generation, route, matrix, and provisioning state is fixed.
7. Regenerate the deterministic eight-row run plan from the committed matrix and fresh identity. Verify its hash and exact canary 2 party before execution.
8. Run canary 2 alone with the generated route-directed budget; do not use a short command-responsiveness smoke as qualification.
9. During the run, use cohort-addressed diagnostics and traces only when needed. Any diagnostic mutation invalidates candidate state for the next authoritative run.
10. Let the operator close, audit, publish, remotely verify, clean up, and evict the batch. Never manually convert an incomplete operator result into a pass.
11. Independently validate the closed capture and acceptance before deciding whether to continue.

### Canary 2 hard gate

Canary 2 passes only if all are true:

- Exact five-target party and expected composition hash
- Current binary/config/database/schema/profile/provisioning/route/matrix identity
- One uninterrupted attempt in the intended Stonecore instance
- Terminal evidence for every one of the 14 route nodes
- Real death evidence for every boss and required trash/mechanic evidence
- No timeout, machine-failure predicate, teacher/forced completion, stale identity, instance substitution, or dropped required events
- Feral identity-scoped all-hostile retention at least 0.90
- Healer target-exposure and dwell gates pass
- Generic role-quality and target-specific capability audits pass for all five targets
- Session closure and exact cleanup pass
- Raw and compact bundles are independently hashed, DVC-added, pushed, remotely verified, and receipted
- Raw/compact workspace and exact batch cache objects are locally evicted only after remote verification

If any condition fails, stop the serial sequence. Diagnose that one immutable batch before changing code or rerunning.

## Serial canaries 3-8

Only after canary 2 passes, run rows 3-8 in pinned order under the same current identity when possible. A qualifying source/config/profile/provisioning/route/policy change starts a new identity and invalidates earlier rows for the final eight-row set.

For each row:

1. Verify expected composition hash and exact party before admission.
2. Verify candidate leases, group, instance, route cursor, profile generation, and absence of prior-attempt state.
3. Run one strict uninterrupted 14-node clear.
4. Close the attempt before starting another.
5. Recompute route, role-quality, target capability, and identity acceptance without trusting stored booleans.
6. Publish raw and compact evidence separately through the single DVC publisher.
7. Verify remote hashes and receipt, then evict local raw/compact payloads and exact batch cache objects immediately.
8. Confirm cleanup and lease release before admitting the next row.

Stop at the first route, identity, isolation, role-quality, capability, publication, or cleanup failure. Infrastructure-aborted attempts are not gameplay failures, but they also do not count as passing rows.

## Phase 9 aggregate and gate closure

After all eight serial rows pass under one compatible final identity set:

1. Build a normalized Phase 9 aggregate from compact/retained evidence only.
2. Reconstruct the 31-target catalog and canonical unordered pair universe independently.
3. Recompute all 449 required pairs and 47 structural exclusions.
4. Verify the 85-row covering array has zero uncovered required pairs and valid composition-to-pair mappings.
5. Verify representation counts/bounds and that the eight serial rows cover all 31 targets.
6. Recompute strict route acceptance for every row from node/boss/mechanic facts.
7. Recompute role and target-specific acceptance for every party member.
8. Verify compatible evidence identity, current profile generation, current route/matrix, distinct batch identities, receipts, remote synchronization, cleanup, and local raw eviction.
9. Run `pixi run dvc repro all_spec_phase9_pairwise_contract`.
10. Reconcile the Phase 9 stage in `dvc.lock`; do not silently reconcile unrelated dirty stages.
11. Run targeted Phase 9 `dvc status`, repository `dvc status`, `dvc push`, and remote verification. Record the two known legacy missing hashes separately from Phase 9 results.
12. Confirm all Phase 9 SQL migrations remain tracked despite `sql/custom/world/*.sql` ignore rules.
13. Update the program-status JSON and handoff with all evidence paths, hashes, validation outcomes, cleanup state, and exact next prompt.

Phase 9 remains `in_progress` unless every item above passes.

## Mandatory independent pre-concurrency review

Run `.agents/skills/trinity-orchestrator/scripts/check-openai-models.sh --smoke`. Do not launch the mandatory reviewer until the exact smoke succeeds for `gpt-5.6-sol`; do not substitute Claude or another model.

The independent reviewer must use `gpt-5.6-sol` with high reasoning and receive immutable, compact evidence plus exact source/config hashes. It must independently assess:

- Pair-universe construction, exclusions, deterministic coverage, balance, and eight-row target union
- Evidence identity completeness and incompatibility rejection
- Strict 14-node route acceptance and boss/mechanic evidence
- Feral threat-retention and healer exposure/dwell evidence
- All party role/capability audits
- Cohort/party/instance/lease/trace/capture isolation while serial
- Batch publication, remote receipts, targeted eviction, and hydration path
- Serial performance/soak adequacy
- Whether any runtime or acceptance change weakened the approved contract
- Whether exactly two isolated parties may safely begin Phase 10

The reviewer must return an explicit approve/reject verdict, findings, evidence references, and conditions. Resolve every blocking finding and rerun affected evidence. Commit a Phase 9 completion only after approval; label it clearly as Phase 9 completion rather than a checkpoint.

## Phase 10: adaptive multi-party enablement

Phase 10 begins only after the Phase 9 completion commit and approval dossier exist.

### Initial enablement

- Start with exactly two already-passing canary compositions.
- Use separate Stonecore instances, cohorts, parties, leases, routes, capture streams, watchdogs, and evidence identities.
- Keep one worldserver owner, scheduler, capture demultiplexer, acceptance recomputer, and DVC publisher.
- Reject ambiguous global commands once more than one cohort exists.
- Do not raise concurrency beyond two until the complete two-party soak gate passes.

### Required instrumentation

- World update p50/p95/p99/max
- BotWorld total and per-cohort update duration
- Decision due-to-executed latency
- Map-update duration
- CPU, RSS, swap, service limits, and throttling
- Database query rate and latency
- SOAP/command latency and failure rate
- Capture queue depth, write latency, dropped-event count, and backpressure
- Per-party route progress and no-progress intervals
- Lease collisions, ambiguous commands, cross-cohort reads/writes, profile-generation mixing, and instance crossover
- Disk reserve, pending-unpushed bytes, oldest unpublished batch, DVC publisher latency, and publication failure state

### Admission policy

- Pause new admission on yellow load.
- Stop newest work first on sustained red load.
- Never drop required evidence to preserve throughput.
- Keep disk reserve for at least two worst-case raw batches.
- Permit at most one closed unpublished batch.
- Stop admission if the DVC publisher fails, capture loses events, swap grows materially, or isolation is uncertain.
- Raise concurrency one cohort at a time only after stable multi-hour evidence.

### Phase 10 gate

No cross-cohort state/evidence, lease collision, profile mixing, ambiguous command, capture loss, performance red-state interval, or material route/role regression during the two-party soak. Publish and independently verify the Phase 10 isolation/load dossier before Phase 11.

## Phase 11: full pairwise Stonecore campaign

Run the 85 selected covering-array compositions under adaptive admission. Use three seeded strict uninterrupted full clears per selected composition by default. Extra targeted repeats are required for failures, high variance, near-threshold role results, suspected higher-order interactions, or performance-sensitive outcomes.

A pair counts as covered only through a passing, current, strict uninterrupted attempt under the final catalog, provisioning, profile, policy, route, matrix, and evidence identities. Diagnostic segments may localize failures but never certify or repair a full-clear result. Infrastructure aborts do not count as gameplay failures or passing coverage.

Automatically schedule targeted triples/full parties for repeated buff/debuff, melee/ranged density, interrupt/dispelling, pet/pathing, threat, healing, or simultaneous-add interactions that pairwise coverage alone cannot explain.

Publish/verify/evict every closed batch immediately. The Phase 11 gate requires zero uncovered required pairs from the independent verifier, current calibration for all 31 targets, verified receipts for every accepted attempt, no isolation failure, and no accepted attempt spanning a performance red-state interval.

## Phase 12: compact readiness report

Build one static, self-contained HTML report from normalized compact DVC evidence only. Hydrate compact bundles by immutable hash one batch at a time and evict them after use. Raw logs must not be required for normal rendering.

The report must include:

- Overall readiness verdict and all current identity hashes
- A 31-target table with role, provider/revision, calibration ratio, 75/80 state, capability gates, freshness, and DVC receipt
- DPS single-target/AoE evidence
- Healer phase delivery, effective HPS, overheal/absorbs, mana, dispels, deaths, latency, targeting, and cooldown use
- Tank DPS/TPS, snap/add threat, all-hostile retention, healer exposure/dwell, mitigation, smoothing, survival, interrupts, and action validity
- Required/covered/uncovered/excluded pair matrices
- Per-target representation and composition drill-down
- Stonecore node/boss/mechanic evidence, repeats, failures, and supersession
- Concurrency, isolation, load, admission, capture, database, disk, and publisher metrics
- Epoch/profile/route/matrix lineage and on-demand DVC hydration commands
- Optimization backlog and higher-order follow-ups

Use small embedded normalized JSON plus accessible inline CSS/SVG. No network dependencies or heavyweight frontend. The report may display `ready` only after independently reconstructing the target universe, role acceptance, pair universe, strict current coverage, freshness, isolation/performance results, and every DVC receipt.

## Failure taxonomy and response

Classify each failed immutable batch before changing anything:

- Provisioning/identity
- Profile legality or missing action
- Priority/cadence
- Target selection or ownership
- Resource/cooldown/pet/form/stance behavior
- Threat pickup or retention
- Healer delivery/targeting/exposure/dwell
- Movement/range/facing/line-of-sight
- Hazard/recovery/route progression
- Encounter mechanic or TrinityCore deviation
- Isolation/lease/instance/capture contamination
- Publication/storage/infrastructure
- Audit/acceptance attribution

One owner performs the complete batch diagnosis. Use an optional second worker only for one concrete unresolved uncertainty. Do not fan out by class, spec, failure category, or review angle.

## Model routing and ownership

Before any OpenAI-backed worker or reviewer pass, run the model availability script. Use exact IDs.

- Root orchestrator: `gpt-5.6-sol`, high reasoning, direct owner by default.
- Large/high-risk runtime, evidence, DVC cleanup, concurrency, healer/tank, or adversarial review task: `gpt-5.6-sol`, high.
- Routine implementation/diagnosis/tooling: `gpt-5.6-terra`, medium or high as justified.
- Structured repetitive extraction/cross-check: `gpt-5.6-luna`, medium.

Use at most one worker by default and a second only to resolve a specific uncertainty. Worker nesting is forbidden. One live operator and one DVC publisher remain exclusive regardless of analysis workers.

## Git, DVC, disk, and security closeout for every pass

Before ending a pass:

1. Stop/verify the exact operator and worldserver unit when no longer needed.
2. Close every experiment batch and verify cleanup.
3. DVC-add raw and compact bundles separately.
4. Run targeted `dvc status`, push, remote verification, and content-hash receipt.
5. Evict only the verified workspace and exact cache objects; never broad-GC.
6. Keep raw data off disk after verified publication.
7. Update program status and this handoff with evidence, outcomes, blockers, and exact continuation.
8. Inspect Git status and ignored files. Keep generated run folders ignored while leaving real code/configuration visible.
9. Commit coherent code/configuration and DVC pointers. Never commit runtime credentials or `.dvc/config.local`.
10. Push the active branch and verify local/remote HEAD equality.

## Exact next-thread instruction

Read `AGENTS.md`, `.agents/skills/trinity-orchestrator/SKILL.md`, `.codex/plans/all_class_sc_plan.md`, `experiments/configs/all_spec_stonecore_program_status_v1.json`, and this file. Continue the approved execution program directly with Phase 9 as the only active phase. Hydrate only the minimum rerun127 evidence from the verified history archive, independently validate the capture, determine the evidence-backed cause of `role_quality:Feraltank:healer_target_exposure`, write/hash the retained diagnosis, validate and re-evict the data, implement the smallest Feral threat-retention or proven audit correction without weakening any gate, build worldserver, reprovision, capture a fresh identity and deterministic eight-row plan, and run canary 2 alone. Run canaries 3-8 only after canary 2 passes every strict route, identity, retention, exposure/dwell, role, publication, cleanup, and eviction gate. Do not begin Phase 10 until the Phase 9 aggregate, DVC contract, serial soak/isolation evidence, and mandatory independent `gpt-5.6-sol` high-reasoning approval all pass. Then continue automatically through Phases 10-12.
