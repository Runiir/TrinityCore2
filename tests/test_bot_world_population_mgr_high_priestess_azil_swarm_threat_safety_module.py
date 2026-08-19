from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MGR_HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"
MODULE_HEADER = ROOT / (
    "src/server/game/Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/"
    "HighPriestessAzilSwarmThreatSafety.h"
)
MODULE = MODULE_HEADER.with_suffix(".cpp")
ORCHESTRATION_MODULE = MODULE_HEADER.with_name(
    "HighPriestessAzilAddWaveOrchestration.cpp"
)
CONTEXT_HEADER = MODULE_HEADER.with_name(
    "HighPriestessAzilHealerAddWavePreposition.h"
)


def test_azil_swarm_threat_safety_is_registered_and_bounded():
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
    assert "HighPriestessAzilSwarmThreatSafety.cpp" in cmake
    assert "SwarmThreatSafetyRequest" in module_header
    assert "AddWaveDiscoveryResult const* Discovery" in module_header
    assert "AddWaveDensityResult const* Density" in module_header
    assert "HunterThreatTransferResult const* HunterThreatTransfer" in module_header
    assert "TrySwarmThreatSafety" in module_header
    assert "static bool Run(SwarmThreatSafetyRequest const& request);" in (
        context_header
    )
    assert "HighPriestessAzilAddWaveOrchestration.h" in world


def test_azil_swarm_threat_safety_owns_the_exact_ordered_window():
    world = WORLD.read_text(encoding="utf-8")
    orchestration = ORCHESTRATION_MODULE.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")

    recovery = orchestration.index("TryTankThreatRecovery(")
    dispatch = orchestration.index("TrySwarmThreatSafety(", recovery)
    density_range = orchestration.index("TryHighDensityPositioning(", dispatch)
    manager_gap = world
    for marker in (
        "swarm_pickup_emergency_defensive",
        "dps_wait_for_swarm_tank_ownership",
        "dps_stack_for_swarm_pickup",
        "dps_stack_for_add_pickup",
        "dps_hold_for_nearby_add_pickup",
        "hand_of_salvation_healer_threat_drop",
    ):
        assert marker in module
        assert marker not in manager_gap

    assert module.index("swarm_pickup_emergency_defensive") < module.index(
        "dps_wait_for_swarm_tank_ownership"
    )
    assert module.index("dps_wait_for_swarm_tank_ownership") < module.index(
        "dps_stack_for_add_pickup"
    )
    assert module.index("dps_stack_for_add_pickup") < module.index(
        "dps_hold_for_nearby_add_pickup"
    )
    assert module.index("dps_hold_for_nearby_add_pickup") < module.index(
        "hand_of_salvation_healer_threat_drop"
    )


def test_azil_swarm_threat_safety_preserves_native_pet_and_action_boundaries():
    module = MODULE.read_text(encoding="utf-8")

    for marker in (
        "TryCastFriendlySpell(bot, bot, swarmDefensiveSpellId)",
        "SubmitMeleeAutoAttackIntent(state",
        "if (Pet* pet = bot->GetPet())",
        "pet->AttackStop();",
        "MoveBotToPoint(state, bot",
        "TargetGuid",
        "RecordEvent(state, bot",
        "return false;",
    ):
        assert marker in module
    for forbidden in ("SetVictim", "AddThreat", "SetThreat", "NearTeleportTo"):
        assert forbidden not in module
