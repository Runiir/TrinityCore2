import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEADER = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h").read_text(encoding="utf-8")
IMPL = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text(encoding="utf-8")
MAGMAW_IMPL = (
    ROOT / "src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent/boss_magmaw.cpp"
).read_text(encoding="utf-8")
GENERIC_SMOKE = json.loads((ROOT / "experiments/configs/cata_raid_phase1_generic_mechanic_smoke_v1.json").read_text())


def test_bwd_entry_to_magmaw_uses_frozen_junction_below_native_path_limit():
    config = json.loads(
        (ROOT / "experiments/configs/validation_scenarios_cata_001.json").read_text()
    )
    bwd = next(row for row in config["scenarios"] if row["id"] == "blackwing_descent_10n")
    trash, junction, corridor, magmaw = bwd["route"][:4]

    assert (trash["label"], junction["label"], corridor["label"], magmaw["label"]) == (
        "entry trash",
        "BWD entrance junction regroup",
        "Drakonid corridor pack",
        "Magmaw",
    )
    assert junction["kind"] == "regroup"
    assert junction["step"] == 2
    assert {axis: junction[axis] for axis in ("x", "y", "z", "o")} == {
        axis: bwd["start_position"][axis] for axis in ("x", "y", "z", "o")
    }
    assert junction["source_guid"] == "blackwing_descent_10n.start_position"
    assert junction["source_table"] == "validation_scenario.start_position"

    path_limit_yards = 74 * 4.0
    direct_leg = math.dist(
        (trash["x"], trash["y"], trash["z"]),
        (
            magmaw["navigation_anchor"]["x"],
            magmaw["navigation_anchor"]["y"],
            magmaw["navigation_anchor"]["z"],
        ),
    )
    first_leg = math.dist(
        (trash["x"], trash["y"], trash["z"]),
        (junction["x"], junction["y"], junction["z"]),
    )
    second_leg = math.dist(
        (junction["x"], junction["y"], junction["z"]),
        (corridor["x"], corridor["y"], corridor["z"]),
    )
    third_leg = math.dist(
        (corridor["x"], corridor["y"], corridor["z"]),
        (
            magmaw["navigation_anchor"]["x"],
            magmaw["navigation_anchor"]["y"],
            magmaw["navigation_anchor"]["z"],
        ),
    )

    assert direct_leg > path_limit_yards
    assert first_leg < path_limit_yards
    assert second_leg < path_limit_yards
    assert third_leg < path_limit_yards


def test_bwd_drakonid_corridor_has_explicit_native_pack_hazard_and_range_contract():
    config = json.loads(
        (ROOT / "experiments/configs/validation_scenarios_cata_001.json").read_text()
    )
    bwd = next(row for row in config["scenarios"] if row["id"] == "blackwing_descent_10n")
    corridor = next(row for row in bwd["route"] if row["label"] == "Drakonid corridor pack")

    assert corridor["step"] == 3
    assert corridor["kind"] == "trash"
    assert corridor["source_entry"] == 42649
    assert corridor["source_guid"] == "250050"
    assert corridor["pack_target_entries"] == [42649, 42362]
    assert corridor["cluster_radius_yards"] == 48.0
    assert (corridor["hazard_source_entry"], corridor["hazard_damage_spell_id"]) == (42690, 79580)
    assert (corridor["hazard_shape"], corridor["hazard_radius_yards"]) == ("radial", 20.0)
    assert (corridor["minimum_distance_source_entry"], corridor["minimum_distance_yards"]) == (42362, 15.0)
    assert bwd["mechanic_profiles"]["trash_ground_danger_movement"] == [
        "ground_danger", "movement_check", "minimum_distance"
    ]


def _validation_route_anchor_model(*, canonical_anchor, safe_memory_anchor,
                                   override_reason, pack_generation,
                                   route_generation, live_members, dead_members,
                                   transition_members, active_combat,
                                   repeated_death_near_route):
    """Model only the route-anchor precedence relevant to the live-pack bug."""
    live_pack_authority = (
        pack_generation == route_generation
        and any(
            guid not in dead_members and guid not in transition_members
            for guid in live_members
        )
    )
    if (
        override_reason == "validation_route_safe_memory_after_death_loop"
        and live_pack_authority
    ):
        override_reason = None

    if override_reason:
        return safe_memory_anchor, override_reason
    if (
        not active_combat
        and repeated_death_near_route
        and not live_pack_authority
    ):
        return safe_memory_anchor, "validation_route_safe_memory_after_death_loop"
    return canonical_anchor, "validation_route"


def _legacy_validation_route_anchor_model(*, canonical_anchor,
                                          safe_memory_anchor, override_reason,
                                          active_combat,
                                          repeated_death_near_route):
    """The pre-fix precedence: any installed override wins over the route."""
    if override_reason:
        return safe_memory_anchor, override_reason
    if not active_combat and repeated_death_near_route:
        return safe_memory_anchor, "validation_route_safe_memory_after_death_loop"
    return canonical_anchor, "validation_route"


def test_live_pack_is_counterexample_to_generic_safe_memory_route_recovery():
    canonical = (-328.403, -88.036, 213.921)
    safe_memory = (-339.765, -316.824, 212.549)
    live_members = {59, 60}

    # Before the authority fix, an already-installed generic override wins
    # even though both persisted members belong to the current pack.
    legacy_anchor, legacy_reason = _legacy_validation_route_anchor_model(
        canonical_anchor=canonical,
        safe_memory_anchor=safe_memory,
        override_reason="validation_route_safe_memory_after_death_loop",
        active_combat=False,
        repeated_death_near_route=True,
    )
    assert (legacy_anchor, legacy_reason) == (
        safe_memory,
        "validation_route_safe_memory_after_death_loop",
    )

    anchor, reason = _validation_route_anchor_model(
        canonical_anchor=canonical,
        safe_memory_anchor=safe_memory,
        override_reason="validation_route_safe_memory_after_death_loop",
        pack_generation=7,
        route_generation=7,
        live_members=live_members,
        dead_members=set(),
        transition_members=set(),
        active_combat=False,
        repeated_death_near_route=True,
    )
    assert (anchor, reason) == (canonical, "validation_route")

    # Generation, death, and transition mismatches revoke this authority and
    # leave the safe-memory fallback available exactly as before.
    for pack_generation, dead_members, transition_members in (
        (6, set(), set()),
        (7, {59, 60}, set()),
        (7, set(), {59, 60}),
    ):
        fallback_anchor, fallback_reason = _validation_route_anchor_model(
            canonical_anchor=canonical,
            safe_memory_anchor=safe_memory,
            override_reason=None,
            pack_generation=pack_generation,
            route_generation=7,
            live_members=live_members,
            dead_members=dead_members,
            transition_members=transition_members,
            active_combat=False,
            repeated_death_near_route=True,
        )
        assert (fallback_anchor, fallback_reason) == (
            safe_memory,
            "validation_route_safe_memory_after_death_loop",
        )


def test_live_pack_authority_clears_and_blocks_safe_memory_override():
    route_start = IMPL.index("bool BotWorldPopulationMgr::TryValidationRouteObjective")
    route_end = IMPL.index("bool BotWorldPopulationMgr::IsBossContext", route_start)
    route_runtime = IMPL[route_start:route_end]
    authority = route_runtime.index("routeHasCurrentGenerationLivePackAuthority")
    anchor_end = route_runtime.index("Map* routeMap", authority)
    anchor_logic = route_runtime[authority:anchor_end]

    assert "persistedValidationRoutePackHasLiveMembers()" in anchor_logic
    assert 'state.ValidationRouteAnchorOverrideReason\n            == "validation_route_safe_memory_after_death_loop"' in anchor_logic
    clear = anchor_logic.index("state.ValidationRouteAnchorOverrideValid = false;")
    assert anchor_logic.index("routeHasCurrentGenerationLivePackAuthority") < clear
    install = anchor_logic.rindex("routeHasCurrentGenerationLivePackAuthority)")
    assert "&& !routeHasCurrentGenerationLivePackAuthority" in anchor_logic[install - 120:install + 80]
    assert "validation_route_partial_wipe_retreat_rendezvous" in anchor_logic
    assert "validation_route_live_pack_reapproach" in route_runtime

    helper_start = route_runtime.index("auto persistedValidationRoutePackHasLiveMembers")
    helper_end = route_runtime.index("auto activeValidationRoutePackTarget", helper_start)
    helper = route_runtime[helper_start:helper_end]
    assert "ValidationRoutePackGeneration != Party().ValidationRouteGeneration" in helper
    assert "ValidationRoutePackDeathGuids.find(guid)" in helper
    assert "ValidationRoutePackTransitionGuids.find(guid)" in helper


def _partial_recovery_model(*, pack_generation, route_generation, pack_members,
                            dead_pack_members, transition_pack_members,
                            live_pack_attackable, live_pack_combat_linked,
                            living_roles, dead_roles, group_combat_active,
                            living_combat_resurrection, native_full_wipe_only,
                            living_tank_paths=None, frozen_living_roles=None):
    """Model the narrow live-pack precedence over partial-death retreat."""
    exact_live_pack = (
        pack_generation == route_generation
        and any(
            guid not in dead_pack_members and guid not in transition_pack_members
            for guid in pack_members
        )
        and live_pack_attackable
        and live_pack_combat_linked
    )
    frozen_roles = frozen_living_roles if frozen_living_roles is not None else living_roles
    live_pack_can_continue = (
        exact_live_pack
        and "tank" in frozen_roles
        and "healer" in frozen_roles
        and "dps" in frozen_roles
        and (any(living_tank_paths.values()) if living_tank_paths is not None else True)
    )
    alive_count = len(living_roles)
    dead_count = len(dead_roles)
    critical_role_dead = bool(set(dead_roles) & {"tank", "healer"})
    majority_dead = alive_count <= 2 and dead_count >= 3
    generic_retreat = (
        (majority_dead or critical_role_dead)
        and group_combat_active
        and not living_combat_resurrection
    )
    if generic_retreat and not live_pack_can_continue:
        return "native_full_wipe_hold_partial_death" if native_full_wipe_only else "tactical_retreat_no_combat_res"
    return "continue_live_pack" if live_pack_can_continue else "native_route_recovery"


def test_partial_death_live_drudge_pack_precedes_generic_retreat():
    # Exact Phase 1 counterexample: Chainwielder is dead, Drudges 59/60 are
    # current-generation live members, and the off-tank/healers/living DPS can
    # continue natively despite the main tank and two DPS being dead.
    decision = _partial_recovery_model(
        pack_generation=3,
        route_generation=3,
        pack_members={27, 59, 60},
        dead_pack_members={27},
        transition_pack_members=set(),
        live_pack_attackable=True,
        live_pack_combat_linked=True,
        living_roles=["tank", "healer", "healer", "dps", "dps", "dps", "dps"],
        dead_roles=["tank", "dps", "dps"],
        group_combat_active=True,
        living_combat_resurrection=False,
        native_full_wipe_only=False,
        living_tank_paths={"main_tank": False, "off_tank": True},
    )
    assert decision == "continue_live_pack"


def test_partial_death_live_pack_guard_falls_back_when_composition_is_nonviable():
    for kwargs, expected in (
        (
            dict(
                pack_generation=2, route_generation=3,
                pack_members={59, 60}, dead_pack_members=set(),
                transition_pack_members=set(), live_pack_attackable=True,
                live_pack_combat_linked=True, living_roles=["healer", "dps"],
                dead_roles=["tank", "healer", "dps"], group_combat_active=True,
                living_combat_resurrection=False, native_full_wipe_only=False,
            ),
            "tactical_retreat_no_combat_res",
        ),
        (
            dict(
                pack_generation=3, route_generation=3,
                pack_members={59, 60}, dead_pack_members=set(),
                transition_pack_members=set(), live_pack_attackable=True,
                live_pack_combat_linked=True, living_roles=["tank"],
                dead_roles=["healer", "dps", "dps"], group_combat_active=True,
                living_combat_resurrection=False, native_full_wipe_only=False,
                living_tank_paths={"off_tank": False},
            ),
            "tactical_retreat_no_combat_res",
        ),
        (
            dict(
                pack_generation=3, route_generation=3,
                pack_members={59, 60}, dead_pack_members=set(),
                transition_pack_members=set(), live_pack_attackable=True,
                live_pack_combat_linked=True,
                # A foreign same-map tank and mutable role drift cannot
                # replace missing frozen roster roles.
                living_roles=["tank", "healer", "dps", "tank"],
                frozen_living_roles=["healer", "dps"],
                dead_roles=["tank", "healer", "dps"], group_combat_active=True,
                living_combat_resurrection=False, native_full_wipe_only=False,
                living_tank_paths={"foreign_tank": True},
            ),
            "tactical_retreat_no_combat_res",
        ),
        (
            dict(
                pack_generation=3, route_generation=3,
                pack_members={59, 60}, dead_pack_members={59, 60},
                transition_pack_members=set(), live_pack_attackable=True,
                live_pack_combat_linked=True, living_roles=["tank", "healer"],
                dead_roles=["tank", "healer", "dps"], group_combat_active=True,
                living_combat_resurrection=False, native_full_wipe_only=True,
            ),
            "native_full_wipe_hold_partial_death",
        ),
    ):
        assert _partial_recovery_model(**kwargs) == expected


def test_partial_death_live_pack_guard_is_before_generic_retreat_and_preserves_fallbacks():
    objective = IMPL[
        IMPL.index("bool BotWorldPopulationMgr::TryValidationRouteObjective"):
        IMPL.index("bool BotWorldPopulationMgr::IsBossContext")
    ]
    guard = objective.index("auto currentLiveValidationRoutePackCanContinue")
    retreat_gate = objective.index("if ((majorityDead || criticalRoleDead)", guard)
    assert guard < retreat_gate
    helper_logic = objective[guard:objective.index("// If most of the party", guard)]
    for token in (
        'Cohort().Config.ValidationRouteKind == "boss"',
        "Cohort().Raid.RosterComplete",
        "Cohort().Raid.UniqueLeases",
        "Cohort().Raid.RosterCompositionValid",
        "Cohort().Raid.RosterByGuid.size() != Party().Bots.size()",
        "persistedValidationRoutePackHasLiveMembers()",
        "auto isSharedValidationCohortCombatLinked",
        "auto frozenRaidRole",
        "std::vector<Player*> livingTanks",
        "std::sort(livingTanks.begin(), livingTanks.end()",
        "std::vector<ObjectGuid> packGuids",
        "std::sort(packGuids.begin(), packGuids.end()",
        "IsValidationCohortMemberInOriginalInstance(cohortState, member)",
        "RosterByGuid.find(cohortState.Guid.GetCounter())",
        "LeaseOwnedByCurrentCohort(cohortState.Guid.GetCounter(), rosterSlot.RosterSlotId)",
        "rosterSlot.Role",
        "rosterSlot.Active",
        "rosterSlot.LeaseOwned",
        "hasStrictNativePath(tank, creature)",
        "tank->IsValidAttackTarget(creature)",
        "livingTanksCount > 0 && livingHealers > 0 && livingDps > 0",
    ):
        assert token in helper_logic
    assert "activeValidationRoutePackTarget()" not in helper_logic
    assert "bot->GetMap()" not in helper_logic
    assert "GetDungeonRole" not in helper_logic
    assert "&& !currentLivePackCanContinue" in objective[retreat_gate:retreat_gate + 180]
    assert 'action = "native_full_wipe_hold";' in objective
    assert 'validation_route_partial_wipe_retreat_rendezvous' in objective


def test_boss_route_rejects_undeclared_engaged_trash_before_shared_actions():
    route_runtime = IMPL[
        IMPL.index("bool BotWorldPopulationMgr::TryValidationRouteObjective"):
        IMPL.index("bool BotWorldPopulationMgr::TryValidationRouteReadiness")
    ]
    early_rejection = route_runtime.index(
        'if (Cohort().Config.ValidationRouteKind == "boss"\n'
        "        && trashThreatControl.EngagedCount > 0"
    )

    assert early_rejection < route_runtime.index("bool insecureTrashSwarm")
    assert early_rejection < route_runtime.index("hunterTrashMisdirectionActive")
    assert early_rejection < route_runtime.index('action = "misdirection_to_tank";')
    assert early_rejection < route_runtime.index('action = "trash_density_area_threat";')
    assert 'rejected, "boss_route_target_not_declared"' in route_runtime[
        early_rejection:route_runtime.index("bool insecureTrashSwarm")
    ]
    assert 'action = "boss_route_prerequisite_blocked";' in route_runtime[
        early_rejection:route_runtime.index("bool insecureTrashSwarm")
    ]


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
        "validation_raid_preflight_initial_recovery_state",
        "ValidationGhostCharacterFlag",
        "ValidationResurrectAtLoginFlag",
        "ValidationGhostAuraId",
        "SELECT c.health, c.power1, c.characterFlags, c.at_login",
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
    assert "!bot->IsAlive()" in admission_runtime
    assert "bot->HasFlag(PLAYER_FLAGS, PLAYER_FLAGS_GHOST)" in admission_runtime
    assert "bot->HasCorpse()" in admission_runtime
    assert "state.ValidationCohortInstanceId != bot->GetInstanceId()" in admission_runtime


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
        "rollbackAdmission(\"validation_raid_admission_exact_group_or_alive_state_failed\")",
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
        "IsNativeReleasedGhostWorldport(*state, bot)",
        "IsNativeBlackwingDescentRunbackWorldport(*state, bot)",
        "!bot->IsInWorld() && !nativeRecoveryWorldport",
        "IsValidationCohortMemberInOriginalInstance(*state, bot)",
        "group->GetGUID() != state->ValidationCohortGroupGuid",
        "group->GetLeaderGUID() != state->ValidationCohortLeaderGuid",
        "Cohort().Raid.GroupGuid == exactGroupGuid",
        "sBotMgr->RemoveWorldBot(state.Guid);",
        "ReleaseBotGuid(guid);",
        "Party() = PartyRuntime();",
        "Cohort().Raid = RaidRuntime();",
        "Cohort().RosterLeases.clear();",
        "Cohort().Metrics.ActiveBots = 0;",
        '"validation_raid_admission_identity_drift:" + identityDriftDetail',
    ):
        assert token in complete
    cleanup = complete.index("if (!exactIdentity)")
    latch = complete.index("Cohort().ValidationRaidAdmissionFailed = true;", cleanup)
    assert cleanup < complete.index("sBotMgr->RemoveWorldBot(state.Guid);", cleanup) < latch


def test_completed_validation_raid_defers_only_exact_native_recovery_worldports():
    def accepted(*, in_world, loaded=True, group=True, lease=True, slot=True,
                 group_identity=True, original_instance=True,
                 native_release=False, native_runback=False):
        if not loaded or not group or not lease or not slot or not group_identity:
            return False
        native_recovery = (not in_world) and (native_release or native_runback)
        if not in_world and not native_recovery:
            return False
        if not native_recovery and not original_instance:
            return False
        return True

    assert accepted(in_world=True)
    assert accepted(in_world=False, native_release=True)
    assert accepted(in_world=False, native_runback=True)
    assert not accepted(in_world=False)
    assert not accepted(in_world=False, native_release=True, loaded=False)
    assert not accepted(in_world=False, native_release=True, group=False)
    assert not accepted(in_world=False, native_release=True, lease=False)
    assert not accepted(in_world=False, native_release=True, slot=False)
    assert not accepted(in_world=False, native_release=True, group_identity=False)
    assert not accepted(in_world=True, original_instance=False)

    population = IMPL[
        IMPL.index("if (Cohort().ValidationRaidAdmissionComplete)"):
        IMPL.index("auto terminalFailure")
    ]
    assert population.index("bool const nativeRecoveryWorldport") < population.index(
        "IsValidationCohortMemberInOriginalInstance(*state, bot)")
    assert "No generic death or teleport grace window" in population
    assert "validation raid admission deferred native recovery worldports" in population
    for detail in (
        "roster_state_missing", "loaded_bot_missing", "native_group_missing",
        "not_in_world_without_native_recovery_authority", "lease_identity_mismatch",
        "frozen_roster_slot_mismatch", "frozen_group_or_leader_mismatch",
        "frozen_map_or_instance_mismatch", "split_native_group",
    ):
        assert detail in population


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
    assert "sObjectMgr->GetClosestGraveyard(*bot, bot->GetTeam()" in native_release
    assert "graveyard->Continent != entranceEntry->ContinentID" in native_release
    assert "destination.GetPositionX() - graveyard->Loc.X" in native_release
    assert "destination.GetPositionY() - graveyard->Loc.Y" in native_release
    assert "destination.GetPositionZ() - graveyard->Loc.Z" in native_release
    assert "GetGraveyardOrientation(graveyard->ID)" in native_release
    assert "!bot->GetTeleportDestInstanceId()" in native_release
    assert "bot->GetTeleportDestOptions() == TELE_TO_NONE" in native_release
    assert "destination.GetMapId() == entranceDestination->target_mapId" in native_release
    assert "bot->GetTeleportDestOptions() == TELE_TO_NOT_LEAVE_TRANSPORT" in native_release

    assert "ResolveNativeBlackwingDescentEntrance(entranceEntry, entranceDestination)" in native_runback
    assert "bot->GetMapId() == entranceEntry->ContinentID" in native_runback
    assert "uint32 entranceTriggerId = BlackwingDescentEntranceTriggerId;" in native_runback
    assert "WorldPacket areaTrigger(CMSG_AREATRIGGER" in native_runback
    assert "TeleportTo(" not in native_runback
    assert "NearTeleportTo(" not in native_runback
    assert "ResurrectPlayer" not in native_runback


def test_validation_party_resurrection_fails_closed_until_exact_corpse_authority_exists():
    start = IMPL.index("bool BotWorldPopulationMgr::TryNativePartyResurrection")
    end = IMPL.index("bool BotWorldPopulationMgr::TryValidationRouteReadiness", start)
    native = IMPL[start:end]

    gate = "Cohort().Config.ValidationRouteEnable && Cohort().Config.AllowRaids"
    assert gate in native
    assert "!HasNativeRaidCorpseAuthority(*memberState, member)" in native
    assert native.index("memberState != nullptr") < native.index(gate) < native.index("bool requestedByHealer")
    assert "KillPlayer leaves only a dead Player object" in native
    assert "Non-validation party resurrection deliberately keeps its" in native

    authority_start = IMPL.index("bool BotWorldPopulationMgr::HasNativeRaidCorpseAuthority")
    authority_end = IMPL.index("bool BotWorldPopulationMgr::ResolveNativeBlackwingDescentEntrance", authority_start)
    authority = IMPL[authority_start:authority_end]
    for rejection in (
        "!bot->HasCorpse()",
        "bot->GetCorpseLocation().GetMapId() != state.ValidationCohortMapId",
        "originalCorpse->GetOwnerGUID() == bot->GetGUID()",
        "originalCorpse->GetInstanceId() == state.ValidationCohortInstanceId",
    ):
        assert rejection in authority


def test_bot_dungeon_cross_map_guard_allows_only_exact_native_ghost_graveyard_release():
    player_impl = (ROOT / "src/server/game/Entities/Player/Player.cpp").read_text()
    teleport = player_impl[
        player_impl.index("bool Player::TeleportTo(uint32 mapid"):
        player_impl.index("bool Player::TeleportTo(WorldLocation const& loc", player_impl.index("bool Player::TeleportTo(uint32 mapid"))
    ]

    assert "IsBotSession() && GetMap() && GetMap()->IsDungeon() && mapid != GetMapId()" in teleport
    assert "an exact owned corpse in this dungeon instance" in teleport
    assert "!IsAlive() && HasFlag(PLAYER_FLAGS, PLAYER_FLAGS_GHOST) && HasCorpse()" in teleport
    assert "GetCorpseLocation().GetMapId() == GetMapId()" in teleport
    assert "corpse->GetOwnerGUID() == GetGUID()" in teleport
    assert "corpse->GetInstanceId() == GetInstanceId()" in teleport
    assert "sObjectMgr->GetClosestGraveyard(*this, GetTeam(), this)" in teleport
    assert "mapid == graveyard->Continent" in teleport
    assert "options == TELE_TO_NONE && !instanceId" in teleport
    assert "std::fabs(x - graveyard->Loc.X) <= 0.01f" in teleport
    assert "std::fabs(y - graveyard->Loc.Y) <= 0.01f" in teleport
    assert "std::fabs(z - graveyard->Loc.Z) <= 0.01f" in teleport
    assert "std::fabs(orientation - expectedOrientation) <= 0.01f" in teleport
    assert "if (!nativeGhostRelease)" in teleport
    assert "return false;" in teleport.split("if (!nativeGhostRelease)", 1)[1]


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


def test_magmaw_body_lifecycle_is_manual_reconstructable_and_fail_closed():
    reset = MAGMAW_IMPL[
        MAGMAW_IMPL.index("void Reset() override"):
        MAGMAW_IMPL.index("void JustAppeared() override")
    ]
    appeared = MAGMAW_IMPL[
        MAGMAW_IMPL.index("void JustAppeared() override"):
        MAGMAW_IMPL.index("void JustEngagedWith(Unit* who) override")
    ]
    engaged = MAGMAW_IMPL[
        MAGMAW_IMPL.index("void JustEngagedWith(Unit* who) override"):
        MAGMAW_IMPL.index("void PassengerBoarded", MAGMAW_IMPL.index("void JustEngagedWith(Unit* who) override"))
    ]
    setup = MAGMAW_IMPL[
        MAGMAW_IMPL.index("uint8 SetupBody()"):
        MAGMAW_IMPL.index("Creature* GetBodyPart", MAGMAW_IMPL.index("uint8 SetupBody()"))
    ]

    assert "RebuildBody()" in appeared
    assert "_magmaProjectileCount = 0;" in reset
    assert "_headEngaged = false;" in reset
    assert "_heroicPhaseTwoActive = !IsHeroic();" in reset
    assert "me->SetReactState(REACT_PASSIVE);" in reset
    assert "missingBodyMask = GetMissingBodyMask();" in engaged
    assert "RebuildBody();" not in engaged
    held_closed = engaged[engaged.index("if (missingBodyMask)"):]
    assert "EnterEvadeMode(EVADE_REASON_OTHER);" in held_closed
    assert held_closed.index("EnterEvadeMode(EVADE_REASON_OTHER);") < held_closed.index("return;")
    assert held_closed.index("return;") < held_closed.index("BossAI::JustEngagedWith(who);")
    missing = MAGMAW_IMPL[
        MAGMAW_IMPL.index("uint8 GetMissingBodyMask() const"):
        MAGMAW_IMPL.index("void DespawnBody()")
    ]
    assert "!bodyPart->IsAlive()" in missing
    assert "!bodyPart->IsInWorld()" in missing
    assert "bodyPart->GetVehicleBase() != me" in missing
    assert setup.count("TEMPSUMMON_MANUAL_DESPAWN") == 4
    assert "if (!pincer1)" in setup
    assert "if (!pincer2)" in setup
    assert setup.index("if (missingBodyMask)") < setup.index("pincer1->EnterVehicle")
    assert "return missingBodyMask;" in setup
    assert "_bodyPartGUIDs[BODY_PART_EXPOSED_HEAD_1] = exposedHead1->GetGUID();" in setup
    assert "_bodyPartGUIDs[BODY_PART_EXPOSED_HEAD_2] = exposedHead2->GetGUID();" in setup
    assert "DespawnBody();" in setup
    died = MAGMAW_IMPL[
        MAGMAW_IMPL.index("void JustDied(Unit* /*killer*/) override"):
        MAGMAW_IMPL.index("void JustSummoned", MAGMAW_IMPL.index("void JustDied(Unit* /*killer*/) override"))
    ]
    assert died.index("DespawnBody();") < died.index("_JustDied();")


def test_phase1_diagnosis_retains_exact_live_location_and_recovery_state():
    assert r'\"current_position\":{\"x\"' in IMPL
    assert r'\"alive\":' in IMPL
    assert r'\"ghost\":' in IMPL
    assert r'\"has_corpse\":' in IMPL
    assert r'\"in_world\":' in IMPL


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


def test_boss_nodes_fail_closed_on_undeclared_prerequisite_hostiles():
    route_start = IMPL.index("bool BotWorldPopulationMgr::TryValidationRouteObjective")
    route_end = IMPL.index("bool BotWorldPopulationMgr::IsBossContext", route_start)
    route_runtime = IMPL[route_start:route_end]

    assert 'if (!tankFocusIsRouteTarget)' in route_runtime
    assert '"boss_route_target_not_declared"' in route_runtime
    assert 'action = "boss_route_prerequisite_blocked";' in route_runtime
    assert '&& !isValidationRouteObjectiveTarget(seenRouteTarget->ToCreature())' in route_runtime
    assert '"boss_route_undeclared_prerequisite_blocked"' in route_runtime
    scan_start = route_runtime.index("Creature* prerequisiteTarget = nullptr;")
    boss_hold = route_runtime.rindex(
        'if (Cohort().Config.ValidationRouteKind == "boss")', 0, scan_start
    )
    assert boss_hold < scan_start


def test_raid_trash_uses_native_threat_headroom_and_declared_minimum_distance():
    route_start = IMPL.index("bool BotWorldPopulationMgr::TryValidationRouteObjective")
    route_end = IMPL.index("bool BotWorldPopulationMgr::IsBossContext", route_start)
    route_runtime = IMPL[route_start:route_end]

    minimum_start = route_runtime.index("auto tryValidationRouteMinimumDistance")
    minimum_end = route_runtime.index("auto tryValidationRouteAdds", minimum_start)
    minimum = route_runtime[minimum_start:minimum_end]
    assert "ValidationRouteMinimumDistanceSourceEntry" in minimum
    assert "ValidationRouteMinimumDistanceYards" in minimum
    assert 'profile.MovementDirective == "ranged"' in minimum
    assert 'profile.MovementDirective == "healer_support"' in minimum
    assert 'creature->GetEntry() != sourceEntry' in minimum
    assert 'safeDistance = minimumDistance + 2.0f' in minimum
    assert "sources.push_back(creature)" in minimum
    assert "for (size_t left = 0; left < sources.size(); ++left)" in minimum
    assert "addDirection(-pairY, pairX);" in minimum
    assert "PathGenerator path(bot);" in minimum
    assert "for (G3D::Vector3 const& point : path.GetPath())" in minimum
    assert "std::min(startDistance, minimumDistance) - 0.25f" in minimum
    assert "< safeDistance" in minimum
    assert '"minimum_distance_exit_started"' in minimum
    assert route_runtime.index("if (tryValidationRouteMovementCheck(target))") < route_runtime.index(
        "if (tryValidationRouteMinimumDistance())"
    )

    assert 'tankThreat >= highestPartyThreat * 1.3f' in route_runtime
    assert 'tankThreat >= 2000.0f && tankThreat >= highestPartyThreat * 2.5f' in route_runtime
    assert 'bot->GetMap()->IsRaid()' in route_runtime
    assert 'Cohort().Config.ValidationRouteKind != "boss"' in route_runtime

    generator = (ROOT / "tools/bot_ml/build_validation_scenario_manifests.py").read_text()
    assert '"minimum_distance_source_entry": int(step.get("minimum_distance_source_entry") or 0)' in generator
    assert '"minimum_distance_yards": float(step.get("minimum_distance_yards") or 0.0)' in generator


def test_overlapping_drakonid_minimum_distance_uses_union_safe_perpendicular_exit():
    # The two frozen Drudges are about 9.11 yards apart. A player between them
    # cannot safely use the nearest-source ray because it points toward the
    # second source. The pair-derived perpendicular keeps distance from both
    # nondecreasing and finishes outside both 15-yard native damage radii plus
    # the declared two-yard endpoint margin.
    sources = ((0.0, 0.0), (9.11, 0.0))
    start = (4.0, 0.0)
    safe_distance = 17.0
    direction = (0.0, 1.0)
    required = max(
        math.sqrt(safe_distance**2 - math.dist(start, source) ** 2)
        for source in sources
    ) + 0.5
    endpoint = (
        start[0] + direction[0] * required,
        start[1] + direction[1] * required,
    )

    for source in sources:
        assert math.dist(endpoint, source) >= safe_distance
        prior = math.dist(start, source)
        for step in range(1, 21):
            point = (
                start[0] + (endpoint[0] - start[0]) * step / 20.0,
                start[1] + (endpoint[1] - start[1]) * step / 20.0,
            )
            distance = math.dist(point, source)
            assert distance >= prior
            prior = distance


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


def test_phase1_magmaw_uses_typed_native_full_wipe_recovery_policy():
    config = json.loads((ROOT / "experiments/configs/validation_scenarios_cata_001.json").read_text())
    bwd = next(row for row in config["scenarios"] if row["id"] == "blackwing_descent_10n")
    magmaw = next(row for row in bwd["route"] if row["label"] == "Magmaw")
    assert magmaw["boss_recovery_policy"] == "native_full_wipe_only"

    generator = (ROOT / "tools/bot_ml/build_validation_scenario_manifests.py").read_text()
    assert '"boss_recovery_policy": str(step.get("boss_recovery_policy") or "")' in generator
    assert "ValidationRouteBossRecoveryPolicy" in HEADER
    assert "NativeFullWipeOnly" in HEADER
    assert "ValidationRouteBossRecovery = node.BossRecoveryPolicy" in IMPL


def test_phase1_partial_critical_death_holds_native_fight_without_tactical_retreat():
    objective = IMPL[
        IMPL.index("bool BotWorldPopulationMgr::TryValidationRouteObjective"):
        IMPL.index("bool BotWorldPopulationMgr::IsBossContext")
    ]
    retreat = objective.index("bool majorityDead = aliveMembers <= 2 && deadMembers >= 3;")
    hold = objective.index('"native_full_wipe_hold_partial_death"', retreat)
    retreat_action = objective.index('if (!retreatThreat)', hold)
    assert hold < retreat_action
    assert 'action = "native_full_wipe_hold";' in objective[hold:retreat_action]
    assert 'state.LastRecoveryMode = "native_full_wipe_only";' in objective[hold:retreat_action]
    assert 'cohortState.ValidationRouteAnchorOverrideReason = "validation_route_partial_wipe_retreat_rendezvous"' not in objective[hold:retreat_action]


def test_phase1_dead_member_gate_requires_latched_exact_native_full_wipe():
    update = IMPL[
        IMPL.index("void BotWorldPopulationMgr::UpdateBot"):
        IMPL.index("bool BotWorldPopulationMgr::TryValidationRouteObjective")
    ]
    gate = update.index("ValidationRouteBossRecoveryPolicy::NativeFullWipeOnly")
    native_release = update.index("&& TryNativeSelfResurrection(state, bot)", gate)
    assert gate < native_release
    gate_block = update[gate:native_release]
    for token in (
        'raid.WipeState == "wiped"',
        "raid.WipeGeneration > 0",
        "raid.AttemptId == Cohort().AttemptId",
        "raid.NativeSignalsByGuid.size() == raid.RosterByGuid.size()",
        "row.second.WipeGeneration == raid.WipeGeneration",
        "row.second.DeathSequence > 0",
        "Party().Bots.size() == Cohort().Config.TargetPopulation",
        "aliveMembers",
        '"native_full_wipe_wait_partial_death"',
        '"native_full_wipe_wait_unlatched"',
        '"native_full_wipe_latched_release_allowed"',
        '"wipe_latched\\":true',
        '"direct_respawn\\":false',
        '"direct_state_manufacture\\":false',
    ):
        assert token in gate_block
    assert "TryNativeSelfResurrection(state, bot)" in update[native_release:]


def test_native_full_wipe_policy_disables_native_resurrection_shortcuts_for_smoke_only():
    update = IMPL[
        IMPL.index("void BotWorldPopulationMgr::UpdateBot"):
        IMPL.index("bool BotWorldPopulationMgr::TryValidationRouteObjective")
    ]
    self_res = update.index("&& TryNativeSelfResurrection(state, bot)")
    assert (
        "Cohort().Config.ValidationRouteBossRecovery != "
        "ValidationRouteBossRecoveryPolicy::NativeFullWipeOnly"
    ) in update[self_res - 220:self_res]

    objective = IMPL[
        IMPL.index("bool BotWorldPopulationMgr::TryValidationRouteObjective"):
        IMPL.index("bool BotWorldPopulationMgr::IsBossContext")
    ]
    party_res = objective.index("TryNativePartyResurrection(state, bot")
    assert "ValidationRouteBossRecoveryPolicy::NativeFullWipeOnly" in objective[party_res - 300:party_res]

    mechanics = IMPL[
        IMPL.index("BotWorldPopulationMgr::BossMechanicActionResult BotWorldPopulationMgr::TryBossMechanics"):
        IMPL.index("BotWorldPopulationMgr::RaidRoleAssignment BotWorldPopulationMgr::BuildRaidRoleAssignment")
    ]
    battle_res = mechanics.index("TryNativePartyResurrection(state, bot")
    assert "ValidationRouteBossRecoveryPolicy::NativeFullWipeOnly" in mechanics[battle_res - 500:battle_res]


def test_native_full_wipe_latch_survives_first_ghost_leaving_instance():
    def release_allowed(*, wipe_state, wipe_generation, attempt_id, cohort_attempt_id,
                        roster_guids, signal_rows):
        exact_signal_roster = (
            len(roster_guids) == 10
            and set(signal_rows) == set(roster_guids)
        )
        return (
            attempt_id == cohort_attempt_id
            and wipe_state == "wiped"
            and wipe_generation > 0
            and exact_signal_roster
            and all(
                row["wipe_generation"] == wipe_generation and row["death_sequence"] > 0
                for row in signal_rows.values()
            )
        )

    roster = tuple(range(1271, 1281))
    signals = {
        guid: {"wipe_generation": 7, "death_sequence": index + 1, "in_world": True}
        for index, guid in enumerate(roster)
    }
    assert release_allowed(
        wipe_state="wiped", wipe_generation=7, attempt_id=11, cohort_attempt_id=11,
        roster_guids=roster, signal_rows=signals,
    )

    # The runtime latch is immutable recovery authority. The first released
    # ghost may leave BWD before the remaining dead members make a decision;
    # that observation must not revoke the already-proven all-dead wipe.
    signals[1271]["in_world"] = False
    assert release_allowed(
        wipe_state="wiped", wipe_generation=7, attempt_id=11, cohort_attempt_id=11,
        roster_guids=roster, signal_rows=signals,
    )

    assert not release_allowed(
        wipe_state="partial_deaths", wipe_generation=7, attempt_id=11, cohort_attempt_id=11,
        roster_guids=roster, signal_rows=signals,
    )
    assert not release_allowed(
        wipe_state="wiped", wipe_generation=7, attempt_id=10, cohort_attempt_id=11,
        roster_guids=roster, signal_rows=signals,
    )
    missing = dict(signals)
    missing.pop(1280)
    assert not release_allowed(
        wipe_state="wiped", wipe_generation=7, attempt_id=11, cohort_attempt_id=11,
        roster_guids=roster, signal_rows=missing,
    )


def test_validation_raid_boss_recovery_fails_closed_before_direct_spawn_manufacture():
    objective = IMPL[
        IMPL.index("bool BotWorldPopulationMgr::TryValidationRouteObjective"):
        IMPL.index("bool BotWorldPopulationMgr::IsBossContext")
    ]
    lambda_start = objective.index("auto tryCanonicalValidationRouteBossRecovery")
    lambda_end = objective.index("auto isNaturalValidationRoutePackMember", lambda_start)
    recovery = objective[lambda_start:lambda_end]
    raid_guard = recovery.index("bot->GetMap()->IsRaid()")
    direct_respawn = recovery.index("loaded->Respawn(true)")
    direct_scheduled_respawn = recovery.index("routeMap->Respawn")
    direct_load = recovery.index("recovered->LoadFromDB")
    assert raid_guard < direct_respawn < direct_scheduled_respawn < direct_load
    raid_block = recovery[raid_guard:direct_respawn]
    assert 'recoveryResult = "native_boss_recovery_pending"' in raid_block
    assert '"assistance\\":\\"none\\"' in raid_block
    assert '"direct_respawn\\":false' in raid_block
    assert '"direct_state_manufacture\\":false' in raid_block
    assert "SetBossState" not in raid_block


def test_nonraid_canonical_recovery_remains_explicitly_scoped():
    objective = IMPL[
        IMPL.index("bool BotWorldPopulationMgr::TryValidationRouteObjective"):
        IMPL.index("bool BotWorldPopulationMgr::IsBossContext")
    ]
    lambda_start = objective.index("auto tryCanonicalValidationRouteBossRecovery")
    lambda_end = objective.index("auto isNaturalValidationRoutePackMember", lambda_start)
    recovery = objective[lambda_start:lambda_end]
    raid_guard = recovery.index("bot->GetMap()->IsRaid()")
    legacy = recovery.index("This legacy canonical-spawn recovery is intentionally scoped to")
    assert raid_guard < legacy
    assert "non-raid validation routes only" in recovery[legacy:]
