import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_DIR = ROOT / "src/server/game/Bots"


def _read_source_set(paths: tuple[Path, ...]) -> str:
    if not paths:
        raise AssertionError("expected at least one BotWorldPopulationMgr source module")
    return "\n".join(path.read_text(encoding="utf-8") for path in paths)


def _ordered_manager_sources() -> tuple[Path, ...]:
    """Return the split manager sources in a stable assertion-friendly order.

    Most tests only need whole-family membership. A few compare a range that
    crosses translation units, so the owner modules for those ranges are kept
    adjacent and ordered by the runtime call flow. This is a test view only;
    it does not imply a unity build or change CMake ownership.
    """
    all_sources = set(BOT_DIR.glob("BotWorldPopulationMgr*.cpp"))
    all_sources.update((BOT_DIR / "Content").rglob("*.cpp"))
    priority = (
        BOT_DIR / "BotWorldPopulationMgrUpdateBot.cpp",
        BOT_DIR / "BotWorldPopulationMgrUpdateBotPreparation.cpp",
        BOT_DIR / "BotWorldPopulationMgrUpdateBotDecision.cpp",
        BOT_DIR / "BotWorldPopulationMgrUpdateBotFinalization.cpp",
        BOT_DIR / "BotWorldPopulationMgrUpdateBotKernelPreparation.cpp",
        BOT_DIR / "BotWorldPopulationMgrUpdateBotKernelCandidates.cpp",
        BOT_DIR / "BotWorldPopulationMgrUpdateBotKernelFallback.cpp",
        BOT_DIR / "BotWorldPopulationMgrUpdateBotLegacy.cpp",
        BOT_DIR / "BotWorldPopulationMgrUpdateDeath.cpp",
        BOT_DIR / "BotWorldPopulationMgr.cpp",
        BOT_DIR / "BotWorldPopulationMgrValidationRouteTrashThreatControl.cpp",
        BOT_DIR / "BotWorldPopulationMgrValidationRouteSharedFocusAction.cpp",
        BOT_DIR / "BotWorldPopulationMgrValidationRouteTargetEngagement.cpp",
        BOT_DIR / "BotWorldPopulationMgrValidationRouteActiveCombat.cpp",
        BOT_DIR / "BotWorldPopulationMgrValidationRouteFeralTrashHandoff.cpp",
        BOT_DIR / "BotWorldPopulationMgrValidationRouteGroupRecovery.cpp",
        BOT_DIR / "BotWorldPopulationMgrValidationRoutePack.cpp",
        BOT_DIR / "BotWorldPopulationMgrValidationRouteTerminalArrival.cpp",
        BOT_DIR / "BotWorldPopulationMgrValidationPatrolPull.cpp",
        BOT_DIR / "BotWorldPopulationMgrValidationLivePack.cpp",
        BOT_DIR / "BotWorldPopulationMgrValidationFocus.cpp",
        BOT_DIR / "BotWorldPopulationMgrValidationTargeting.cpp",
        BOT_DIR / "BotWorldPopulationMgrValidationRouteGate.cpp",
        BOT_DIR / "BotWorldPopulationMgrValidationRouteRuntime.cpp",
        BOT_DIR / "BotWorldPopulationMgrValidationRouteMovementCheck.cpp",
        BOT_DIR / "BotWorldPopulationMgrValidationRouteMovementCheckActions.cpp",
        BOT_DIR / "BotWorldPopulationMgrValidationGroupHeal.cpp",
        BOT_DIR / "Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeGeometry.cpp",
        BOT_DIR / "Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeLaneSelection.cpp",
        BOT_DIR / "Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeActions.cpp",
        BOT_DIR / "Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeSeed.cpp",
        BOT_DIR / "BotWorldPopulationMgrBossTargeting.cpp",
        BOT_DIR / "BotWorldPopulationMgrDungeonRoute.cpp",
        BOT_DIR / "BotWorldPopulationMgrValidationCohortGroup.cpp",
        BOT_DIR / "BotWorldPopulationMgrValidationCohortRuntime.cpp",
        BOT_DIR / "BotWorldPopulationMgrValidationLifecycle.cpp",
        BOT_DIR / "BotWorldPopulationMgrPopulation.cpp",
        BOT_DIR / "BotWorldPopulationMgrCalibrationPopulation.cpp",
        BOT_DIR / "BotWorldPopulationMgrSpawnMemory.cpp",
        BOT_DIR / "BotWorldPopulationMgrMovement.cpp",
        BOT_DIR / "BotWorldPopulationMgrCombatMovement.cpp",
        BOT_DIR / "BotWorldPopulationMgrRoster.cpp",
        BOT_DIR / "BotWorldPopulationMgrValidationRouteManifest.cpp",
        BOT_DIR / "BotWorldPopulationMgrRuntimeProfiles.cpp",
        BOT_DIR / "BotWorldPopulationMgrCombatLog.cpp",
        BOT_DIR / "BotWorldPopulationMgrCombatNotifications.cpp",
        BOT_DIR / "BotWorldPopulationMgrValidationRecoveryGate.cpp",
        BOT_DIR / "BotWorldPopulationMgrRaidRuntime.cpp",
        BOT_DIR / "BotWorldPopulationMgrEncounterJson.cpp",
        BOT_DIR / "BotWorldPopulationMgrCombatResolver.cpp",
        BOT_DIR / "BotWorldPopulationMgrCombatExecution.cpp",
        BOT_DIR / "BotWorldPopulationMgrBossMechanics.cpp",
        BOT_DIR / "BotWorldPopulationMgrRaidPlanning.cpp",
    )
    ordered = [path for path in priority if path in all_sources]
    ordered.extend(sorted(all_sources.difference(ordered)))
    return tuple(ordered)


HEADER = _read_source_set(
    tuple(sorted(
        set(BOT_DIR.glob("BotWorldPopulationMgr*.h"))
        | set((BOT_DIR / "Content").rglob("BotWorldPopulationMgr*.h"))
    ))
)
IMPL = _read_source_set(_ordered_manager_sources())
GROUP_RECOVERY = (
    ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteGroupRecovery.cpp"
).read_text(encoding="utf-8")
UPDATE_PREPARATION = (
    ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateBotPreparation.cpp"
).read_text(encoding="utf-8")
UPDATE_DEATH = (
    ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateDeath.cpp"
).read_text(encoding="utf-8")
UPDATE_BOT_FAMILY = _read_source_set(tuple(
    BOT_DIR / name
    for name in (
        "BotWorldPopulationMgrUpdateBot.cpp",
        "BotWorldPopulationMgrUpdateBotPreparation.cpp",
        "BotWorldPopulationMgrUpdateBotDecision.cpp",
        "BotWorldPopulationMgrUpdateBotFinalization.cpp",
        "BotWorldPopulationMgrUpdateBotKernelPreparation.cpp",
        "BotWorldPopulationMgrUpdateBotKernelCandidates.cpp",
        "BotWorldPopulationMgrUpdateBotKernelFallback.cpp",
        "BotWorldPopulationMgrUpdateBotLegacy.cpp",
    )
))
VALIDATION_COHORT_RUNTIME = (
    BOT_DIR / "BotWorldPopulationMgrValidationCohortRuntime.cpp"
).read_text(encoding="utf-8")
VALIDATION_HAZARDS = (
    BOT_DIR / "BotWorldPopulationMgrValidationHazards.cpp"
).read_text(encoding="utf-8")
VALIDATION_MOVEMENT = (
    BOT_DIR / "BotWorldPopulationMgrValidationRouteMovementCheck.cpp"
).read_text(encoding="utf-8")
VALIDATION_PATROL_PULL = (
    BOT_DIR / "BotWorldPopulationMgrValidationPatrolPull.cpp"
).read_text(encoding="utf-8")
VALIDATION_AUTHORITY = (
    BOT_DIR / "BotWorldPopulationMgrValidationAuthority.cpp"
).read_text(encoding="utf-8")
VALIDATION_RECOVERY_GATE = (
    BOT_DIR / "BotWorldPopulationMgrValidationRecoveryGate.cpp"
).read_text(encoding="utf-8")
VALIDATION_COHORT_GROUP = (
    BOT_DIR / "BotWorldPopulationMgrValidationCohortGroup.cpp"
).read_text(encoding="utf-8")
VALIDATION_COHORT_LIFECYCLE = (
    BOT_DIR / "BotWorldPopulationMgrValidationLifecycle.cpp"
).read_text(encoding="utf-8")
VALIDATION_LIVE_PACK = (
    BOT_DIR / "BotWorldPopulationMgrValidationLivePack.cpp"
).read_text(encoding="utf-8")
VALIDATION_TERMINAL_ARRIVAL = (
    BOT_DIR / "BotWorldPopulationMgrValidationRouteTerminalArrival.cpp"
).read_text(encoding="utf-8")
VALIDATION_ROUTE_TANK_FOCUS = (
    BOT_DIR / "BotWorldPopulationMgrValidationRouteTankFocusAssist.cpp"
).read_text(encoding="utf-8")
VALIDATION_ROUTE_SHARED_FOCUS = (
    BOT_DIR / "BotWorldPopulationMgrValidationRouteSharedFocusAction.cpp"
).read_text(encoding="utf-8")
VALIDATION_ROUTE_TARGET_ENGAGEMENT = (
    BOT_DIR / "BotWorldPopulationMgrValidationRouteTargetEngagement.cpp"
).read_text(encoding="utf-8")
VALIDATION_ROUTE_ACTIVE_COMBAT = (
    BOT_DIR / "BotWorldPopulationMgrValidationRouteActiveCombat.cpp"
).read_text(encoding="utf-8")
VALIDATION_ROUTE_DISPATCH = _read_source_set((
    BOT_DIR / "BotWorldPopulationMgrValidationRouteTankFocusAssist.cpp",
    BOT_DIR / "BotWorldPopulationMgrValidationRouteSharedFocusAction.cpp",
    BOT_DIR / "BotWorldPopulationMgrValidationRouteActiveCombat.cpp",
    BOT_DIR / "BotWorldPopulationMgrValidationRouteTargetEngagement.cpp",
))
VALIDATION_ROUTE_PACK = (
    BOT_DIR / "BotWorldPopulationMgrValidationRoutePack.cpp"
).read_text(encoding="utf-8")
VALIDATION_FOCUS = (
    BOT_DIR / "BotWorldPopulationMgrValidationFocus.cpp"
).read_text(encoding="utf-8")
VALIDATION_ROUTE_RUNTIME = _read_source_set(tuple(
    BOT_DIR / name
    for name in (
        "BotWorldPopulationMgr.cpp",
        "BotWorldPopulationMgrValidationRouteGate.cpp",
        "BotWorldPopulationMgrValidationRouteRuntime.cpp",
        "BotWorldPopulationMgrValidationRoutePack.cpp",
        "BotWorldPopulationMgrValidationRouteTargetEngagement.cpp",
        "BotWorldPopulationMgrValidationRouteSharedFocusAction.cpp",
        "BotWorldPopulationMgrValidationRouteTankFocusAssist.cpp",
        "BotWorldPopulationMgrValidationRouteActiveCombat.cpp",
        "BotWorldPopulationMgrValidationRouteTrashThreatControl.cpp",
        "BotWorldPopulationMgrValidationRouteTrashIntervention.cpp",
        "BotWorldPopulationMgrValidationRouteTankTrashRecovery.cpp",
        "BotWorldPopulationMgrValidationRouteGroupRecovery.cpp",
        "BotWorldPopulationMgrValidationRouteTerminalArrival.cpp",
        "BotWorldPopulationMgrValidationPatrolPull.cpp",
    )
))
VALIDATION_ADMISSION = (
    BOT_DIR / "BotWorldPopulationMgrValidationAdmission.cpp"
).read_text(encoding="utf-8")
VALIDATION_TARGETING = (
    BOT_DIR / "BotWorldPopulationMgrValidationTargeting.cpp"
).read_text(encoding="utf-8")
VALIDATION_MANIFEST = (
    BOT_DIR / "BotWorldPopulationMgrValidationRouteManifest.cpp"
).read_text(encoding="utf-8")
VALIDATION_GROUP_HEAL = (
    BOT_DIR / "BotWorldPopulationMgrValidationGroupHeal.cpp"
).read_text(encoding="utf-8")
ROSTER = (BOT_DIR / "BotWorldPopulationMgrRoster.cpp").read_text(encoding="utf-8")
MOVEMENT = (BOT_DIR / "BotWorldPopulationMgrMovement.cpp").read_text(encoding="utf-8")
MOVEMENT_LEASE = (
    BOT_DIR / "BotWorldPopulationMgrMovementLease.cpp"
).read_text(encoding="utf-8")
MOVEMENT_EXECUTOR = (
    BOT_DIR / "BotWorldPopulationMgrMovementExecutor.cpp"
).read_text(encoding="utf-8")
MOVEMENT_PLANNER = (
    BOT_DIR / "BotWorldPopulationMgrMovementPlanner.cpp"
).read_text(encoding="utf-8")
COMBAT_RES = (BOT_DIR / "BotWorldPopulationMgrCombatRes.cpp").read_text(encoding="utf-8")
NATIVE_ACTION = (BOT_DIR / "BotWorldPopulationMgrNativeAction.cpp").read_text(encoding="utf-8")
RECOVERY = (BOT_DIR / "BotWorldPopulationMgrRecovery.cpp").read_text(encoding="utf-8")
COMBAT_LOG = (BOT_DIR / "BotWorldPopulationMgrCombatLog.cpp").read_text(encoding="utf-8")
UPDATE_CONTEXT = (BOT_DIR / "BotWorldPopulationMgrUpdate.cpp").read_text(encoding="utf-8")
UPDATE_DEATH = (
    ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateDeath.cpp"
).read_text(encoding="utf-8")
RUNTIME_CONTRACTS = (
    BOT_DIR / "BotWorldPopulationMgrRuntimeContracts.h"
).read_text(encoding="utf-8")
CALIBRATION_METRICS = (
    BOT_DIR / "BotWorldPopulationMgrCalibrationMetrics.h"
).read_text(encoding="utf-8")
POPULATION = (BOT_DIR / "BotWorldPopulationMgrPopulation.cpp").read_text(encoding="utf-8")
CALIBRATION_POPULATION = (
    BOT_DIR / "BotWorldPopulationMgrCalibrationPopulation.cpp"
).read_text(encoding="utf-8")
DRUDGE_MODULES = _read_source_set(tuple(sorted(
    (BOT_DIR / "Content/Raids/BlackwingDescent/Trash/Drudge").glob("*.cpp")
)))
BOSS_MECHANICS = (BOT_DIR / "BotWorldPopulationMgrBossMechanics.cpp").read_text(encoding="utf-8")
BOSS_DISPATCH = (BOT_DIR / "BotWorldPopulationMgrBossDispatch.cpp").read_text(encoding="utf-8")
BOSS_TARGETING = (BOT_DIR / "BotWorldPopulationMgrBossTargeting.cpp").read_text(encoding="utf-8")
COMBAT_RESOLUTION = _read_source_set((
    BOT_DIR / "BotWorldPopulationMgrCombatResolver.cpp",
    BOT_DIR / "BotWorldPopulationMgrCombatExecution.cpp",
))
STATUS = (
    ROOT / "src/server/game/Bots/BotWorldPopulationMgrStatus.cpp"
).read_text(encoding="utf-8")
ACTION_EXECUTOR = (ROOT / "src/server/game/Bots/BotActionExecutor.cpp").read_text(encoding="utf-8")
RAID_AUTHORITY = (ROOT / "src/server/game/Bots/BotRaidAreaAuthority.h").read_text(encoding="utf-8")
PET_AI = (ROOT / "src/server/game/AI/CoreAI/PetAI.cpp").read_text(encoding="utf-8")
UNIT_AI = (ROOT / "src/server/game/AI/CoreAI/UnitAI.cpp").read_text(encoding="utf-8")
TOTEM_AI = (ROOT / "src/server/game/AI/CoreAI/TotemAI.cpp").read_text(encoding="utf-8")
TOTEM = (ROOT / "src/server/game/Entities/Totem/Totem.cpp").read_text(encoding="utf-8")
DRUDGE_NATIVE_RUSH = (
    BOT_DIR / "Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeNativeRushState.h"
).read_text(encoding="utf-8")
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
    assert "Cohort().ValidationAdmission == ValidationAdmissionPhase::Active" in member_sample
    assert "IsNativeReleasedGhostWorldport(state, bot)" in member_sample
    assert "IsNativeValidationRunbackWorldport(state, bot)" in member_sample
    assert "Include only the two independently-authorized native worldports" in member_sample

    runtime_refresh = admitted_group[
        admitted_group.index("currentSignal.Initialized"):
        admitted_group.index("auto signalComplete")
    ]
    assert "HasNativeRaidCorpseAuthority(*botState, bot)" in runtime_refresh
    assert "releaseLandingIdentityBound" in runtime_refresh
    assert "NativeReleaseLandingWipeGeneration == raid.WipeGeneration" in runtime_refresh
    assert "NativeRunbackAreaTriggerId" in runtime_refresh
    assert "AdmissionRecoveryEntranceAreaTriggerId" in runtime_refresh
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

    runtime_refresh = VALIDATION_COHORT_RUNTIME[
        VALIDATION_COHORT_RUNTIME.index("if (!signal.ReleaseSequence"):
        VALIDATION_COHORT_RUNTIME.index("bool const exactSignalRoster")
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
                                    hold_active, scope_matches,
                                    wipe_generation, evidence_complete):
    return (
        policy == "native_full_wipe_only"
        and active
        and attempt_matches
        and hold_active
        and scope_matches
        and wipe_generation > 0
        and not evidence_complete
    )


def test_native_recovery_evidence_gate_holds_offense_navigation_and_reengagement():
    assert _native_recovery_objective_gate(
        policy="native_full_wipe_only", active=True, attempt_matches=True,
        hold_active=True, scope_matches=True, wipe_generation=2,
        evidence_complete=False,
    )
    assert _native_recovery_objective_gate(
        policy="native_full_wipe_only", active=True, attempt_matches=True,
        hold_active=True, scope_matches=True, wipe_generation=2,
        evidence_complete=False,
    )
    assert not _native_recovery_objective_gate(
        policy="native_full_wipe_only", active=True, attempt_matches=True,
        hold_active=False, scope_matches=True, wipe_generation=2,
        evidence_complete=False,
    )
    assert not _native_recovery_objective_gate(
        policy="native_full_wipe_only", active=True, attempt_matches=True,
        hold_active=True, scope_matches=True, wipe_generation=2,
        evidence_complete=True,
    )
    assert not _native_recovery_objective_gate(
        policy="native_full_wipe_only", active=True, attempt_matches=True,
        hold_active=True, scope_matches=False, wipe_generation=2,
        evidence_complete=False,
    )

    objective = IMPL[
        IMPL.index("bool BotWorldPopulationMgr::TryValidationRouteObjective"):
        IMPL.index("bool BotWorldPopulationMgr::IsBossContext")
    ]
    gate = objective.index("if (IsNativeRaidRecoveryEvidencePending())")
    clear = VALIDATION_AUTHORITY.index(
        "BotRaidAreaAuthority::SetAllOffenseSuppressed(raidAuthorityOwner, false)"
    )
    assert gate >= 0 and clear >= 0
    for token in (
        "SuppressNativeRaidRecovery(state, bot);",
        'action = "hold_native_recovery_evidence";',
        "return true;",
    ):
        assert token in objective[gate:]

    pending = IMPL[
        IMPL.index("bool BotWorldPopulationMgr::IsNativeRaidRecoveryEvidencePending"):
        IMPL.index("void BotWorldPopulationMgr::SuppressNativeRaidRecovery")
    ]
    for token in (
        "raid.NativeRecoveryEvidenceComplete",
        "raid.NativeRecoveryHoldActive",
        "raid.NativeRecoveryRouteGeneration != Party().ValidationRouteGeneration",
        "raid.NativeRecoveryNodeId != Cohort().Config.ValidationRouteNodeId",
    ):
        assert token in pending


def test_native_recovery_hold_precedes_readycheck_and_uses_no_forced_combat_stop():
    update = UPDATE_PREPARATION
    hold = update.index("if (context.Bot->IsAlive() && IsNativeRaidRecoveryEvidencePending())")
    ready_check = update.index("TryRespondNativeRaidReadyCheck(context.State, context.Bot);", hold)
    timer = update.index("if (context.State.DecisionTimer > context.Diff)")
    assert hold < ready_check < timer
    assert "context.State.DecisionTimer = 0;" in update[hold:timer]

    suppress = VALIDATION_RECOVERY_GATE[
        VALIDATION_RECOVERY_GATE.index("void BotWorldPopulationMgr::SuppressNativeRaidRecovery"):
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
    assert "TryRestoreNativeRaidRecoveryPet(context.State, context.Bot)" in update[hold:ready_check]


def _frontal_hazard_inside(*, distance, relative_radians, radius=12.0):
    return distance <= radius and abs(relative_radians) <= math.pi / 2


def test_frontal_hazard_requires_configured_radius_and_arc_together():
    assert _frontal_hazard_inside(distance=6.0, relative_radians=0.0)
    assert not _frontal_hazard_inside(distance=6.0, relative_radians=math.pi * 0.75)
    # Forward-facing but beyond the configured radius is safe.
    assert not _frontal_hazard_inside(distance=13.0, relative_radians=0.0)

    impl = VALIDATION_MOVEMENT[
        VALIDATION_MOVEMENT.index("auto positionOutsideHazard"):
        VALIDATION_MOVEMENT.index("auto pathOutsideActiveHazards")
    ]
    assert "BotWorldValidationHazards::PositionOutside" in impl
    assert "inside = inside && std::fabs(relative) <= float(M_PI_2);" in VALIDATION_HAZARDS

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
    assert chainwielder["patrol_pull_policy"] == "ranged_patrol_to_anchor"
    assert chainwielder["patrol_wait_anchor"] == {
        "x": -346.5827, "y": -83.71657, "z": 213.9893,
    }
    assert chainwielder["patrol_pull_owner_roster_slot"] == 9

    assert (drudges["step"], drudges["source_entry"], drudges["source_guid"]) == (3, 42362, "250140")
    assert drudges["pack_target_entries"] == [42362]
    assert drudges["split_source_guids"] == [250140, 250141]
    assert drudges["split_lane_a_roster_slots"] == [1, 3, 4, 6, 7]
    assert drudges["split_lane_b_roster_slots"] == [2, 5, 8, 9, 10]
    assert drudges["split_lane_tank_slots"] == [1, 2]
    assert drudges["split_minimum_separation_yards"] == 15.0
    assert drudges["split_native_melee_stop_yards"] == 8.0
    assert [row["source_guid"] for row in drudges["split_source_home_anchors"]] == [250140, 250141]
    tank_anchors = {row["roster_slot"]: row for row in drudges["split_tank_combat_anchors"]}
    assert math.dist(
        (tank_anchors[1]["x"], tank_anchors[1]["y"]),
        (tank_anchors[2]["x"], tank_anchors[2]["y"]),
    ) > 33.0
    navigation_anchors = {
        row["roster_slot"]: row for row in drudges["split_tank_navigation_anchors"]
    }
    assert set(navigation_anchors) == {1, 2}
    assert navigation_anchors == tank_anchors
    assert drudges["split_arrival_tolerance_yards"] == 1.0
    assert drudges["split_tank_arrival_tolerance_yards"] == 1.0
    assert math.dist(
        (navigation_anchors[1]["x"], navigation_anchors[1]["y"]),
        (navigation_anchors[2]["x"], navigation_anchors[2]["y"]),
    ) > 33.0
    assert (drudges["minimum_distance_source_entry"], drudges["minimum_distance_yards"]) == (42362, 15.0)
    assert (drudges["thunderclap_spell_id"], drudges["charge_spell_id"], drudges["charge_range_yards"]) == (79604, 79630, 80.0)
    assert drudges["charge_native_interval_ms"] == 20000
    assert drudges["vengeful_rage_spell_id"] == 80035
    assert bwd["mechanic_profiles"]["trash_ground_danger_movement"] == [
        "ground_danger", "movement_check", "minimum_distance"
    ]


def test_bwd_drudge_pair_executes_exact_roster_lanes_and_native_charge_reseparation():
    dispatch = (BOT_DIR / "BotWorldPopulationMgr.cpp").read_text(encoding="utf-8")
    geometry = (BOT_DIR / "Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeGeometry.cpp").read_text(
        encoding="utf-8"
    )
    recovery = (BOT_DIR / "Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeRecovery.cpp").read_text(
        encoding="utf-8"
    )
    lane = (BOT_DIR / "Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeLaneSelection.cpp").read_text(
        encoding="utf-8"
    )
    actions = (BOT_DIR / "Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeActions.cpp").read_text(
        encoding="utf-8"
    )
    seed = (BOT_DIR / "Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeSeed.cpp").read_text(
        encoding="utf-8"
    )

    # The facade owns only dispatch ordering. The typed contract, geometry,
    # action phases, and threat-seed coordinator are asserted in their
    # respective translation units so a split cannot hide a missing phase.
    terminal = dispatch.index("terminalArrivalContext.Run()")
    lanes = dispatch.index("TryValidationRouteDrudgeChargeLanes(state, bot, power, stage")
    movement = dispatch.index("TryValidationRouteMovementCheck(state, bot, power, stage")
    patrol = dispatch.index("tryValidationRoutePatrolPull()")
    minimum = dispatch.index("TryValidationRouteDrudgeMinimumDistance(state, bot, power, stage")
    assert lanes < terminal < movement < patrol < minimum

    for token in (
        "trash_two_tank_charge_lanes",
        "ValidationRouteSplitSourceGuids",
        "ValidationRouteSplitLaneARosterSlots",
        "ValidationRouteSplitLaneBRosterSlots",
        "ValidationRouteSplitLaneTankSlots",
        "ValidationRouteSplitMemberAnchors",
        "ValidationRouteSplitTankCombatAnchors",
        "ValidationRouteSplitTankNavigationAnchors",
        "ValidationRouteSplitTankRecoveryAnchors",
        "RosterByGuid",
        "ResolveSources",
        "GetCreatureBySpawnId",
        "GetHomePosition",
        "ExactRosterSlots = { 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 }",
        "laneSlots == ExactRosterSlots",
        "anchorSlots == ExactRosterSlots",
        "ComputeExactCombatTankPathsProven",
        "ComputeExactRecoveryTankPathsProven",
        "ComputeExactLiveRecoveryTankPathsPreflighted",
        "RecordReseparationEvidence",
    ):
        assert token in lane

    for token in (
        "ValidationRouteSplitMinimumSeparationYards",
        "ValidationRouteSplitNavigationMarginYards",
        "ValidationRouteSplitArrivalToleranceYards",
        "ValidationRouteSplitTankArrivalToleranceYards",
        "ValidationRouteSplitNativeMeleeStopYards",
        "ValidationRouteMinimumDistanceYards",
        "ValidationRouteSplitSeedRosterSlots",
        "ValidationRouteSplitSeedMaxRangeYards",
        "ValidationRouteSplitTankThreatHeadroomMultiplier",
        "ValidationRouteVengefulRageSpellId",
        "ValidationRouteChargeSpellId",
    ):
        assert token in lane

    for token in (
        "RunFormationActions",
        "PrepullStaged",
        "ChargeAwaitingLanding",
        "NativeChargePending",
        "Charge->Landed",
        "NativeChargeTargetLaneViolation",
        "NativeChargeTargetRoleViolation",
        "ExactCombatTankPathsProven",
        "ExactRecoveryTankPathsProven",
        "ExactLiveRecoveryTankPathsPreflighted",
        "drudge_prepull_exact_roster_staged",
        "earlyPullOwnershipWindow",
        "drudge_prepull_early_combat_recovery",
        "drudge_tank_anchor_strict_path_rejected",
        "drudge_tank_recovery_anchor_preflight_wait",
        "drudge_recovery_anchor_live_preflight_failed",
        "LandedRushRecoveryComplete",
        "drudge_native_charge_reseparation_complete",
        "SelectMemberRecoveryAction",
        "MoveBotToPoint",
        "drudge_lane_native_taunt",
        "drudge_lane_native_taunt_approach",
        "drudge_native_tank_threat_build",
        "drudge_native_tank_threat_sustain",
        "drudge_pre_first_rush_ready_hold",
        "drudge_native_farthest_seed_wait",
        "drudge_lane_profile_hold_contract_unsafe",
        "drudge_kill_sync_hold_lower_health_lane",
        "drudge_tank_health_sync_hold",
        "drudge_lane_single_target_action",
        "ResolveProfileCombatAction",
        "SetAllOffenseSuppressed",
    ):
        assert token in actions

    formation = actions[
        actions.index("if (PrepullStaged && !NativeChargePending"):
        actions.index("DrudgeLaneContext::PhaseResult DrudgeLaneContext::RunThreatAndEvidenceActions")
    ]
    early_pull_window = actions.index("bool const earlyPullOwnershipWindow =")
    early_pull_recovery = actions.index("EarlyPullRecoveryActive =")
    seed_coordinator = actions.index("RunDrudgeSeedCoordinator", early_pull_recovery)
    taunt = actions.index("drudge_lane_native_taunt", seed_coordinator)
    assert early_pull_window < early_pull_recovery < seed_coordinator < taunt
    assert "|| earlyPullOwnershipWindow;" in actions[early_pull_recovery:seed_coordinator]
    assert formation.index("drudge_tank_anchor_strict_path_rejected") < formation.index(
        "drudge_tank_recovery_anchor_preflight_wait"
    )
    assert formation.index("RunDrudgeSeedCoordinator") < formation.index(
        "drudge_lane_native_taunt"
    )
    assert formation.index("drudge_native_tank_threat_sustain") < formation.index(
        "bool const recoveryNeeded"
    )
    assert formation.index("!NativeChargePending && !ChargeAwaitingLanding") < formation.index(
        "drudge_native_tank_threat_sustain"
    )
    assert formation.index("LandedRushRecoveryComplete") < formation.index(
        "drudge_native_charge_reseparation_complete"
    )
    assert formation.index("SelectMemberRecoveryAction") < formation.index(
        "drudge_staging_support"
    )
    assert "false, 0, false, false, true, false, true" in actions

    threat = actions[
        actions.index("DrudgeLaneContext::PhaseResult DrudgeLaneContext::RunThreatAndEvidenceActions"):
    ]
    assert threat.index("RunDrudgeSeedCoordinator") < threat.index("laneOwnershipSafe")
    assert threat.index("RunDrudgeSeedCoordinator") < threat.index(
        "drudge_lane_profile_hold_contract_unsafe"
    )
    assert threat.index("drudge_lane_profile_hold_contract_unsafe") < threat.index(
        "drudge_lane_single_target_action"
    )

    for token in (
        "ExactDrudgeAuthorityRoster",
        "ResolveDrudgeSeedCandidate",
        "AdvanceCoordinator",
        "initialSeedOpportunity",
        "!seedState.SeededLanes[0] && !seedState.SeededLanes[1]",
        "!chargeObserved",
        "bothVictimsOwned || initialSeedOpportunity",
        "drudge_pre_first_rush_threat_seed",
        "ValidationRouteDrudgeThreatSeedFailure",
        "native_action_rejected",
        'roster->second.Role != "tank"',
        'selected.Action.MaxRange <= 5.0f',
        "SetAllOffenseSuppressed",
    ):
        assert token in seed

    for token in (
        "SelectMinimumDistanceOwner",
        "MinimumDistanceOwner::LandedRushRecovery",
        "ValidationRouteDrudgeChargeObservations",
        "RecoveryPathPreservesTankSeparation",
        "ValidationRouteDrudgeAnchorSource0Identity",
        "ExactRosterPrepullStaged",
        "RecoveryAnchorReachedFor",
        "ExactRecoveryTankAnchorsReached",
        "ExactCombatTankAnchorsReached",
        "TryMinimumDistance",
    ):
        assert token in geometry or token in recovery

    cast_hook = COMBAT_LOG[
        COMBAT_LOG.index("uint64 BotWorldPopulationMgr::NotifyNativeCreatureSpellStarted"):
    ]
    for token in (
        'ValidationRouteMechanicProfile != "trash_two_tank_charge_lanes"',
        "ValidationRouteChargeRangeYards",
        "ValidationRouteChargeNativeIntervalMs",
        "ValidationRouteDrudgeChargeGeneration",
        "ValidationRouteDrudgeChargeObservations.push_back",
        "GetUnsortedThreatList",
        "MaxNativeThreatCandidates",
        "NativeThreatCandidatesCount",
        "NativeThreatCandidatesComplete",
        "NativeThreatCandidatesTruncated",
        "candidateEvidence.IsPlayer",
        "candidateEvidence.Alive",
        "candidateEvidence.SameMap",
        "ValidationRouteDrudgeChargeQueueOverflow = true",
        "void BotWorldPopulationMgr::NotifyNativeCreatureSpellLanded",
        "candidate.Sequence == observationSequence",
        "candidate.AttemptId == Cohort().AttemptId",
        "candidate.WipeGeneration == Cohort().Raid.WipeGeneration",
    ):
        assert token in cast_hook
    assert cast_hook.index("if (!exactSource)") < cast_hook.index(
        "Scope const currentScope"
    ) < cast_hook.index("Result const transition = Advance(seedState, rushInput);")
    drudge_header = (BOT_DIR / "Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudge.h").read_text(
        encoding="utf-8"
    )
    assert "DrudgeLaneCallbacks" in drudge_header
    assert "TryGroupHeal" in drudge_header

    spell_impl = (ROOT / "src/server/game/Spells/Spell.cpp").read_text(encoding="utf-8")
    assert "NotifyNativeCreatureSpellStarted" in spell_impl
    assert "effect == SPELL_EFFECT_CHARGE" in spell_impl
    assert "NotifyNativeCreatureSpellLanded" in spell_impl



def test_botworld_hot_path_defers_progression_scoring_and_rate_limits_repeated_logs():
    update = UPDATE_PREPARATION
    hold = update.index("if (context.Bot->IsAlive() && IsNativeRaidRecoveryEvidencePending())")
    timer = update.index("if (context.State.DecisionTimer > context.Diff)")
    score = update.index("context.EnsureProgressionScored();", timer)
    assert hold < timer < score
    assert "SuppressNativeRaidRecovery(context.State, context.Bot);" in update[hold:timer]
    assert "LastNotInWorldInfoLogMs" in UPDATE_CONTEXT
    assert "SuppressedNotInWorldInfoLogs" in UPDATE_CONTEXT
    assert "LastNativeWorldportDeferredLogMs" in VALIDATION_ADMISSION
    assert "SuppressedNativeWorldportDeferredLogs" in VALIDATION_ADMISSION
    assert "suppressed=%u" in UPDATE_CONTEXT + VALIDATION_ADMISSION
    suppress = VALIDATION_RECOVERY_GATE
    assert "NativeRecoveryHoldWipeGeneration" in suppress
    assert "periodicVerify" in suppress
    assert "if (!newHold && !periodicVerify && !ownerActive && !controlledUnitActive)" in suppress
    assert "SetReactState(REACT_PASSIVE)" not in suppress


def test_native_recovery_hold_is_latched_at_wipe_and_cleared_only_after_complete_evidence():
    runtime = RUNTIME_CONTRACTS[
        RUNTIME_CONTRACTS.index("struct RaidRuntime"):
        RUNTIME_CONTRACTS.index("struct CohortRuntime")
    ]
    assert "bool NativeRecoveryHoldActive" in runtime
    assert "uint64 NativeRecoveryRouteGeneration" in runtime
    assert "std::string NativeRecoveryNodeId" in runtime

    ensure = VALIDATION_COHORT_RUNTIME
    wipe = ensure.index("if (allDead)")
    latch = ensure.index("raid.NativeRecoveryHoldActive =", wipe)
    policy = ensure.rindex("bool const nativeRecoveryPolicy", wipe, latch)
    assert "ValidationRouteBossRecoveryPolicy::NativeFullWipeOnly" in ensure[policy:latch]
    evidence = ensure.index("raid.NativeRecoveryEvidenceComplete =", latch)
    clear = ensure.index("if (raid.NativeRecoveryEvidenceComplete)", evidence)
    assert latch < evidence < clear

    pending = VALIDATION_RECOVERY_GATE[
        VALIDATION_RECOVERY_GATE.index("bool BotWorldPopulationMgr::IsNativeRaidRecoveryEvidencePending"):
        VALIDATION_RECOVERY_GATE.index("void BotWorldPopulationMgr::SuppressNativeRaidRecovery")
    ]
    assert "!raid.NativeRecoveryHoldActive" in pending
    assert "raid.NativeRecoveryRouteGeneration != Party().ValidationRouteGeneration" in pending
    assert "raid.NativeRecoveryNodeId != Cohort().Config.ValidationRouteNodeId" in pending
    assert "exactWipeRoster" not in pending
    assert "return !raid.NativeRecoveryEvidenceComplete;" in pending

    update = UPDATE_PREPARATION
    hold = update.index("if (context.Bot->IsAlive() && IsNativeRaidRecoveryEvidencePending())")
    assert hold < update.index("TryRespondNativeRaidReadyCheck(context.State, context.Bot);", hold)

    runtime_json = (BOT_DIR / "BotWorldPopulationMgrRaidRuntime.cpp").read_text(encoding="utf-8")
    assert runtime_json.count("native_recovery_hold_active") >= 2
    assert runtime_json.count("native_recovery_route_generation") >= 2
    assert runtime_json.count("native_recovery_node_id") >= 2


def test_drudge_full_wipe_resets_every_attempt_scoped_seed_and_charge_gate():
    ensure = IMPL[
        IMPL.index("void BotWorldPopulationMgr::EnsureValidationCohortGroup"):
        IMPL.index("bool BotWorldPopulationMgr::ResolveSpawnPlacement")
    ]
    wipe = ensure.index("if (allDead)")
    drudge = ensure.index(
        'if (Cohort().Config.ValidationRouteMechanicProfile == "trash_two_tank_charge_lanes")',
        wipe,
    )
    latch = ensure.index("raid.NativeRecoveryHoldActive =", drudge)
    reset = ensure[drudge:latch]
    assert ensure.index("++raid.WipeGeneration;", wipe) < drudge
    for token in (
        "ValidationRouteDrudgeChargeObservations.clear()",
        "ValidationRouteDrudgeChargePreparedCount = 0",
        "ValidationRouteDrudgeChargeDeliveredCount = 0",
        "ValidationRouteDrudgeOwnershipRosterGuids.clear()",
        "ValidationRouteDrudgeReseparatedRosterGuids.clear()",
        "ValidationRouteDrudgePrepullStaged = false",
        "ValidationRouteDrudgeProfileActionRosterGuids.clear()",
        "ValidationRouteDrudgeThreatSeedWipeGeneration = raid.WipeGeneration",
        "ValidationRouteDrudgeThreatSeedClosed = false",
        "ValidationRouteDrudgeThreatSeedComplete = false",
        "ValidationRouteDrudgeThreatSeedFailure = false",
        "ValidationRouteDrudgeThreatSeedEvidenceRows.clear()",
        "botState.ValidationRouteDrudgeAnchorValid = false",
    ):
        assert token in reset


def test_native_recovery_hold_cannot_leak_from_drudge_trash_into_magmaw():
    apply_node = IMPL[
        IMPL.index("bool BotWorldPopulationMgr::ApplyValidationRouteManifestNode"):
        IMPL.index("void BotWorldPopulationMgr::ResetTraceStreams")
    ]
    policy = apply_node.index("Cohort().Config.ValidationRouteBossRecovery = node.BossRecoveryPolicy;")
    clear = apply_node.index("raid.NativeRecoveryHoldActive = false;", policy)
    reset = apply_node.index("ResetValidationRouteRuntimeState", clear)
    assert policy < clear < reset
    assert (
        "node.BossRecoveryPolicy != ValidationRouteBossRecoveryPolicy::NativeFullWipeOnly"
        in apply_node[policy:clear]
    )
    assert "Cohort().Raid.NativeRecoveryRouteGeneration != Party().ValidationRouteGeneration" in apply_node[policy:clear]
    assert "Cohort().Raid.NativeRecoveryNodeId != node.NodeId" in apply_node[policy:clear]
    for token in (
        "raid.NativeRecoveryRouteGeneration = 0;",
        "raid.NativeRecoveryNodeId.clear();",
        "raid.NativeRecoveryEvidenceComplete = false;",
        "raid.NativeSignalsByGuid.clear();",
        "raid.NativeReadyCheckActionObserved = false;",
        "raid.NativeReadyCheckPending = false;",
        "raid.NativeReadyCheckResponders.clear();",
        'raid.WipeState = "ready";',
        'raid.RecoveryState = "none";',
    ):
        assert token in apply_node[clear:reset]

    pending = IMPL[
        IMPL.index("bool BotWorldPopulationMgr::IsNativeRaidRecoveryEvidencePending"):
        IMPL.index("void BotWorldPopulationMgr::SuppressNativeRaidRecovery")
    ]
    # Stale monotonic wipe/signal fields are never a fallback authority on a
    # newly installed native-recovery node.
    assert "exactWipeRoster" not in pending
    assert "raid.WipeState == \"wiped\"" not in pending

    update = IMPL[
        IMPL.index("void BotWorldPopulationMgr::UpdateBot"):
        IMPL.index("Player* BotWorldPopulationMgr::GetLoadedBot")
    ]
    latched = update.index("bool const nativeFullWipeLatched")
    release = update.index("native_full_wipe_latched_release_allowed", latched)
    assert "raid.NativeRecoveryHoldActive" in update[latched:release]
    assert "raid.NativeRecoveryRouteGeneration == Party().ValidationRouteGeneration" in update[latched:release]
    assert "raid.NativeRecoveryNodeId == Cohort().Config.ValidationRouteNodeId" in update[latched:release]


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

    movement = VALIDATION_HAZARDS
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

    geometry = (
        BOT_DIR / "Content/Raids/BlackwingDescent/Trash/Drudge/"
        "BotWorldPopulationMgrValidationRouteDrudgeGeometry.cpp"
    ).read_text(encoding="utf-8")
    assert "CachedAnchorSafe = [this]" in geometry
    assert "GroupPositionSafe = [this]" in geometry
    assert "AnchorCacheMatchesGeneration = [this]" in geometry
    assert "for (auto const& candidate : candidates)" not in geometry
    assert "ValidationRouteDrudgeAnchorCandidateIndex >= candidates.size()" in geometry
    assert "SelectPathableDrudgeAnchor = [this]" in geometry


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
    route_runtime = VALIDATION_FOCUS
    authority = route_runtime.index("routeHasCurrentGenerationLivePackAuthority")
    anchor_logic = route_runtime[authority:]

    assert "persistedPackHasLiveMembers()" in anchor_logic
    assert 'state.ValidationRouteAnchorOverrideReason\n            == "validation_route_safe_memory_after_death_loop"' in anchor_logic
    clear = anchor_logic.index("state.ValidationRouteAnchorOverrideValid = false;")
    assert anchor_logic.index("routeHasCurrentGenerationLivePackAuthority") < clear
    install = anchor_logic.rindex("routeHasCurrentGenerationLivePackAuthority)")
    assert "&& !routeHasCurrentGenerationLivePackAuthority" in anchor_logic[install - 120:install + 80]
    assert "validation_route_partial_wipe_retreat_rendezvous" in anchor_logic
    assert "validation_route_live_pack_reapproach" in VALIDATION_TERMINAL_ARRIVAL

    helper = VALIDATION_LIVE_PACK
    pack = VALIDATION_ROUTE_PACK
    assert "ValidationRoutePackGeneration != Party().ValidationRouteGeneration" in pack
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
    helper = VALIDATION_LIVE_PACK
    recovery = GROUP_RECOVERY
    focus = VALIDATION_FOCUS

    for token in (
        'Cohort().Config.ValidationRouteKind == "boss"',
        "Cohort().Raid.RosterComplete",
        "Cohort().Raid.UniqueLeases",
        "Cohort().Raid.RosterCompositionValid",
        "Cohort().Raid.RosterByGuid.size() != Party().Bots.size()",
        "persistedValidationRoutePackHasLiveMembers",
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
        assert token in helper
    assert "activeValidationRoutePackTarget" not in helper
    assert "bot->GetMap()" not in helper
    assert "GetDungeonRole" not in helper
    recovery_guard = recovery.index("bool currentLivePackCanContinue")
    retreat_gate = recovery.index("&& !currentLivePackCanContinue", recovery_guard)
    assert recovery_guard < retreat_gate
    assert "validation_route_partial_wipe_retreat_rendezvous" in recovery
    assert "validation_route_live_pack_reapproach" in VALIDATION_TERMINAL_ARRIVAL


def test_boss_route_rejects_undeclared_engaged_trash_before_shared_actions():
    route_runtime = VALIDATION_ROUTE_RUNTIME
    threat = (BOT_DIR / "BotWorldPopulationMgrValidationRouteTrashThreatControl.cpp").read_text(
        encoding="utf-8"
    )
    early_rejection = threat.index(
        'if (Cohort().Config.ValidationRouteKind == "boss"\n'
        "        && trashThreatControl.EngagedCount > 0"
    )

    assert early_rejection < threat.index("trashThreatControl.InsecureTrashSwarm")
    assert early_rejection < threat.index("hunterTrashMisdirectionActive")
    rejection = threat[early_rejection:]
    assert 'rejected, "boss_route_target_not_declared"' in rejection
    assert 'action = "boss_route_prerequisite_blocked";' in rejection
    assert "bool ObjectiveContext::RunTrashThreatControl(" in threat
    target_engagement = (BOT_DIR / "BotWorldPopulationMgrValidationRouteTargetEngagement.cpp").read_text(
        encoding="utf-8"
    )
    assert '"boss_route_undeclared_prerequisite_blocked"' in target_engagement
    assert 'action = "boss_route_prerequisite_blocked";' in target_engagement


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
    population = POPULATION
    group = VALIDATION_COHORT_GROUP
    update = UPDATE_PREPARATION
    original_instance = VALIDATION_COHORT_LIFECYCLE

    assert 'Cohort().Config.ValidationRouteEnable || placement.Source != "saved_position"' not in population
    assert 'sBotMgr->ProvisionWorldBot("any", std::to_string(candidateGuid),' in population
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
    assert 'context.State.LastDecisionResult = "validation_cohort_formation_pending";' in update
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
def test_validation_raid_preflights_exact_saved_roster_before_first_claim_or_spawn():
    admission = VALIDATION_ADMISSION
    admission_runtime = admission
    manifest = VALIDATION_MANIFEST
    preflight = admission.index("// Read and validate every GUID")
    first_claim = admission.index("ClaimBotGuid(planned.Guid, planned.RosterSlotId)")
    first_spawn = admission.index(
        'sBotMgr->ProvisionWorldBot("any", std::to_string(planned.Guid)'
    )
    plan_complete = admission.index(
        "if (validationRaidSpawnPlan.size() != rosterPlan.size()",
        preflight,
    )

    assert preflight < plan_complete < first_claim < first_spawn
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
        "placement.MapId = routeStart.BotStartMapId",
        "placement.X = routeStart.BotStartX",
        'placement.Source = "server_route_manifest_entrance"',
    ):
        assert token in admission
    before_claim = admission[preflight:first_claim]
    assert "ClaimBotGuid(" not in before_claim
    assert "ProvisionWorldBot" not in before_claim
    assert "ProvisionWorldBotInGroup" not in before_claim
    assert "ResolveSpawnPlacement(candidateGuid, placement)" not in before_claim
    transaction = admission[plan_complete:]
    assert "validationRaidSpawnPlan" in transaction
    assert "ProvisionWorldBot(" in transaction
    assert "ProvisionWorldBotInGroup(" in transaction
    assert "!bot->IsAlive()" in transaction
    assert "bot->HasFlag(PLAYER_FLAGS, PLAYER_FLAGS_GHOST)" in transaction
    assert "bot->HasCorpse()" in transaction
    assert "state.ValidationCohortInstanceId != bot->GetInstanceId()" in transaction

    assert "bot->HasCorpse()" in admission_runtime
    assert "state.ValidationCohortInstanceId != bot->GetInstanceId()" in admission_runtime


def test_validation_raid_admission_rolls_back_late_failures_and_cannot_retry_unpinned():
    runtime = VALIDATION_ADMISSION
    terminal_check = runtime.index("if (Cohort().ValidationRaidAdmissionFailed)")
    pinned_selection = runtime.index(
        "SelectPoolCandidateGuid(slot.RosterSlotId, &plannedGuids,"
    )
    transaction_claim = runtime.index("ClaimBotGuid(planned.Guid, planned.RosterSlotId)")
    rollback = runtime.index("auto rollbackAdmission")
    assert terminal_check < pinned_selection < rollback < transaction_claim
    for token in (
        "Cohort().ValidationRaidAdmissionFailed",
        "Cohort().ValidationRaidAdmissionComplete",
        'rollbackAdmission("validation_raid_admission_claim_failed")',
        'rollbackAdmission("validation_raid_admission_spawn_failed")',
        'rollbackAdmission("validation_raid_admission_exact_group_or_alive_state_failed")',
        "sBotMgr->RemoveWorldBot(*itr);",
        "ReleaseBotGuid(guid);",
        "Party() = partyBeforeAdmission;",
        "Cohort().Raid = raidBeforeAdmission;",
        "Cohort().Metrics = metricsBeforeAdmission;",
        "Cohort().RosterLeases.clear();",
    ):
        assert token in runtime
    assert runtime.count("SelectPoolCandidateGuid(slot.RosterSlotId, &plannedGuids,") == 1
    assert "SelectPoolCandidateGuid(rosterSlotId)" not in runtime
    assert "ResolveSpawnPlacement(candidateGuid, placement)" not in runtime
    cohort = RUNTIME_CONTRACTS[
        RUNTIME_CONTRACTS.index("struct CohortRuntime"):
        RUNTIME_CONTRACTS.index("struct BotGuidLease")
    ]
    assert "bool ValidationRaidAdmissionComplete = false;" in cohort
    assert "bool ValidationRaidAdmissionFailed = false;" in cohort


def test_completed_validation_raid_drift_verifies_exact_identity_and_cleans_all_state():
    population = VALIDATION_ADMISSION
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
        "IsNativeValidationRunbackWorldport(*state, bot)",
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
    population = VALIDATION_ADMISSION
    complete = population[
        population.index("if (Cohort().ValidationRaidAdmissionComplete)"):
        population.index("auto terminalFailure")
    ]
    drift_start = complete.index("if (!exactIdentity)")
    refresh = complete.index("EnsureValidationCohortGroup();")
    drift_end = complete.index(
        "\n        else\n        {\n            // Admission identity is immutable",
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
    population = VALIDATION_ADMISSION
    selector = ROSTER[
        ROSTER.index("uint32 BotWorldPopulationMgr::SelectPoolCandidateGuid"):
        ROSTER.index("uint32 BotWorldPopulationMgr::SelectCalibrationPoolCandidateGuid")
    ]
    for token in (
        "routeStart.ExpectedRoster.size() != rosterPlan.size()",
        "expected->Role != slot.Role",
        "!expected->Guid || expected->Name.empty()",
        "expected->ClassSpec.empty()",
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
    route_runtime = _read_source_set(tuple(
        BOT_DIR / name
        for name in (
            "BotWorldPopulationMgrValidationRouteTankFocusAssist.cpp",
            "BotWorldPopulationMgrValidationRouteSharedFocusAction.cpp",
            "BotWorldPopulationMgrValidationRouteActiveCombat.cpp",
            "BotWorldPopulationMgrValidationRouteTargetEngagement.cpp",
        )
    ))
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
        IMPL.index("bool BotWorldPopulationMgr::ResolveNativeValidationEntrance")
    ]
    native_runback = IMPL[
        IMPL.index("bool BotWorldPopulationMgr::TryNativeCorpseRun"):
        IMPL.index("bool BotWorldPopulationMgr::AreNativeRaidRecoveryControlledUnitsReady")
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
    assert "ResolveNativeValidationEntrance" in native_release
    assert "sObjectMgr->GetClosestGraveyard(*bot, bot->GetTeam()" in native_release
    assert "ResolveNativeValidationEntrance" in native_release
    assert "destination.GetPositionX() - graveyard->Loc.X" in native_release
    assert "destination.GetPositionY() - graveyard->Loc.Y" in native_release
    assert "destination.GetPositionZ() - graveyard->Loc.Z" in native_release
    assert "GetGraveyardOrientation(graveyard->ID)" in native_release
    assert "!bot->GetTeleportDestInstanceId()" in native_release
    assert "bot->GetTeleportDestOptions() == TELE_TO_NONE" in native_release
    assert "worldport.GetMapId() == entranceDestination->target_mapId" in native_release
    assert "bot->GetTeleportDestOptions() == TELE_TO_NOT_LEAVE_TRANSPORT" in native_release

    assert "ResolveNativeValidationEntrance" in native_runback
    assert "BotNativeAction::Move" in native_runback
    assert "BotNativeAction::AreaTrigger" in native_runback
    assert "BotMovementArbitration::Owner::Recovery" in native_runback
    assert "native_entrance_unavailable" in native_runback
    assert "native_runback_no_progress" in native_runback
    assert "GetMotionMaster()->MovePoint" not in native_runback
    assert "TeleportTo(" not in native_runback
    assert "NearTeleportTo(" not in native_runback
    assert "ResurrectPlayer" not in native_runback


def test_validation_party_resurrection_fails_closed_to_exact_typed_target_identity():
    builder = COMBAT_RES[COMBAT_RES.index("BotWorldPopulationMgr::BuildCombatResNativeActionCandidate"):]
    predicate = COMBAT_RES[
        COMBAT_RES.index("bool BotWorldPopulationMgr::CurrentCombatResOwnerUsable"):
        COMBAT_RES.index("void BotWorldPopulationMgr::PublishNativeBattleResDecision")
    ]
    executor = NATIVE_ACTION[
        NATIVE_ACTION.index("BotActionArbitration::Outcome BotWorldPopulationMgr::ExecuteNativeActionIntent"):
    ]

    assert "TryNativePartyResurrection" not in COMBAT_RES + NATIVE_ACTION
    assert "CurrentCombatResOwnerUsable" in builder
    assert "IsNativeCombatResTarget(targetState, target)" in predicate
    assert "targetState.NativeBattleResOwnerGuid" in predicate
    assert "targetState.NativeBattleResSpellId" in predicate
    assert "targetState->NativeBattleResDecisionAtMs != reservationAtMs" in executor
    assert "targetState->NativeBattleResDecisionUntilMs != reservationUntilMs" in executor
    assert "BotNativeAction::CombatResApproach" in executor
    assert "BotNativeAction::CombatResCast" in executor
    assert "BotNativeAction::CombatResAccept" in executor
    assert "HandleResurrectResponseOpcode(response)" in executor

    authority = VALIDATION_COHORT_LIFECYCLE[
        VALIDATION_COHORT_LIFECYCLE.index("bool BotWorldPopulationMgr::HasNativeRaidCorpseAuthority"):
        VALIDATION_COHORT_LIFECYCLE.index("bool BotWorldPopulationMgr::ResolveNativeValidationEntrance")
    ]
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
        "target_entries": [41570, 42347, 41806, 42321],
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
    # The route facade now delegates the tank-focus branch to its own
    # translation unit. Inspect that owner directly so a module split cannot
    # make a valid branch disappear from this contract test.
    assist = VALIDATION_ROUTE_TANK_FOCUS

    contract_authority = assist.index("if (tankFocusIsBossRoute)")
    profile_action = assist.index("ResolvedCombatAction profileAction = ResolveProfileCombatAction(bot, target);")
    assert contract_authority < profile_action
    assert "BossMechanicActionResult mechanic = TryBossMechanics(state, bot, power, stage, activity, target);" in assist[contract_authority:profile_action]
    assert "if (mechanic.Handled)" in assist[contract_authority:profile_action]
    assert 'action = "raid_mechanic_contract_fail_closed";' in assist[contract_authority:profile_action]
    assert "return true;" in assist[contract_authority:profile_action]

    dispatch = BOSS_DISPATCH
    mechanics = BOSS_MECHANICS
    assert 'bool const routeDirectedBoss = Cohort().Config.ValidationRouteKind == "boss"' in dispatch
    assert "routeCreature->GetEntry() == Cohort().Config.ValidationRouteTargetEntry" in dispatch
    assert "Cohort().Config.ValidationRouteAlternateTargetEntries.end()" in dispatch
    assert "if (!IsBossContext(bot, result.Target) && !routeDirectedBoss)" in dispatch
    assert 'result.Action = "raid_mechanic_contract_fail_closed";' in mechanics
    assert "0, false, false, forbidArea, raidAdapter.AllowMultidot" in mechanics


def test_trash_profile_damage_cannot_pull_or_compound_the_next_boss_encounter():
    route_runtime = (BOT_DIR / "BotWorldPopulationMgr.cpp").read_text(encoding="utf-8")
    hold = route_runtime[
        route_runtime.index("Creature* prematureNextEncounter = nullptr;"):
        route_runtime.index("\n\n    ValidationRoutePackContext pack", route_runtime.index("Creature* prematureNextEncounter = nullptr;"))
    ]
    resolver = (BOT_DIR / "BotWorldPopulationMgrCombatResolver.cpp").read_text(encoding="utf-8")
    executor = (BOT_DIR / "BotWorldPopulationMgrCombatExecution.cpp").read_text(encoding="utf-8")
    authority = VALIDATION_AUTHORITY
    future_guard = VALIDATION_TARGETING

    assert "IsImmediateNextValidationRouteBossTarget" in future_guard
    assert "IsImmediateNextValidationRouteEncounterMember" in future_guard
    assert "SpellHostileMultiTargetReach" not in route_runtime
    assert "SetProtectedEncounterEntries" in authority
    # Future-encounter splash protection is geometry-aware: the route may keep
    # a protected-entry set while current trash is far outside splash range.
    assert "HasNearbyProtectedEncounterTarget(bot, target)" in resolver
    assert "HasProtectedEncounterEntries(bot->GetGUID().GetRawValue())" not in resolver
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
    assert "SubmitMeleeAutoAttackIntent(state," in hold
    assert "BotMeleeAutoAttack::Kind::Suppress" in hold
    assert '"future_encounter_contamination"' in hold
    assert "bot->AttackStop();" not in hold
    assert "pet->AttackStop();" in hold
    assert "controlled->AttackStop();" in hold
    assert "SetAllOffenseSuppressed(raidAuthorityOwner, true)" in hold
    assert "controlledCreature->SetReactState(REACT_PASSIVE);" not in hold
    assert "charmInfo->SetIsCommandAttack(false);" not in hold
    assert "ValidationAttemptFailureReason" in hold
    assert '"validation_route_future_encounter_contamination"' in hold

    future_guard = future_guard[
        future_guard.index("auto wouldPullProtectedFutureValidationRouteSource"):
        future_guard.index("auto isValidationRouteEntry")
    ]
    assert "std::max(35.0f" in future_guard
    assert "ValidationRouteClusterRadiusYards" in future_guard
    assert VALIDATION_TARGETING.count(
        "!Party().ValidationRoutePackObservedEngagement\n"
        "            && wouldPullProtectedFutureValidationRouteSource(creature)"
    ) >= 2

    # Every offensive submission surface shares the same fail-closed policy.
    # This includes the exact manual Hunter Multi-Shot executor path and direct
    # Protection spell helpers, not only profile-resolved actions.
    assert "IsAllOffenseSuppressed(ownerGuid)" in ACTION_EXECUTOR
    assert "IsProtectedEncounterTarget(" in ACTION_EXECUTOR
    assert "HasNearbyProtectedEncounterTarget(bot, target)" in ACTION_EXECUTOR
    assert "BotRaidAreaAuthority::HasProtectedEncounterEntries" in resolver
    assert "BotRaidAreaAuthority::IsProtectedEncounterTarget(" in resolver
    assert "AllOffenseSuppressedOwners" in RAID_AUTHORITY
    assert "ProtectedEncounterEntriesByOwner" in RAID_AUTHORITY
    assert "ProtectedEncounterSpawnIdsByOwner" in RAID_AUTHORITY
    assert "AllowedEncounterGuidsByOwner" in RAID_AUTHORITY
    assert "SetProtectedEncounterSpawnIds" in authority
    assert "SetAllowedEncounterGuids" in authority
    assert "nextNode.SplitSourceGuids" in authority
    assert "nextNode.PackTargetEntries" in authority
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
    # UnitAI.cpp and TotemAI.cpp share one CMake unity translation unit, so
    # their anonymous-namespace helpers must not have colliding names.
    assert "bool TotemSpellHasHostileMultiTargetSemantics" in TOTEM_AI
    assert "bool TotemSpellHasHostileMultiTargetSemantics" not in UNIT_AI
    assert "RaidTotemSpellSuppressed(this, GetSpell())" in TOTEM
    assert "UnSummon();" in TOTEM


def test_boss_nodes_fail_closed_on_undeclared_prerequisite_hostiles():
    tank_focus = VALIDATION_ROUTE_TANK_FOCUS
    target_engagement = VALIDATION_ROUTE_TARGET_ENGAGEMENT

    assert 'if (!tankFocusIsRouteTarget)' in tank_focus
    assert '"boss_route_target_not_declared"' in tank_focus
    assert 'action = "boss_route_prerequisite_blocked";' in tank_focus
    assert '&& !isValidationRouteObjectiveTarget(seenRouteTarget->ToCreature())' in target_engagement
    assert '"boss_route_undeclared_prerequisite_blocked"' in target_engagement
    scan_start = target_engagement.index("Creature* prerequisiteTarget = nullptr;")
    boss_hold = target_engagement.rindex(
        'if (Cohort().Config.ValidationRouteKind == "boss")', 0, scan_start
    )
    assert boss_hold < scan_start


def test_raid_trash_uses_native_threat_headroom_and_declared_minimum_distance():
    route_runtime = (BOT_DIR / "BotWorldPopulationMgr.cpp").read_text(encoding="utf-8")
    minimum = (
        BOT_DIR
        / "Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeGeometry.cpp"
    ).read_text(encoding="utf-8")
    recovery = (
        BOT_DIR
        / "Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeRecovery.cpp"
    ).read_text(encoding="utf-8")
    lane_selection = (
        BOT_DIR
        / "Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeLaneSelection.cpp"
    ).read_text(encoding="utf-8")
    drudge_actions = (
        BOT_DIR
        / "Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeActions.cpp"
    ).read_text(encoding="utf-8")
    assert "ValidationRouteMinimumDistanceSourceEntry" in minimum
    assert "ValidationRouteMinimumDistanceYards" in minimum
    assert 'profile.MovementDirective == "ranged"' in minimum
    assert 'profile.MovementDirective == "healer_support"' in minimum
    assert 'creature->GetEntry() != sourceEntry' in minimum
    assert 'safeDistance = minimumDistance + 2.0f' in minimum
    assert "sources.push_back(creature)" in minimum
    assert "for (size_t left = 0; left < sources.size(); ++left)" in minimum
    assert "addDirection(-pairY, pairX);" in minimum
    assert "PathGenerator path(Bot);" in minimum
    assert "for (G3D::Vector3 const& point : path.GetPath())" in minimum
    assert "std::min(startDistance, minimumDistance) - 0.25f" in minimum
    assert "< safeDistance" in minimum
    assert '"minimum_distance_exit_started"' in minimum
    assert "SelectMinimumDistanceOwner" in minimum
    assert "MinimumDistanceOwner::LandedRushRecovery" in minimum
    assert "specializedDrudgeRecovery" in minimum
    assert "if (TryMinimumDistance(true))" not in lane_selection
    landed_owner = recovery[
        recovery.index("bool DrudgeLaneContext::IsLandedRushPending() const"):
        recovery.index("bool DrudgeLaneContext::IsDynamicGroupRecoveryActive() const")
    ]
    assert "auto observation = std::find_if(" in landed_owner
    assert "&& observation->Landed" in landed_owner
    assert "std::any_of(" not in landed_owner
    assert minimum.index("drudge_anchor_source_unsafe") < minimum.index(
        "if (!pathSearch.NativePathSearchDue)"
    )
    source_reject = minimum.index('"drudge_anchor_source_unsafe"')
    spacing_reject = minimum.index('"drudge_anchor_spacing_unsafe"')
    path_transition = minimum.index("SelectAnchorPathSearch(")
    assert path_transition < source_reject < spacing_reject
    assert "pathSearch.RetryAfterMs" in minimum[path_transition:source_reject]
    assert lane_selection.index("ContractResolved =") < lane_selection.index(
        "if (!ContractResolved"
    )
    assert "State.LastRecoveryResult.clear();" in minimum
    assert route_runtime.index("if (TryValidationRouteMovementCheck(state, bot, power, stage,") < route_runtime.index(
        "if (TryValidationRouteDrudgeMinimumDistance(state, bot, power, stage,"
    )

    assert "input.TankThreat = source->GetThreatManager().GetThreat(tank, true);" in drudge_actions
    assert "input.HighestOtherThreat = std::max(input.HighestOtherThreat," in drudge_actions
    assert "input.ThreatHeadroomMultiplier" in drudge_actions
    assert "TankThreatSecure" in DRUDGE_NATIVE_RUSH
    assert "input.ThreatHeadroomMultiplier >= 1.3f" in DRUDGE_NATIVE_RUSH
    assert "input.TankThreat >= input.HighestOtherThreat" in DRUDGE_NATIVE_RUSH
    assert "ShouldBuildTankThreat" in drudge_actions
    assert "AuthorityReady" in drudge_actions
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
    shared_focus = VALIDATION_ROUTE_SHARED_FOCUS

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

    boss_dispatch = BOSS_DISPATCH
    boss_runtime = BOSS_MECHANICS
    boss_runtime = boss_dispatch + "\n" + boss_runtime
    assert "result.Target = boundRouteTarget ? boundRouteTarget : FindBossTarget(bot);" in boss_runtime
    assert "if (!result.Target && !boundRouteTarget && !state.TargetGuid.IsEmpty())" in boss_runtime
    assert "if (boundRouteTarget && !routeDirectedBoss)" in boss_runtime
    assert 'result.Action = "raid_target_not_declared_hold";' in boss_runtime
    assert "forbidArea, raidAdapter.AllowMultidot" in boss_runtime
    assert 'RecordRaidTelemetry(state, bot, focus, "raid_focus_fire", "declared_target_selected"' in boss_runtime

    unbound_search = BOSS_TARGETING
    assert "usableBoss(bot->GetVictim())" in unbound_search
    assert "usableBoss(member->GetVictim())" in unbound_search
    assert "Cell::VisitAllObjects(bot, searcher, 60.0f);" in unbound_search


def test_every_route_boss_dispatch_binds_declared_target_and_never_uses_generic_boss_search():
    route_runtime = VALIDATION_ROUTE_DISPATCH
    bound_call = "TryBossMechanics(state, bot, power, stage, activity, target)"
    unbound_call = "TryBossMechanics(state, bot, power, stage, activity)"

    # Tank focus, shared focus, current combat, and newly resolved route target
    # are the complete route-boss dispatch surface. Every one binds the exact
    # target that the route-specific declaration check already accepted.
    assert route_runtime.count(bound_call) == 4
    assert unbound_call not in route_runtime

    tank_focus = VALIDATION_ROUTE_TANK_FOCUS
    shared_focus = VALIDATION_ROUTE_SHARED_FOCUS
    current_combat = VALIDATION_ROUTE_ACTIVE_COMBAT
    resolved_target = VALIDATION_ROUTE_TARGET_ENGAGEMENT
    for dispatch in (tank_focus, shared_focus, current_combat, resolved_target):
        assert bound_call in dispatch
        assert 'action = "raid_mechanic_contract_fail_closed";' in dispatch
        assert dispatch.index(bound_call) < dispatch.index('action = "raid_mechanic_contract_fail_closed";')

    assert 'if (!routeTarget && Cohort().Config.ValidationRouteKind == "boss")\n        routeTarget = FindBossTarget(bot);' not in route_runtime
    assert '&& !isValidationRouteObjectiveTarget(routeTarget->ToCreature()))' in route_runtime
    assert 'action = "raid_target_not_declared_hold";' in route_runtime

    boss_runtime = BOSS_DISPATCH
    assert "result.Target = boundRouteTarget ? boundRouteTarget : FindBossTarget(bot);" in boss_runtime
    assert "if (boundRouteTarget && !routeDirectedBoss)" in boss_runtime


def test_phase1_target_transfer_and_swap_controls_are_executable():
    for token in (
        'raidAdapter.TargetControl == "focus_fire"',
        '"declared_target_selected"',
        "BuildCombatResNativeActionCandidate",
        "BotNativeAction::CombatResCast",
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
        IMPL.index("void BotWorldPopulationMgr::ReconcileNativeBattleResDecisions"):
        IMPL.index("BotWorldPopulationMgr::BuildCombatResNativeActionCandidate")
    ]
    assert 'std::string(role) == "healer"' not in raid_brez
    for token in (
        'uint32 score = role == "tank" ? 300 : role == "healer" ? 250 : 100;',
        "if (bossCommitment)",
        "if (living.size() <= 2)",
        "std::max_element(eligibleDead.begin(), eligibleDead.end()",
        'applyDecision(member, "declined_lower_priority")',
    ):
        assert token in raid_brez
    for token in (
        "uniqueBattleResSlots.size() == node.BattleResurrectionSlots.size()",
        "slot > 0 && slot <= Cohort().Config.RaidSize",
    ):
        assert token in IMPL


def test_controlled_aoe_counts_only_declared_targets_and_fails_closed_near_undeclared_hostiles():
    controlled_aoe = "\n".join((BOSS_MECHANICS, BOSS_DISPATCH, COMBAT_RESOLUTION))
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
        "ReconcileRaidAreaAutocasts(bot, !controlledAoeReleased);",
        "ReconcileRaidAreaAutocasts(bot, false);",
        'raidAdapter.TargetControl == "controlled_aoe" && !controlledAoeReleased',
        "bot->InterruptSpell(CURRENT_CHANNELED_SPELL, false);",
    ):
        assert token in controlled_aoe


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
        "auto stopWrongControlledFocusTarget = [focus, &interruptWrongFocusCasts](Unit* attacker)",
        "auto stopWrongPlayerFocusTarget = [&]()",
        "attacker->InterruptSpell(CURRENT_GENERIC_SPELL, false);",
        "attacker->InterruptSpell(CURRENT_AUTOREPEAT_SPELL, false);",
        "attacker->InterruptSpell(CURRENT_CHANNELED_SPELL, false);",
        "SubmitMeleeAutoAttackIntent(state,",
        '"raid_focus_target_transition"',
        "stopWrongPlayerFocusTarget();",
        "stopWrongControlledFocusTarget(pet);",
        "stopWrongControlledFocusTarget(controlled);",
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
        "uint32 const expectedTanks = uint32(std::count_if(rosterPlan.begin(), rosterPlan.end()",
        "uint32 const expectedHealers = uint32(std::count_if(rosterPlan.begin(), rosterPlan.end()",
        "uint32 const expectedDps = uint32(std::count_if(rosterPlan.begin(), rosterPlan.end()",
        "tankCount == expectedTanks && healerCount == expectedHealers && dpsCount == expectedDps",
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

    lifecycle = VALIDATION_COHORT_LIFECYCLE
    visitor_start = lifecycle.index("struct NativeRaidHostileActivityVisitor")
    visitor_end = lifecycle.index("\n};", visitor_start) + len("\n};")
    observer_visitor = lifecycle[visitor_start:visitor_end]
    observer = lifecycle
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
    assert "GetCurrentSpell(CURRENT_GENERIC_SPELL)" not in observer_visitor
    assert "GetCurrentSpell(CURRENT_CHANNELED_SPELL)" not in observer_visitor

    ensure = VALIDATION_COHORT_RUNTIME
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
    runtime_json = (BOT_DIR / "BotWorldPopulationMgrRaidRuntime.cpp").read_text(encoding="utf-8")
    for token in (
        "native_hostile_observation_attempt_id",
        "native_hostile_observation_route_generation",
        "native_hostile_observation_node_id",
    ):
        assert token in runtime_json

    update = UPDATE_DEATH
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
                         update.index("// A critical-role death can make the survivors retreat", gate)]
    assert "TeleportTo(" not in gate_block
    assert "ResurrectPlayer" not in gate_block

    ready = RECOVERY
    assert "postWipeNativeResetReady" in ready
    assert "!raid.NativeHostileActivityActive" in ready

    cohort = (BOT_DIR / "BotWorldPopulationMgrCohort.cpp").read_text(encoding="utf-8")
    request = cohort[
        cohort.index("std::string BotWorldPopulationMgr::RequestNativeRaidReadyCheckForCohort"):
        cohort.index("std::string BotWorldPopulationMgr::GetBotDiagnosisJsonForCohort", cohort.index("std::string BotWorldPopulationMgr::RequestNativeRaidReadyCheckForCohort"))
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
    drudges = next(row for row in bwd["route"] if row["label"] == "Magmaw Drudge pair")
    assert magmaw["boss_recovery_policy"] == "native_full_wipe_only"
    assert drudges["boss_recovery_policy"] == "native_full_wipe_only"
    assert [row["roster_slot"] for row in drudges["split_member_anchors"]] == list(range(1, 11))

    diagnostic = next(
        row for row in config["diagnostic_scenarios"]
        if row["id"] == "blackwing_descent_10n_magmaw_diagnostic"
    )
    diagnostic_drudges = next(
        row for row in diagnostic["route"] if row["label"] == "Magmaw Drudge pair"
    )
    assert diagnostic_drudges["boss_recovery_policy"] == "native_full_wipe_only"
    assert diagnostic_drudges["split_member_anchors"] == drudges["split_member_anchors"]
    assert diagnostic_drudges["split_healer_roster_slots"] == [3, 4, 5]
    assert diagnostic_drudges["split_tank_navigation_anchors"] \
        == drudges["split_tank_navigation_anchors"]

    generator = (ROOT / "tools/bot_ml/build_validation_scenario_manifests.py").read_text()
    assert '"boss_recovery_policy": str(step.get("boss_recovery_policy") or "")' in generator
    assert "ValidationRouteBossRecoveryPolicy" in HEADER
    assert "NativeFullWipeOnly" in HEADER
    assert "ValidationRouteBossRecovery = node.BossRecoveryPolicy" in IMPL


def test_phase1_partial_critical_death_holds_native_fight_without_tactical_retreat():
    objective = GROUP_RECOVERY
    retreat = objective.index("bool majorityDead = aliveMembers <= 2 && deadMembers >= 3;")
    hold = objective.index('"native_full_wipe_hold_partial_death"', retreat)
    retreat_action = objective.index('if (!retreatThreat)', hold)
    assert hold < retreat_action
    assert 'Action = "native_full_wipe_hold";' in objective[hold:retreat_action]
    assert 'State.LastRecoveryMode = "native_full_wipe_only";' in objective[hold:retreat_action]
    assert 'cohortState.ValidationRouteAnchorOverrideReason = "validation_route_partial_wipe_retreat_rendezvous"' not in objective[hold:retreat_action]


def test_drudge_partial_death_keeps_live_pack_outcome_path_running():
    assert "Partial deaths do not make a trash pull terminal" in GROUP_RECOVERY
    assert "drudge_partial_death_before_threat_seed" not in GROUP_RECOVERY
    assert "drudge_native_full_wipe_hold_partial_death" not in GROUP_RECOVERY
    generic_recovery = GROUP_RECOVERY.index(
        "if ((majorityDead || criticalRoleDead) && groupCombatActive"
    )
    assert "&& !currentLivePackCanContinue" in GROUP_RECOVERY[
        generic_recovery:generic_recovery + 220
    ]


def test_terminal_failure_hold_remains_without_drudge_partial_death_latch():
    alive_terminal = UPDATE_PREPARATION.index(
        "if (!Cohort().ValidationAttemptFailureReason.empty()"
    )
    dead_member = UPDATE_PREPARATION.index("if (!context.Bot->IsAlive())")
    assert alive_terminal < dead_member
    assert "HoldValidationAttemptFailure(context.State, context.Bot);" in UPDATE_PREPARATION[
        alive_terminal:dead_member
    ]
    assert 'state.LastDecisionAction = "validation_route_terminal_hold";' in UPDATE_PREPARATION
    assert "CombatStop" not in UPDATE_PREPARATION[alive_terminal:dead_member]
    death_record = UPDATE_DEATH.index("if (!state.DeathEpisodeRecorded)")
    dead_terminal = UPDATE_DEATH.index(
        "if (!Cohort().ValidationAttemptFailureReason.empty()", death_record
    )
    native_dead_recovery = UPDATE_DEATH.index(
        "bool const nativeDeathDecisionWindowComplete", dead_terminal
    )
    assert death_record < dead_terminal < native_dead_recovery
    assert "HoldValidationAttemptFailure(state, bot);" in UPDATE_DEATH[
        dead_terminal:native_dead_recovery
    ]

    assert "drudge_partial_death_before_threat_seed" not in GROUP_RECOVERY
    assert '<< ",\\\"failure_reason\\\":"' in STATUS
    assert "Cohort().ValidationAttemptFailureAttemptId == Cohort().AttemptId" in UPDATE_PREPARATION


def test_repeated_owned_destination_skips_floor_and_native_path_recalculation():
    lease = MOVEMENT_LEASE
    executor = MOVEMENT_EXECUTOR
    planner = MOVEMENT_PLANNER
    assert "active.ScopeMatches && active.MatchingDestination" in executor
    assert "state.ActivePathValid" in executor
    assert "NativePointPathActive" in executor
    assert "NativeTargetChaseActive" in executor
    for token in (
        "ActivePathAttemptId == request.MovementScope.AttemptId",
        "ActivePathWipeGeneration",
        "ActivePathRouteGeneration",
        "ActivePathRouteNodeId\n                == Cohort().Config.ValidationRouteNodeId",
        "MatchingDestination",
    ):
        assert token in lease
    assert planner.index("GetHeight(") < planner.index("PathGenerator path(bot)")


def test_telemetry_rate_limit_precedes_frame_construction():
    telemetry = (ROOT / "src/server/game/Bots/BotTelemetryBuffer.cpp").read_text()
    observe = telemetry[
        telemetry.index("bool BotTelemetryBuffer::Observe"):
        telemetry.index("uint64 BotTelemetryBuffer::CaptureEvent")
    ]
    assert observe.index("BotTelemetryNowMs()") < observe.index("BuildFrame(")
    assert observe.index("FrameIntervalMs") < observe.index("BuildFrame(")


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
    # No certifying route may use a class self-res shortcut. The native CR
    # reservation/decline contract precedes this branch; only non-certifying
    # free-roam autonomy retains ordinary class self-res behavior.
    assert "if (!Cohort().Config.ValidationRouteEnable" in update[
        self_res - 220:self_res
    ]

    builder = IMPL[
        IMPL.index("BotWorldPopulationMgr::BuildCombatResNativeActionCandidate"):
        IMPL.index("void BotWorldPopulationMgr::ApplyRuntimeConfigOverride")
    ]
    assert "ValidationRouteBossRecoveryPolicy::NativeFullWipeOnly" in builder
    assert "return std::nullopt;" in builder
    assert "TryNativePartyResurrection" not in IMPL


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
    targeting = VALIDATION_TARGETING
    lambda_start = targeting.index("auto tryCanonicalValidationRouteBossRecovery")
    lambda_end = targeting.index("auto isNaturalForwardHostile", lambda_start)
    recovery = targeting[lambda_start:lambda_end]
    assert 'recoveryResult = "native_boss_recovery_pending"' in recovery
    assert '"assistance\\":\\"none\\"' in recovery
    assert '"direct_respawn\\":false' in recovery
    assert '"direct_state_manufacture\\":false' in recovery
    assert "SetBossState" not in recovery
    assert "Respawn(" not in recovery
    assert "LoadFromDB" not in recovery
    assert "SpawnGroupSpawn" not in recovery


def test_nonraid_canonical_recovery_is_native_only_too():
    targeting = VALIDATION_TARGETING
    lambda_start = targeting.index("auto tryCanonicalValidationRouteBossRecovery")
    lambda_end = targeting.index("auto isNaturalForwardHostile", lambda_start)
    recovery = targeting[lambda_start:lambda_end]
    assert "regardless of map type" in recovery
    assert "Respawn(" not in recovery
    assert "LoadFromDB" not in recovery
    assert "SpawnGroupSpawn" not in recovery
