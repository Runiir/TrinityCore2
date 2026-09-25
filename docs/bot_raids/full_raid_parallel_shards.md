# Full-raid bots: parallel boss shards

Status (2026-09-25): foundation round 1 is done; round 2 is in progress. Seeded lockouts and parallel shards are
proven live. Only Magmaw 10N has a real bot strategy; the other bosses start with the boss rounds.
Goal: every boss of every Cataclysm raid is played by bots, then a full end-to-end
clear (trash, bosses and interactions). Blackwing Descent 10N comes first; Bastion of
Twilight, Throne of the Four Winds, Firelands and Dragon Soul reuse everything here.
Nothing in this document may be BWD-specific unless it lives in per-raid data.

## Finish line (user, 2026-09-25)

A fresh agent receives only a plain request such as `implement bwd 10n bots` and
carries the whole raid to completion on its own: parallel boss shards, synchronized
rounds with one build each, and the end-to-end clear with trash and interactions. The
program stops once we are confident this works. BWD 10N is the canary; the other raids
then run from the same prompt shape.

This means every piece here must be reachable from the raid-level workloop and from
the skills and AGENTS.md routing a fresh agent reads, with no knowledge carried over
from the session that built it. Today `raid_workloop start "implement bwd 10n bots"`
fails with `unknown or ambiguous boss/raid: bwd`: the workloop, AGENTS.md and the
orchestrator skill are boss-level only.

## Decisions (user, 2026-09-25)

- **Parallel boss shards.** Each boss is developed and run in its own lockout (its own
  instance ID, like a fresh group) where exactly its prerequisites are already dead.
  Examples: Nefarian's shard has the five other BWD bosses dead. Maloriak's shard has
  Magmaw and Omnotron dead, which opens the lower wing. Shards never share or pollute
  data: separate instance, group, bot pool, captures and records.
- **Rounds.** Agents change code in parallel with disjoint file ownership. Then one
  build covers every change, all shards run live in parallel, each part analyzes its
  own results, and the cycle repeats. Only the coordinator commits, builds and runs
  servers.
- **One composition per raid.** Every shard uses duplicate characters (a separate GUID
  set) with identical gear. Bots switch spec per boss and carry the needed gear in bags.
- **The composition optimizes raid buffs and debuffs, not class uniqueness.** Tanks are
  a Blood DK, plus a Feral druid when a second tank is needed (the druid's other spec is
  Balance). A Protection Paladin is added only for three-tank bosses.
- **Canonical 10N composition** (proposed by the user):

  | Character | Default spec | Other spec |
  | --- | --- | --- |
  | Death Knight | Blood (tank) | — |
  | Druid | Balance | Feral tank (two-tank bosses) |
  | Hunter | Beast Mastery | — |
  | Mage | Fire | — |
  | Paladin | Holy | — |
  | Paladin | Retribution | — |
  | Priest | Discipline | — |
  | Rogue | Assassination | — |
  | Shaman | Elemental | Restoration (three-healer bosses) |
  | Warlock | Demonology | — |

  **Buff coverage.** Scored against the 20 buff and debuff categories of WoWSims
  `ui/core/components/inputs/buffs_debuffs.ts` at the pinned provider revision
  `70d87383a9b92f30fb9e370c4676d3ce33b6e6b6`. Providers come from the client DBCs:
  Talent, TalentTab, SkillLineAbility, CreatureFamily and SpellEffect.

  | Configuration | Coverage | Missing |
  | --- | --- | --- |
  | 1 tank, 2 healers (default) | 19/20 | 30% bleed. The hunter pet covers 4% physical damage instead. |
  | 2 tanks (druid Feral) | 19/20 | 5% spell haste. The shaman picks Windfury or Wrath of Air. |
  | 3 healers, shaman Resto | 18/20 (1 tank), 19/20 (2 tanks) | 4% physical damage |

  25-man compositions follow the same method; buffs stack more easily there.

## Findings (foundation audit, 2026-09-25)

1. **Lockouts.** Admission always makes a fresh instance: the first bot creates a group,
   enters with no bind, and the core allocates a new instance
   (`BotMgrLoading.cpp:198-245`, `MapManager.cpp:198-221`). Nothing seeds bosses as dead.
   - `tools/raid_program/bwd_shard_fixtures.py` stores predecessor metadata that nothing
     reads. It has a linear Maloriak→Atramedes→Chimaeron chain that the script does not
     require, and it lists Omnotron as 42166 (Arcanotron) instead of 42186.
   - The BWD script (`instance_blackwing_descent.cpp`): boss indices are 0 Magmaw,
     1 Omnotron, 2 Chimaeron, 3 Atramedes, 4 Maloriak, 5 Nefarian. The inner door opens
     when Magmaw and Omnotron are done. Nefarian needs the other five done (spawn group
     402). The save data is the header, the boss states, then a raw-byte Atramedes intro
     value.
   - Free instance IDs are read only at startup (`MapManager.cpp:425-436`), so seeding
     with SQL while the server runs collides IDs.
2. **Concurrency.** Native callbacks already resolve their cohort by lease and
   map/instance, and the update loop scopes each cohort over a frozen set. What remains:
   - the process-wide `_selectedCohortId` fallback in `Cohort()`;
   - the separate `SELECT LAST_INSERT_ID()` ID race (`BotExperimentCoordinator.cpp`,
     `BotTelemetryBuffer.cpp`);
   - shared learning and semantic writes;
   - unguarded `.botauto rotations reload|rollback` and `botexp`;
   - `MaxActiveCohorts = 2`, and concurrent admission requires `MapUpdate.Threads <= 1`;
   - the Python harness runs one scenario per worldserver.
3. **Roster and provisioning.**
   - The shard generator is hard-coded to 6 BWD shards (60 bots,
     GUID `30000 + shard*100 + slot`).
   - Provisioning writes talent group 0 only and puts nothing in container bags, and the
     readbacks check only bag 0 and group 0.
   - Admission treats any post-admission spec or gear change as a fatal identity failure.
4. **Routes and interactions.** `validation_scenarios_cata_001.json` has a 23-step full
   BWD route, but it can't run:
   - `ALLOWED_ROUTE_KINDS` (`canonical_route_catalog.py:26`, and a copy in
     `run_live_bot_validation.py:971`) drops `interaction` rows.
   - The completion kinds `intro_complete_and_elevator_ready` and
     `player_in_nefarian_arena` are parsed but never evaluated.
   - A `native_walk_jump_or_fall` descent always stops the run.
   - The shard and full-raid rows have drifted apart.
   - Bot-side interaction already works: the lowest-GUID bot walks to the object, then
     uses it or opens the gossip and selects the option
     (`BotWorldPopulationMgrUpdateBotKernelPreparation.cpp:308-391`).

## Round 1 (foundation)

Round 1 changes must be **validation-neutral**. The accepted Magmaw 10N scenario (a fresh
instance, one cohort, roster 30001-30010) must behave exactly as before. Every new path is
opt-in. After the single build, the coordinator runs a Magmaw smoke kill, then the proof run.

### Work packages and file ownership

An agent edits **only** the files it owns plus new files under its prefix. It needs a
change in another file? Then it writes the exact patch into its handoff and does not edit.
The coordinator applies wiring lines such as command-table entries and CMake lists.

**A. Seeded lockouts.** Owned files:
- new `src/server/game/Bots/BotRaidLockout*.{h,cpp}`;
- new `src/server/scripts/Commands/cs_botauto_lockout.cpp`;
- `BotWorldPopulationMgrValidationAdmission.cpp`, `BotWorldPopulationMgrValidationProfile.cpp`,
  `BotWorldPopulationMgrValidationCohortGroup.cpp`, `BotWorldPopulationMgrRuntimeContracts.h`;
- `BotMgrLoading.cpp`, `src/server/game/Instances/*`, `src/server/game/Maps/MapManager.*`;
- new `experiments/configs/raid_prerequisites/*.json`;
- new `tools/raid_program/raid_prerequisites.py`;
- new tests `tests/test_raid_prerequisites*.py` and `tests/test_bot_raid_lockout*.py`.

Deliver:
1. The per-raid prerequisite graph (schema below). BWD is complete and verified against
   the native script. Add the other raids where their scripts exist.
2. An in-server seeder. It allocates an instance, creates the save, marks exactly the
   requested bosses done (boss states, `completedEncounters`, script extra values),
   writes the save, and binds the shard's group permanently.
3. An admission option that makes a cohort's group bind to, and its bots enter, the seeded
   instance instead of a fresh one. The shard reset keeps that bind.
4. Readback before bots act: boss states and instance ID match the request, and the
   state is marked `diagnostic_only_assistance`.
5. Teardown: unbind and delete.

**B. Parallel cohorts and the shard harness.** Owned files:
- `BotWorldPopulationMgrCohort.cpp`, `BotWorldPopulationMgrCohortScope*.{h,cpp}`,
  `BotWorldPopulationMgrLifecycle.cpp`, `BotWorldPopulationMgrUpdate.cpp`;
- `BotWorldPopulationMgr.h` (990 lines: split it before adding anything);
- `BotExperimentCoordinator.{h,cpp}`, `BotTelemetryBuffer.{h,cpp}`,
  `BotClassSpecActionProfileDb.cpp`, `BotExperienceLearningPolicy.{h,cpp}`,
  `BotWorldPopulationMgrSemantic.cpp`;
- `BotWorldPopulationMgrPlay.{h,cpp}`, `Content/.../Magmaw/BotMagmawBaiterRotation.h`;
- `src/server/scripts/Commands/cs_botauto.cpp`;
- `tools/raid_program/run_live_bot_validation.py`, `scoreboard_run.py`,
  `shared_instance_validation.py`, `run_shared_instance_canary.py`;
- new `tools/raid_program/shard_coordinator.py` and `tests/test_shard_coordinator*.py`;
- tests for the files above.

Deliver:
1. Up to 6 active cohorts, with `MapUpdate.Threads` still 1 in round 1.
2. No fallback to the process-wide selected cohort. Replace the swaps with scoped
   cohorts, and make `Cohort()` fail without a scope.
3. Insert and `LAST_INSERT_ID` on the same connection.
4. Rotation reload/rollback and `botexp` refused while any cohort is active.
5. Learning and semantic writes off (or keyed by cohort) for shard runs.
6. The Magmaw baiter registry cleared when a cohort stops.
7. `run_live_bot_validation.py` imports `ALLOWED_ROUTE_KINDS` from
   `canonical_route_catalog` instead of keeping its own copy (package D owns the
   constant).
8. `shard_coordinator.py` drives one worldserver with N shards. It alone owns
   stdin. It seeds lockouts through package A's commands (the contract below), creates and
   starts each cohort with its own profile, polls cohort-qualified
   status/diagnose/trace, demultiplexes output into one run directory per shard, and
   stops everything cleanly. Each run directory must be ingestible with
   `scoreboard ingest`.

**C. Composition, copies and loadouts.** Owned files:
- `tools/raid_program/bwd_shard_fixtures.py` (generalize it, or add a raid-generic
  successor and keep the old one as a thin wrapper);
- `experiments/configs/validation_provisioning_cata_001.json`,
  `experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json`;
- `tools/bot_ml/build_validation_provisioning.py`, `tools/bot_ml/validate_validation_provisioning.py`,
  `tools/bot_ml/build_validation_gear_profiles.py`, `tools/bot_ml/build_validation_scenario_manifests.py`;
- `tools/raid_program/capture_phase1_provisioning_readback.py`, `tools/raid_program/scenario_catalog.py`;
- their tests.

Deliver:
1. The shard generator as raid × boss × N copies, with no BWD or 6/60 hard-coding.
   Per-copy GUID, account, pet and item ranges. Names are letters only. Per-copy pool
   tags and profile IDs. Precompleted bosses come from package A's prerequisite files.
2. The canonical composition above declared for BWD 10N as a new composition. Do
   **not** replace the accepted Magmaw roster 30001-30010 in round 1; it moves to the new
   composition in the first boss round.
3. A loadout model:
   - `talentGroupsCount = 2`, with talents and glyphs for both groups;
   - off-spec gear in container bags (real bag items in bag slots plus
     `character_inventory` rows with bag ≠ 0);
   - both readbacks extended to talent group 1 and bag ≠ 0.
4. Per-boss spec selection before admission. The shard chooses each character's active
   spec, the active group and the equipped set are written before the bot logs in, and
   the pool's `class_spec` follows. Keep it in Python/SQL/config. If admission identity
   or C++ must change, write that into the handoff.
5. Check that WoWSims P4 gear profiles exist for the new specs (BM hunter, Ret,
   Assassination, Demonology, Feral tank, Resto shaman). List the gaps.

**D. Route interactions and full-raid composition.** Owned files:
- `BotWorldPopulationMgrValidationRouteManifest.cpp`, `BotWorldPopulationMgrValidationRouteRuntime.cpp`,
  `BotWorldPopulationMgrValidationRouteTerminalArrival.{h,cpp}`,
  `BotWorldPopulationMgrUpdateBotKernelPreparation.cpp`, `BotWorldPopulationMgrNativeAction.cpp`,
  `BotNativeActionIntent.h`, `BotWorldPopulationMgrEncounterBlackboard.cpp`;
- `tools/raid_program/canonical_route_catalog.py`, `canonical_route_staging.py`;
- `experiments/configs/validation_scenarios_cata_001.json`;
- new `tools/raid_program/raid_route_composer.py`;
- their tests.

Deliver:
1. `interaction` in `ALLOWED_ROUTE_KINDS`, with the tests that assert the drop updated.
2. Every completion kind the parser accepts is evaluated; reject the rest. Add
   `gameobject_despawned`, `instance_boss_state`, `on_transport` and `vehicle_seated`.
3. Generic interaction fields:
   - the owner by role or roster slot, plus a backup (not lowest GUID);
   - the target by entry or spawn ID, with an ambiguity check;
   - `spellclick`, `vehicle_enter` and `area_trigger` actions;
   - a timeout and retry;
   - whether the group gathers.
   Also add a range check to `GameObjectUse` and honour the seat for `VehicleEnter`.
4. A transport route kind (elevator, slipstream): wait for the transport, board, and
   confirm the bot is on it. It replaces `native_walk_jump_or_fall` for BWD's Nefarian
   descent.
5. `raid_route_composer.py` builds the full-raid route from per-boss node sets, keeps node
   IDs, and reports duplicate or conflicting rows. Fix the Magmaw shard/full drift
   without changing the accepted Magmaw shard behaviour.

### Contracts between packages

- **Prerequisite file** `experiments/configs/raid_prerequisites/<raid>.json`:
  `{schema: "raid_prerequisites_v1", raid, map_id, difficulties, script_header,
  bosses: [{key, boss_index, creature_entry, credit_entry, dungeon_encounter_bit,
  predecessors: [key...], extra_save_values: {...}}], save_extras: [...]}`.
  Package A writes it. Package C reads `predecessors` to compute a shard's precompleted
  set, as the transitive closure.
- **Lockout commands** (package A; the coordinator wires them into `cs_botauto.cpp`):
  - `.botauto lockout seed <cohort> <raid> <difficulty> <boss-key,...|none>` returns
    JSON with `ok`, `instance_id`, `map_id`, `bosses_done` and `failure_reason`.
  - `.botauto lockout status <cohort>` returns the same JSON after readback.
  - `.botauto lockout clear <cohort>` unbinds and deletes.

  `.botauto start <cohort> <profile>` then admits the cohort into that lockout.
- **Cohort and profile naming:** the cohort ID is `<raid>_<size><diff>_<boss>_c<copy>`, and
  the pool tag and profile ID are the same string with the `_diagnostic` suffix used today.
- Records carry `cohort_id`, `instance_id` and the lockout's precompleted set, so no
  scoreboard record mixes shards.

### Rules for every agent

- Work in `/home/runiir/Games/trinity-cata` (master). Do not create worktrees, commit,
  stash, reset, checkout, build, or start or stop any server.
- Other agents edit other files in the same checkout at the same time. Never touch files
  you don't own, and never run formatters over directories.
- Keep C/C++ files below 1,000 lines; split by concern. Match the surrounding code.
- Use Python through `pixi run`. Run only your focused tests: `pixi run python -m pytest -q <your tests>`,
  plus header-only g++ tests in the existing style. Report any pre-existing failures.
- Stay lawful. Never invent auras, buffs, damage, teleports or casts. Seeding a lockout is
  diagnostic assistance and is marked as such; it never certifies a natural clear.
- Handoff: a JSON block with `changed_files`, `new_files`, `tests` (command and result),
  `patch_requests` (for non-owned files), `validation_neutrality` (why the accepted Magmaw
  scenario is unchanged), `risks`, and `open_items`.

### Proof run (after the round-1 build)

1. Magmaw 10N smoke kill through the scoreboard (validation neutrality).
2. One worldserver with two shards at once:
   - Magmaw 10N on a fresh lockout, killed natively;
   - a Maloriak shard on a seeded lockout (Magmaw and Omnotron done). Readback shows
     boss states 0 and 1 done and the inner door open. Bots are admitted into the
     seeded instance and reach their regroup node.

   Distinct instance IDs, separate run directories and records, and no cross-cohort
   attribution.

## Round 1 results (2026-09-25)

- **Packages:**
  - A, seeded lockouts: `dae6c1a7bb`, `d9843cddb9`, `18d0d47865`, `3dea9d6dc2`.
  - B, parallel cohorts and the shard coordinator: `1734c60404`, `c05f8e3772`, `db90d5289f`,
    `72628abfb6`.
  - C, compositions, copies and loadouts: `a63f7ef57a`, `2658d41c59`, `15104b10dd`.
  - D, route interactions, transports and the composer: `38b67b22ea`, `b1bcaccdb5`,
    `3ca8259e51`.

  Each package has coordinator wiring commits and at least two independent review passes.
- **Build and data:**
  - Builds now use the `host10` policy (10 jobs, two CPUs left free).
  - Data are reproduced and the closure rebound in `6ed2ad9077`.
- **Magmaw smoke** (`smoke-r1-6ed2ad9`): native clear, 0 deaths, 100.8 s kill, 279.7k party
  DPS. The single-cohort accepted scenario is unchanged.
- **Two-shard proof** in one worldserver (plan `experiments/configs/shard_runs/bwd_10n_round1_proof_v1.json`,
  evidence `artifacts/cata_raid_program/round1_two_shard_proof_20260925.tar.gz.dvc`):
  - **Magmaw c0**, fresh instance 4: the full route completed, 273.7k party DPS (learning off
    under shard isolation).
  - **Maloriak c0**, seeded instance 1:
    - Magmaw and Omnotron done (states `[3,3,5,5,5,5]`, mask 36, diagnostic-only assistance);
    - admitted into the seeded instance, reached its regroup area and cleared 2 trash packs
      with 0 deaths;
    - then stopped on the progress-plateau watchdog, because its strategy is still a stub.
  - **Isolation:** distinct instance IDs, 0 cross-cohort replies, 0 foreign payloads, and the
    seeded instance was entered.
  - **Teardown:** verified, with the lockout cleared.
- **Open from round 1:**
  - **Transport movement support.** The Nefarian ledge-to-platform drop and the lower-wing
    elevator lip are off the static navmesh, so those transport nodes fail with a typed
    reason on their timeouts. They need a lawful jump/fall and platform-surface movement
    design.
  - **Magmaw to the canonical composition.** Move Magmaw over: runtime profiles, route
    rows, the `raid_shard_provisioning` DVC stage, and a closure rebind.
  - **LAST_INSERT_ID readers.** Run, activity and replay IDs still rely on
    `MapUpdate.Threads = 1`; convert them before raising the thread count.
  - **Catalog error.** The demonology_warlock profile lists 33697 (the shaman's Blood Fury).
  - **Minor review notes:**
    - coordinator: the drain timeout doubling, the dirty-console run status, and a vacuous
      test assertion;
    - A: the header wording about the map unload.
  - Final re-review of the C and D second fixes (approved) left three minor notes:
    - a provisioning plan built before `15104b10dd` passes the source-drift check silently,
      so refuse plans without the new source records;
    - the auto-learned spell baseline is a superset of what the core teaches (skill
      ownership, rank rules). No current spec is affected; add an overlap test;
    - `transport_member_floor_unverified` holds until the node timeout; fall through to a
      re-snapping move instead.
  - C's and D's second fixes (`15104b10dd`, `3ca8259e51`) are not in the round-1 binary
    (built at `72628abfb6`). They go into the next build.
  - Round rule learned: no agent edits while a build is in flight, because any worktree or
    HEAD change aborts it on provenance.

## Round 2 (2026-09-25): every remaining boss in parallel, plus the raid-level workloop

The user approved round 2 and asked for one agent per remaining boss. Eight
implementation packages run at once. No agent runs live kills. After all eight land,
the coordinator does one build, reproduces the DVC data, rebinds the closure and runs
every BWD shard in parallel in one worldserver.

### Packages and file ownership

The round-1 rules still apply: edit only owned files, send changes to other files as
`patch_requests`, and make no git writes, builds, servers or DVC writes.

**R. Raid-level workloop.** Owns:
- tools/raid_program/raid_workloop.py and new tools/raid_program/raid_program*.py;
- the trinity-orchestrator, raid-tuning-playbook and raid-shard-architecture SKILL.md
  files and their references (not the user's untracked `raid-shard-architecture/references/`);
- tests.

`AGENTS.md` changes go in as patch requests. Deliver `raid_workloop start "implement bwd
10n bots"`, which selects a data-driven raid program:
- one unit per boss shard, using the prerequisite DAG, the composition and the shard
  cohort IDs;
- a round state machine: parallel implementation, one build, parallel shard runs through
  `shard_coordinator`, per-boss assessment;
- an end-to-end acceptance unit.

Also deliver `resume` and status readouts. Other raids resolve with their missing inputs
listed. The boss-level flow (Magmaw's saved graph) must keep working.

**T. Transport movement.** Owns:
- the movement planner (BotWorldPopulationMgrMovementPlanner*.{h,cpp},
  BotWorldPopulationMgrNativePath*.{h,cpp}, BotNativePathCheckpoint.h);
- round-1 package D's transport code: BotWorldPopulationMgrValidationRouteBoardingAction.*,
  BotWorldPopulationMgrValidationRouteNativeFacts.*, and the transport parts of
  BotValidationRouteNative{Logic,Contract,Types}.h and
  BotWorldPopulationMgrValidationRouteNativeRuntime.cpp;
- BotWorldPopulationMgrValidationRouteTerminalArrival.*;
- tests.

Deliver lawful movement onto a transport surface that lies off the static navmesh, and
a lawful ledge drop (walk off, native fall, fall damage) for the Nefarian platform. Fix
the `floor_unverified` hold note. No teleports.

**M. Canonical composition activation and Magmaw migration.** Owns:
- experiments/configs/validation_scenarios_cata_001.json, dataset/bot_runtime_profiles/profiles.json
  and dvc.yaml;
- experiments/configs/raid_compositions/**;
- tools/raid_program/shard_coordinator.py, tools/raid_program/raid_shard_*.py,
  tools/raid_program/raid_loadout*.py and tools/bot_ml/build_validation_scenario_manifests.py;
- the Magmaw content directory (Encounters/Magmaw/**) and the Magmaw raid target;
- tests.

Deliver:
- the `raid_shard_provisioning` DVC stage;
- runtime profiles and scenario rows for the canonical c0 cohort of all six BWD bosses;
- shard_coordinator provisioning through the guarded apply path;
- the Magmaw duty plan remapped from fixed slots to capabilities for the canonical
  composition (baiters, chain riders, mushrooms, lust, pull tank);
- C's two minor notes.

Apply boss agents' patch requests for scenario rows and spec selections as they arrive.

**Boss packages O (Omnotron), MA (Maloriak), AT (Atramedes), CH (Chimaeron), NE (Nefarian).**
Each owns:
- its `Content/Raids/BlackwingDescent/Encounters/<Boss>/**`;
- its native script `src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent/boss_<boss>.cpp`;
- its research files: `experiments/configs/cata_raid_encounters/blackwing_descent/<boss>_*`
  (contract, ledger, new WCL reference and cast-timeline files) and its dossier
  `docs/bot_raids/strategies/t11/blackwing_descent/<boss>.md`;
- a new `experiments/configs/raid_targets/blackwing_descent_10n_<boss>.json`;
- new staged SQL under `sql/custom/staged/world/` named for the boss;
- new `tests/test_<boss>_*.py`.

Patch requests go:
- to M for its shard's scenario rows and the per-boss spec selection in the composition;
- to the coordinator for `instance_blackwing_descent.cpp`, the strategy dispatch
  (`BotWorldPopulationMgrUpdateBotKernelPreparation.cpp`, `BotWorldPopulationMgr.cpp`)
  and `experiments/configs/encounter_fidelity/creature_damage_calibration_v1.json`.

Each boss agent delivers a live-attempt-ready shard:
1. Research: follow the raid-encounter-research skill, including WCL references by
   browser extraction.
2. Native script: audit the script against it and fix it.
3. Encounter damage fidelity: calibrate it (staged SQL plus a registry patch request).
4. Raid target: write the target file.
5. Strategy: replace the stub with a real strategy for the canonical composition,
   following the raid-encounter-implementation skill.
6. Tests.

Boss notes:
- Omnotron has no prerequisites and fights two tanks.
- Maloriak, Atramedes and Chimaeron need Magmaw and Omnotron dead. Atramedes's dwarven
  spirits and bell intro stay unseeded. Chimaeron needs the Finkle gossip.
- Nefarian needs all five dead, the orb, and T's descent.

### Round 2 contract: transport movement (package T)

- **Route rows.** A transport contract may declare `approach`. `wait_point` is not
  allowed next to an approach.
  - **`surface_walk` {start_point}.** The member waits at the start point on the navmesh
    lip. Once the platform is ready, and its remaining rest covers the walk plus 550 ms,
    it walks one checked straight segment to the board point on the platform's own
    model, then boards.
  - **`ledge_drop`** {start_point, step_off_point, landing_z, landing_tolerance_yards,
    landing_surface transport|static, min_health_after_fall_pct}. The member waits at
    the lip, then steps off where its whole footprint has left the lip. It falls with
    `MotionMaster::MoveFall` and reports the landing (MSG_MOVE_FALL_LAND, so
    `Player::HandleFall` applies fall damage), then boards.
  - **Riders with an exit.** With an approach and an exit, a rider crosses the car to
    `disembark_point` in one checked walk and leaves over static ground there.
  - **Cohort barrier (ledge_drop).** Nobody steps off until every living route member
    is at the lip on a verified floor and healthy enough for the fall, or already
    dropping or aboard (`transport_drop_waiting_for_cohort`). A member on a floor-probe
    miss re-snaps first. A timeout names the member holding it
    (`native_transport_timeout:waiting_for_cohort:<guid>`).
  - **`completion_override`.** An optional `instance_boss_state` contract (or
    `any_of`/`all_of` of them; no `timeout_ms`, no exit), for example on
    `bwd.nefarian.descent` with boss index 5 `in_progress`. It is a fail-fast guard,
    not an early completion: the node still completes only when every member is
    aboard, and the barrier makes everyone drop together. The guard arms once the boss
    state holds with a member aboard (a stale state with nobody aboard, or one that
    stops holding, disarms it). Armed, it waits for members mid-walk, mid-step,
    mid-fall or landed but unboarded, and fails the node when a living member is
    neither aboard nor in flight 2 s after arming
    (`transport_completion_override_member_not_aboard:<guid>`). Without a resolved
    platform it reports `transport_missing` or `transport_ambiguous`.
  - **Walk supervision.** A walk or step in flight is stopped and re-planned when its
    generator is suspended, when the member leaves a 1.25 yd corridor around the
    declared line, or when the rest no longer covers the rest of the walk plus 250 ms.
    A member already on the car stops and boards at once.
  - **Falls.** A landing with no floor under the feet falls on from there (not counted
    toward `max_submissions`, nor is a root holding it); the landing is reported only
    onto a verified floor.
  - **Legacy rows.** A settled member with no floor within tolerance that never stood
    on the platform no longer holds until the node timeout. It re-snaps with an ordinary
    navmesh move up to 3 times when some floor lies within 1.6 yd, then fails
    (`transport_member_floor_unverified`); with no floor near it fails at once
    (`transport_member_airborne_without_floor`).
- **Encounter seam.** `BotNativeAction::TransportSurfaceMove` (executor
  `BotTransportSurfaceMovement::Execute`, header BotWorldPopulationMgrNativePathTransportSurface.h).
  - **`Walk` to a point:** EndOnTransport is true for a point on the platform and false
    for static ground (then the walk must start aboard or on the platform's floor).
    Passengers stay passengers, and the platform must be stationary and move only
    vertically. A new Walk replaces a running one and is checked from where the member
    is now; it is refused only under a controlled effect, while falling, or while
    rooted or stunned. Legs stay at most 12 yd (`native_surface_walk_length_invalid`).
  - **`StepOff`, then `Fall` once settled with no floor, then `Land`** once
    `BotValidationRouteBoardingAction::NativeFallLandingPending`: works from static
    ground or from a raised part of the same transport, such as a pillar top.

  Each stage re-checks floor, collision and landing, and otherwise returns a typed
  Retryable/Unsafe reason. It cannot swim or climb.
- **Nefarian geometry (client data).** No static navmesh covers the platform (the lava
  navmesh lies at z 3.0), so ordinary Move intents are rejected there; use the seam.
  - The model frame is world rotated by pi about (-107.213, -224.62).
  - The centre floor is at local z -0.5..+0.1, rising to +1.44 at r 32-60 (the outer
    ring, world z 8.47 when raised).
  - Pillar blocks sit at headings 0/120/240 deg, r 36-44, with tops at +9.925 and
    near-vertical sides.
  - The ledge lip is at x -157.65. A ledge drop lands on the outer ring at z 8.51 (a
    32.8 yd fall, 34.9% of max health).

### Coordination rules for round 2

- Use `raid_workloop start --preview` or `raid_workloop boss ...` read-only. Only the
  coordinator (and later R's raid program) selects or advances the saved graph.
- Keep CPU load modest: focused tests only, and prefix heavy commands with `nice -n 10`.
  The user keeps four CPUs free: builds use the `host8` policy (8 jobs, exact `--parallel 8`).
- No edits after your handoff. The coordinator builds only after every agent has
  finished, and any edit during a build aborts it.

### Round 2 integration checklist (coordinator)

The full handoffs, with patch texts, are in `.git/round2_patches/<package>/handoff.md`.

1. Land every package's review fixes and re-reviews first.
2. Shared dispatch files, applied in this order by one owner. Each patch's handoff
   names its merge points. Never use `patch -F3`: it silently misplaces hunks.
   - Atramedes P1-P6 (clean on HEAD).
   - The Chimaeron dispatch patch with `patch -p1`, leaving out the blackboard file.
     `UpdateContext.h` takes fuzz 1. For `EncounterBlackboard.cpp`, apply
     `chimaeron_encounter_blackboard_after_atramedes.patch`, which applies cleanly.
   - Omnotron right after Chimaeron: run
     `.git/round2_patches/omnotron/apply_omnotron_dispatch.py <tree>`. It anchors
     after Chimaeron's declarations and route observation. `KernelCandidates.cpp`
     goes from 967 to 862 lines.
   - Nefarian R1-R5 and W1 (R3 brings `KernelCandidates.cpp` to 915; Nefarian may move
     its block into its own TU).
   - M's MP1 and MP2 (MP2 carries the Bloodlust owner fix).
   - Maloriak's `maloriak_dispatch.patch` applies at `-F0` last, with no hand merge.
     Then apply `maloriak_dispatch_dead_code_removal.after_round2_stack.patch`
     (`KernelCandidates.cpp` goes to 809 lines).
   - Never stage an intermediate tree. Applying Nefarian R3 before Omnotron's
     extraction takes `KernelCandidates.cpp` to 1,020 lines, which the module-size
     hook rejects. Land the whole merge in one commit.
   - The arbitration replay (`tests/test_bot_action_arbitration.py`) must get past the
     older Magmaw `pillar_bait_switch` and `StackSeparation` assertions, so the
     Atramedes, Chimaeron, Omnotron, Maloriak and Nefarian sections run. Also land
     Atramedes' `arbitration_test.patch` and Nefarian's R5.
   - After the round: replace the three kill-credit observers (Maloriak's Fallback
     branch, Omnotron's route authority, Chimaeron's route observation) with one
     table-driven observer, keeping Magmaw's key and reason strings byte-identical.
     Also factor out the offense-suppression near-copies.
3. Done in 145b98826d: fidelity registry rows for all five bosses (83 rows appended) and
   the Omnotron catalog count going to 10. Still to do: regenerate
   `cata_raid_bwd_quantitative_resolution_audit_v1.json` (and the blocker total in its
   test) from the round-2 ledgers, since the boss agents renamed their unresolved keys.
4. Decide on the staged Atramedes SQL (Devastation targets the Noisy player).
5. Configure CMake again (new TUs: `boss_atramedes_spells.cpp`,
   `boss_nefarians_end_{adds,spells}.cpp`, Chimaeron and Omnotron candidate TUs, and the
   Maloriak and Omnotron spell splits). Master does not compile until the Chimaeron
   dispatch lands, because `ChimaeronCandidates.cpp` needs it.
6. Focused tests, then ONE build (host8, fresh configure ticket, no agent edits).
7. DVC: apply MP4-MP6, delete the stale untracked `dataset/raid_shard_provisioning`,
   then `dvc repro validation_scenarios`. That also runs `validation_provisioning`,
   `validation_provisioning_verify` and `raid_shard_provisioning` (now with
   `full_c0`). Push, then rebind the closure manifest (`validation_routes` and
   `runtime_profile_source`) and commit. The steps are in
   `.git/round2_patches/m/handoff_fix_pass.md`.
8. Magmaw smoke on the canonical roster, then the six BWD c0 shards in parallel through
   the raid program (`program run-plan`, `shard_coordinator`, `program run`,
   `program ingest`, `program assess`).
9. Done: the AGENTS.md routing and the `development_graph.md` note landed in
   d335b6a506, after R's approval.

## Round 2 results (2026-09-25)

- **Approvals:** R, T, Omnotron, Maloriak, Chimaeron, Atramedes, Nefarian and M were
  approved after 1-5 review passes each.
- **Integration:** c0efb93a61 (one change set, no hand-merges). DVC: b969995aca
  (provisioning, raid shard plans with 7 shards and 70 bots, scenarios, closure rebind).
  Build: worldserver c0efb93a6158 through host8. Evidence: `round2_batch1_20260925.tar.gz`
  in DVC.
- **Magmaw smoke** (canonical roster, c0 alone): a native clear in 120.7 s at 234k raid
  DPS, with no deaths, stalls or loops. It found two problems: the Assassination rogue
  used no rogue abilities (3k DPS, auto-attack only), and the assigned Elemental shaman
  never cast Bloodlust.
- **Six-shard parallel batch** (one worldserver, instances 8/19/1/3/5/6, zero
  cross-cohort traffic), no clears:

  | Shard | Ended as | Reason |
  |---|---|---|
  | Magmaw | machine failure predicate | `bot_diagnosis_error`, after boss kill evidence |
  | Omnotron | plateau | `validation_route_future_encounter_contamination`, never engaged |
  | Chimaeron | action gate | `native_interaction_timeout` (Finkle or the wake) |
  | Atramedes | plateau | 199 trash pulls, never engaged |
  | Maloriak | machine failure predicate | `bot_diagnosis_error` after 3 kills |
  | Nefarian | action gate | `transport_submissions_exhausted` before the encounter |

  Round 3 starts with the per-boss analysis of these runs.

## Round 3 candidates (from the round 2 reviews)

- **Nefarian:** a lawful pillar ascent (swimming onto a pillar top) and the pillar-top
  descent (StepOff, Fall, Land). Phase 2 fails typed (`pillar_ascent_unsupported`)
  until these exist. Pillar path clearance (7 yd) is safe for body radius up to 1.0 yd.
  Derive it from the roster's largest radius before any Tauren (1.27 yd) joins the
  Nefarian roster.
- **Maloriak:** melee hold near a sphere parked by the boss (35-41% uptime in replay).
  The main tank should drag Maloriak at least 6 yd away from it.
- **Shared code:** one table-driven kill-credit observer (replacing the Maloriak,
  Omnotron and Chimaeron copies, with Magmaw's strings kept byte-identical), one
  offense-suppression helper, and the arbitration replay's older Magmaw assertions.
- **Atramedes:** the first live run must confirm that the Take Off timer (86915) reaches
  the boss snapshot through `encounter_blackboard.patch`. Without it, the owner's air
  standby starts late. Later minors: a ground duty shield that stays in range after
  three ground phases, a nearer fallback when the backup is far from every shield, and
  no elective 80-Sound gong that spends a relay shield.
- **Magmaw baiter rotation:** it latches the roster once per scope. If play mode
  (or a backfill) ever swaps a bot for a different GUID mid-scope, re-latch when the
  roster GUID set changes.
- **Harness lock:** `bot-live-validate --transport process` (scoreboard runs) should
  take `live_validation_lock` and refuse while any worldserver runs. Until then the
  coordinator runs one live thing at a time.
- **Chimaeron:** if live traces show long armed holds near 20%, publish the native
  Break/Double Attack timer so the Death Knight takes each Break while the arm holds.
- **Evidence:** WCL references, cast timelines and melee samples for every boss once
  the site's human check is passed. Damage fidelity stays open until then.

## Later rounds

- **Raid-level workloop.** `raid_workloop start "implement <raid> <mode> bots"` selects
  a raid program:
  - one unit per boss shard, with its lockout, copy and composition from the round-1
    tooling;
  - round bookkeeping: parallel implementation, one shared build, parallel shard runs,
    per-boss assessment;
  - the end-to-end acceptance run.
  AGENTS.md, the orchestrator skill and the playbook route a raid-level request there.
  Acceptance is a clean-context agent completing BWD 10N from the plain prompt.
- **Boss rounds.** One agent per remaining boss: research acceptance, native script
  audit, encounter damage fidelity, strategy, then tuning. Magmaw moves to the canonical
  composition.
- **End-to-end.** The composed full route: trash, all six bosses, a bot clicking the
  orb, the elevator, then Nefarian. After that, the other raids.
