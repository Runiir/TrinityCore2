from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"
MODULE_HEADER = ROOT / (
    "src/server/game/Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/"
    "HighPriestessAzilHealerAddWavePreposition.h"
)
MODULE = MODULE_HEADER.with_suffix(".cpp")
ORCHESTRATION_MODULE = MODULE_HEADER.with_name(
    "HighPriestessAzilAddWaveOrchestration.cpp"
)


def test_azil_healer_add_wave_preposition_boundary_is_registered_and_ordered():
    world = WORLD.read_text(encoding="utf-8")
    orchestration = ORCHESTRATION_MODULE.read_text(encoding="utf-8")
    header = HEADER.read_text(encoding="utf-8")
    module_header = MODULE_HEADER.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")
    cmake = CMAKE.read_text(encoding="utf-8")

    assert len(header.splitlines()) <= 1000
    assert len(module_header.splitlines()) <= 1000
    assert len(module.splitlines()) <= 1000
    assert "HighPriestessAzilHealerAddWavePreposition.cpp" in cmake
    assert "TryHealerAddWavePreposition" in module_header
    assert "struct Context" in module_header
    assert "ValidationRouteBossProgressTargetGuid" in module
    assert "fade_before_urgent_add_pickup_preposition" in module
    assert "healer_preposition_for_add_pickup" in module
    assert "TryRouteGroupHeal" in module_header
    assert "HighPriestessAzilAddWaveOrchestration.h" in world

    guard = world.index("ValidationRouteAddTargetEntries.empty()")
    dispatch = world.index("TryAddWaveOrchestration(", guard)
    healer_dispatch = orchestration.index("TryHealerAddWavePreposition(")
    generic_adds = orchestration.index("Unit* add = nullptr;", healer_dispatch)
    assert guard < dispatch
    assert healer_dispatch < generic_adds
    assert "fade_before_urgent_add_pickup_preposition" not in world
    assert "healer_preposition_for_add_pickup" not in world
