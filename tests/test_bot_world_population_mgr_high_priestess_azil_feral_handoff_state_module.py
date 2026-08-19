from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MGR_HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"
MODULE_HEADER = ROOT / (
    "src/server/game/Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/"
    "HighPriestessAzilFeralHandoffState.h"
)
MODULE = MODULE_HEADER.with_suffix(".cpp")
CONTEXT_HEADER = MODULE_HEADER.with_name(
    "HighPriestessAzilHealerAddWavePreposition.h"
)
ACTIVE_MODULE = MODULE_HEADER.with_name(
    "HighPriestessAzilFeralActiveSwarmMovement.cpp"
)


def test_azil_feral_handoff_state_is_registered_and_bounded():
    world = WORLD.read_text(encoding="utf-8")
    mgr_header = MGR_HEADER.read_text(encoding="utf-8")
    module_header = MODULE_HEADER.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")
    context_header = CONTEXT_HEADER.read_text(encoding="utf-8")
    cmake = CMAKE.read_text(encoding="utf-8")

    assert len(mgr_header.splitlines()) <= 990
    assert len(module_header.splitlines()) <= 1000
    assert len(module.splitlines()) <= 1000
    assert "HighPriestessAzilFeralHandoffState.cpp" in cmake
    assert "FeralHandoffStateRequest" in module_header
    assert "FeralHandoffStateResult" in module_header
    assert "ResolveFeralHandoffState" in module_header
    assert "static FeralHandoffStateResult Run(" in context_header
    assert "HighPriestessAzilFeralHandoffState.h" in world


def test_azil_feral_handoff_state_stops_before_local_swipe_window():
    world = WORLD.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")

    dispatch = world.index("ResolveFeralHandoffState(")
    retention_dispatch = world.index("TryFeralLocalRetention(")
    assert dispatch < retention_dispatch
    assert "localHealerOwnedSwipeWindow" not in world[dispatch:retention_dispatch]
    for marker in (
        "feralChargeNowMs = NowMs()",
        "feralChargePickupTarget = ObjectAccessor::GetUnit(",
        '"feral_charge_swarm_pickup_in_flight"',
        "Rerun156 proved the boss handoff discarded",
        "feralHealerHandoffActive = role == \"tank\"",
        "feralHealerHandoffArrived =",
    ):
        assert marker in module


def test_azil_feral_handoff_state_preserves_identity_order_and_callback():
    module = MODULE.read_text(encoding="utf-8")
    world = WORLD.read_text(encoding="utf-8")
    active_module = ACTIVE_MODULE.read_text(encoding="utf-8")

    assert "std::function<bool(bool)> TryFeralRoarPickup;" in MODULE_HEADER.read_text(
        encoding="utf-8"
    )
    assert "feralHandoff.TryFeralRoarPickup" in world
    assert module.index("feralChargeNowMs = NowMs()") < module.index(
        "feralChargePickupTarget = ObjectAccessor::GetUnit("
    )
    assert module.index('"feral_charge_swarm_pickup_in_flight"') < module.index(
        "feralHealerHandoffNowMs = NowMs()"
    )
    assert module.index("feralHealerHandoffActive = role == \"tank\"") < module.index(
        "feralHealerHandoffArrived ="
    )
    assert "static constexpr float TankDensityClusterRadius = 10.0f;" in active_module
    assert active_module.index("static constexpr float TankDensityClusterRadius = 10.0f;") < active_module.index(
        "<= TankDensityClusterRadius"
    )
