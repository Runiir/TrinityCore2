from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MGR_HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"
MODULE_HEADER = ROOT / (
    "src/server/game/Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/"
    "HighPriestessAzilAddWaveOrchestration.h"
)
MODULE = MODULE_HEADER.with_suffix(".cpp")
CONTEXT_HEADER = MODULE_HEADER.with_name(
    "HighPriestessAzilHealerAddWavePreposition.h"
)


def test_azil_add_wave_orchestration_is_registered_and_bounded():
    world = WORLD.read_text(encoding="utf-8")
    mgr_header = MGR_HEADER.read_text(encoding="utf-8")
    module_header = MODULE_HEADER.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")
    context_header = CONTEXT_HEADER.read_text(encoding="utf-8")
    cmake = CMAKE.read_text(encoding="utf-8")

    assert len(mgr_header.splitlines()) <= 1000
    assert len(module_header.splitlines()) <= 1000
    assert len(module.splitlines()) <= 1000
    assert "HighPriestessAzilAddWaveOrchestration.cpp" in cmake
    assert "HighPriestessAzilAddWaveOrchestration.h" in world
    assert "AddWaveOrchestrationRequest" in module_header
    assert "TryAddWaveOrchestration" in module_header
    assert (
        "static bool Run(AddWaveOrchestrationRequest const& request);"
        in context_header
    )


def test_azil_add_wave_orchestration_keeps_manager_gate_and_ownership_boundary():
    world = WORLD.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")

    gate = world.index("ValidationRouteAddTargetEntries.empty()")
    dispatch = world.index("TryAddWaveOrchestration(", gate)
    assert gate < dispatch
    assert "AddWaveOrchestrationRequest request;" in world
    assert "TryRouteGroupHeal.Function" in world
    assert "CanonicalRouteDistance = canonicalRouteDistance" in world
    assert "RouteArrivalRadius = routeArrivalRadius" in world
    for marker in (
        "ResolveAddWaveDensity(",
        "TryFeralActiveSwarmMovement(",
        "TryDensityCombatResolution(",
        "tank_swarm_defensive",
        "manager.RecordEvent(",
    ):
        assert marker not in world
        assert marker in module


def test_azil_add_wave_orchestration_preserves_submodule_order_and_defensive_logic():
    module = MODULE.read_text(encoding="utf-8")

    calls = (
        "TryHealerAddWavePreposition(",
        "DiscoverAddWave(",
        "ResolveAddWaveDensity(",
        "TryAddWaveOpeningActions(",
        "PrepareAddWaveTank(",
        "ResolveFeralHandoffState(",
        "TryFeralLocalRetention(",
        "TryFeralRemoteActions(",
        "TryFeralActiveSwarmMovement(",
        "TryHunterThreatTransfer(",
        "TryPassiveSwarmStaging(",
        "TryTankThreatRecovery(",
        "TrySwarmThreatSafety(",
        "TryHighDensityPositioning(",
        "TryDensityCombatResolution(",
    )
    positions = [module.index(call) for call in calls]
    assert positions == sorted(positions)
    assert "std::array<uint32, 3> defensiveSpells" in module
    assert "manager.TryCastFriendlySpell(bot, bot, defensiveSpellId)" in module
    assert "return Context::Run(request);" in module
