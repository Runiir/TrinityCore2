from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MGR_HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"
MODULE_HEADER = ROOT / (
    "src/server/game/Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/"
    "HighPriestessAzilTankThreatRecovery.h"
)
MODULE = MODULE_HEADER.with_suffix(".cpp")
ORCHESTRATION_MODULE = MODULE_HEADER.with_name(
    "HighPriestessAzilAddWaveOrchestration.cpp"
)
CONTEXT_HEADER = MODULE_HEADER.with_name(
    "HighPriestessAzilHealerAddWavePreposition.h"
)


def test_azil_tank_threat_recovery_is_registered_and_bounded():
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
    assert "HighPriestessAzilTankThreatRecovery.cpp" in cmake
    assert "TankThreatRecoveryRequest" in module_header
    assert "AddWaveDiscoveryResult const* Discovery" in module_header
    assert "AddWaveDensityResult const* Density" in module_header
    assert "ContinueStableTankSwarmApproach" in module_header
    assert "RouteEngageRange" in module_header
    assert "TryTankThreatRecovery" in module_header
    assert "static bool Run(TankThreatRecoveryRequest const& request);" in (
        context_header
    )
    assert "HighPriestessAzilAddWaveOrchestration.h" in world


def test_azil_tank_threat_recovery_owns_the_exact_ordered_window():
    world = WORLD.read_text(encoding="utf-8")
    orchestration = ORCHESTRATION_MODULE.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")

    dispatch = orchestration.index("TryTankThreatRecovery(")
    swarm_threat_safety = orchestration.index(
        "TrySwarmThreatSafety(", dispatch
    )
    manager_gap = world
    for marker in (
        "warrior_taunt_residual_healer_threat",
        "warrior_charge_healer_swarm_pickup",
        "warrior_shockwave_healer_swarm_gap",
        "righteous_defense_healer_before_area_gcd",
        "hand_of_protection_healer_before_area_gcd",
        "preferSelfCenteredProtectionArea",
        "righteous_defense_healer_before_area_approach",
        "hand_of_reckoning_healer_before_area_approach",
        "avengers_shield_healer_before_area_approach",
        "tank_immediate_aoe_threat",
        "hand_of_protection_healer_emergency",
        "righteous_defense_healer_pickup",
        "hand_of_reckoning_add_pickup",
        "avengers_shield_healer_add_pickup",
        "consecration_healer_pickup",
    ):
        assert marker in module
        assert marker not in manager_gap

    assert module.index("warrior_taunt_residual_healer_threat") < module.index(
        "warrior_charge_healer_swarm_pickup"
    )
    assert module.index("warrior_charge_healer_swarm_pickup") < module.index(
        "warrior_shockwave_healer_swarm_gap"
    )
    assert module.index("warrior_shockwave_healer_swarm_gap") < module.index(
        "righteous_defense_healer_before_area_gcd"
    )
    assert module.index("righteous_defense_healer_before_area_gcd") < module.index(
        "tank_immediate_aoe_threat"
    )
    assert module.index("tank_immediate_aoe_threat") < module.index(
        "hand_of_protection_healer_emergency"
    )
    assert module.index("hand_of_protection_healer_emergency") < module.index(
        "righteous_defense_healer_pickup"
    )
    assert module.index("righteous_defense_healer_pickup") < module.index(
        "hand_of_reckoning_add_pickup"
    )
    assert module.index("hand_of_reckoning_add_pickup") < module.index(
        "avengers_shield_healer_add_pickup"
    )
    assert module.index("avengers_shield_healer_add_pickup") < module.index(
        "consecration_healer_pickup"
    )

    assert "swarmDefensiveThreshold" not in manager_gap


def test_azil_tank_threat_recovery_keeps_native_execution_and_callbacks():
    world = WORLD.read_text(encoding="utf-8")
    orchestration = ORCHESTRATION_MODULE.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")

    assert orchestration.index("continueStableTankSwarmApproach =") < orchestration.index(
        "TryTankThreatRecovery("
    )
    assert "continueStableTankSwarmApproach(add)" in module
    for marker in (
        "manager.TryCastCombatSpell(",
        "manager.TryCastFriendlySpell(",
        "manager.ResolveProfileCombatAction(",
        "manager.ExecuteProfileCombatAction(",
        "manager.MoveBotToProfileRange(",
        "manager.RecordEvent(",
        "routeEngageRange(bot, add",
        "continueStableTankSwarmApproach(add)",
        "DecisionTimer, 250",
        "TargetGuid",
        "WasInCombat = true",
        "IsWithinLOSInMap",
    ):
        assert marker in module
    for forbidden in ("SetVictim", "AddThreat", "SetThreat", "NearTeleportTo"):
        assert forbidden not in module
