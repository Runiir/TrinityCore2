# Autonomy Data Engine v2

## Phase 1: runtime truth repair

Status: implementation complete; live Stonecore gate not yet passed.

Changed:

- Trash liveness is independent from target selectability, evade state, and path availability.
- Trash nodes require observed engagement and verified cluster clearance; `expected_alive_count` is descriptive only.
- Boss nodes require a naturally dead target. Validation force damage, forced death, and teacher completion were removed.
- Route terminals and boss kills are scoped by exact node and generation in runtime traces and report aggregation.
- Stuck recovery requires progress after the latest stuck or target-loss event.
- Full-clear and segment reports reject unscoped counters, stale nodes, forced assistance, missing terminals, and missing per-boss kills.
- Pytest ignores `generated/orchestrator_worktrees`.

Worker routing:

- Large/high-risk diagnosis used `gpt-5.6-sol` with high reasoning.
- Medium implementation and debugging used `gpt-5.6-terra` with medium reasoning.
- Structured SQL/manifest audits used `gpt-5.6-luna` with low reasoning.
- Simple disk/DVC and predicate audits used `gpt-5.3-codex-spark` with low reasoning.
- These were direct worker Codex sessions selected from the orchestration skill; `tools/bot_ml/orchestrator_daemon.py` was never invoked. A later Sol audit launch was blocked by account quota, so the existing collaboration reviewer performed that read-only audit.

Strict live iterations:

- Runs 001-003 isolated motion resets, cohort routing, and overlapping trash scopes.
- Runs 004-005 established exact post-stuck progress and let dungeon cohorts join the tank's authoritative focus.
- Run 006 exposed the three-second combat cadence; the active route/combat cadence is now capped at one second.
- Run 007 reached Slabhide after a real Corborus kill, but its final trace was incomplete and the airborne approach failed strict Z validation.
- Run 008 verified full trace capture and terrain-projected approaches, then wiped at Corborus with the healer dying first at 17.4% boss health.
- Run 009 proved targeted aura movement for Crystal Barrage spell 86881, but also misclassified shared Dampening Wave spell 82415 and caused a manifest-route death loop.
- Run 010 was aborted before Corborus after a DBC audit proved its periodic-trigger refinement would reject 86881. The aborted diagnostic is also checkpointed in DVC.
- The current implementation matches the loaded spell shape: a harmful `PERSISTENT_AREA_AURA` with `PERIODIC_DAMAGE`, and moves away from the aura's dynamic-object owner rather than the boss caster. This accepts 86881, rejects 82415, and remains encounter-ID independent.
- Run 011 verified 20 real 86881 movement events and zero 82415 movement events. The healer was never selected by 86881 but still died first immediately after the boss submerge/add phase, followed by a death-loop watchdog stop.
- The manifest's `adds` tactic now uses a dedicated `add_target_entries` list inside the strict route handler: non-healers select only engaged listed adds with their DB-backed class/spec action profile, while the healer continues triage. Boss legality and kill evidence are unchanged.
- Run 012 proved the dedicated manifest list selects only Rock Borer 43917, never charge hazard 43743 or unrelated creatures. The healer survived the previous failure point, but two of the first three add decisions returned `no_action`; DPS1266 and the tank died next.
- Add engagement now initiates the normal auto-attack/pull alongside the class/spec action, matching the established boss-target path without changing hard masks or terminal evidence.
- Run 013 made every listed-add action succeed, but tank and DPS selected three different borer GUIDs and still wiped. A generation-scoped shared add focus now keeps the party on the first valid listed add until it dies, without touching boss focus or terminal evidence.
- Run 014 verified the listed-entry mask, successful add actions, and coordinated sequential focus: 73 complete-trace add actions covered 29 GUIDs in 29 non-interleaved contiguous blocks, with explicit dead-target evidence on several transitions. The first truthful failure is now add-wave survivability/throughput, not focus divergence. The party stopped on `validation_route_death_loop` with 21 trash kills, 11 deaths, Corborus at a 48.36% minimum, no boss kill, and exact terminals only for generations 1-4. The run contains no forbidden assistance. Its artifact is checkpointed and pushed as `stonecore_strict_repair_run_014.dvc`.
- Run 015 persistently verified 39 real Rock Borer deaths and coherent focus transitions, then exposed the actual overlap: Crystalspawn Giant 42810 at `(1150.24, 929.81)` remained alive beside Corborus because the generation-4 antechamber manifest omitted its entry. Its repeated Quake 81008 mechanics overlapped the boss/add phase before the death-loop stop. The antechamber cluster now includes 42810, so its observed clearance is required before the boss node.
- Run 016 proved that manifest membership alone was insufficient: generation 4 included 42810 but terminaled after 21 other trash kills without a 42810 kill; the same live Giant then emitted Quake mechanics during Corborus. The terminal scan had been allowed before a bot reached the node anchor, so an unloaded nearby grid looked empty. Kill-triggered clearance is now deferred and scan-based terminal requires arrival within the node radius before verifying no live pack member.
- Run 017 was intentionally aborted after the deferred-terminal path repeatedly emitted the same dead GUID 14 from the tank's stale victim, reaching 140 duplicate `mob_killed` rows and fabricating watchdog progress. The evidence boundary now rejects an already-recorded dead GUID before changing metrics, writing telemetry, or returning early, allowing anchor verification to proceed on the same tick.
- Run 018 reduced the GUID-14 duplication to one row per observing bot, but a second bot could still record the same generation kill and the target-search path continued walking the tank toward the confirmed-dead corpse. It stopped in generation 1 with five counted kills over four GUIDs and a death loop. Kill evidence is now generation-global, and confirmed-dead search targets are discarded before corpse approach logic.
- Run 019 verified unique kill GUIDs and exact terminals through the first two packs, then was intentionally stopped when the route strategy was corrected: the optional antechamber Giant should not be killed. Corborus now uses the open east side `(1182, 960, 283.89)` as its tank pull anchor, over 40 yards from the Giant, and 42810 is no longer part of the antechamber pack.
- Runs 020-021 verified the first exact terminal, then exposed next-node target leakage rather than a pathless current pack member. Generation 2 had already killed its four unique members; GUID 56 was the generation-3 source exactly 75.85 yards from the generation-2 anchor, outside its 35-yard radius, but the shared entry 42696 let it hijack target search. Script-target identity is now scoped by current node map, center, and radius. Legal visible DB-profile ranged pulls remain available for genuinely pathless members inside the current cluster.
- Runs 001-021, including aborted runs 017 and 019, are committed as DVC pointers and pushed. Their working copies and the local DVC cache were removed after push; use `pixi run dvc pull <pointer>` to restore one.

Verification:

- `pixi run pytest -q`: 250 passed after the persistent-area spell-shape contract test.
- `cmake --build build --target worldserver -j2`: passed; exact revision verification is required again after committing the current source and progress update.
- DVC remote credentials match the main worktree; `pixi run dvc status` was recorded and reports pre-existing missing-cache drift plus the changed validation stages.
- Every strict live artifact through run 009 was checkpointed and pushed with DVC before local cleanup.

Next handoff:

Commit node-scoped trash target identity, rebuild exact `HEAD`, and run strict run 022. Require unique kill GUIDs and exact terminals for generations 1-4 without later-node acquisition, no 42810 engagement or Quake 81008 during Corborus, tank arrival at the east pull anchor before engagement, coherent 43917 death/switch evidence, healer/tank survival, spell 86881 movement, no spell 82415 movement, and a real `boss_killed` terminal. Checkpoint and push the run before cleanup. Continue repairing the first truthful failure until 10 consecutive clears show five bots in the original instance, four exact node/generation-scoped real boss kills, a terminal for every route node, zero forced/teacher completion, zero false terminals, and zero unresolved stuck states. Do not start Phase 2 until that gate passes.
