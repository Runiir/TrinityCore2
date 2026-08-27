from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"
CONTRACT = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudge.h"
GEOMETRY = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeGeometry.cpp"
ESCAPE = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeEscape.cpp"
RECOVERY = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeRecovery.cpp"
RECOVERY_HEADER = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeRecovery.h"
LANES = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeLaneSelection.cpp"
ACTIONS = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeActions.cpp"
ENTRANCE_PULL = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeEntrancePull.cpp"
SEED = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeSeed.cpp"
SPACING = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeSpacing.cpp"


def test_drudge_route_modules_are_bounded_and_registered():
    world = WORLD.read_text(encoding="utf-8")
    header = HEADER.read_text(encoding="utf-8")
    cmake = CMAKE.read_text(encoding="utf-8")
    assert len(header.splitlines()) <= 1000
    for module in (CONTRACT, GEOMETRY, ESCAPE, RECOVERY, RECOVERY_HEADER, LANES, ENTRANCE_PULL, ACTIONS, SEED, SPACING):
        assert len(module.read_text(encoding="utf-8").splitlines()) <= 1000
    for name in (
        "BotWorldPopulationMgrValidationRouteDrudgeGeometry.cpp",
        "BotWorldPopulationMgrValidationRouteDrudgeEscape.cpp",
        "BotWorldPopulationMgrValidationRouteDrudgeRecovery.cpp",
        "BotWorldPopulationMgrValidationRouteDrudgeLaneSelection.cpp",
        "BotWorldPopulationMgrValidationRouteDrudgeEntrancePull.cpp",
        "BotWorldPopulationMgrValidationRouteDrudgeActions.cpp",
        "BotWorldPopulationMgrValidationRouteDrudgeSeed.cpp",
        "BotWorldPopulationMgrValidationRouteDrudgeSpacing.cpp",
    ):
        assert name in cmake
    assert "TryValidationRouteDrudgeChargeLanes" in header
    assert "DrudgeLaneCallbacks" in CONTRACT.read_text(encoding="utf-8")
    assert "auto drudgeLandedRushPending" not in world
    assert "auto tryValidationRouteMinimumDistance" not in world
    assert "auto drudgeRecoveryFormationActive" not in world
    assert "auto tryValidationRouteDrudgeChargeLanes" not in world


def test_drudge_entrance_pull_is_single_owner_native_and_magmaw_excluding():
    pull = ENTRANCE_PULL.read_text(encoding="utf-8")
    lanes = LANES.read_text(encoding="utf-8")

    assert lanes.index("RunEntrancePullActions()") < lanes.index("RunFormationActions()")
    assert "ValidationRouteSplitSeedRosterSlots.front()" in pull
    assert "if (OneBasedSlot != pullOwnerSlot)" in pull
    assert "ValidationRouteSplitSourceGuids[0] != 250140" in pull
    assert "ValidationRouteSplitSourceGuids[1] != 250141" in pull
    assert "Creature* source = Sources[0];" in pull
    assert "action.TargetGuid == source->GetGUID()" in pull
    assert 'action.MovementDirective == "ranged"' in pull
    assert "Bot->IsWithinLOSInMap(source)" in pull
    assert "ValidationRouteSplitSeedMaxRangeYards" in pull
    assert "ResolveProfileCombatAction" in pull
    assert "ExecuteProfileCombatAction" in pull
    assert "StrictNativePath" in pull
    assert "MoveBotToPointWithReferenceFloor" in pull
    assert "TeleportTo" not in pull
    assert "41570" not in pull


def test_drudge_entrance_pull_holds_nonowners_then_returns_before_handoff():
    pull = ENTRANCE_PULL.read_text(encoding="utf-8")
    pull_started = pull.index("if (pullStarted)")
    early_taunt = pull.index("RunNativeTauntConfirmation(", pull_started)
    puller_return = pull.index('"drudge_entrance_return_move"', pull_started)
    owner = pull.index("uint32 const pullOwnerSlot")
    cast = pull.index("ExecuteProfileCombatAction")

    assert pull_started < owner < cast
    assert pull_started < early_taunt < puller_return < owner
    assert "AssignedTank && !NativeChargePending" in pull[pull_started:puller_return]
    assert "true, false, false" in pull[early_taunt:puller_return]
    assert "recoveryAnchorFor(OneBasedSlot)" in pull
    assert "exactRosterAtEntrance()" in pull
    assert '"drudge_entrance_pull_owner_wait"' in pull
    assert '"drudge_entrance_return_move"' in pull
    assert '"drudge_entrance_native_pack_link_wait"' in pull
    assert "if (!packLinked)" in pull
    assert "return PhaseResult::Continue;" in pull[pull_started:owner]


def test_drudge_dispatch_keeps_movement_and_minimum_distance_order():
    world = WORLD.read_text(encoding="utf-8")
    movement = world.index("TryValidationRouteMovementCheck(state, bot, power, stage")
    minimum = world.index("TryValidationRouteDrudgeMinimumDistance(state, bot, power, stage")
    lanes = world.index("TryValidationRouteDrudgeChargeLanes(state, bot, power, stage")
    patrol = world.index("tryValidationRoutePatrolPull()")
    assert movement < patrol < minimum < lanes


def test_adaptive_drudge_owner_dispatches_typed_lane_contract_before_owner_skip():
    fallback = (
        ROOT / "src/server/game/Bots/"
        "BotWorldPopulationMgrUpdateBotKernelFallback.cpp"
    ).read_text(encoding="utf-8")
    route_owner = fallback.index("auto routeOwnerReason")
    route_dispatch_end = fallback.index(
        "BotActionArbitration::Candidate routeAction;", route_owner
    )
    route_dispatch = fallback[route_owner:route_dispatch_end]
    run_route = route_dispatch.index("auto runRoute")
    owner_gate = route_dispatch.index(
        "if (char const* ownerReason = routeOwnerReason(); ownerReason",
        run_route,
    )
    objective = route_dispatch.index("TryValidationRouteObjective(", owner_gate)

    # AdaptiveDrudgeOwnsNode remains the generic owner signal, but the exact
    # typed Drudge profile must be allowed through the route adapter so its
    # lane contract can execute.
    assert "typedDrudgeValidationRoute" in route_dispatch
    assert '== "trash_two_tank_charge_lanes"' in route_dispatch
    assert "&& !typedDrudgeValidationRoute" in route_dispatch[owner_gate:objective]
    assert owner_gate < objective

    # The exception is local to the route candidate. Generic boss dispatch
    # still rejects adaptive Drudge ownership and cannot replace the typed
    # lane target or native action.
    boss = fallback.index('boss.Key = "world.boss_mechanics"')
    trash = fallback.index("BotActionArbitration::Candidate trash;", boss)
    boss_candidate = fallback[boss:trash]
    assert '"adaptive_drudge_owns_live_pack"' in boss_candidate
    assert "context.AdaptiveDrudgeOwnsNode" in boss_candidate


def test_drudge_contract_keeps_scope_evidence_and_native_lane_guards():
    geometry = GEOMETRY.read_text(encoding="utf-8")
    escape = ESCAPE.read_text(encoding="utf-8")
    recovery = RECOVERY.read_text(encoding="utf-8")
    lanes = LANES.read_text(encoding="utf-8")
    actions = ACTIONS.read_text(encoding="utf-8")
    seed = SEED.read_text(encoding="utf-8")
    for marker in (
        "ValidationRouteDrudgeChargeObservations",
        "ReseparationRecorded",
        "ValidationRouteDrudgeAnchorAttemptId",
        "ValidationRouteDrudgeAnchorSource0Identity",
        "SelectAnchorPathSearch",
        "drudge_anchor_source_unsafe",
        "drudge_anchor_spacing_unsafe",
        "drudge_anchor_native_path_rejected:path_type=",
        "drudge_anchor_native_end_rejected:end2d=",
        "RecoveryPathPreservesTankSeparation",
        "TryMinimumDistance",
    ):
        assert marker in geometry or marker in recovery
    for marker in (
        "trash_two_tank_charge_lanes",
        "ValidationRouteSplitSourceGuids",
        "ValidationRouteSplitLaneARosterSlots",
        "RosterByGuid",
        "ResolveSources",
        "ComputeExactCombatTankPathsProven",
        "RecordReseparationEvidence",
    ):
        assert marker in lanes
    for marker in (
        "SetAllOffenseSuppressed",
        "drudge_lane_native_taunt",
        "drudge_lane_native_taunt_approach",
        "BotRaidDrudgeNativeRush::Evaluate",
        "drudge_native_tank_threat_build",
        "drudge_first_source_death_observed",
        "ValidationRouteDrudgeHealthSyncRosterGuids",
        "drudge_native_charge_reseparation_complete",
        "drudge_lane_single_target_action",
        "TryGroupHeal",
    ):
        assert marker in actions
    assert "drudge_pre_first_rush_threat_seed" in seed
    assert "AdvanceCoordinator" in seed
    assert "native_action_rejected" in seed
    assert "!IsLandedRushPending()" in escape


def test_drudge_runtime_targets_only_the_exact_pack_and_does_not_gate_on_post_rush_seed_order():
    world = WORLD.read_text(encoding="utf-8")
    contract = CONTRACT.read_text(encoding="utf-8")
    lanes = LANES.read_text(encoding="utf-8")
    resolve = lanes[lanes.index("DrudgeLaneContext::PhaseResult DrudgeLaneContext::ResolveSources()") :]
    assert "ValidationRouteSplitSourceGuids" in resolve
    assert "GetCreatureBySpawnId(spawnId)" in resolve
    assert "ValidationRouteMinimumDistanceSourceEntry" in resolve
    assert "EnrollPackMember" in contract
    assert "RecordDefeatedPackMembers" in contract
    assert "Callbacks.EnrollPackMember(source, nativeCombatObserved)" in resolve
    both_dead = resolve.index("if (!Sources[0]->IsAlive() && !Sources[1]->IsAlive())")
    record_deaths = resolve.index("Callbacks.RecordDefeatedPackMembers()", both_dead)
    generic_handoff = resolve.index("return PhaseResult::Abort;", record_deaths)
    assert both_dead < record_deaths < generic_handoff
    dispatch = world[world.index("TryValidationRouteDrudgeChargeLanes(state, bot, power, stage") :]
    assert dispatch.index("enrollValidationRoutePackMember") < dispatch.index(
        "recordDefeatedValidationRoutePackMembers"
    )
    assert "repeatedNativeFarthestGeometrySafe" not in lanes
