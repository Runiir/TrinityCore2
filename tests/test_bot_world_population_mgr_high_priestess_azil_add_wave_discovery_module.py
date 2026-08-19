from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"
MODULE_HEADER = ROOT / (
    "src/server/game/Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/"
    "HighPriestessAzilAddWaveDiscovery.h"
)
MODULE = MODULE_HEADER.with_suffix(".cpp")
HEALER_HEADER = MODULE_HEADER.with_name(
    "HighPriestessAzilHealerAddWavePreposition.h"
)


def test_azil_add_wave_discovery_is_registered_and_bounded():
    source = SOURCE.read_text(encoding="utf-8")
    module_header = MODULE_HEADER.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")
    healer_header = HEALER_HEADER.read_text(encoding="utf-8")
    cmake = CMAKE.read_text(encoding="utf-8")

    assert len(module_header.splitlines()) <= 1000
    assert len(module.splitlines()) <= 1000
    assert "HighPriestessAzilAddWaveDiscovery.cpp" in cmake
    assert "AddWaveDiscoveryRequest" in module_header
    assert "AddWaveDiscoveryResult" in module_header
    assert "DiscoverAddWave" in module_header
    assert "static AddWaveDiscoveryResult Run(AddWaveDiscoveryRequest const& request);" in healer_header
    assert "HighPriestessAzilAddWaveDiscovery.h" in source


def test_azil_add_discovery_owns_eligibility_and_stops_before_density_decisions():
    source = SOURCE.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")

    dispatch = source.index("DiscoverAddWave(")
    discovery_result = source.index("Unit* add = nullptr;", dispatch)
    passive_guard = source.index("bool sharedLargePassiveSwarmStaging", discovery_result)
    assert dispatch < discovery_result < passive_guard
    for marker in (
        "isUsableUnexpectedPartyHostile",
        "ValidationRouteAddFocusGeneration",
        "observed_dead",
        "unexpectedPartyHostiles.size() >= 3",
        "CohortSwarmActive",
        "Cell::VisitAllObjects",
    ):
        assert marker in module
    for marker in (
        "isUsableUnexpectedPartyHostile",
        "unexpectedPartyHostiles",
        "GuidSet cohortAddGuids",
        "Trinity::AllWorldObjectsInRange check(bot, 45.0f)",
    ):
        assert marker not in source


def test_azil_add_selection_tie_breaks_and_observation_gates_are_deterministic():
    module = MODULE.read_text(encoding="utf-8")

    for marker in (
        "priority > bestPriority",
        "healthPct < bestHealthPct",
        "guid < bestGuid",
        "bot->GetExactDist2d(creature) <= 12.0f",
        "ValidationRouteBossAddDensityGeneration",
        "cohortAddGuids.size() >= 3",
        "observer->IsWithinLOSInMap(creature)",
    ):
        assert marker in module
