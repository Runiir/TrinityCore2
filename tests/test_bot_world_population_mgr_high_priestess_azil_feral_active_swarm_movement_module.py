from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MGR_HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"
MODULE_HEADER = ROOT / (
    "src/server/game/Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/"
    "HighPriestessAzilFeralActiveSwarmMovement.h"
)
MODULE = MODULE_HEADER.with_suffix(".cpp")
ORCHESTRATION_MODULE = MODULE_HEADER.with_name(
    "HighPriestessAzilAddWaveOrchestration.cpp"
)
CONTEXT_HEADER = MODULE_HEADER.with_name(
    "HighPriestessAzilHealerAddWavePreposition.h"
)


def test_azil_feral_active_swarm_movement_is_registered_and_bounded():
    world = WORLD.read_text(encoding="utf-8")
    orchestration = ORCHESTRATION_MODULE.read_text(encoding="utf-8")
    mgr_header = MGR_HEADER.read_text(encoding="utf-8")
    module_header = MODULE_HEADER.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")
    context_header = CONTEXT_HEADER.read_text(encoding="utf-8")
    cmake = CMAKE.read_text(encoding="utf-8")

    assert len(mgr_header.splitlines()) <= 1000
    assert len(module_header.splitlines()) <= 1000
    assert len(module.splitlines()) <= 1000
    assert (
        "HighPriestessAzilFeralActiveSwarmMovement.cpp" in cmake
    )
    assert "FeralActiveSwarmMovementRequest" in module_header
    assert "AddWaveDiscoveryResult const* Discovery" in module_header
    assert "AddWaveDensityResult const* Density" in module_header
    assert "FeralHandoffStateResult const* FeralHandoff" in module_header
    assert "TryFeralActiveSwarmMovement" in module_header
    assert "static bool Run(FeralActiveSwarmMovementRequest const& request);" in (
        context_header
    )
    assert "HighPriestessAzilAddWaveOrchestration.h" in world


def test_azil_active_swarm_movement_owns_the_bounded_window():
    world = WORLD.read_text(encoding="utf-8")
    orchestration = ORCHESTRATION_MODULE.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")

    remote_dispatch = orchestration.index("TryFeralRemoteActions(")
    active_dispatch = orchestration.index("TryFeralActiveSwarmMovement(")
    hunter_window = orchestration.index("TryHunterThreatTransfer(")
    assert remote_dispatch < active_dispatch < hunter_window
    manager_gap = world
    assert "activeSwarmPickupNowMs" not in manager_gap
    assert "stationary_healer_swarm_pickup" not in manager_gap

    for marker in (
        "static constexpr float TankDensityClusterRadius = 10.0f;",
        "uint64 activeSwarmPickupNowMs = NowMs();",
        "activeSwarmPickupReserved",
        "FeralActiveSwarmPickupAnchorGuid",
        "FeralActiveSwarmPickupUntilMs",
        "FeralActiveSwarmPickupArrived",
        "tryFeralRoarPickup(true)",
        "MoveBotToPoint(state, bot",
        "feral_hold_bounded_active_swarm_cluster_for_roar",
        "feral_continue_bounded_active_swarm_cluster",
        "feral_move_to_bounded_active_swarm_cluster",
        "feral_continue_to_stationary_healer_swarm_pickup",
        "feral_move_to_stationary_healer_swarm_pickup",
        "feral_stationary_healer_swarm_pickup_path_rejected",
    ):
        assert marker in module


def test_azil_active_swarm_movement_preserves_identity_and_native_boundaries():
    module = MODULE.read_text(encoding="utf-8")

    assert module.index("activeSwarmPickupNowMs = NowMs()") < module.index(
        "activeSwarmPickupNowMs + 1500"
    )
    assert module.index("activeSwarmPickupNowMs + 1500") < module.index(
        "tryFeralRoarPickup(true)"
    )
    assert module.index("activeSwarmPickupNowMs + 2500") < module.index(
        "feral_move_to_bounded_active_swarm_cluster"
    )
    assert "FeralHandoffStateResult const& feralHandoff" in module
    assert "GetVictim() == densityHealer" in module
    assert "hazard movement remains" in module
    assert "authoritative because it runs before this resolver" in module
    for forbidden in ("SetVictim", "AddThreat", "SetThreat", "NearTeleportTo"):
        assert forbidden not in module
