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
- Run 022 proved 21 unique kills and exact terminals for generations 1-4, then exposed an invalid east pull anchor at `(1182, 960)`. The replacement `(1128.04, 966.894, 284.703)` is a world-DB-proven reachable floor point, 29.8 yards from Corborus for a legal paladin ranged pull and 43.2 yards from the optional Giant.
- The same audit found a forbidden activation fallback that summoned the route boss when the real instance target was not immediately visible. That fallback and its faction/attack forcing are removed: only the tank may activate a boss, only after reaching the pull anchor, and instance `SetData` must expose the real encounter target.
- Trash routing is migrating from enumerated pack paths to discovery. Stage A will persist generation-scoped GUID cohorts and death evidence while existing nodes seed them; Stage B will replace Stonecore pack coordinates/entry lists with navmesh-corridor discovery legs between strategic boss/regroup anchors; Stage C will migrate the remaining dungeon legs. Evade, path, LOS, selectability, and object-resolution failures never imply member death.
- Stage A is implemented: selected and threat-linked natural mobs join a generation-scoped GUID cohort; each GUID must have cohort-specific engagement before its death is accepted; unresolved members remain live; clearance requires the whole party out of combat plus a two-second quiet window. Trash-time per-target `AttackStop`/`CombatStop` paths and the arbitrary empty-entry nearby-mob fallback are removed.
- Stage B now covers the Corborus approach leg. Its explicit `discovery_leg` manifest has no mob entries, radius, or expected count. The tank projects natural hostiles onto the 3D navmesh path to the strategic endpoint, selects the earliest aggro-envelope intersection with a deterministic GUID tie-break, and persists the discovered GUID. Invalid/incomplete paths fail closed. Boss activation is restricted to eight yards from the pull anchor, avoiding the prior 40-yard activation boundary beside the optional Giant.
- The generated `dataset/validation_scenarios` output was reproduced under DVC and now contains the discovery leg; the stale radius/entry manifest cannot silently select the old behavior.
- Run 023 validated the strict cohort boundary on exact revision `bca870c928`: generation 1 enrolled five engaged GUIDs, recorded four real deaths, and correctly refused to terminal while the fifth remained unresolved by death evidence. The fifth was Millhouse Manastorm 43391, whose real script transitions below 50% to passive Blur 81216 and retreat rather than death. Runtime does not yet parse `scripted_event_entries`, so the valid scripted transition could not satisfy the node and the run ended at the 900-second wall-clock budget with four kills, zero teacher kills, and zero false terminals.
- Run 023 also proved the semantic plateau watchdog is counting repeated unchanged-health `validation_route_combat_progress` diagnoses as progress. Kill count and Millhouse health were unchanged for over 12 minutes, but the no-progress watchdog did not fire. The repair must count actual health improvement after the latest failure event, not repeated diagnosis rows.
- Runs 001-022, including aborted runs 017 and 019, are committed as DVC pointers and pushed. Their working copies and the local DVC cache were removed after push; use `pixi run dvc pull <pointer>` to restore one.

Verification:

- `pixi run pytest -q`: 250 passed after persistent cohort and discovery-leg contract tests.
- `cmake --build build --target worldserver -j2`: passed; exact revision verification is required again after committing the discovery source and progress update.
- DVC remote credentials match the main worktree; `pixi run dvc status` was recorded and reports pre-existing missing-cache drift plus the changed validation stages.
- Every strict live artifact through run 009 was checkpointed and pushed with DVC before local cleanup.

Next handoff:

Parse `scripted_event_entries` into runtime node state and implement manifest-driven scripted-transition evidence: a scripted member requires prior cohort engagement plus its declared observable transition (Millhouse Blur/passive retreat), while natural trash remains death-only and generic evade/unattackable/unresolved states remain live. Repair the completion watchdog so repeated unchanged-health diagnoses do not advance semantic progress. Rebuild exact `HEAD`, then run strict run 024 and require generation 1 to terminal only after four deaths plus Millhouse transition evidence. Continue requiring the generation-3 `discovery_leg` contract, no Giant engagement/Quake during Corborus, eight-yard pull-anchor activation, and real boss kills. Checkpoint and push every run before cleanup; do not start Phase 2 until the 10-clear Stonecore gate passes.
