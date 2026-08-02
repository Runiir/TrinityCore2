# All-spec Stonecore next-thread handoff

This is an in-progress Phase 9 checkpoint on `all-spec-stonecore-execution`, not a Phase 9 completion. Phases 10-12 remain blocked.

## Fixed execution constraints

- Keep Phase 9 as the only active phase and `MaxActiveCohorts = 1`.
- Keep one live operator, one worldserver, and one DVC publisher.
- Use explicit SQL/rule profiles as runtime authority; ML remains offline/shadow-only.
- Preserve the 75% calibration hard floor, 80% optimization target, true `300 +/- 5` second qualification windows where applicable, and strict uninterrupted current-identity 14-node Stonecore clears.
- Use constrained parties of exactly one tank, one healer, and three DPS. Treat Feral tank and Feral DPS separately and keep Unholy as the preferred Death Knight DPS specialization.
- Never weaken route acceptance, teleport to completion, or use teacher completion.
- Use Pixi for Python and DVC/DVCLive for experiment evidence. Publish, remotely verify, and locally evict raw evidence after every closed batch.
- Never expose credentials or commit `.dvc/config.local`.

## Checkpoint state

- The deterministic Phase 9 matrix, evidence-identity, run-plan, serial-operator, and independent-verification implementation is present in the worktree.
- Rerun127 ran canary 2 under its exact identity and party, closed normally, cleaned up, published, and remotely verified. It failed `role_quality:Feraltank:healer_target_exposure`.
- Rerun127 publication receipt SHA-256: `2e176b912ece0f45918a14d06e9509030f5800b0b2d4006da7613e3d272f6769`.
- No live operator or worldserver remains active.
- Generated Phase 9 history through rerun127 is checkpointed at `artifacts/all_spec_program/phase9_generated_history_through_rerun127_20260802.tar.zst.dvc` (DVC MD5 `9cb8af3f7a26e34e46d2100db7dd0356`, 5,525,534 bytes). Its expanded folders, local archive payload, and batch-local DVC cache have been deleted after remote verification.
- The repository-wide DVC push uploaded nine objects and warned about two older hashes that are absent locally and remotely: the stale `dataset/all_spec_phase1_catalogs` lock object `24b9d133fe3fe1b6f253e500c266562f.dir` and legacy `stonecore_strict_repair_run_053` object `c67ee8935753b8ceccbdddbafdfebe.dir`. Neither is the Phase 9 history archive. Regenerate the Phase 1 catalog through its DVC stage when reconciling current dependencies; treat the legacy 1.8 GiB repair-run pointer as unavailable historical evidence unless another verified source is found.

## Immediate Phase 9 sequence

1. Read `AGENTS.md`, `.agents/skills/trinity-orchestrator/SKILL.md`, and `experiments/configs/all_spec_stonecore_program_status_v1.json` before acting.
2. Hydrate only the history archive and rerun127 files needed to resolve a concrete uncertainty. Extract only the rerun127 subtree; hydrate its immutable raw/compact batch through its DVC pointers only if retained summaries and reports are insufficient.
3. Revalidate rerun127's exact party, evidence/runtime identity, clean session closure, cleanup, receipt, remote verification, and raw part/row counts before interpreting combat behavior.
4. Characterize the Feral tank failure precisely: hostile ownership over time, healer-target exposure and dwell, threat-margin transitions, target swaps, taunt/area-threat cadence, hazard/recovery interaction, and whether healer exposure came from threat loss, stale ownership, unreachable positioning, or audit attribution.
5. Write and hash a compact diagnosis under rerun127's retained evidence. Run the established capture validator, confirm the publication receipt and remote data again, then evict every hydrated raw/compact/archive payload locally.
6. Apply only the smallest evidence-backed correction to Feral threat retention or its identity-scoped audit if the audit is proven wrong. Do not loosen strict route, identity, exposure, dwell, or retention thresholds.
7. Build `worldserver` through the established host build surface. Do not run tests or typechecks.
8. Reapply deterministic `all_spec_candidate_pool` provisioning, capture a fresh evidence identity, and regenerate the same deterministic eight-row plan. Any source, SQL, binary, configuration, provisioning, route, matrix, timeout, or acceptance-policy change invalidates earlier live evidence.
9. Start one worldserver and run canary 2 alone. Require an uninterrupted full 14-node clear, current identity, Feral identity-scoped all-hostile retention at least 0.90, healer exposure/dwell passage, exact-party cleanup, complete DVC publication, remote verification, and local raw eviction.
10. Run canaries 3-8 serially only after canary 2 passes. Publish, verify, and evict each closed batch immediately. Stop at the first gate failure and repeat the evidence-driven diagnosis loop.

## Phase 9 closeout gate

After all eight current-identity serial rows pass:

1. Build the Phase 9 aggregate and independently reconstruct the canonical unordered pair universe.
2. Confirm required, covered, uncovered, and excluded pairs; structurally reject tank-tank, healer-healer, self, and policy-incompatible pairs; verify balance and composition-to-pair mappings; confirm the eight rows collectively represent all 31 targets.
3. Run `pixi run dvc repro all_spec_phase9_pairwise_contract`, reconcile `dvc.lock`, run targeted and repository `dvc status`, then `dvc push`.
4. Keep the three Phase 9 SQL migrations tracked despite `sql/custom/world/*.sql` ignore rules.
5. Run `.agents/skills/trinity-orchestrator/scripts/check-openai-models.sh --smoke` and launch the mandatory independent `gpt-5.6-sol` high-reasoning architecture/evidence reviewer only after the exact smoke succeeds.
6. Mark Phase 9 complete and create a Phase 9 completion commit only when every gate and reviewer approval passes.

## Phases 10-12 after Phase 9 passes

1. Phase 10: begin with exactly two isolated parties; add comprehensive load, isolation, identity, cohort, database, timing, and publication instrumentation; establish adaptive multi-party safety before scaling.
2. Phase 11: execute the full constrained pairwise Stonecore campaign, normally three seeded uninterrupted current-identity clears per selected composition, with immediate per-batch publication, verification, and eviction.
3. Phase 12: normalize compact DVC evidence and build a compact, static, self-contained HTML readiness report covering all 31 targets, pair coverage, route success, role-quality gates, identity lineage, exclusions, concurrency/isolation results, and remaining blockers.
