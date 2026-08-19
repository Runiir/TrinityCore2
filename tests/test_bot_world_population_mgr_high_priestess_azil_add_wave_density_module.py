from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"
MODULE_HEADER = ROOT / (
    "src/server/game/Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/"
    "HighPriestessAzilAddWaveDensity.h"
)
MODULE = MODULE_HEADER.with_suffix(".cpp")
HEALER_HEADER = MODULE_HEADER.with_name(
    "HighPriestessAzilHealerAddWavePreposition.h"
)
OPENING_MODULE = MODULE_HEADER.with_name(
    "HighPriestessAzilAddWaveOpeningActions.cpp"
)


def test_azil_add_wave_density_is_registered_and_bounded():
    source = SOURCE.read_text(encoding="utf-8")
    header = HEADER.read_text(encoding="utf-8")
    module_header = MODULE_HEADER.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")
    healer_header = HEALER_HEADER.read_text(encoding="utf-8")
    cmake = CMAKE.read_text(encoding="utf-8")

    assert len(header.splitlines()) <= 990
    assert len(module_header.splitlines()) <= 1000
    assert len(module.splitlines()) <= 1000
    assert "HighPriestessAzilAddWaveDensity.cpp" in cmake
    assert "AddWaveDensityRequest" in module_header
    assert "AddWaveDensityResult" in module_header
    assert "ResolveAddWaveDensity" in module_header
    assert "static AddWaveDensityResult Run(AddWaveDensityRequest const& request);" in healer_header
    assert "HighPriestessAzilAddWaveDensity.h" in source


def test_azil_density_owns_prearrival_and_generation_state_before_pending_pickup():
    source = SOURCE.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")
    opening_module = OPENING_MODULE.read_text(encoding="utf-8")

    density_call = source.index("ResolveAddWaveDensity(")
    assert "pendingSwarmPickupNowMs" not in source
    assert density_call < source.index("TryAddWaveOpeningActions(")
    assert "pendingSwarmPickupNowMs" in opening_module
    for marker in (
        "sharedLargePassiveSwarmStaging",
        "CanonicalRouteDistance > request.RouteArrivalRadius",
        "ValidationRouteBossAddDensityGeneration",
        "ResetValidationRouteBossAddDensityState",
        "ValidationRouteBossProgressTargetGuid",
        "routeBossUnavailable",
        "HighDensityPhase",
        "SwarmDefenseActive",
        "BotInsideTankPickup",
    ):
        assert marker in module
    for marker in (
        "auto explicitListedAttackerCount =",
        "bool routeBossUnavailable =",
        "uint32 densityTankSecureAddCount = 0;",
        "bool densityTankOwnsSecureMajority = addCount > 0",
    ):
        assert marker not in source


def test_azil_density_selection_and_threat_gates_remain_deterministic():
    module = MODULE.read_text(encoding="utf-8")

    for marker in (
        "distance == nearestDistance && guid < nearestAnchorGuid",
        "distance == bestDistance && guid < bestAnchorGuid",
        "priority > loosePriority",
        "distance == looseDistance && guid < looseGuid",
        "rolePriority > densityDefenseRolePriority",
        "attackerCount == densityDefenseAttackerCount",
        "guid < densityDefenseGuid",
        "tankThreat >= 2000.0f",
        "highestPartyThreat * 2.5f",
        "densityTankSecureAddCount * 10 >= addCount * 9",
        "densityTankOwnedAddCount * 10 >= addCount * 8",
        "cohortSwarmActive && addCount >= 24",
        "std::max(member->getAttackers().size()",
    ):
        assert marker in module
