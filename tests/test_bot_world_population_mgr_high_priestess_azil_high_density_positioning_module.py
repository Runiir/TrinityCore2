from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MGR_HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"
MODULE_HEADER = ROOT / (
    "src/server/game/Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/"
    "HighPriestessAzilHighDensityPositioning.h"
)
MODULE = MODULE_HEADER.with_suffix(".cpp")
CONTEXT_HEADER = MODULE_HEADER.with_name(
    "HighPriestessAzilHealerAddWavePreposition.h"
)


def test_azil_high_density_positioning_is_registered_and_bounded():
    world = WORLD.read_text(encoding="utf-8")
    mgr_header = MGR_HEADER.read_text(encoding="utf-8")
    module_header = MODULE_HEADER.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")
    context_header = CONTEXT_HEADER.read_text(encoding="utf-8")
    cmake = CMAKE.read_text(encoding="utf-8")

    assert len(mgr_header.splitlines()) <= 990
    assert len(module_header.splitlines()) <= 1000
    assert len(module.splitlines()) <= 1000
    assert "HighPriestessAzilHighDensityPositioning.cpp" in cmake
    assert "HighDensityPositioningRequest" in module_header
    assert "AddWaveDiscoveryResult const* Discovery" in module_header
    assert "AddWaveDensityResult const* Density" in module_header
    assert "TryRouteGroupHeal" in module_header
    assert "TryHighDensityPositioning" in module_header
    assert "static bool Run(HighDensityPositioningRequest const& request);" in (
        context_header
    )
    assert "HighPriestessAzilHighDensityPositioning.h" in world


def test_azil_high_density_positioning_owns_the_exact_ordered_window():
    world = WORLD.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")

    dispatch = world.index("TryHighDensityPositioning(")
    continuation = world.index("TryDensityCombatResolution(", dispatch)
    manager_gap = world[dispatch:continuation]
    for marker in (
        "densityHealerRange",
        "tank_move_to_add_centroid",
        "healer_stack_for_swarm_pickup",
        "reissue_shared_escape_unreached",
        "continue_to_boss_add_density_escape",
        'if (role == "healer")',
    ):
        assert marker in module
        assert marker not in manager_gap

    assert module.index("densityHealerRange") < module.index(
        "tank_move_to_add_centroid"
    )
    assert module.index("tank_move_to_add_centroid") < module.index(
        "healer_stack_for_swarm_pickup"
    )
    assert module.index("healer_stack_for_swarm_pickup") < module.index(
        "reissue_shared_escape_unreached"
    )
    assert module.index("reissue_shared_escape_unreached") < module.index(
        "continue_to_boss_add_density_escape"
    )


def test_azil_high_density_positioning_keeps_native_movement_and_callback():
    module = MODULE.read_text(encoding="utf-8")

    for marker in (
        "manager.ResetValidationRouteBossAddEscapeState()",
        "manager.MoveBotToPoint(state, densityTank",
        "manager.MoveBotToPoint(state, bot",
        "manager.RecordEvent(state, bot",
        "request.TryRouteGroupHeal(bot, add)",
        "TargetGuid",
        "ValidationRouteBossAddEscapeIssuedGuids",
    ):
        assert marker in module
    for forbidden in ("Pet", "NearTeleportTo", "SetVictim", "AddThreat", "SetThreat"):
        assert forbidden not in module
