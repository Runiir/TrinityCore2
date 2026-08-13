import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEADER = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h").read_text(encoding="utf-8")
IMPL = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text(encoding="utf-8")
ACTION_EXECUTOR = (ROOT / "src/server/game/Bots/BotActionExecutor.cpp").read_text(encoding="utf-8")
RAID_AUTHORITY = (ROOT / "src/server/game/Bots/BotRaidAreaAuthority.h").read_text(encoding="utf-8")
PET_AI = (ROOT / "src/server/game/AI/CoreAI/PetAI.cpp").read_text(encoding="utf-8")
UNIT_AI = (ROOT / "src/server/game/AI/CoreAI/UnitAI.cpp").read_text(encoding="utf-8")
TOTEM_AI = (ROOT / "src/server/game/AI/CoreAI/TotemAI.cpp").read_text(encoding="utf-8")
TOTEM = (ROOT / "src/server/game/Entities/Totem/Totem.cpp").read_text(encoding="utf-8")
MAGMAW_IMPL = (
    ROOT / "src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent/boss_magmaw.cpp"
).read_text(encoding="utf-8")
GENERIC_SMOKE = json.loads((ROOT / "experiments/configs/cata_raid_phase1_generic_mechanic_smoke_v1.json").read_text())


def _completed_admission_runtime_tick(*, prior_runtime, expected_size,
                                      live_roster, boss_states=(), identity_ok=True):
    """Small model of the completed-admission refresh boundary.

    The C++ path performs the native observation; this model keeps the tests
    focused on the admission/refresh contract without requiring a worldserver.
    """
    if not identity_ok:
        return {"identity_drift": True, "runtime": prior_runtime}
    if len(live_roster) != expected_size:
        return {"identity_drift": False, "runtime": prior_runtime}

    runtime = dict(prior_runtime)
    runtime["alive_size"] = sum(1 for member in live_roster if member["alive"])
    runtime["boss_states"] = tuple(boss_states)
    runtime["encounter_in_progress"] = "IN_PROGRESS" in runtime["boss_states"]
    if runtime["alive_size"] == 0 and runtime.get("wipe_state") != "wiped":
        runtime["wipe_state"] = "wiped"
        runtime["wipe_generation"] = runtime.get("wipe_generation", 0) + 1
        runtime["evidence_sequence"] = runtime.get("evidence_sequence", 0) + expected_size
    return {"identity_drift": False, "runtime": runtime}


def _raid_recovery_runtime_tick(*, prior_runtime, expected_size, alive_size,
                                encounter_in_progress=False,
                                native_recovery_evidence_complete=False):
    """Model the wipe-scoped recovery state transition in the C++ refresh."""
    runtime = dict(prior_runtime)
    previous_wipe_state = runtime.get("wipe_state", "ready")
    previous_recovery_state = runtime.get("recovery_state", "none")
    runtime["alive_size"] = alive_size
    runtime["encounter_in_progress"] = encounter_in_progress
    runtime["native_recovery_evidence_complete"] = native_recovery_evidence_complete

    all_dead = alive_size == 0
    all_alive = alive_size == expected_size
    if all_dead:
        if previous_wipe_state != "wiped":
            runtime["wipe_generation"] = runtime.get("wipe_generation", 0) + 1
        runtime["wipe_state"] = "wiped"
        runtime["recovery_state"] = (
            "awaiting_native_reset" if encounter_in_progress
            else "release_resurrection_pending"
        )
    elif not all_alive:
        native_wipe_recovery = previous_wipe_state == "wiped" and runtime.get("wipe_generation", 0) > 0
        runtime["wipe_state"] = "wiped" if previous_wipe_state == "wiped" else "partial_deaths"
        runtime["recovery_state"] = "native_resurrection_runback" if native_wipe_recovery else "none"
    elif encounter_in_progress:
        runtime["wipe_state"] = "engaged"
        runtime["recovery_state"] = "none"
    elif (
        (previous_wipe_state == "wiped" and runtime.get("wipe_generation", 0) > 0)
        or (
            runtime.get("wipe_generation", 0) > 0
            and previous_recovery_state in {
                "awaiting_native_reset",
                "release_resurrection_pending",
                "native_resurrection_runback",
            }
        )
    ):
        if native_recovery_evidence_complete:
            runtime["wipe_state"] = "ready"
            runtime["recovery_state"] = "recovered_ready_check"
        else:
            runtime["wipe_state"] = "wiped"
            runtime["recovery_state"] = "recovery_evidence_pending"
    elif runtime.get("wipe_generation", 0) > 0 and previous_recovery_state == "recovered_ready_check":
        if native_recovery_evidence_complete:
            runtime["wipe_state"] = "ready"
            runtime["recovery_state"] = "recovered_ready_check"
        else:
            runtime["wipe_state"] = "wiped"
            runtime["recovery_state"] = "recovery_evidence_pending"
    else:
        runtime["wipe_state"] = "ready"
        runtime["recovery_state"] = "none"
    return runtime


def _native_group_identity_gate(*, expected_guids, group_members, frozen_subgroups):
    """Model the fail-closed native group membership/subgroup gate."""
    expected = set(expected_guids)
    if len(group_members) != len(expected):
        return False
    for member in group_members:
        guid = member["guid"]
        if guid not in expected:
            return False
        if member["subgroup"] != frozen_subgroups[guid]:
            return False
    return True


def _native_recovery_signal_edges(samples):
    """Model the observable native recovery edges across refresh samples."""
    signal = {
        "death": 0,
        "corpse": 0,
        "release": 0,
        "runback": 0,
        "reentry": 0,
        "resurrection": 0,
    }
    previous = None
    evidence_sequence = 0
    for current in samples:
        if not current["alive"] and not signal["death"]:
            evidence_sequence += 1
            signal["death"] = evidence_sequence
        if signal["death"] and current["corpse"] and not signal["corpse"]:
            evidence_sequence += 1
            signal["corpse"] = evidence_sequence
        if signal["corpse"] and current["released"] and not signal["release"]:
            evidence_sequence += 1
            signal["release"] = evidence_sequence
        released_outside = (
            previous
            and previous["released"]
            and current["released"]
            and previous["outside"]
            and current["outside"]
            and current["native_runback_armed"]
            and current["landing_identity_bound"]
            and current["path_progressed"]
        )
        if signal["release"] and released_outside and not signal["runback"]:
            evidence_sequence += 1
            signal["runback"] = evidence_sequence
        if (
            signal["runback"]
            and previous
            and previous["released"]
            and previous["outside"]
            and not current["outside"]
            and not signal["reentry"]
        ):
            evidence_sequence += 1
            signal["reentry"] = evidence_sequence
        if (
            signal["reentry"]
            and previous
            and not previous["alive"]
            and current["alive"]
            and not signal["resurrection"]
        ):
            evidence_sequence += 1
            signal["resurrection"] = evidence_sequence
        previous = current
    return signal


def test_native_recovery_refresh_keeps_worldport_intermediate_edges_observable():
    samples = [
        {"alive": False, "corpse": True, "released": False, "outside": False,
         "native_release_requested": False, "native_runback_armed": False,
         "landing_identity_bound": False, "path_progressed": False},
        {"alive": False, "corpse": True, "released": True, "outside": False,
         "native_release_requested": True, "native_runback_armed": False,
         "landing_identity_bound": False, "path_progressed": False},
        {"alive": False, "corpse": True, "released": True, "outside": True,
         "native_release_requested": True, "native_runback_armed": False,
         "landing_identity_bound": True, "path_progressed": False},
        {"alive": False, "corpse": True, "released": True, "outside": True,
         "native_release_requested": True, "native_runback_armed": True,
         "landing_identity_bound": True, "path_progressed": True},
        {"alive": True, "corpse": False, "released": False, "outside": False,
         "native_release_requested": True, "native_runback_armed": True,
         "landing_identity_bound": True, "path_progressed": False},
    ]

    signal = _native_recovery_signal_edges(samples)
    assert signal["death"] < signal["corpse"] < signal["release"] < signal["runback"]
    assert signal["runback"] < signal["reentry"] < signal["resurrection"]

    admitted_group = IMPL[
        IMPL.index("void BotWorldPopulationMgr::EnsureValidationCohortGroup"):
        IMPL.index("bool BotWorldPopulationMgr::ResolveSpawnPlacement")
    ]
    member_sample = admitted_group[:admitted_group.index("if (members.empty())")]
    assert "Cohort().ValidationRaidAdmissionComplete" in member_sample
    assert "IsNativeReleasedGhostWorldport(state, bot)" in member_sample
    assert "IsNativeBlackwingDescentRunbackWorldport(state, bot)" in member_sample
    assert "Include only the two independently-authorized native worldports" in member_sample

    runtime_refresh = admitted_group[
        admitted_group.index("currentSignal.Initialized"):
        admitted_group.index("auto signalComplete")
    ]
    assert "HasNativeRaidCorpseAuthority(*botState, bot)" in runtime_refresh
    assert "releaseLandingIdentityBound" in runtime_refresh
    assert "NativeReleaseLandingWipeGeneration == raid.WipeGeneration" in runtime_refresh
    assert "NativeRunbackAreaTriggerId == BlackwingDescentEntranceTriggerId" in runtime_refresh
    assert "nativeReleaseMovedOutside" not in runtime_refresh
    assert "botState->NativeReleaseRequested" in runtime_refresh
    assert "bot->GetCorpse() != nullptr" not in runtime_refresh


def test_native_recovery_rejects_release_worldport_or_stale_outside_state_as_runback():
    release_landing_only = [
        {"alive": False, "corpse": True, "released": False, "outside": False,
         "native_release_requested": False, "native_runback_armed": False,
         "landing_identity_bound": False, "path_progressed": False},
        {"alive": False, "corpse": True, "released": True, "outside": False,
         "native_release_requested": True, "native_runback_armed": False,
         "landing_identity_bound": False, "path_progressed": False},
        {"alive": False, "corpse": True, "released": True, "outside": True,
         "native_release_requested": True, "native_runback_armed": False,
         "landing_identity_bound": True, "path_progressed": False},
    ]
    stale_outside = [
        {"alive": False, "corpse": True, "released": False, "outside": False,
         "native_release_requested": False, "native_runback_armed": False,
         "landing_identity_bound": False, "path_progressed": False},
        {"alive": False, "corpse": True, "released": True, "outside": True,
         "native_release_requested": True, "native_runback_armed": True,
         "landing_identity_bound": False, "path_progressed": True},
    ]

    assert _native_recovery_signal_edges(release_landing_only)["runback"] == 0
    assert _native_recovery_signal_edges(stale_outside)["runback"] == 0

    runtime_refresh = IMPL[
        IMPL.index("if (!signal.ReleaseSequence"):
        IMPL.index("bool const exactSignalRoster")
    ]
    assert "prior->OutsideOriginalInstance" in runtime_refresh
    assert "progressedFromReleaseLanding" in runtime_refresh
    assert "NativeReleaseLandingObserved" in runtime_refresh
    assert "NativeReleaseLandingMapId" in runtime_refresh
    assert "NativeReleaseLandingInstanceId" in runtime_refresh
    assert "NativeReleaseLandingWipeGeneration" in runtime_refresh


def _runback_from_landing_samples(samples, *, wipe_generation=7,
                                  landing_map=0, landing_instance=0):
    """Model cumulative movement from the exact release landing."""
    for sample in samples:
        identity = (
            sample["wipe_generation"] == wipe_generation
            and sample["map_id"] == landing_map
            and sample["instance_id"] == landing_instance
            and sample["alive"] is False
            and sample["corpse"] is True
            and sample["ghost"] is True
            and sample["runback_trigger"] == 6581
        )
        if identity and math.hypot(sample["x"] - 10.0, sample["y"] - 20.0) > 2.0:
            return True
    return False


def test_native_recovery_runback_uses_cumulative_landing_displacement_and_exact_identity():
    small_steps = [
        {"wipe_generation": 7, "map_id": 0, "instance_id": 0, "alive": False,
         "corpse": True, "ghost": True, "runback_trigger": 6581, "x": x, "y": 20.0}
        for x in (10.5, 11.0, 11.5, 12.1)
    ]
    no_movement = [dict(sample, x=10.0, y=20.0) for sample in small_steps]
    wrong_wipe = [dict(sample, wipe_generation=8) for sample in small_steps]
    wrong_map = [dict(sample, map_id=1) for sample in small_steps]
    no_corpse = [dict(sample, corpse=False) for sample in small_steps]

    assert _runback_from_landing_samples(small_steps)
    assert not _runback_from_landing_samples(no_movement)
    assert not _runback_from_landing_samples(wrong_wipe)
    assert not _runback_from_landing_samples(wrong_map)
    assert not _runback_from_landing_samples(no_corpse)

    runtime_refresh = IMPL[
        IMPL.index("bool const releaseLandingIdentityBound"):
        IMPL.index("if (!signal.RunbackSequence")
    ]
    assert "signal.HasCorpse" in runtime_refresh
    assert "NativeReleaseLandingWipeGeneration == raid.WipeGeneration" in runtime_refresh
    assert "NativeReleaseLandingMapId" in runtime_refresh
    assert "NativeReleaseLandingInstanceId" in runtime_refresh
    assert "NativeReleaseLandingX" in runtime_refresh
    assert "NativeReleaseLandingY" in runtime_refresh
    assert "NativeReleaseLandingZ" in runtime_refresh
    assert "progressedFromReleaseLanding" in runtime_refresh
    assert "prior->OutsideOriginalInstance" in runtime_refresh


def _native_recovery_objective_gate(*, policy, active, attempt_matches,
                                    exact_roster, wipe_generation,
                                    state, evidence_complete):
    pending_state = state in {
        "wiped",
        "recovery_evidence_pending",
        "native_resurrection_runback",
        "awaiting_native_reset",
        "release_resurrection_pending",
    }
    return (
        policy == "native_full_wipe_only"
        and active
        and attempt_matches
        and exact_roster
        and wipe_generation > 0
        and pending_state
        and not evidence_complete
    )


def test_native_recovery_evidence_gate_holds_offense_navigation_and_reengagement():
    assert _native_recovery_objective_gate(
        policy="native_full_wipe_only", active=True, attempt_matches=True,
        exact_roster=True, wipe_generation=2, state="wiped",
        evidence_complete=False,
    )
    assert _native_recovery_objective_gate(
        policy="native_full_wipe_only", active=True, attempt_matches=True,
        exact_roster=True, wipe_generation=2, state="recovery_evidence_pending",
        evidence_complete=False,
    )
    assert not _native_recovery_objective_gate(
        policy="native_full_wipe_only", active=True, attempt_matches=True,
        exact_roster=True, wipe_generation=2, state="ready",
        evidence_complete=False,
    )
    assert not _native_recovery_objective_gate(
        policy="native_full_wipe_only", active=True, attempt_matches=True,
        exact_roster=True, wipe_generation=2, state="wiped",
        evidence_complete=True,
    )
    assert not _native_recovery_objective_gate(
        policy="native_full_wipe_only", active=True, attempt_matches=True,
        exact_roster=False, wipe_generation=2, state="wiped",
        evidence_complete=False,
    )

    objective = IMPL[
        IMPL.index("bool BotWorldPopulationMgr::TryValidationRouteObjective"):
        IMPL.index("bool BotWorldPopulationMgr::IsBossContext")
    ]
    gate = objective.index("if (IsNativeRaidRecoveryEvidencePending())")
    clear = objective.index(
        "BotRaidAreaAuthority::SetAllOffenseSuppressed(raidAuthorityOwner, false)"
    )
    assert gate < clear
    for token in (
        "SuppressNativeRaidRecovery(state, bot);",
        'action = "hold_native_recovery_evidence";',
        "return true;",
    ):
        assert token in objective[gate:clear]

    pending = IMPL[
        IMPL.index("bool BotWorldPopulationMgr::IsNativeRaidRecoveryEvidencePending"):
        IMPL.index("void BotWorldPopulationMgr::SuppressNativeRaidRecovery")
    ]
    for token in (
        "raid.NativeSignalsByGuid.size() != raid.RosterByGuid.size()",
        "signal->second.WipeGeneration == raid.WipeGeneration",
        "signal->second.DeathSequence > 0",
        "raid.NativeRecoveryEvidenceComplete",
        "raid.NativeRecoveryHoldActive",
    ):
        assert token in pending


def test_native_recovery_hold_precedes_readycheck_and_uses_no_forced_combat_stop():
    update = IMPL[
        IMPL.index("void BotWorldPopulationMgr::UpdateBot"):
    ]
    hold = update.index("if (bot->IsAlive() && IsNativeRaidRecoveryEvidencePending())")
    ready_check = update.index("TryRespondNativeRaidReadyCheck(state, bot);", hold)
    timer = update.index("if (state.DecisionTimer > diff)")
    assert hold < ready_check < timer
    assert "state.DecisionTimer = 0;" in update[hold:timer]

    suppress = IMPL[
        IMPL.index("void BotWorldPopulationMgr::SuppressNativeRaidRecovery"):
        IMPL.index("bool BotWorldPopulationMgr::TryValidationRouteObjective")
    ]
    for token in (
        "SetAllOffenseSuppressed(ownerGuid, true)",
        "controlledUnitActive",
        "native encounter reset must clear any old",
    ):
        assert token in suppress
    assert "CombatStop(" not in suppress
    assert "InterruptSpell(" not in suppress
    assert "AttackStop(" not in suppress
    assert "MoveIdle(" not in suppress
    assert "AreNativeRaidRecoveryControlledUnitsReady(bot)" in IMPL
    assert "TryRestoreNativeRaidRecoveryPet(state, bot)" in update[hold:ready_check]


def _frontal_hazard_inside(*, distance, relative_radians, radius=12.0):
    return distance <= radius and abs(relative_radians) <= math.pi / 2


def test_frontal_hazard_requires_configured_radius_and_arc_together():
    assert _frontal_hazard_inside(distance=6.0, relative_radians=0.0)
    assert not _frontal_hazard_inside(distance=6.0, relative_radians=math.pi * 0.75)
    # Forward-facing but beyond the configured radius is safe.
    assert not _frontal_hazard_inside(distance=13.0, relative_radians=0.0)

    impl = IMPL[
        IMPL.index("auto positionOutsideHazard"):
        IMPL.index("auto pathOutsideActiveHazards")
    ]
    assert "inside = inside && std::fabs(relative) <= float(M_PI_2);" in impl

    overlap_guard = IMPL[
        IMPL.index("bool outsideHazard = bot->GetExactDist2d(previousHazard)"):
        IMPL.index("// Persistent ground objects", IMPL.index("bool outsideHazard = bot->GetExactDist2d(previousHazard)"))
    ]
    assert "bool insideActiveHazard" in overlap_guard
    assert "insideActiveHazard = insideActiveHazard" in overlap_guard
    assert "bool outsideActiveHazard = !insideActiveHazard;" in overlap_guard


def test_bwd_magmaw_only_corridor_precedes_omnotron_and_uses_bounded_native_legs():
    config = json.loads(
        (ROOT / "experiments/configs/validation_scenarios_cata_001.json").read_text()
    )
    bwd = next(row for row in config["scenarios"] if row["id"] == "blackwing_descent_10n")
    junction, chainwielder, drudges, magmaw = bwd["route"][:4]

    assert (junction["label"], chainwielder["label"], drudges["label"], magmaw["label"]) == (
        "BWD entrance junction regroup",
        "Magmaw Chainwielder trash",
        "Magmaw Drudge pair",
        "Magmaw",
    )
    assert junction["kind"] == "regroup"
    assert junction["step"] == 1
    assert {axis: junction[axis] for axis in ("x", "y", "z", "o")} == {
        axis: bwd["start_position"][axis] for axis in ("x", "y", "z", "o")
    }
    assert junction["source_guid"] == "blackwing_descent_10n.start_position"
    assert junction["source_table"] == "validation_scenario.start_position"

    path_limit_yards = 74 * 4.0
    first_leg = math.dist(
        (junction["x"], junction["y"], junction["z"]),
        (chainwielder["x"], chainwielder["y"], chainwielder["z"]),
    )
    second_leg = math.dist(
        (chainwielder["x"], chainwielder["y"], chainwielder["z"]),
        (drudges["x"], drudges["y"], drudges["z"]),
    )
    third_leg = math.dist(
        (drudges["x"], drudges["y"], drudges["z"]),
        (
            magmaw["navigation_anchor"]["x"],
            magmaw["navigation_anchor"]["y"],
            magmaw["navigation_anchor"]["z"],
        ),
    )

    assert first_leg < path_limit_yards
    assert second_leg < path_limit_yards
    assert third_leg < path_limit_yards
    magmaw_index = next(i for i, row in enumerate(bwd["route"]) if row["label"] == "Magmaw")
    omnotron_trash_index = next(i for i, row in enumerate(bwd["route"]) if row["label"] == "Omnotron Golem Sentries")
    assert magmaw_index < omnotron_trash_index


def test_bwd_magmaw_trash_splits_chainwielder_hazard_from_drudge_charge_contract():
    config = json.loads(
        (ROOT / "experiments/configs/validation_scenarios_cata_001.json").read_text()
    )
    bwd = next(row for row in config["scenarios"] if row["id"] == "blackwing_descent_10n")
    chainwielder = next(row for row in bwd["route"] if row["label"] == "Magmaw Chainwielder trash")
    drudges = next(row for row in bwd["route"] if row["label"] == "Magmaw Drudge pair")

    assert (chainwielder["step"], chainwielder["source_entry"], chainwielder["source_guid"]) == (2, 42649, "250050")
    assert chainwielder["pack_target_entries"] == [42649]
    assert (chainwielder["hazard_source_entry"], chainwielder["hazard_damage_spell_id"]) == (42690, 79580)
    assert (chainwielder["hazard_shape"], chainwielder["hazard_radius_yards"]) == ("radial", 20.0)

    assert (drudges["step"], drudges["source_entry"], drudges["source_guid"]) == (3, 42362, "250140")
    assert drudges["pack_target_entries"] == [42362]
    assert drudges["split_source_guids"] == [250140, 250141]
    assert drudges["split_lane_a_roster_slots"] == [1, 3, 4, 6, 7]
    assert drudges["split_lane_b_roster_slots"] == [2, 5, 8, 9, 10]
    assert drudges["split_lane_tank_slots"] == [1, 2]
    assert drudges["split_minimum_separation_yards"] == 15.0
    assert (drudges["minimum_distance_source_entry"], drudges["minimum_distance_yards"]) == (42362, 15.0)
    assert (drudges["thunderclap_spell_id"], drudges["charge_spell_id"], drudges["charge_range_yards"]) == (79604, 79630, 80.0)
    assert drudges["charge_native_interval_ms"] == 20000
    assert drudges["vengeful_rage_spell_id"] == 80035
    assert bwd["mechanic_profiles"]["trash_ground_danger_movement"] == [
        "ground_danger", "movement_check", "minimum_distance"
    ]


def test_bwd_omnotron_golem_sentry_uses_authoritative_laser_strike_geometry_after_magmaw():
    config = json.loads(
        (ROOT / "experiments/configs/validation_scenarios_cata_001.json").read_text()
    )
    bwd = next(row for row in config["scenarios"] if row["id"] == "blackwing_descent_10n")
    entry = next(row for row in bwd["route"] if row["label"] == "Omnotron Golem Sentries")

    assert entry["step"] == 5
    assert entry["source_entry"] == 42800
    assert entry["pack_target_entries"] == [42800]
    assert entry["mechanic_profile"] == "trash_ground_danger_movement"
    assert (
        entry["hazard_source_entry"],
        entry["hazard_detection_spell_id"],
        entry["hazard_damage_spell_id"],
        entry["hazard_shape"],
        entry["hazard_radius_yards"],
        entry["hazard_safety_margin_yards"],
    ) == (43362, 81066, 81067, "radial", 12.0, 0.0)


def test_bwd_drudge_pair_executes_exact_roster_lanes_and_native_charge_reseparation():
    route_start = IMPL.index("bool BotWorldPopulationMgr::TryValidationRouteObjective")
    route_end = IMPL.index("bool BotWorldPopulationMgr::IsBossContext", route_start)
    route_runtime = IMPL[route_start:route_end]
    lane_start = route_runtime.index("auto tryValidationRouteDrudgeChargeLanes")
    lane_end = route_runtime.index("auto tryValidationRouteAdds", lane_start)
    lane = route_runtime[lane_start:lane_end]

    assert '"trash_two_tank_charge_lanes"' in lane
    assert "laneSlots == exactRosterSlots" in lane
    assert '"raid_tank_1", "raid_tank_2", "raid_healer_1", "raid_healer_2"' in lane
    assert "GetCreatureBySpawnId(spawnId)" in lane
    assert "source->GetEntry() != Cohort().Config.ValidationRouteMinimumDistanceSourceEntry" in lane
    assert "GetHomePosition()" in lane
    assert "ValidationRouteSplitMinimumSeparationYards" in lane
    assert "ValidationRouteSplitNavigationMarginYards" in lane
    assert "ValidationRouteSplitArrivalToleranceYards" in lane
    assert "ValidationRouteDrudgeChargeGeneration" in lane
    assert "nativeChargePending" in lane
    assert "chargeObservation->Landed" in lane
    assert "chargeObservation->AttemptId != Cohort().AttemptId" in lane
    assert "chargeObservation->WipeGeneration != Cohort().Raid.WipeGeneration" in lane
    assert "ValidationRouteDrudgeChargeObservations" in lane
    assert '"drudge_native_charge_lane_reseparate"' in lane
    assert "UnitHealthPct(laneSource) < UnitHealthPct(otherSource)" in lane
    assert '"drudge_kill_sync_hold_lower_health_lane"' in lane
    assert "ValidationRouteVengefulRageSpellId" in lane
    assert "BotCombatActionCategory::Taunt" in lane
    assert "if (formationRequiredMutable || pairTooClose || nativeChargePending || chargeAwaitingLanding)" in lane
    assert "laneSource = sources[laneIndex]" in lane
    assert "bool const sourceInLaneA = nativeChargeSource == sources[0]" in lane
    assert "markAllRosterReseparated" in lane
    assert "ReseparationRecorded" in lane
    assert "uniqueGroupAnchor" in lane
    assert "sameLaneMemberMinimum" in lane
    assert "sources[0]->GetExactDist2d(sources[1])" in lane
    assert "drudge_tank_health_sync_hold" in lane
    assert "ValidationRouteDrudgeOwnershipRosterGuids" in lane
    assert "sourceOnFrozenLane" in lane
    assert "laneTank->GetExactDist2d(laneSource)" in lane
    assert "drudge_lane_native_ownership" in lane
    assert "chargeAwaitingLanding" in lane
    assert "!chargeObservation->Landed" in lane
    health_sync_call = lane.rindex("recordHealthSyncHold();")
    assert lane.index("if (!laneOwnershipSafe)") < health_sync_call
    assert lane.index("if (sources[0]->IsAlive() && sources[1]->IsAlive() && !exactRosterReSeparated())") < health_sync_call
    assert '"drudge_lane_wait_lane_ownership"' in lane
    assert '"drudge_lane_profile_hold_contract_unsafe"' in lane
    assert '"drudge_native_charge_target_tank_reseparated"' in lane
    assert "bool const taunted = TryCastCombatSpell" in lane
    assert lane.index("SetAllOffenseSuppressed(bot->GetGUID().GetRawValue(), false)") < lane.index(
        "bool const taunted = TryCastCombatSpell"
    ) < lane.index("SetAllOffenseSuppressed(bot->GetGUID().GetRawValue(), true)")
    assert "ResolveProfileCombatAction(bot, laneSource" in lane
    assert "true, false);" in lane  # forbid area, disallow multidot
    cast_hook = IMPL[
        IMPL.index("uint64 BotWorldPopulationMgr::NotifyNativeCreatureSpellStarted"):
        IMPL.index("void BotWorldPopulationMgr::NotifyCombatDamage")
    ]
    assert 'ValidationRouteMechanicProfile != "trash_two_tank_charge_lanes"' in cast_hook
    assert "ValidationRouteChargeRangeYards" in cast_hook
    assert "ValidationRouteChargeNativeIntervalMs" in cast_hook
    assert "ValidationRouteDrudgeChargeGeneration" in cast_hook
    assert "ValidationRouteDrudgeChargeObservations.push_back" in cast_hook
    assert "GetUnsortedThreatList" in cast_hook
    assert "nativeThreatList.size()" not in cast_hook
    assert "nativeThreatCandidateCount" in cast_hook
    header = (Path(__file__).parents[1] / "src/server/game/Bots/BotWorldPopulationMgr.h").read_text(
        encoding="utf-8",
    )
    drudge_observation = header[
        header.index("struct ValidationRouteDrudgeChargeObservation") :
        header.index("struct ValidationRouteDrudgeThreatSeedEvidence")
    ]
    generic_evidence = header[
        header.index("struct ValidationRouteEvidence") :
        header.index("struct ValidationRouteDrudgeMemberGeometry")
    ]
    assert "uint64 TargetRawGuid = 0;" in drudge_observation
    assert "TargetRawGuid" not in generic_evidence
    assert "MaxNativeThreatCandidates" in cast_hook
    assert "NativeThreatCandidatesCount" in cast_hook
    assert "NativeThreatCandidatesComplete" in cast_hook
    assert "NativeThreatCandidatesTruncated" in cast_hook
    assert "candidateEvidence.IsPlayer" in cast_hook
    assert "candidateEvidence.Alive" in cast_hook
    assert "candidateEvidence.SameMap" in cast_hook
    assert "ValidationRouteDrudgeChargeQueueOverflow = true" in cast_hook
    assert "void BotWorldPopulationMgr::NotifyNativeCreatureSpellLanded" in cast_hook
    assert "candidate.Sequence == observationSequence" in cast_hook
    assert "candidate.AttemptId == Cohort().AttemptId" in cast_hook
    assert "candidate.WipeGeneration == Cohort().Raid.WipeGeneration" in cast_hook
    spell_impl = (ROOT / "src/server/game/Spells/Spell.cpp").read_text()
    assert "NotifyNativeCreatureSpellStarted" in spell_impl
    assert spell_impl.index("NotifyNativeCreatureSpellStarted") < spell_impl.index(
        "// Creatures focus their target when possible"
    )
    assert "m_nativeCreatureSpellObservationSequence" in spell_impl
    assert "if (!preventDefault)" in spell_impl
    assert "effect == SPELL_EFFECT_CHARGE" in spell_impl
    assert "NotifyNativeCreatureSpellLanded" in spell_impl
    assert "else if (!assignedTank && UnitHealthPct" not in lane
    assert route_runtime.index("if (tryValidationRouteMinimumDistance())") < route_runtime.index(
        "if (tryValidationRouteDrudgeChargeLanes())"
    ) < route_runtime.index("struct TrashThreatControl")


def test_botworld_hot_path_defers_progression_scoring_and_rate_limits_repeated_logs():
    update_start = IMPL.index("void BotWorldPopulationMgr::UpdateBot")
    update_end = IMPL.index("Player* BotWorldPopulationMgr::GetLoadedBot", update_start)
    update = IMPL[update_start:update_end]
    assert update.index("if (state.DecisionTimer > diff)") < update.index(
        "ensureProgressionScored();", update.index("if (state.DecisionTimer > diff)")
    )
    assert update.index("SuppressNativeRaidRecovery(state, bot)") < update.index(
        "if (state.DecisionTimer > diff)"
    )
    assert "LastNotInWorldInfoLogMs" in IMPL
    assert "SuppressedNotInWorldInfoLogs" in IMPL
    assert "LastNativeWorldportDeferredLogMs" in IMPL
    assert "SuppressedNativeWorldportDeferredLogs" in IMPL
    assert "suppressed=%u" in IMPL
    suppress_start = IMPL.index("void BotWorldPopulationMgr::SuppressNativeRaidRecovery")
    suppress_end = IMPL.index("bool BotWorldPopulationMgr::TryValidationRouteObjective", suppress_start)
    suppress = IMPL[suppress_start:suppress_end]
    assert "NativeRecoveryHoldWipeGeneration" in suppress
    assert "periodicVerify" in suppress
    assert "if (!newHold && !periodicVerify && !ownerActive && !controlledUnitActive)" in suppress
    assert "SetReactState(REACT_PASSIVE)" not in suppress


def test_native_recovery_hold_is_latched_at_wipe_and_cleared_only_after_complete_evidence():
    runtime = HEADER[HEADER.index("struct RaidRuntime"):HEADER.index("struct CohortRuntime")]
    assert "bool NativeRecoveryHoldActive" in runtime

    ensure = IMPL[
        IMPL.index("void BotWorldPopulationMgr::EnsureValidationCohortGroup"):
        IMPL.index("bool BotWorldPopulationMgr::ResolveSpawnPlacement")
    ]
    wipe = ensure.index("if (allDead)")
    latch = ensure.index("raid.NativeRecoveryHoldActive =", wipe)
    assert "ValidationRouteBossRecoveryPolicy::NativeFullWipeOnly" in ensure[latch:latch + 220]
    evidence = ensure.index("raid.NativeRecoveryEvidenceComplete =", latch)
    clear = ensure.index("if (raid.NativeRecoveryEvidenceComplete)", evidence)
    assert latch < evidence < clear

    pending = IMPL[
        IMPL.index("bool BotWorldPopulationMgr::IsNativeRaidRecoveryEvidencePending"):
        IMPL.index("void BotWorldPopulationMgr::SuppressNativeRaidRecovery")
    ]
    hold = pending.index("if (raid.NativeRecoveryHoldActive)")
    exact_roster = pending.index("if (raid.ExpectedSize !=", hold)
    assert hold < exact_roster
    assert "return !raid.NativeRecoveryEvidenceComplete;" in pending[hold:exact_roster]

    update = IMPL[
        IMPL.index("void BotWorldPopulationMgr::UpdateBot"):
        IMPL.index("bool BotWorldPopulationMgr::TryValidationRouteObjective")
    ]
    assert update.index("if (bot->IsAlive() && IsNativeRaidRecoveryEvidencePending())") < update.index(
        "TryRespondNativeRaidReadyCheck(state, bot);"
    )

    runtime_json = IMPL[
        IMPL.index("std::string BotWorldPopulationMgr::BuildRaidRuntimeJson"):
        IMPL.index("std::string BotWorldPopulationMgr::BuildRaidPositioningAnchorsJson")
    ]
    assert runtime_json.count("native_recovery_hold_active") >= 2


def test_native_recovery_hold_cannot_leak_from_drudge_trash_into_magmaw():
    apply_node = IMPL[
        IMPL.index("bool BotWorldPopulationMgr::ApplyValidationRouteManifestNode"):
        IMPL.index("void BotWorldPopulationMgr::ResetTraceStreams")
    ]
    policy = apply_node.index("Cohort().Config.ValidationRouteBossRecovery = node.BossRecoveryPolicy;")
    clear = apply_node.index("Cohort().Raid.NativeRecoveryHoldActive = false;", policy)
    reset = apply_node.index("ResetValidationRouteRuntimeState", clear)
    assert policy < clear < reset
    assert (
        "node.BossRecoveryPolicy != ValidationRouteBossRecoveryPolicy::NativeFullWipeOnly"
        in apply_node[policy:clear]
    )


def _laser_exit_path_is_safe(path, hazards, radius=12.0):
    """Model the runtime's contaminated-prefix/union exit contract."""
    start = path[0]
    previous = [math.dist(start, center) for center in hazards]
    started_outside = [distance > radius for distance in previous]
    exited = [False] * len(hazards)
    for point in path:
        distances = [math.dist(point, center) for center in hazards]
        for index, distance in enumerate(distances):
            if started_outside[index]:
                if distance <= radius:
                    return False
                continue
            if not exited[index]:
                if distance + 0.5 < previous[index]:
                    return False
                previous[index] = max(previous[index], distance)
                if distance > radius:
                    exited[index] = True
            elif distance <= radius:
                return False
    return all(math.dist(path[-1], center) > radius for center in hazards)


def test_bwd_laser_exit_requires_monotonic_union_safe_path_for_overlapping_strikes():
    hazards = ((0.0, 0.0), (10.0, 0.0))
    # The endpoint is outside the first 12-yard strike but still inside the
    # second; the second source also gets closer along this path.
    nearest_only_exit = [(5.0, 0.0), (17.0, 0.0)]
    assert not _laser_exit_path_is_safe(nearest_only_exit, hazards)

    union_safe_exit = [(5.0, 0.0), (5.0, 8.0), (5.0, 16.0)]
    assert _laser_exit_path_is_safe(union_safe_exit, hazards)

    movement = IMPL[
        IMPL.index("auto pathOutsideActiveHazards"):
        IMPL.index("auto isScopedGenericCastCandidate")
    ]
    assert "startedOutside" in movement
    assert "exitedHazards" in movement
    assert "distance + 0.5f < previousDistances[index]" in movement
    assert "return endpointOutside;" in movement


def _drudge_cached_anchor_model(*, member_position, cached_anchor,
                                strict_path, cache_scope, current_scope,
                                arrival_tolerance=2.0):
    """Model the runtime's scoped cached-anchor acceptance boundary."""
    if not strict_path or cache_scope != current_scope or cached_anchor is None:
        return False
    return math.dist(member_position, cached_anchor) <= arrival_tolerance


def test_drudge_legacy_candidate_k_cannot_certify_when_selector_cached_j():
    legacy_candidate_k = (0.0, 0.0)
    selected_cached_j = (10.0, 0.0)
    scope = (41, 2, 7)

    # The bot can begin on K, but the selector's strict native path proof is
    # for J.  Runtime must move it to J before accepting formation evidence.
    assert not _drudge_cached_anchor_model(
        member_position=legacy_candidate_k,
        cached_anchor=selected_cached_j,
        strict_path=True,
        cache_scope=scope,
        current_scope=scope,
    )
    assert _drudge_cached_anchor_model(
        member_position=selected_cached_j,
        cached_anchor=selected_cached_j,
        strict_path=True,
        cache_scope=scope,
        current_scope=scope,
    )

    route_start = IMPL.index("bool BotWorldPopulationMgr::TryValidationRouteObjective")
    route_end = IMPL.index("bool BotWorldPopulationMgr::IsBossContext", route_start)
    route_runtime = IMPL[route_start:route_end]
    group_start = route_runtime.index("auto groupPositionSafe")
    group_end = route_runtime.index("auto sourceOnFrozenLane", group_start)
    group = route_runtime[group_start:group_end]
    assert "cachedAnchorSafe(*memberState, member)" in group
    assert "for (auto const& candidate : anchorCandidatesFor(memberSlot))" not in group
    assert "ValidationRouteDrudgeAnchorCandidateIndex >= candidates.size()" in route_runtime


def test_drudge_cached_anchor_is_invalidated_by_attempt_wipe_or_route_scope():
    cached_scope = (41, 2, 7)
    for current_scope in ((42, 2, 7), (41, 3, 7), (41, 2, 8)):
        assert not _drudge_cached_anchor_model(
            member_position=(10.0, 0.0),
            cached_anchor=(10.0, 0.0),
            strict_path=True,
            cache_scope=cached_scope,
            current_scope=current_scope,
        )

    # A cache invalidation also cannot be revived by a stale path bit.
    assert not _drudge_cached_anchor_model(
        member_position=(10.0, 0.0),
        cached_anchor=(10.0, 0.0),
        strict_path=False,
        cache_scope=cached_scope,
        current_scope=cached_scope,
    )


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


def test_completed_validation_raid_exact_identity_refreshes_live_runtime_each_tick():
    population = IMPL[
        IMPL.index("void BotWorldPopulationMgr::EnsurePopulation()"):
        IMPL.index("void BotWorldPopulationMgr::EnsureCalibrationPopulation()")
    ]
    complete = population[
        population.index("if (Cohort().ValidationRaidAdmissionComplete)"):
        population.index("auto terminalFailure")
    ]
    drift_start = complete.index("if (!exactIdentity)")
    refresh = complete.index("EnsureValidationCohortGroup();")
    drift_end = complete.index(
        "\n            else\n            {\n                // Admission identity is immutable",
        drift_start,
    )

    assert drift_end < refresh < complete.index("return;")
    assert "EnsureValidationCohortGroup();" not in complete[drift_start:drift_end]
    assert "Cohort().Raid.GroupGuid == exactGroupGuid" in complete
    assert "nativeRecoveryWorldportsDeferred" in complete


def test_completed_validation_raid_refresh_advances_all_dead_wipe_and_evidence():
    group = IMPL[
        IMPL.index("void BotWorldPopulationMgr::EnsureValidationCohortGroup()"):
        IMPL.index("bool BotWorldPopulationMgr::ResolveSpawnPlacement")
    ]
    prior = {
        "alive_size": 10,
        "wipe_state": "ready",
        "wipe_generation": 0,
        "evidence_sequence": 0,
    }
    observed = _completed_admission_runtime_tick(
        prior_runtime=prior,
        expected_size=10,
        live_roster=[{"alive": False} for _ in range(10)],
    )

    assert observed["runtime"]["alive_size"] == 0
    assert observed["runtime"]["wipe_state"] == "wiped"
    assert observed["runtime"]["wipe_generation"] == 1
    assert observed["runtime"]["evidence_sequence"] > prior["evidence_sequence"]
    for token in (
        "bool const allDead = raid.ActiveSize > 0 && raid.AliveSize == 0;",
        "++raid.WipeGeneration;",
        "signal.DeathSequence = ++raid.EvidenceSequence;",
        "signal.CorpseSequence = signal.HasCorpse ? ++raid.EvidenceSequence : 0;",
    ):
        assert token in group


def test_partial_death_then_all_alive_does_not_create_native_wipe_recovery():
    group = IMPL[
        IMPL.index("void BotWorldPopulationMgr::EnsureValidationCohortGroup()"):
        IMPL.index("bool BotWorldPopulationMgr::ResolveSpawnPlacement")
    ]
    prior = {
        "alive_size": 10,
        "wipe_state": "ready",
        "recovery_state": "none",
        "wipe_generation": 0,
    }
    partial = _raid_recovery_runtime_tick(
        prior_runtime=prior, expected_size=10, alive_size=9,
    )
    recovered = _raid_recovery_runtime_tick(
        prior_runtime=partial, expected_size=10, alive_size=10,
    )

    assert partial["wipe_state"] == "partial_deaths"
    assert partial["recovery_state"] == "none"
    assert recovered["wipe_state"] == "ready"
    assert recovered["recovery_state"] == "none"
    assert recovered["wipe_generation"] == 0
    assert recovered["native_recovery_evidence_complete"] is False
    assert "bool const nativeWipeRecovery = previousWipeState == \"wiped\" && raid.WipeGeneration > 0;" in group
    assert 'raid.RecoveryState = nativeWipeRecovery ? "native_resurrection_runback" : "none";' in group
    assert 'raid.WipeState = "wiped";' in group
    assert 'raid.RecoveryState = "recovery_evidence_pending";' in group


def test_real_full_wipe_keeps_ordered_native_recovery_evidence_gate():
    prior = {
        "alive_size": 10,
        "wipe_state": "ready",
        "recovery_state": "none",
        "wipe_generation": 0,
    }
    wiped = _raid_recovery_runtime_tick(
        prior_runtime=prior, expected_size=10, alive_size=0,
    )
    pending = _raid_recovery_runtime_tick(
        prior_runtime=wiped, expected_size=10, alive_size=10,
    )
    recovered = _raid_recovery_runtime_tick(
        prior_runtime=pending, expected_size=10, alive_size=10,
        native_recovery_evidence_complete=True,
    )

    assert wiped["wipe_state"] == "wiped"
    assert wiped["recovery_state"] == "release_resurrection_pending"
    assert wiped["wipe_generation"] == 1
    assert pending["wipe_state"] == "wiped"
    assert pending["recovery_state"] == "recovery_evidence_pending"
    assert recovered["wipe_state"] == "ready"
    assert recovered["recovery_state"] == "recovered_ready_check"
    assert recovered["wipe_generation"] == 1


def test_completed_validation_raid_refresh_observes_native_boss_in_progress():
    group = IMPL[
        IMPL.index("void BotWorldPopulationMgr::EnsureValidationCohortGroup()"):
        IMPL.index("bool BotWorldPopulationMgr::ResolveSpawnPlacement")
    ]
    prior = {"alive_size": 10, "wipe_state": "ready", "evidence_sequence": 0}
    observed = _completed_admission_runtime_tick(
        prior_runtime=prior,
        expected_size=10,
        live_roster=[{"alive": True} for _ in range(10)],
        boss_states=("NOT_STARTED", "IN_PROGRESS"),
    )

    assert observed["runtime"]["encounter_in_progress"] is True
    assert "raid.EncounterInProgress = instance->IsEncounterInProgress();" in group
    assert "raid.BossStates.push_back(uint8(instance->GetBossState(bossId)));" in group


def test_completed_validation_raid_native_worldport_defers_then_reattach_refreshes():
    population = IMPL[
        IMPL.index("if (Cohort().ValidationRaidAdmissionComplete)"):
        IMPL.index("auto terminalFailure")
    ]
    group = IMPL[
        IMPL.index("void BotWorldPopulationMgr::EnsureValidationCohortGroup()"):
        IMPL.index("bool BotWorldPopulationMgr::ResolveSpawnPlacement")
    ]
    prior = {
        "alive_size": 10,
        "wipe_state": "ready",
        "wipe_generation": 0,
        "evidence_sequence": 0,
    }
    deferred = _completed_admission_runtime_tick(
        prior_runtime=prior,
        expected_size=10,
        live_roster=[{"alive": True} for _ in range(9)],
    )
    reattached = _completed_admission_runtime_tick(
        prior_runtime=deferred["runtime"],
        expected_size=10,
        live_roster=[{"alive": True} for _ in range(10)],
    )

    assert deferred["identity_drift"] is False
    assert deferred["runtime"] == prior
    assert reattached["runtime"]["alive_size"] == 10
    assert "nativeRecoveryWorldport" in population
    assert "++nativeRecoveryWorldportsDeferred" in population
    assert group.index("members.size() != exactFormationSize") < group.index("RaidRuntime& raid")


def test_completed_validation_raid_identity_drift_cleans_and_returns_without_refresh():
    population = IMPL[
        IMPL.index("if (Cohort().ValidationRaidAdmissionComplete)"):
        IMPL.index("auto terminalFailure")
    ]
    drift_start = population.index("if (!exactIdentity)")
    refresh = population.index("EnsureValidationCohortGroup();")
    drift = population[drift_start:refresh]

    observed = _completed_admission_runtime_tick(
        prior_runtime={"alive_size": 10, "wipe_state": "ready"},
        expected_size=10,
        live_roster=[{"alive": True} for _ in range(10)],
        identity_ok=False,
    )

    assert observed["identity_drift"] is True
    assert observed["runtime"]["wipe_state"] == "ready"
    for token in (
        "sBotMgr->RemoveWorldBot(state.Guid);",
        "ReleaseBotGuid(guid);",
        "Party() = PartyRuntime();",
        "Cohort().Raid = RaidRuntime();",
        "Cohort().RosterLeases.clear();",
    ):
        assert token in drift
    assert "EnsureValidationCohortGroup();" not in drift
    assert "return;" in population[refresh:]


def test_completed_validation_raid_rejects_native_group_foreign_member_or_subgroup_drift():
    expected_guids = tuple(range(1001, 1011))
    frozen_subgroups = {guid: (guid - expected_guids[0]) // 5 for guid in expected_guids}
    exact_group = [
        {"guid": guid, "subgroup": frozen_subgroups[guid]}
        for guid in expected_guids
    ]
    foreign_member = exact_group + [{"guid": 9001, "subgroup": 0}]
    subgroup_drift = [dict(member) for member in exact_group]
    subgroup_drift[3]["subgroup"] = 4

    assert _native_group_identity_gate(
        expected_guids=expected_guids,
        group_members=exact_group,
        frozen_subgroups=frozen_subgroups,
    )
    assert not _native_group_identity_gate(
        expected_guids=expected_guids,
        group_members=foreign_member,
        frozen_subgroups=frozen_subgroups,
    )
    assert not _native_group_identity_gate(
        expected_guids=expected_guids,
        group_members=subgroup_drift,
        frozen_subgroups=frozen_subgroups,
    )

    complete = IMPL[
        IMPL.index("if (Cohort().ValidationRaidAdmissionComplete)"):
        IMPL.index("auto terminalFailure")
    ]
    refresh = complete.index("EnsureValidationCohortGroup();")
    drift = complete[complete.index("if (!exactIdentity)"):refresh]
    for token in (
        "expectedGuids.size() == expectedPopulation",
        "exactNativeGroup->GetMembersCount() != expectedPopulation",
        "exactNativeGroup->GetMemberSlots()",
        '"native_group_foreign_member:"',
        '"native_group_subgroup_drift:"',
        "member.group != frozen->second.SubGroup",
        "Cohort().Raid.RosterByGuid.find(memberGuid)",
        "Cohort().Raid = RaidRuntime();",
        "Cohort().ValidationRaidAdmissionFailed = true;",
    ):
        assert token in complete
    assert "ChangeMembersGroup" not in complete
    assert "EnsureValidationCohortGroup();" not in drift


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
    assert 'route["roster_identity"] = scenario_roster' in generator
    assert 'diagnostic_rosters_by_scenario' in generator


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


def test_trash_profile_damage_cannot_pull_or_compound_the_next_boss_encounter():
    route_start = IMPL.index("bool BotWorldPopulationMgr::TryValidationRouteObjective")
    route_end = IMPL.index("bool BotWorldPopulationMgr::IsBossContext", route_start)
    route_runtime = IMPL[route_start:route_end]
    hold = route_runtime[
        route_runtime.index("Creature* prematureNextEncounter = nullptr;"):
        route_runtime.index("auto validationPartyHasActiveCombat", route_runtime.index("Creature* prematureNextEncounter = nullptr;"))
    ]
    resolver_start = IMPL.index("ResolvedCombatAction BotWorldPopulationMgr::ResolveProfileCombatAction")
    resolver_end = IMPL.index("BotActionResult BotWorldPopulationMgr::ExecuteProfileCombatAction", resolver_start)
    resolver = IMPL[resolver_start:resolver_end]
    executor = IMPL[
        resolver_end:
        IMPL.index("BotActionResult BotWorldPopulationMgr::ExecuteProfileCombatAction(Player*", resolver_end)
    ]

    assert "IsImmediateNextValidationRouteBossTarget" in IMPL
    assert "IsImmediateNextValidationRouteEncounterMember" in IMPL
    assert "SpellHostileMultiTargetReach" not in IMPL
    assert "SetProtectedEncounterEntries" in route_runtime
    assert "HasProtectedEncounterEntries" in resolver
    assert "future_encounter_splash_forbidden" in resolver
    assert "!IsImmediateNextValidationRouteEncounterMember(unit->ToCreature())" in resolver
    assert "if (IsImmediateNextValidationRouteEncounterMember(creature))" in resolver
    assert "future_encounter_target_forbidden" in resolver
    assert "future_encounter_target_forbidden" in executor
    assert "TryEnsurePersistentCombatSetup" in executor
    assert executor.index("future_encounter_target_forbidden") < executor.index("TryEnsurePersistentCombatSetup")
    assert "validation_route_future_encounter_contamination" in hold
    assert "future_encounter_premature_engagement" in hold
    assert "hold_for_native_future_encounter_reset" in hold
    assert "InterruptSpell(CURRENT_AUTOREPEAT_SPELL" in hold
    assert "bot->AttackStop();" in hold
    assert "pet->AttackStop();" in hold
    assert "controlled->AttackStop();" in hold
    assert "SetAllOffenseSuppressed(raidAuthorityOwner, true)" in hold
    assert "controlledCreature->SetReactState(REACT_PASSIVE);" in hold
    assert "charmInfo->SetIsCommandAttack(false);" in hold

    # Every offensive submission surface shares the same fail-closed policy.
    # This includes the exact manual Hunter Multi-Shot executor path and direct
    # Protection spell helpers, not only profile-resolved actions.
    assert "IsAllOffenseSuppressed(ownerGuid)" in ACTION_EXECUTOR
    assert "IsProtectedEncounterTarget(" in ACTION_EXECUTOR
    assert "HasProtectedEncounterEntries(ownerGuid)" in ACTION_EXECUTOR
    assert "BotRaidAreaAuthority::HasProtectedEncounterEntries(ownerGuid)" in IMPL
    assert "BotRaidAreaAuthority::IsProtectedEncounterTarget(" in IMPL
    assert "AllOffenseSuppressedOwners" in RAID_AUTHORITY
    assert "ProtectedEncounterEntriesByOwner" in RAID_AUTHORITY
    assert "ProtectedEncounterSpawnIdsByOwner" in RAID_AUTHORITY
    assert "AllowedEncounterGuidsByOwner" in RAID_AUTHORITY
    assert "SetProtectedEncounterSpawnIds" in route_runtime
    assert "SetAllowedEncounterGuids" in route_runtime
    assert "nextNode.SplitSourceGuids" in route_runtime
    assert "nextNode.PackTargetEntries" in route_runtime
    assert "BotRaidAreaAuthority::IsAllOffenseSuppressed" in PET_AI
    assert "BotRaidAreaAuthority::IsProtectedEncounterTarget" in PET_AI
    assert "bool const offenseSuppressed = ControlledOffenseSuppressed(owner);" in PET_AI
    assert "if (offenseSuppressed && me->GetVictim())" in PET_AI
    assert "if (owner && offenseSuppressed && !spellInfo->IsPositive())" in PET_AI
    assert "RaidControlledOffenseRejected(me, victim)" in UNIT_AI
    assert "RaidControlledOffenseRejected(me, target, spellInfo)" in UNIT_AI
    assert "BotRaidAreaAuthority::HasProtectedEncounterEntries(ownerGuid)" in UNIT_AI
    assert "BotRaidAreaAuthority::HasProtectedEncounterEntries(ownerGuid)" in TOTEM_AI
    assert "BotRaidAreaAuthority::IsAllOffenseSuppressed(ownerGuid)" in TOTEM_AI
    assert "ProtectedTotemTarget(owner, victim)" in TOTEM_AI
    assert "RaidTotemSpellSuppressed(this, GetSpell())" in TOTEM
    assert "UnSummon();" in TOTEM


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


def _native_full_wipe_reentry_gate(*, hostile_active, boss_reset_observed,
                                   hostile_reset_observed):
    """The native recovery gate must require reset evidence and no active pack."""
    return (boss_reset_observed or hostile_reset_observed) and not hostile_active


def _native_hostile_reset_samples(samples):
    """Model attempt/node-scoped active -> stable-inactive evidence."""
    state = {
        "scope": None,
        "seen": False,
        "seen_at_wipe": False,
        "reset": False,
        "inactive_since": None,
    }
    for sample in samples:
        scope = (sample["attempt"], sample["route_generation"], sample["node"])
        if state["scope"] != scope:
            state.update(scope=scope, seen=False, seen_at_wipe=False,
                         reset=False, inactive_since=None)
        if sample.get("active"):
            state["seen"] = True
            state["inactive_since"] = None
        elif sample.get("wiped") and (state["seen_at_wipe"] or state["seen"]):
            if state["inactive_since"] is None:
                state["inactive_since"] = sample.get("elapsed_ms", 0)
            if sample.get("elapsed_ms", 0) - state["inactive_since"] >= 5000:
                state["reset"] = True
        if sample.get("wipe_transition"):
            state["seen_at_wipe"] = state["seen"]
            state["seen"] = False
            state["reset"] = False
            state["inactive_since"] = None
    return state


def test_native_recovery_blocks_survivor_pack_reentry_until_native_reset():
    # A trash pack can remain active while the instance script reports no boss
    # encounter. It must not be allowed to kill newly resurrected members.
    assert not _native_full_wipe_reentry_gate(
        hostile_active=True, boss_reset_observed=True, hostile_reset_observed=True,
    )
    assert not _native_full_wipe_reentry_gate(
        hostile_active=False, boss_reset_observed=False, hostile_reset_observed=False,
    )
    assert _native_full_wipe_reentry_gate(
        hostile_active=False, boss_reset_observed=False, hostile_reset_observed=True,
    )

    runtime = HEADER[HEADER.index("struct RaidRuntime"):HEADER.index("struct CohortRuntime")]
    for token in (
        "bool NativeHostileActivityActive",
        "bool NativeHostileActivitySeenAtWipe",
        "bool NativeHostileInactivityObserved",
        "uint64 NativeHostileResetGeneration",
        "uint64 NativeHostileResetGenerationAtWipe",
        "uint64 NativeHostileObservationAttemptId",
        "uint64 NativeHostileObservationRouteGeneration",
        "std::string NativeHostileObservationNodeId",
    ):
        assert token in runtime

    observer = IMPL[
        IMPL.index("struct NativeRaidHostileActivityVisitor"):
        IMPL.index("bool BotWorldPopulationMgr::ResolveNativeBlackwingDescentEntrance")
    ]
    for token in (
        "MapStoredObjectTypesContainer",
        "creature->IsHostileTo(Observer)",
        "creature->IsInCombat()",
        "creature->GetVictim()",
        "creature->IsInEvadeMode()",
        "native_raid_map_unavailable",
        "native_hostiles_inactive",
    ):
        assert token in observer

    ensure = IMPL[
        IMPL.index("void BotWorldPopulationMgr::EnsureValidationCohortGroup"):
        IMPL.index("bool BotWorldPopulationMgr::ResolveSpawnPlacement")
    ]
    for token in (
        "ObserveNativeRaidHostileActivity",
        "hostileObservationScopeChanged",
        "NativeHostileObservationAttemptId",
        "NativeHostileObservationRouteGeneration",
        "NativeHostileObservationNodeId",
        "native_hostile_observation_scope_reset",
        "NativeHostileActivitySeenAtWipe",
        "NativeHostileInactiveSinceMs",
        "NativeHostileInactivityObserved",
        "++raid.NativeHostileResetGeneration",
        "raid.NativeHostileActivitySeenAtWipe || raid.NativeHostileActivitySeen",
        "raid.NativeHostileActivitySeen = false",
    ):
        assert token in ensure
    runtime_json = IMPL[
        IMPL.index("std::string BotWorldPopulationMgr::BuildRaidRuntimeJson"):
        IMPL.index("std::string BotWorldPopulationMgr::BuildRaidPositioningAnchorsJson")
    ]
    for token in (
        "native_hostile_observation_attempt_id",
        "native_hostile_observation_route_generation",
        "native_hostile_observation_node_id",
    ):
        assert token in runtime_json

    update = IMPL[
        IMPL.index("void BotWorldPopulationMgr::UpdateBot"):
        IMPL.index("bool BotWorldPopulationMgr::TryValidationRouteObjective")
    ]
    gate = update.index("native_recovery_wait_hostile_activity")
    for token in (
        "native_recovery_wait_native_reset",
        "raid.NativeHostileActivityActive",
        "nativeResetObserved",
        '"assistance\\":\\"none\\"',
        '"direct_respawn\\":false',
        '"direct_state_manufacture\\":false',
    ):
        assert token in update[gate - 1800:gate + 1800]
    gate_block = update[update.index("bool const nativeHostileRecoveryBlocked"):
                         update.index("if (Cohort().Config.ValidationRouteEnable && Cohort().Config.AllowRaids)", gate)]
    assert "TeleportTo(" not in gate_block
    assert "ResurrectPlayer" not in gate_block

    ready = IMPL[
        IMPL.index("void BotWorldPopulationMgr::TryRespondNativeRaidReadyCheck"):
        IMPL.index("void BotWorldPopulationMgr::UpdateBot")
    ]
    assert "postWipeNativeResetReady" in ready
    assert "!raid.NativeHostileActivityActive" in ready

    request = IMPL[
        IMPL.index("std::string BotWorldPopulationMgr::RequestNativeRaidReadyCheckForCohort"):
        IMPL.index("void BotWorldPopulationMgr::TryRespondNativeRaidReadyCheck")
    ]
    assert '"native_recovery_hostile_activity"' in request
    assert '"native_recovery_reset_not_observed"' in request


def test_historical_prior_node_activity_cannot_arm_later_trash_reset():
    state = _native_hostile_reset_samples([
        {"attempt": 1, "route_generation": 4, "node": "chainwielder",
         "active": True, "wiped": False},
        {"attempt": 1, "route_generation": 5, "node": "drudge",
         "active": False, "wiped": True, "wipe_transition": True, "elapsed_ms": 0},
        {"attempt": 1, "route_generation": 5, "node": "drudge",
         "active": False, "wiped": True, "elapsed_ms": 6000},
    ])
    assert state["seen"] is False
    assert state["seen_at_wipe"] is False
    assert state["reset"] is False


def test_post_wipe_activity_sample_can_arm_reset_after_first_active_sample_was_missed():
    state = _native_hostile_reset_samples([
        # The first post-wipe sample missed the still-active pack.
        {"attempt": 1, "route_generation": 5, "node": "drudge",
         "active": False, "wiped": True, "wipe_transition": True, "elapsed_ms": 0},
        # A later sample sees the pack before it naturally goes inactive.
        {"attempt": 1, "route_generation": 5, "node": "drudge",
         "active": True, "wiped": True, "elapsed_ms": 1000},
        {"attempt": 1, "route_generation": 5, "node": "drudge",
         "active": False, "wiped": True, "elapsed_ms": 7000},
        {"attempt": 1, "route_generation": 5, "node": "drudge",
         "active": False, "wiped": True, "elapsed_ms": 12000},
    ])
    assert state["seen_at_wipe"] is False
    assert state["reset"] is True


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


def test_drudge_partial_death_cannot_enter_tactical_recovery():
    objective = IMPL[
        IMPL.index("bool BotWorldPopulationMgr::TryValidationRouteObjective"):
        IMPL.index("bool BotWorldPopulationMgr::IsBossContext")
    ]
    drudge_guard = objective.index(
        'if (Cohort().Config.ValidationRouteMechanicProfile == "trash_two_tank_charge_lanes"\n'
        '            && deadMembers > 0 && groupCombatActive)'
    )
    generic_recovery = objective.index(
        "if ((majorityDead || criticalRoleDead) && groupCombatActive"
    )
    assert drudge_guard < generic_recovery
    guard = objective[drudge_guard:generic_recovery]
    assert '"drudge_native_full_wipe_hold_partial_death"' in guard
    assert 'action = "native_full_wipe_hold";' in guard
    assert "SetAllOffenseSuppressed" in guard
    assert "CombatStopWithPets" not in guard
    assert "MoveBotToPoint" not in guard


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
