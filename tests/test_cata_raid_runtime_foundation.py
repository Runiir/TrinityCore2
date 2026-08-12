import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEADER = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h").read_text(encoding="utf-8")
IMPL = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text(encoding="utf-8")
GENERIC_SMOKE = json.loads((ROOT / "experiments/configs/cata_raid_phase1_generic_mechanic_smoke_v1.json").read_text())


def test_single_cohort_owns_one_raid_runtime():
    raid_struct = HEADER.index("struct RaidRuntime")
    cohort_struct = HEADER.index("struct CohortRuntime")
    cohort_end = HEADER.index("struct BotGuidLease", cohort_struct)

    assert raid_struct < cohort_struct
    assert "RaidRuntime Raid;" in HEADER[cohort_struct:cohort_end]
    assert "uint64 ServerEpoch" in HEADER[raid_struct:cohort_struct]
    assert "uint64 AttemptId" in HEADER[raid_struct:cohort_struct]
    assert "std::map<uint32, RaidRosterSlot> RosterByGuid" in HEADER[raid_struct:cohort_struct]


def test_no_pch_runtime_declares_roster_plan_before_use_and_compares_transport_identity_by_guid():
    group_start = IMPL.index("void BotWorldPopulationMgr::EnsureValidationCohortGroup()")
    group_end = IMPL.index("bool BotWorldPopulationMgr::ResolveSpawnPlacement", group_start)
    group_runtime = IMPL[group_start:group_end]
    assert group_runtime.index("std::vector<RaidRosterPlanSlot> const rosterPlan") < group_runtime.index("rosterPlan.size()")
    assert '#include "VehicleDefines.h"' in IMPL[:IMPL.index("namespace")]
    assert "transport->GetTransportGUID() == gameObject->GetGUID()" in IMPL
    assert "bot->GetTransport() == gameObject->ToTransport()" not in IMPL


def test_live_raid_instance_identity_freezes_atomically_from_the_exact_roster():
    population = IMPL[
        IMPL.index("void BotWorldPopulationMgr::EnsurePopulation()"):
        IMPL.index("void BotWorldPopulationMgr::EnsureCalibrationPopulation()")
    ]
    group = IMPL[
        IMPL.index("void BotWorldPopulationMgr::EnsureValidationCohortGroup()"):
        IMPL.index("bool BotWorldPopulationMgr::ResolveSpawnPlacement")
    ]
    update = IMPL[
        IMPL.index("void BotWorldPopulationMgr::UpdateBot"):
        IMPL.index("bool BotWorldPopulationMgr::TryValidationRouteObjective")
    ]
    original_instance = IMPL[
        IMPL.index("bool BotWorldPopulationMgr::IsValidationCohortMemberInOriginalInstance"):
        IMPL.index("void BotWorldPopulationMgr::MarkValidationCohortViolation")
    ]

    assert 'Cohort().Config.ValidationRouteEnable || placement.Source != "saved_position"' in population
    assert 'sBotMgr->SpawnWorldBot("any", std::to_string(candidateGuid), placement.MapId' in population
    assert 'Cohort().LastPopulationFailureReason = "validation_cohort_formation_pending";' in group
    assert group.index("members.size() != exactFormationSize") < group.index("RaidRuntime& raid")
    assert 'Cohort().LastPopulationFailureReason = "validation_cohort_live_instance_pending";' in group
    assert 'Cohort().LastPopulationFailureReason = "validation_cohort_live_instance_split";' in group
    assert 'Cohort().LastPopulationFailureReason = "validation_cohort_zero_instance_identity";' in group
    assert "state.ValidationCohortGroupGuid != group->GetGUID()" in group
    assert "state.ValidationCohortLeaderGuid != group->GetLeaderGUID()" in group
    assert '"validation_cohort_immutable_group_leader_drift"' in group
    assert "!member->GetInstanceId()" in group
    assert "if (!memberState->ValidationCohortLocked)" in group
    assert '"validation_cohort_immutable_identity_drift"' in group
    assert 'state.LastDecisionResult = "validation_cohort_formation_pending";' in update
    assert "sMapMgr->FindMap(state.ValidationCohortMapId, state.ValidationCohortInstanceId)" in original_instance
    assert "originalMap ? originalMap->GetCorpseByPlayer(bot->GetGUID()) : nullptr" in original_instance
    assert "originalCorpse->GetOwnerGUID() == bot->GetGUID()" in original_instance
    assert "originalCorpse->GetInstanceId() == state.ValidationCohortInstanceId" in original_instance
    assert "bot->GetCorpse()->GetInstanceId()" not in original_instance
    assert "group->GetGUID() != state.ValidationCohortGroupGuid" in original_instance
    assert "group->GetLeaderGUID() != state.ValidationCohortLeaderGuid" in original_instance


def test_validation_saved_position_is_route_map_bound_without_spawn_fallback():
    placement = IMPL[
        IMPL.index("bool BotWorldPopulationMgr::ResolveSpawnPlacement"):
        IMPL.index("bool BotWorldPopulationMgr::ResolveSavedSpawnPlacement")
    ]
    resume = IMPL[
        IMPL.index("bool BotWorldPopulationMgr::IsValidBotResumePosition"):
        IMPL.index("void BotWorldPopulationMgr::PersistBotPosition")
    ]

    assert "if (Cohort().Config.ValidationRouteEnable)" in placement
    assert placement.index("if (Cohort().Config.ValidationRouteEnable)") < placement.index(
        'if (mode == "resume_only")'
    )
    assert "mapId != Cohort().Config.ValidationRouteMapId" in resume


def test_validation_raid_preflights_exact_saved_roster_before_first_claim_or_spawn():
    population = IMPL[
        IMPL.index("void BotWorldPopulationMgr::EnsurePopulation()"):
        IMPL.index("void BotWorldPopulationMgr::EnsureCalibrationPopulation()")
    ]
    manifest = IMPL[
        IMPL.index("void BotWorldPopulationMgr::LoadValidationRouteManifest()"):
        IMPL.index("bool BotWorldPopulationMgr::ApplyValidationRouteManifestNode")
    ]
    admission = population.index("if (validationRaidAdmission)")
    first_claim = population.index("ClaimBotGuid(planned.Guid, planned.RosterSlotId)")
    first_spawn = population.index('sBotMgr->SpawnWorldBot("any", std::to_string(planned.Guid)')
    generic_population = population.index("uint32 attempts = 0;")

    assert admission < first_claim < first_spawn < generic_population
    for field in ("bot_start_map_id", "bot_start_x", "bot_start_y", "bot_start_z", "bot_start_o"):
        assert field in manifest
    for token in (
        "Party().ValidationRouteManifest.front()",
        "routeStart.ExpectedBotCount != rosterPlan.size()",
        "SelectPoolCandidateGuid(slot.RosterSlotId, &plannedGuids,",
        "ResolveSavedSpawnPlacement(candidateGuid, placement)",
        "placement.MapId != routeStart.BotStartMapId",
        "RouteStartHorizontalToleranceYards",
        "RouteStartVerticalToleranceYards",
        'validation_raid_preflight_route_start_mismatch',
    ):
        assert token in population
    before_claim = population[admission:first_claim]
    assert "ClaimBotGuid(" not in before_claim
    assert "SpawnWorldBot" not in before_claim
    assert "SpawnWorldBotInGroup" not in before_claim
    assert "new Group" not in before_claim
    assert "ResolveSpawnPlacement(candidateGuid, placement)" not in before_claim
    admission_runtime = population[admission:generic_population]
    assert "ResolveSpawnPlacement(" not in admission_runtime
    assert "AllowConfiguredCenterFallback" not in admission_runtime
    assert "validationRaidSpawnPlan" in admission_runtime


def test_validation_raid_admission_rolls_back_late_failures_and_cannot_retry_unpinned():
    population = IMPL[
        IMPL.index("void BotWorldPopulationMgr::EnsurePopulation()"):
        IMPL.index("void BotWorldPopulationMgr::EnsureCalibrationPopulation()")
    ]
    admission = population.index("if (validationRaidAdmission)")
    generic_population = population.index("uint32 attempts = 0;")
    runtime = population[admission:generic_population]

    for token in (
        "Cohort().ValidationRaidAdmissionFailed",
        "Cohort().ValidationRaidAdmissionComplete",
        "rollbackAdmission(\"validation_raid_admission_claim_failed\")",
        "rollbackAdmission(\"validation_raid_admission_spawn_failed\")",
        "rollbackAdmission(\"validation_raid_admission_exact_group_failed\")",
        "sBotMgr->RemoveWorldBot(*itr);",
        "ReleaseBotGuid(guid);",
        "Party() = partyBeforeAdmission;",
        "Cohort().Raid = raidBeforeAdmission;",
        "Cohort().Metrics = metricsBeforeAdmission;",
        "Cohort().RosterLeases.clear();",
    ):
        assert token in runtime

    terminal_check = runtime.index("if (Cohort().ValidationRaidAdmissionFailed)")
    pinned_selection = runtime.index("SelectPoolCandidateGuid(slot.RosterSlotId, &plannedGuids,")
    transaction_claim = runtime.index("ClaimBotGuid(planned.Guid, planned.RosterSlotId)")
    assert terminal_check < pinned_selection < transaction_claim
    assert runtime.count("SelectPoolCandidateGuid(") == 1
    assert "SelectPoolCandidateGuid(rosterSlotId)" not in runtime
    assert "ResolveSpawnPlacement(candidateGuid, placement)" not in runtime
    assert "continue;" not in runtime[transaction_claim:]

    cohort = HEADER[
        HEADER.index("struct CohortRuntime"):
        HEADER.index("struct BotGuidLease")
    ]
    assert "bool ValidationRaidAdmissionComplete = false;" in cohort
    assert "bool ValidationRaidAdmissionFailed = false;" in cohort


def test_completed_validation_raid_drift_verifies_exact_identity_and_cleans_all_state():
    population = IMPL[
        IMPL.index("void BotWorldPopulationMgr::EnsurePopulation()"):
        IMPL.index("void BotWorldPopulationMgr::EnsureCalibrationPopulation()")
    ]
    complete = population[
        population.index("if (Cohort().ValidationRaidAdmissionComplete)"):
        population.index("auto terminalFailure")
    ]
    for token in (
        "routeStart.ExpectedRoster",
        "row.Guid.GetCounter() == expected.Guid",
        "row.RosterSlotId == expected.RosterSlotId",
        "LeaseOwnedByCurrentCohort(expected.Guid, expected.RosterSlotId)",
        "frozen->second.RosterSlotId != expected.RosterSlotId",
        "Cohort().Raid.GroupGuid == exactGroupGuid",
        "sBotMgr->RemoveWorldBot(state.Guid);",
        "ReleaseBotGuid(guid);",
        "Party() = PartyRuntime();",
        "Cohort().Raid = RaidRuntime();",
        "Cohort().RosterLeases.clear();",
        "Cohort().Metrics.ActiveBots = 0;",
        'Cohort().LastPopulationFailureReason = "validation_raid_admission_identity_drift";',
    ):
        assert token in complete
    cleanup = complete.index("if (!exactIdentity)")
    latch = complete.index("Cohort().ValidationRaidAdmissionFailed = true;", cleanup)
    assert cleanup < complete.index("sBotMgr->RemoveWorldBot(state.Guid);", cleanup) < latch


def test_validation_raid_candidate_selection_is_exact_frozen_identity_not_role_substitution():
    population = IMPL[
        IMPL.index("void BotWorldPopulationMgr::EnsurePopulation()"):
        IMPL.index("void BotWorldPopulationMgr::EnsureCalibrationPopulation()")
    ]
    selector = IMPL[
        IMPL.index("uint32 BotWorldPopulationMgr::SelectPoolCandidateGuid"):
        IMPL.index("uint32 BotWorldPopulationMgr::SelectCalibrationPoolCandidateGuid")
    ]
    for token in (
        "routeStart.ExpectedRoster.size() != rosterPlan.size()",
        "expected->Role != slot.Role",
        "expected->Guid, expected->Name, expected->ClassSpec",
        'terminalFailure("validation_raid_preflight_roster_identity_invalid")',
    ):
        assert token in population
    for token in (
        'query << " AND cbp.guid = " << expectedGuid',
        '" AND c.name = \'" << escapedName << "\'"',
        '" AND cbp.class_spec = \'" << escapedExpectedSpec << "\'"',
    ):
        assert token in selector

    # A lower-GUID same-tag/role/spec row still cannot match the exact GUID and
    # name predicates; ORDER BY is only deterministic ordering after identity.
    expected = {"guid": 1271, "name": "Bwdtanka", "role": "tank", "class_spec": "protection_paladin"}
    extra = {"guid": 1, "name": "Substitute", "role": "tank", "class_spec": "protection_paladin"}
    assert extra["guid"] < expected["guid"]
    assert extra["role"] == expected["role"] and extra["class_spec"] == expected["class_spec"]
    assert not (extra["guid"] == expected["guid"] and extra["name"] == expected["name"])


def test_bwd_route_source_and_generator_bind_exact_roster_identity():
    scenario = json.loads((ROOT / "experiments/configs/validation_scenarios_cata_001.json").read_text())
    bwd = next(row for row in scenario["scenarios"] if row["id"] == "blackwing_descent_10n")
    identities = bwd["roster_identity"]
    assert len(identities) == 10
    assert [row["roster_slot_id"] for row in identities] == [
        "raid_tank_1", "raid_tank_2",
        "raid_healer_1", "raid_healer_2", "raid_healer_3",
        "raid_dps_1", "raid_dps_2", "raid_dps_3", "raid_dps_4", "raid_dps_5",
    ]
    assert len({row["guid"] for row in identities}) == 10
    assert len({row["name"] for row in identities}) == 10
    assert all(row["guid"] > 0 and row["name"] and row["role"] and row["class_spec"] for row in identities)
    generator = (ROOT / "tools/bot_ml/build_validation_scenario_manifests.py").read_text()
    assert 'route["roster_identity"] = scenario.get("roster_identity") or []' in generator


def test_raid_size_and_difficulty_are_explicit_and_fail_closed():
    assert "uint8 RaidSize = 10;" in HEADER
    assert "uint8 RaidDifficulty = 0;" in HEADER
    assert '"raid_size"' in IMPL
    assert '"raid_difficulty"' in IMPL
    assert '"raid_size_difficulty_mismatch"' in IMPL
    assert "leader->GetSession()->HandleSetRaidDifficultyOpcode(difficultyRequest);" in IMPL
    assert "group->SetRaidDifficulty(requestedRaidDifficulty);" not in IMPL
    assert "group->SetRaidDifficulty(RAID_DIFFICULTY_10MAN_NORMAL);" not in IMPL

    valid = {(10, 0), (10, 2), (25, 1), (25, 3)}
    observed = {
        (size, difficulty)
        for size in (10, 25)
        for difficulty in range(4)
        if ((size == 25) == bool(difficulty & 1))
    }
    assert observed == valid


def test_deterministic_five_player_subgroups_cover_10_and_25():
    assert "memberIndex / MAXGROUPSIZE" in IMPL
    assert "group->ChangeMembersGroup(bot->GetGUID(), subgroup);" in IMPL

    assert [index // 5 for index in range(10)] == [0] * 5 + [1] * 5
    assert [index // 5 for index in range(25)] == sum(([group] * 5 for group in range(5)), [])


def test_generic_raid_mechanic_contracts_are_typed_executable_and_fail_closed():
    assert GENERIC_SMOKE["authority"] == "synthetic_test_only_not_boss_fidelity"
    contracts = [row["mechanic_contract"] for row in GENERIC_SMOKE["routes"]]
    assert {row["formation_family"] for row in contracts} == {"pair", "lane", "quadrant", "ring", "cone"}
    assert all(row["id"] and row["arrival_tolerance_yards"] > 0 for row in contracts)
    assert all(row["target_entries"] for row in contracts)
    assert "node.MechanicContractResolved" in IMPL
    assert 'adapter.AssignmentType = "contract_unresolved"' in IMPL
    assert 'result.Action = "raid_" + raidAnchors.FormationFamily + "_anchor"' in IMPL
    assert 'raidAdapter.TargetControl == "do_not_damage"' in IMPL
    assert 'raidAdapter.TargetControl == "controlled_aoe"' in IMPL
    assert 'raidAdapter.TargetControl == "kill_sync"' in IMPL
    assert "HandleGameObjectUseOpcode(use)" in IMPL
    assert "HandleSpellClick(click)" in IMPL
    assert "transport->GetTransportGUID() == gameObject->GetGUID()" in IMPL
    assert "HandleAreaTriggerOpcode(areaTrigger)" in IMPL
    assert "declarative_area_damage_forbidden" in IMPL
    route_start = IMPL.index("bool BotWorldPopulationMgr::TryValidationRouteObjective")
    route_end = IMPL.index("bool BotWorldPopulationMgr::IsBossContext", route_start)
    route_runtime = IMPL[route_start:route_end]
    assert route_runtime.count("TryBossMechanics(state, bot, power, stage, activity, target)") == 4


def test_bwd_native_ghost_runback_acks_only_corpse_bound_worldports_and_canonical_entrance():
    bwd_entrance_sql = (
        ROOT / "sql/old/4.3.4/TDB00_to_TDB01_updates/world/090_areatrigger_teleport.sql"
    ).read_text(encoding="utf-8")
    reattach = IMPL[
        IMPL.index("bool BotWorldPopulationMgr::TryReattachValidationBot"):
        IMPL.index("bool BotWorldPopulationMgr::HasNativeRaidCorpseAuthority")
    ]
    native_release = IMPL[
        IMPL.index("bool BotWorldPopulationMgr::IsNativeReleasedGhostWorldport"):
        IMPL.index("bool BotWorldPopulationMgr::IsValidationCohortMemberInOriginalInstance")
    ]
    corpse_authority = IMPL[
        IMPL.index("bool BotWorldPopulationMgr::HasNativeRaidCorpseAuthority"):
        IMPL.index("bool BotWorldPopulationMgr::ResolveNativeBlackwingDescentEntrance")
    ]
    native_runback = IMPL[
        IMPL.index("if (Cohort().Config.ValidationRouteEnable && Cohort().Config.AllowRaids)"):
        IMPL.index("// A critical-role death can make the survivors retreat", IMPL.index("if (Cohort().Config.ValidationRouteEnable && Cohort().Config.AllowRaids)"))
    ]

    assert "constexpr uint32 BlackwingDescentMapId = 669;" in IMPL
    assert "constexpr uint32 BlackwingDescentEntranceMapId = 0;" in IMPL
    assert "constexpr uint32 BlackwingDescentEntranceTriggerId = 6581;" in IMPL
    assert "(6581, 'Blackwing Descent (Enterance)', 669," in bwd_entrance_sql
    assert "HasNativeRaidCorpseAuthority(state, bot)" in reattach
    assert "session->HandleMoveWorldportAck()" in reattach
    assert "HandleMoveWorldportAck performs the core's native" in reattach
    assert "bot->IsInWorld() && bot->IsAlive()" in reattach
    assert "!bot->HasFlag(PLAYER_FLAGS, PLAYER_FLAGS_GHOST)" in reattach
    assert "!bot->HasCorpse()" in reattach
    assert "group->GetGUID() == state.ValidationCohortGroupGuid" in reattach
    assert "group->GetLeaderGUID() == state.ValidationCohortLeaderGuid" in reattach
    assert "Never cancel or reattach a native recovery worldport" in reattach
    assert "if (state.NativeReleaseRequested && !nativeRecoveryWorldport" in reattach
    assert "bot->CancelDelayedTeleport()" not in reattach.split("if (nativeRecoveryWorldport)", 1)[1].split("if (destination.GetMapId()", 1)[0]

    assert "originalMap->GetCorpseByPlayer(bot->GetGUID())" in corpse_authority
    assert "originalCorpse->GetOwnerGUID() == bot->GetGUID()" in corpse_authority
    assert "originalCorpse->GetInstanceId() == state.ValidationCohortInstanceId" in corpse_authority
    assert "ResolveNativeBlackwingDescentEntrance" in native_release
    assert "destination.GetMapId() == entranceDestination->target_mapId" in native_release

    assert "ResolveNativeBlackwingDescentEntrance(entranceEntry, entranceDestination)" in native_runback
    assert "bot->GetMapId() == entranceEntry->ContinentID" in native_runback
    assert "uint32 entranceTriggerId = BlackwingDescentEntranceTriggerId;" in native_runback
    assert "WorldPacket areaTrigger(CMSG_AREATRIGGER" in native_runback
    assert "TeleportTo(" not in native_runback
    assert "NearTeleportTo(" not in native_runback
    assert "ResurrectPlayer" not in native_runback


def test_phase1_magmaw_engagement_contract_has_explicit_safe_target_authority():
    scenario = json.loads((ROOT / "experiments/configs/validation_scenarios_cata_001.json").read_text())
    bwd = next(row for row in scenario["scenarios"] if row["id"] == "blackwing_descent_10n")
    magmaw = next(row for row in bwd["route"] if row["label"] == "Magmaw")
    assert magmaw["source_entry"] == 41570
    assert magmaw["mechanic_contract"] == {
        "id": "phase1_magmaw_native_engagement_recovery_v1",
        "target_control": "focus_fire",
        "target_entries": [41570],
        "allow_area_damage": False,
        "allow_multidot": False,
    }
    assert 'adapter.TargetControl = contract->TargetControl.empty() ? "focus_fire"' in IMPL
    assert 'raidAdapter.TargetControl == "focus_fire"' in IMPL
    assert '"raid_focus_fire_target_missing"' in IMPL


def test_route_directed_boss_assist_cannot_bypass_the_typed_contract_authority():
    route_start = IMPL.index("bool BotWorldPopulationMgr::TryValidationRouteObjective")
    route_end = IMPL.index("bool BotWorldPopulationMgr::IsBossContext", route_start)
    route_runtime = IMPL[route_start:route_end]
    assist_start = route_runtime.index('if (Cohort().Config.ValidationRouteKind == "boss" && std::string(GetDungeonRole(bot)) != "tank")')
    assist_end = route_runtime.index("if (routeFocusMemoryActive())", assist_start)
    assist = route_runtime[assist_start:assist_end]

    contract_authority = assist.index("if (tankFocusIsBossRoute)")
    profile_action = assist.index("ResolvedCombatAction profileAction = ResolveProfileCombatAction(bot, target);")
    assert contract_authority < profile_action
    assert "BossMechanicActionResult mechanic = TryBossMechanics(state, bot, power, stage, activity, target);" in assist[contract_authority:profile_action]
    assert "if (mechanic.Handled)" in assist[contract_authority:profile_action]
    assert 'action = "raid_mechanic_contract_fail_closed";' in assist[contract_authority:profile_action]
    assert "return true;" in assist[contract_authority:profile_action]

    boss_start = IMPL.index("BotWorldPopulationMgr::BossMechanicActionResult BotWorldPopulationMgr::TryBossMechanics")
    boss_end = IMPL.index("BotWorldPopulationMgr::RaidRoleAssignment BotWorldPopulationMgr::BuildRaidRoleAssignment", boss_start)
    boss_runtime = IMPL[boss_start:boss_end]
    assert 'bool const routeDirectedBoss = Cohort().Config.ValidationRouteKind == "boss"' in boss_runtime
    assert "routeCreature->GetEntry() == Cohort().Config.ValidationRouteTargetEntry" in boss_runtime
    assert "Cohort().Config.ValidationRouteAlternateTargetEntries.end()" in boss_runtime
    assert "if (!IsBossContext(bot, result.Target) && !routeDirectedBoss)" in boss_runtime
    assert 'result.Action = "raid_mechanic_contract_fail_closed";' in boss_runtime
    assert "0, false, false, forbidArea, raidAdapter.AllowMultidot" in boss_runtime


def test_shared_boss_focus_cannot_bypass_declared_target_or_typed_contract_authority():
    route_start = IMPL.index("bool BotWorldPopulationMgr::TryValidationRouteObjective")
    route_end = IMPL.index("bool BotWorldPopulationMgr::IsBossContext", route_start)
    route_runtime = IMPL[route_start:route_end]
    focus_start = route_runtime.index("if (Unit* focusTarget = routeGroupFocusTarget())")
    focus_end = route_runtime.index(
        'if (std::string(GetDungeonRole(bot)) != "tank"\n        && (', focus_start
    )
    shared_focus = route_runtime[focus_start:focus_end]

    heal = shared_focus.index("if (tryRouteGroupHeal(bot, target))")
    boss_authority = shared_focus.index("if (!routeTrashFocus)")
    profile_action = shared_focus.index(
        "ResolvedCombatAction profileAction = ResolveProfileCombatAction(bot, target);"
    )
    assert heal < boss_authority < profile_action

    typed_boss_path = shared_focus[boss_authority:profile_action]
    assert "if (!isValidationRouteObjectiveTarget(focusCreature))" in typed_boss_path
    assert 'action = "raid_target_not_declared_hold";' in typed_boss_path
    assert "BossMechanicActionResult mechanic = TryBossMechanics(state, bot, power, stage, activity, target);" in typed_boss_path
    assert "if (mechanic.Handled)" in typed_boss_path
    assert 'action = "raid_mechanic_contract_fail_closed";' in typed_boss_path
    assert typed_boss_path.count("return true;") >= 3

    boss_start = IMPL.index("BotWorldPopulationMgr::BossMechanicActionResult BotWorldPopulationMgr::TryBossMechanics")
    boss_end = IMPL.index(
        "BotWorldPopulationMgr::RaidRoleAssignment BotWorldPopulationMgr::BuildRaidRoleAssignment",
        boss_start,
    )
    boss_runtime = IMPL[boss_start:boss_end]
    assert "result.Target = boundRouteTarget ? boundRouteTarget : FindBossTarget(bot);" in boss_runtime
    assert "if (!result.Target && !boundRouteTarget && !state.TargetGuid.IsEmpty())" in boss_runtime
    assert "if (boundRouteTarget && !routeDirectedBoss)" in boss_runtime
    assert 'result.Action = "raid_target_not_declared_hold";' in boss_runtime
    assert "forbidArea, raidAdapter.AllowMultidot" in boss_runtime
    assert 'RecordRaidTelemetry(state, bot, focus, "raid_focus_fire", "declared_target_selected"' in boss_runtime

    find_start = IMPL.index("Unit* BotWorldPopulationMgr::FindBossTarget")
    find_end = IMPL.index(
        "BotWorldPopulationMgr::BossMechanicFeatures BotWorldPopulationMgr::BuildBossMechanicFeatures",
        find_start,
    )
    unbound_search = IMPL[find_start:find_end]
    assert "usableBoss(bot->GetVictim())" in unbound_search
    assert "usableBoss(member->GetVictim())" in unbound_search
    assert "Cell::VisitAllObjects(bot, searcher, 60.0f);" in unbound_search


def test_every_route_boss_dispatch_binds_declared_target_and_never_uses_generic_boss_search():
    route_start = IMPL.index("bool BotWorldPopulationMgr::TryValidationRouteObjective")
    route_end = IMPL.index("bool BotWorldPopulationMgr::IsBossContext", route_start)
    route_runtime = IMPL[route_start:route_end]
    bound_call = "TryBossMechanics(state, bot, power, stage, activity, target)"
    unbound_call = "TryBossMechanics(state, bot, power, stage, activity)"

    # Tank focus, shared focus, current combat, and newly resolved route target
    # are the complete route-boss dispatch surface. Every one binds the exact
    # target that the route-specific declaration check already accepted.
    assert route_runtime.count(bound_call) == 4
    assert unbound_call not in route_runtime

    tank_start = route_runtime.index("if (tankFocusIsBossRoute)")
    tank_focus = route_runtime[
        tank_start:route_runtime.index("if (tryRouteGroupHeal(bot, target))", tank_start)
    ]
    shared_start = route_runtime.index("if (!routeTrashFocus)")
    shared_focus = route_runtime[
        shared_start:route_runtime.index(
            "ResolvedCombatAction profileAction = ResolveProfileCombatAction(bot, target);",
            shared_start,
        )
    ]
    current_start = route_runtime.index(
        'if (routeBossTarget && Cohort().Config.ValidationRouteKind == "boss")'
    )
    current_combat = route_runtime[
        current_start:route_runtime.index("if (tryRouteGroupHeal(bot, target))", current_start)
    ]
    resolved_start = route_runtime.index("target = routeTarget;")
    resolved_target = route_runtime[
        resolved_start:route_runtime.index("if (tryRouteGroupHeal(bot, target))", resolved_start)
    ]
    for dispatch in (tank_focus, shared_focus, current_combat, resolved_target):
        assert bound_call in dispatch
        assert 'action = "raid_mechanic_contract_fail_closed";' in dispatch
        assert dispatch.index(bound_call) < dispatch.index('action = "raid_mechanic_contract_fail_closed";')

    assert 'if (!routeTarget && Cohort().Config.ValidationRouteKind == "boss")\n        routeTarget = FindBossTarget(bot);' not in route_runtime
    assert '&& !isValidationRouteObjectiveTarget(routeTarget->ToCreature()))' in route_runtime
    assert 'action = "raid_target_not_declared_hold";' in route_runtime

    boss_start = IMPL.index("BotWorldPopulationMgr::BossMechanicActionResult BotWorldPopulationMgr::TryBossMechanics")
    boss_end = IMPL.index(
        "BotWorldPopulationMgr::RaidRoleAssignment BotWorldPopulationMgr::BuildRaidRoleAssignment",
        boss_start,
    )
    boss_runtime = IMPL[boss_start:boss_end]
    assert "result.Target = boundRouteTarget ? boundRouteTarget : FindBossTarget(bot);" in boss_runtime
    assert "if (boundRouteTarget && !routeDirectedBoss)" in boss_runtime


def test_phase1_target_transfer_and_swap_controls_are_executable():
    for token in (
        'raidAdapter.TargetControl == "focus_fire"',
        '"declared_target_selected"',
        'raidAdapter.BattleResurrectionPolicy != "assigned_only"',
        'currentTank->GetGUID() == raidAssignment.MainTankGuid',
        'currentTank->GetGUID() == raidAssignment.OffTankGuid',
        '"raid_kill_sync_execution_hold_low_target"',
        'isHeldLowTarget(bot->GetVictim())',
        'isHeldLowTarget(current->m_targets.GetUnitTarget())',
        'isHeldLowTarget(repeat->m_targets.GetUnitTarget())',
        'isHeldLowTarget(pet->GetVictim())',
        'isHeldLowTarget(controlled->GetVictim())',
        'bot->InterruptSpell(CURRENT_GENERIC_SPELL, false);',
        'bot->InterruptSpell(CURRENT_AUTOREPEAT_SPELL, false);',
        'for (Unit* controlled : bot->m_Controlled)',
    ):
        assert token in IMPL


def test_tank_swap_level_triggers_are_edge_latched_until_the_condition_clears():
    assert "std::string LastRaidTankSwapTriggerKey" in HEADER
    assert "uint64 LastRaidTankSwapWipeGeneration" in HEADER
    for token in (
        'tankSwapTriggerKey = "cast:"',
        'tankSwapTriggerKey = "add:"',
        'tankSwapTriggerKey = "phase:"',
        "state.LastRaidTankSwapTriggerKey != tankSwapTriggerKey",
        "state.LastRaidTankSwapTriggerKey.clear();",
        "state.LastRaidTankSwapWipeGeneration != Cohort().Raid.WipeGeneration",
        "state.LastRaidTankSwapWipeGeneration = Cohort().Raid.WipeGeneration;",
        "memberState.LastRaidTankSwapTriggerKey = tankSwapTriggerKey;",
        "memberState.LastRaidTankSwapWipeGeneration = Cohort().Raid.WipeGeneration;",
        "state.LastRaidTankSwapTriggerKey.clear();",
    ):
        assert token in IMPL


def test_battle_res_slots_allow_native_capable_non_healers_and_role_priority_is_real():
    raid_brez = IMPL[
        IMPL.index("bool battleResOwner"):
        IMPL.index("if (result.Features.RaidEncounter && raidAdapter.ContractResolved && raidAdapter.DispelAuraId)")
    ]
    assert 'std::string(role) == "healer"' not in raid_brez
    assert "raidAdapter.BattleResurrectionPolicy" in raid_brez
    for token in (
        'targetPolicy == "tank_then_healer_then_dps"',
        'deadRole == "tank" ? 3 : deadRole == "healer" ? 2 : 1',
        "requestedByHealer ? 100 : pendingByHealer ? 90 : rolePriority",
        "uniqueBattleResSlots.size() == node.BattleResurrectionSlots.size()",
        "slot > 0 && slot <= Cohort().Config.RaidSize",
    ):
        assert token in IMPL


def test_controlled_aoe_counts_only_declared_targets_and_fails_closed_near_undeclared_hostiles():
    for token in (
        "uint32 declaredControlledAoeTargets = 0;",
        "bool undeclaredControlledAoeHostile = false;",
        "declared = std::find(raidAdapter.TargetEntries.begin()",
        "undeclaredControlledAoeHostile = true;",
        "++declaredControlledAoeTargets;",
        "!undeclaredControlledAoeHostile",
        "declaredControlledAoeTargets >= raidAdapter.ControlledAoeMinimumTargets",
        '? declaredControlledAoeTargets : result.Features.AddCount',
        "&profileAction, combatAddCount, controlledAoeReleased",
        "TryEnsureCombatTotems(*state, bot, target, forbidArea ? 1 : hostileCount)",
        "allowMultidot && !forbidArea",
        "magma->UnSummon();",
        "candidate->RemoveAura(44457, bot->GetGUID());",
        "spellInfo->IsAffectingArea()",
        "spellInfo->Effects[effectIndex].ChainTarget > 1",
        "declarative_area_damage_semantics_forbidden",
        "action.SuppressAreaDamage = forbidArea;",
        "raid_area_damage_contamination_fail_closed",
        "HandleCancelAuraOpcode(cancel)",
        "bot->RemoveDynObject(action.SpellId);",
        "creature->GetPetAutoSpellOnPos(index)",
        "BotRaidAreaAuthority::Set(bot->GetGUID().GetRawValue(), suppress);",
        "std::vector<uint32> activeAreaSpells;",
        "controlled->InterruptSpell(spellType, false);",
        "controlled->RemoveAura(spellId);",
        "reconcileRaidAreaAutocasts(!controlledAoeReleased);",
        "reconcileRaidAreaAutocasts(false);",
        'raidAdapter.TargetControl == "controlled_aoe" && !controlledAoeReleased',
        "bot->InterruptSpell(CURRENT_CHANNELED_SPELL, false);",
    ):
        assert token in IMPL


def test_explicit_runtime_profile_survives_start_config_reload():
    load_config = IMPL[IMPL.index("void BotWorldPopulationMgr::LoadConfig("):]
    configured_profile = load_config.index("SelectConfiguredRuntimeProfile()")
    pending_snapshot = load_config.rfind("explicitProfilePending", 0, configured_profile)
    apply_selected = load_config.index("ApplyRuntimeProfile(profileItr->second)", configured_profile)
    pending_consumed = load_config.index("Cohort().RuntimeProfileSelectionPending = false;", apply_selected)
    assert pending_snapshot >= 0
    assert pending_snapshot < configured_profile < apply_selected < pending_consumed
    select_profile = IMPL[IMPL.index("std::string BotWorldPopulationMgr::SelectRuntimeProfile("):]
    assert "Cohort().RuntimeProfileSelectionPending = true;" in select_profile[
        :select_profile.index("std::string BotWorldPopulationMgr::ClearRuntimeProfile()")
    ]
    reload_profile = select_profile[select_profile.index("std::string BotWorldPopulationMgr::ReloadRuntimeProfiles()"):]
    reload_profile = reload_profile[:reload_profile.index("bool BotWorldPopulationMgr::SelectConfiguredRuntimeProfile()")]
    assert "RuntimeProfileSelectionPending = true" not in reload_profile

    cohort_start = IMPL[IMPL.index("bool BotWorldPopulationMgr::StartAutonomyForCohort("):]
    cohort_start = cohort_start[:cohort_start.index("std::string BotWorldPopulationMgr::StopAutonomyForCohort(")]
    capacity_rejection = cohort_start.index("ActiveCohortCount() >= MaxActiveCohorts")
    rollback = cohort_start.index("runtime->RuntimeProfileSelectionPending = false;", capacity_rejection)
    rejection = cohort_start.index("return false;", rollback)
    assert capacity_rejection < rollback < rejection


def test_named_validation_profile_fails_before_provisioning_without_native_route():
    prepare = IMPL[IMPL.index("bool BotWorldPopulationMgr::PrepareCurrentValidationProfile"):]
    prepare = prepare[:prepare.index("bool BotWorldPopulationMgr::ApplyValidationProvisioningSql")]
    route_guard = prepare.index("Party().ValidationRouteManifestLoadError")
    provisioning = prepare.index("ApplyValidationProvisioningSql")
    pool_reset = prepare.index("ResetValidationBotPool")
    assert route_guard < provisioning < pool_reset
    assert "Party().ValidationRouteManifest.empty()" in prepare
    assert "Party().ValidationRouteGeneration != 1" in prepare
    assert "Cohort().Config.ValidationRouteScenarioId != Cohort().Config.Name" in prepare


def test_focus_fire_owns_target_and_cancels_every_wrong_attacker():
    focus_start = IMPL.index('raidAdapter.TargetControl == "focus_fire"')
    focus_end = IMPL.index('if (result.Features.RaidEncounter && raidAdapter.ContractResolved)\n    {', focus_start)
    focus = IMPL[focus_start:focus_end]
    for token in (
        "auto stopWrongFocusTarget = [focus](Unit* attacker)",
        "attacker->InterruptSpell(CURRENT_GENERIC_SPELL, false);",
        "attacker->InterruptSpell(CURRENT_AUTOREPEAT_SPELL, false);",
        "attacker->InterruptSpell(CURRENT_CHANNELED_SPELL, false);",
        "stopWrongFocusTarget(bot);",
        "stopWrongFocusTarget(pet);",
        "stopWrongFocusTarget(controlled);",
        "state.TargetGuid = focus->GetGUID();",
        "if (!focus || current->m_targets.GetUnitTarget() != focus)",
    ):
        assert token in focus
    assert 'raidAdapter.TargetControl != "focus_fire"' in IMPL
    assert '(node.TargetControl != "focus_fire" || (!node.AllowMultidot && !node.AllowAreaDamage))' in IMPL
    assert "state.WasInCombat = true;" in IMPL


def test_platform_completion_requires_all_declared_destination_dimensions():
    for token in (
        "bool const declaredDestinationMap",
        "bool const declaredDestinationArea",
        "bool const declaredDestinationZ",
        "(!declaredDestinationMap",
        "(!declaredDestinationArea",
        "(!declaredDestinationZ || destinationZMatches)",
        'raidAdapter.PlatformPolicy != "altitude"',
        "|| destinationZMatches;",
        'raidAdapter.PlatformPolicy != "flying" || bot->IsFlying()',
    ):
        assert token in IMPL
    platform_start = IMPL.index("bool const platformPostcondition")
    platform_end = IMPL.index("bool const altitudePostcondition", platform_start)
    platform = IMPL[platform_start:platform_end]
    assert "|| (raidAdapter.PlatformDestinationMapId" not in platform
    assert "|| (raidAdapter.PlatformDestinationAreaId" not in platform


def test_phase1_jump_platform_altitude_and_flying_require_native_postconditions():
    for token in (
        'bot->GetMapId() == raidAdapter.PlatformDestinationMapId',
        'bot->GetAreaId() == raidAdapter.PlatformDestinationAreaId',
        'bot->GetPositionZ() >= raidAdapter.PlatformMinimumZ',
        'bot->GetPositionZ() <= raidAdapter.PlatformMaximumZ',
        'raidAdapter.PlatformPolicy != "flying" || bot->IsFlying()',
        '"raid_jump_pad_native_submitted"',
        '"raid_platform_native_transfer_complete"',
        '"raid_platform_native_regroup_complete"',
        'raidAdapter.PlatformPolicy != "ground"',
        'bot->GetExactDist2d(raidAnchors.ResolvedX, raidAnchors.ResolvedY)',
    ):
        assert token in IMPL
    assert 'node.InteractionKind != "jump_pad"' in IMPL
    assert 'node.MovementLink != "none" && node.MovementLink != "regroup"' in IMPL
    assert "&& jumpTransferResolved" in IMPL
    assert "state.LastRaidJumpPadEntrySubmitted == raidAdapter.JumpPadEntry" in IMPL
    assert "state.LastRaidJumpPadRouteGeneration == Party().ValidationRouteGeneration" in IMPL
    assert 'if (raidAdapter.InteractionKind == "jump_pad")' in IMPL


def test_generic_contract_has_explicit_soak_dispel_and_cooldown_assignments():
    cone = next(
        row["mechanic_contract"] for row in GENERIC_SMOKE["routes"]
        if row["mechanic_contract"]["formation_family"] == "cone"
    )
    assert cone["soak_minimum_count"] == len(cone["soak_roster_slots"])
    assert cone["dispel_owner_slot"] != cone["dispel_backup_slot"]
    assert cone["cooldown_trigger_spell_id"] > 0
    for token in (
        "raid_soak_wait_for_assigned_count", "raid_dispel_owner",
        "raid_dispel_backup", "raid_cooldown_schedule",
    ):
        assert token in IMPL


def test_runtime_records_live_identity_lockout_and_unique_leases():
    for token in (
        "raid.GroupGuid = group->GetGUID();",
        "raid.LeaderGuid = leader->GetGUID();",
        "raid.MapDifficulty",
        "raid.LockoutSaveId = bind->save->GetInstanceId();",
        "slot.LeaseOwned = LeaseOwnedByCurrentCohort(guid, slot.LeaseRoleSlot);",
        "raid.RosterComplete = raid.ActiveSize == raid.ExpectedSize;",
    ):
        assert token in IMPL


def test_permanent_roster_slots_and_exact_role_shapes_fail_closed():
    for token in (
        "std::string RosterSlotId",
        "std::string LeaseRoleSlot",
        "std::string ClassSpec",
        "std::string GearIdentity",
        "bool RosterCompositionValid",
    ):
        assert token in HEADER
    for token in (
        "lease.RoleSlot == roleSlot",
        "SelectNextRosterSlot()",
        'slot.RosterSlotId = "raid_tank_"',
        "raid.ExpectedSize == 10 ? 3 : 6",
        "raid.ExpectedSize == 10 ? 5 : 17",
        '"exact_raid_role_composition_mismatch"',
    ):
        assert token in IMPL


def test_permanent_gear_identity_excludes_temporary_weapon_enchants():
    assert "enchantSlot == TEMP_ENCHANTMENT_SLOT" in IMPL
    assert "? 0 : item->GetEnchantmentId" in IMPL


def test_native_ready_check_is_explicit_attempt_and_wipe_scoped():
    command = (ROOT / "src/server/scripts/Commands/cs_healerbot.cpp").read_text(encoding="utf-8")
    for token in (
        "RequestNativeRaidReadyCheckForCohort",
        "MSG_RAID_READY_CHECK",
        "HandleRaidReadyCheckOpcode(request);",
        "HandleRaidReadyCheckOpcode(response);",
        "NativeReadyCheckResponseCount",
        "NativeReadyCheckActionGeneration",
        "NativeReadyCheckActionAttemptId",
        "NativeReadyCheckActionWipeGeneration",
        "raid.NativeReadyCheckActionObserved = false;",
    ):
        assert token in HEADER or token in IMPL
    assert '{ "readycheck"' in command
    assert "HandleAutoReadyCheckCommand" in command


def test_status_diagnose_trace_and_evidence_expose_raid_identity():
    assert IMPL.count('\\\"raid_runtime\\\"') >= 5
    assert "++Cohort().Raid.EvidenceSequence;" in IMPL
    assert 'context << "{\\\"raid_runtime\\\":" << BuildRaidRuntimeJson()' in IMPL
    assert '\\\"strategy_id\\\"' in IMPL
    assert '\\\"assignment_generation\\\"' in IMPL


def test_cleanup_preserves_terminal_raid_identity_for_final_status_demux():
    assert "uint64 ProfileGeneration" in HEADER
    assert "std::string ProfileContentHash" in HEADER
    release_start = IMPL.index("void BotWorldPopulationMgr::ReleaseCohortLeases")
    release = IMPL[
        release_start:
        IMPL.index("bool BotWorldPopulationMgr::LeaseOwnedByCurrentCohort", release_start)
    ]
    assert "Cohort().Raid = RaidRuntime();" not in release
    stop = IMPL[
        IMPL.index("std::string BotWorldPopulationMgr::StopAutonomyForCohort"):
        IMPL.index("std::string BotWorldPopulationMgr::SelectRuntimeProfileForCohort")
    ]
    for token in (
        "uint64 const serverEpoch = Cohort().Raid.ServerEpoch;",
        "uint64 const attemptId = Cohort().Raid.AttemptId;",
        "Cohort().Raid.Active = false;",
        "Cohort().Raid.ActiveSize = 0;",
        "Cohort().Raid.AliveSize = 0;",
    ):
        assert token in stop
    assert "std::vector<uint32> Talents" in HEADER
    assert "std::vector<uint32> Glyphs" in HEADER
    assert "std::vector<RaidRosterItemIdentity> GearManifest" in HEADER
    roster_json = IMPL[
        IMPL.index("std::string BotWorldPopulationMgr::BuildRaidRuntimeJson"):
        IMPL.index("std::string BotWorldPopulationMgr::BuildRaidPositioningAnchorsJson")
    ]
    assert "ObjectAccessor::FindPlayer(slot.Guid)" not in roster_json
    assert "slot.Talents" in roster_json
    assert "slot.Glyphs" in roster_json
    assert "slot.GearManifest" in roster_json


def test_live_kill_sync_holds_low_targets_until_every_peer_reaches_floor():
    assert "lowestPct <= raidAdapter.KillSyncExecutionFloorPct && peerAboveExecutionFloor" in IMPL
    assert '"raid_kill_sync_execution_hold_low_target"' in IMPL
    assert 'result.Action = "raid_kill_sync_balance_high_target";' in IMPL
    assert "UnitHealthPct(highest) <= raidAdapter.KillSyncExecutionFloorPct" not in IMPL


def test_runtime_reconstructs_native_boss_wipe_reset_and_recovery_state():
    raid_struct = HEADER.index("struct RaidRuntime")
    cohort_struct = HEADER.index("struct CohortRuntime")
    runtime = HEADER[raid_struct:cohort_struct]
    for token in (
        "uint32 AliveSize",
        "uint64 WipeGeneration",
        "uint64 BossResetGeneration",
        "uint64 RecoveryGeneration",
        "bool EncounterInProgress",
        "bool ReadyCheckSatisfied",
        "bool NativeDeathObserved",
        "bool NativeReleaseObserved",
        "bool NativeResurrectionObserved",
        "bool NativeRunbackObserved",
        "bool NativeRecoveryEvidenceComplete",
        "std::vector<uint8> BossStates",
    ):
        assert token in runtime
    for token in (
        "instance->IsEncounterInProgress()",
        "instance->GetEncounterCount()",
        "instance->GetBossState(bossId)",
        'raid.WipeState = "wiped";',
        'raid.RecoveryState = "recovered_ready_check";',
        "++raid.BossResetGeneration;",
        "raid.ReadyCheckSatisfied = raid.RosterComplete",
        '\\\"boss_states\\\"',
    ):
        assert token in IMPL


def test_bwd_profile_pins_10n_and_world_defaults_are_documented():
    profiles = json.loads((ROOT / "dataset/bot_runtime_profiles/profiles.json").read_text(encoding="utf-8"))
    bwd = next(profile for profile in profiles["profiles"] if profile["name"] == "blackwing_descent_10n")
    assert bwd["raid_size"] == 10
    assert bwd["raid_difficulty"] == 0

    conf = (ROOT / "src/server/worldserver/worldserver.conf.dist").read_text(encoding="utf-8")
    assert "BotProgression.RaidSize = 10" in conf
    assert "BotProgression.RaidDifficulty = 0" in conf
