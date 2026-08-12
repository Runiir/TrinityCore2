# Cataclysm raid progression handoff

## 2026-08-12T02:40:30Z — Build coordinator foundation ready for real job

The host-wide build coordinator and frozen resource policy are implemented in `tools/raid_program/queued_build.py` and `experiments/configs/cata_raid_build_resource_policy_v1.json`, exposed through `pixi run raid-build`. CMake consumes the coordinator lease identity, caps compilation at three jobs, creates one-linker job pools, and serializes link rule launch through the Git-common lock. Queue state and sanitized receipts live beneath the shared Git common directory, so all worktrees use one FIFO lease.

Eight adversarial tests pass: fan-out validation and shell-wrapper rejection; deterministic FIFO admission; queued-waiter cancellation; PID/start-time-safe stale recovery; actual killed CLI owner recovery; synthetic sustained-pressure abort with complete descendant process-group cleanup; two simultaneous CLI runs with non-overlapping admissions and canonical receipts; and common queue identity across every registered worktree. Production receipt verification rejects synthetic/test receipts. The combined coordinator, BWD research, and inherited Phase 9 qualification suite passes `15 passed`; `git diff --check` is clean. MySQL remained healthy and no worldserver/operator/publisher or compiler/linker process was active.

The coordinator has not yet claimed its real integration-build gate. Commit this foundation first, then invoke the first clean CMake configure/build only through `pixi run raid-build run`, retain and verify its production receipt, confirm zero orphan compilers/linkers and MySQL responsiveness, and update the status before proceeding to boss worktrees.

## 2026-08-11T19:34:04Z — Six-boss BWD research wave completed

Six boss-scoped `gpt-5.6-luna` xhigh turns independently revised Magmaw, Omnotron Defense System, Maloriak, Atramedes, Chimaeron, and Nefarian. Each turn was restricted to its human dossier, machine contract, and value/timer ledger; agents did not delegate, build, run live validation, mutate DB/DVC, or commit. Because the harness has three worker slots, the same three idle agent threads were reused for the second three boss-scoped turns, with fresh disjoint prompts and no inherited acceptance conclusion.

The integration owner reviewed and normalized all six packages with common contract/ledger identity envelopes, created `docs/bot_raids/README.md` and `experiments/configs/cata_raid_strategy_catalog_v1.json`, verified all 12 JSON documents, verified 25 referenced repository paths exist, and added `tests/test_cata_raid_research_contracts.py`. Focused validation passes `4 passed`; `git diff --check` is clean.

The research result is fail-closed, not a fidelity pass. The official Blizzard patch notes establish Cataclysm Classic 4.4.2 / Hour of Twilight on 2025-02-18. A public client-build table identifies 59185 as the live launch candidate, but no primary client-data extract/content hashes or exact Blizzard hotfix cutoff is pinned yet. Every boss retains material unresolved rows: timers/ranges, spell coefficients, target counts, four-mode scaling, and guide-versus-repository conflicts. The shared catalog therefore records `research_unresolved`, and all six bosses remain `fidelity_blocked`; none may be labeled `blizzlike_4_4_2_verified` or used for fixed disputed bot scheduling.

Important conflicts include Magmaw hooks/armor/parasite and heroic breath semantics; Omnotron energy/shield/rotation and heroic controller cadence; Maloriak vial/release/timer/target-count behavior; Atramedes ground-air durations, bomb counts, target rules, and Fiend cadence; Chimaeron Caustic Slime target mapping, outage probability/timing, and reset fields; and Nefarian Electrocute charge, landing/platform cadence, Dominion counts, and Shadowblaze timing.

Exact next objective: complete the queued-build coordinator tests without a heavyweight build, then pin a primary 4.4.2 client-data identity plus a 4.4.2-compatible BigWigs/DBM tag/log set to resolve or formally block each material BWD quantitative row before the Phase 0 gate.

## 2026-08-11T18:51:55Z — Phase 0 opened

The approved Cataclysm raid program is active at Phase 0. The frozen `raid_base_sha` is `889d38cc9451c2b8104db142ce069593b4647a41`, and the active integration branch is `raid/cata-raid-progression-integration`, created directly from that exact local `master` commit. Do not recreate it from `origin/master` or `all-spec-stonecore-execution`. Local `master` remains 430 commits ahead of `origin/master`; remote publication is not authorized.

The approved plan SHA-256 is `ea4cd23208fd3c3c1f2ccc533211fcd35030fb0841c35e0984bba6f03aa0e0fa`. Its ignored path is `.codex/plans/cata_raid_progression_plan.md`. The Stonecore successor evidence is inherited only as dungeon/runtime and 24-mode class-interaction evidence. The authoritative targeted-canary DVC pointer is `artifacts/all_spec_program/phase9_targeted_canary_completion_20260811.dvc`, object `38d4e71d1a4374f69fc9bf886b4df817.dir`; cache and remote were confirmed synchronized at Phase 0 start.

Initial safety checks found a clean Git worktree, no worldserver, validation operator, DVC publisher, build coordinator, compiler, or linker process, and a healthy `trinity-cata-db` MariaDB container. The host exposed 12 logical CPUs, about 30 GiB physical memory with 22 GiB available, 302 MiB swap in use, zero current memory pressure, and 46 GiB free on the repository filesystem. Broad DVC status contains inherited dependency drift and intentionally evicted outputs. The historical unavailable objects `24b9d133fe3fe1b6f253e500c266562f.dir` and `c67ee8935753b8ceccbdddbafdfebe.dir` are not new raid failures.

The stable raid contract is 25 slots: 2 tanks, 6 healers, and 17 DPS, including 12 ranged and 5 melee DPS. It preserves 24 supported modes. Feral tank is a declared offspec of the Feral DPS roster slot, not a permanent third tank; Protection Warrior remains excluded and non-blocking.

Phase 0 is not yet accepted. Exact 4.4.2 build/hotfix identities remain deliberately unresolved pending sourced research. The next coherent checkpoint is the host-wide queued-build coordinator plus frozen resource policy and adversarial queue tests, followed by the consolidated BWD dossiers/value ledgers and full raid script/DB/loader readiness audit. No boss compilation or canonical live validation may begin before the coordinator gate passes.

Exact next command-safe objective: implement `tools/raid_program/queued_build.py` and its focused Pixi tests with one heavyweight FIFO lease, three compiler jobs, one linker, an 8 GiB-or-30% memory reserve, pressure abort classification, PID-start-time stale recovery, process-group cleanup, sanitized receipts, and live-validation exclusion.
