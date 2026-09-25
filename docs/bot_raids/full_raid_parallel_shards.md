# Full-raid bots: parallel boss shards

Status (2026-09-25): foundation round 1 is in progress. Only Magmaw 10N is implemented.
Goal: every boss of every Cataclysm raid is played by bots, then a full end-to-end
clear (trash, bosses and interactions). Blackwing Descent 10N comes first; Bastion of
Twilight, Throne of the Four Winds, Firelands and Dragon Soul reuse everything here.
Nothing in this document may be BWD-specific unless it lives in per-raid data.

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

## Later rounds

- **Boss rounds.** One agent per remaining boss: research acceptance, native script
  audit, encounter damage fidelity, strategy, then tuning. Magmaw moves to the canonical
  composition.
- **End-to-end.** The composed full route: trash, all six bosses, a bot clicking the
  orb, the elevator, then Nefarian. After that, the other raids.
