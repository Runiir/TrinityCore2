from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MGR_HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"
MODULE_HEADER = ROOT / (
    "src/server/game/Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/"
    "HighPriestessAzilFeralRemoteActions.h"
)
MODULE = MODULE_HEADER.with_suffix(".cpp")
ORCHESTRATION_MODULE = MODULE_HEADER.with_name(
    "HighPriestessAzilAddWaveOrchestration.cpp"
)
CONTEXT_HEADER = MODULE_HEADER.with_name(
    "HighPriestessAzilHealerAddWavePreposition.h"
)
ACTIVE_MODULE = MODULE_HEADER.with_name(
    "HighPriestessAzilFeralActiveSwarmMovement.cpp"
)


def test_azil_feral_remote_actions_is_registered_and_bounded():
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
    assert "HighPriestessAzilFeralRemoteActions.cpp" in cmake
    assert "FeralRemoteActionsRequest" in module_header
    assert "AddWaveDiscoveryResult const* Discovery" in module_header
    assert "AddWaveDensityResult const* Density" in module_header
    assert "FeralHandoffStateResult const* FeralHandoff" in module_header
    assert "Unit** Add" in module_header
    assert "TryFeralRemoteActions" in module_header
    assert "static bool Run(FeralRemoteActionsRequest const& request);" in (
        context_header
    )
    assert "HighPriestessAzilAddWaveOrchestration.h" in world


def test_azil_feral_remote_actions_owns_the_exact_native_action_window():
    world = WORLD.read_text(encoding="utf-8")
    orchestration = ORCHESTRATION_MODULE.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")
    active_module = ACTIVE_MODULE.read_text(encoding="utf-8")

    handoff_dispatch = orchestration.index("ResolveFeralHandoffState(")
    retention_dispatch = orchestration.index("TryFeralLocalRetention(")
    remote_dispatch = orchestration.index("TryFeralRemoteActions(")
    active_window = orchestration.index("TryFeralActiveSwarmMovement(")
    assert handoff_dispatch < retention_dispatch < remote_dispatch < active_window
    assert "A remote Charge must not abandon" not in world
    assert "feralHealerHandoffArrived" not in world
    assert "activeSwarmPickupEligible" not in module
    assert "uint64 activeSwarmPickupNowMs = NowMs();" in active_module

    for marker in (
        "A remote Charge must not abandon a useful local healer-owned cluster.",
        "remoteHealerWaveChargeTarget",
        "feral_charge_remote_healer_wave_before_roar",
        "tryFeralRoarPickup(feralHealerHandoffArrived)",
        "feralChargeProtectsHighDensityParty",
        "feral_charge_swarm_pickup",
        "feral_hold_charge_swarm_arrival_for_roar",
        "feral_hold_healer_swarm_handoff_for_roar",
        "feral_growl_lingering_healer_swarm_attacker",
        "feral_swipe_lingering_healer_swarm_attacker",
        "sharedFocusValid = false",
        "return false;",
    ):
        assert marker in module

    assert module.index(
        "feral_charge_remote_healer_wave_before_roar"
    ) < module.index("tryFeralRoarPickup(feralHealerHandoffArrived)")
    assert module.index("feral_charge_swarm_pickup") < module.index(
        "feral_hold_charge_swarm_arrival_for_roar"
    )
    assert module.index("feral_hold_charge_swarm_arrival_for_roar") < module.index(
        "feral_hold_healer_swarm_handoff_for_roar"
    )
    assert module.index("feral_hold_healer_swarm_handoff_for_roar") < module.index(
        "feral_growl_lingering_healer_swarm_attacker"
    )


def test_azil_feral_remote_actions_preserve_native_only_boundaries():
    module = MODULE.read_text(encoding="utf-8")

    assert "SetVictim" not in module
    assert "AddThreat" not in module
    assert "SetThreat" not in module
    assert "NearTeleportTo" not in module
    assert "TryCastCombatSpell" in module
    assert "MovePoint" not in module
