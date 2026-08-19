from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MGR_HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"
MODULE_HEADER = ROOT / (
    "src/server/game/Bots/Content/Dungeons/Stonecore/HighPriestessAzil/"
    "HighPriestessAzilAddWaveTankPreparation.h"
)
MODULE = MODULE_HEADER.with_suffix(".cpp")
CONTEXT_HEADER = MODULE_HEADER.with_name(
    "HighPriestessAzilHealerAddWavePreposition.h"
)


def test_azil_tank_preparation_module_is_registered_and_bounded():
    world = WORLD.read_text(encoding="utf-8")
    mgr_header = MGR_HEADER.read_text(encoding="utf-8")
    module_header = MODULE_HEADER.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")
    context_header = CONTEXT_HEADER.read_text(encoding="utf-8")
    cmake = CMAKE.read_text(encoding="utf-8")

    assert len(mgr_header.splitlines()) <= 990
    assert len(module_header.splitlines()) <= 1000
    assert len(module.splitlines()) <= 1000
    assert "HighPriestessAzilAddWaveTankPreparation.cpp" in cmake
    assert "AddWaveTankPreparationRequest" in module_header
    assert "AddWaveTankPreparationResult" in module_header
    assert "PrepareAddWaveTank" in module_header
    assert (
        "static AddWaveTankPreparationResult Run("
        in context_header
    )
    assert "HighPriestessAzilAddWaveTankPreparation.h" in world


def test_azil_tank_preparation_stops_before_feral_roar_logic():
    world = WORLD.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")

    density = world.index("ResolveAddWaveDensity(")
    opening = world.index("TryAddWaveOpeningActions(")
    preparation = world.index("PrepareAddWaveTank(")
    feral_roar = world.index("ResolveFeralHandoffState(")
    assert density < opening < preparation < feral_roar

    for marker in (
        "densityDefenseAttackers",
        "TankDensityClusterRadius = 10.0f",
        "tank_swarm_defensive",
        "defensiveSpells = { 61336, 22812 }",
        "state.DecisionTimer, 500",
        "state.DecisionTimer, 250",
    ):
        assert marker in module
        assert marker not in world[preparation:feral_roar]

    assert "ResolveFeralHandoffState" not in module
    assert "TryValidationFeralRoarPickup" not in module


def test_azil_tank_preparation_preserves_cluster_and_cadence_order():
    module = MODULE.read_text(encoding="utf-8")

    for earlier, later in (
        ("distance == densityClusterDistance", "guid < densityClusterGuid"),
        ("defensiveSpells = { 61336, 22812 }", "TryCastFriendlySpell"),
        ("TryCastFriendlySpell", "tank_swarm_defensive"),
        ("tank_swarm_defensive", "state.DecisionTimer, 500"),
        ("state.DecisionTimer, 500", "state.DecisionTimer, 250"),
    ):
        assert module.index(earlier) < module.index(later)

    assert "attacker->GetExactDist2d(neighbor) <= TankDensityClusterRadius" in module
    assert "localClusterCount > densityClusterCount" in module
    assert module.index("for (Unit* attacker") < module.index(
        "for (Unit* neighbor")
    assert "UnitHealthPct(bot) <= 0.90f" in module
    assert "observedListedAttackerCount(densityHealer) == 0" in module
    assert "observedListedAttackerCount(densityHealer) >= 2" in module
