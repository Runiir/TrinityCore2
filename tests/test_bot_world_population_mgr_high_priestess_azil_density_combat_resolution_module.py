from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MGR_HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"
MODULE_HEADER = ROOT / (
    "src/server/game/Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/"
    "HighPriestessAzilDensityCombatResolution.h"
)
MODULE = MODULE_HEADER.with_suffix(".cpp")
ORCHESTRATION_MODULE = MODULE_HEADER.with_name(
    "HighPriestessAzilAddWaveOrchestration.cpp"
)
CONTEXT_HEADER = MODULE_HEADER.with_name(
    "HighPriestessAzilHealerAddWavePreposition.h"
)
REPLAY = ROOT / "src/server/game/Bots/BotWorldPopulationMgrReplay.cpp"


def test_azil_density_combat_resolution_is_registered_and_bounded():
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
    assert "HighPriestessAzilDensityCombatResolution.cpp" in cmake
    assert "DensityCombatResolutionRequest" in module_header
    assert "AddWaveDiscoveryResult const* Discovery" in module_header
    assert "AddWaveDensityResult const* Density" in module_header
    assert "ContinueStableTankSwarmApproach" in module_header
    assert "RouteEngageRange" in module_header
    assert "TryDensityCombatResolution" in module_header
    assert "static bool Run(DensityCombatResolutionRequest const& request);" in (
        context_header
    )
    assert "HighPriestessAzilAddWaveOrchestration.h" in world


def test_azil_density_combat_resolution_owns_the_exact_ordered_window():
    world = WORLD.read_text(encoding="utf-8")
    orchestration = ORCHESTRATION_MODULE.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")

    dispatch = orchestration.index("TryDensityCombatResolution(")
    for marker in (
        "if (highDensityPhase && !add && densityApproachAnchor)",
        '"approach_density_anchor"',
        '"no_compatible_density_anchor"',
        '"hold_unattackable_focus"',
        '"tank_auto_attack_density_fallback"',
        '"no_legal_density_action"',
        '"single_target_fallback_selected"',
        '"continue_stable_swarm_approach"',
        '"boss_add_melee_engagement"',
    ):
        assert marker in module
        assert marker not in world

    assert module.index("approach_density_anchor") < module.index(
        "no_compatible_density_anchor"
    )
    assert module.index("no_compatible_density_anchor") < module.index(
        "hold_unattackable_focus"
    )
    assert module.index("hold_unattackable_focus") < module.index(
        "tank_auto_attack_density_fallback"
    )
    assert module.index("tank_auto_attack_density_fallback") < module.index(
        "no_legal_density_action"
    )
    assert module.index("no_legal_density_action") < module.index(
        "single_target_fallback_selected"
    )


def test_azil_density_combat_resolution_keeps_native_execution_and_replay_fix():
    module = MODULE.read_text(encoding="utf-8")
    replay = REPLAY.read_text(encoding="utf-8")

    for marker in (
        "manager.MoveBotToProfileRange(state, bot",
        "manager.ResolveProfileCombatAction(bot, add",
        "manager.ExecuteProfileCombatAction(&state, bot, add",
        "manager.SubmitMeleeAutoAttackIntent(state",
        "manager.RecordEvent(state, bot",
        "manager.Party().ValidationRouteAddFocusGuid",
        "TargetGuid",
        "WasInCombat = true",
        "RouteEngageRange",
    ):
        assert marker in module
    for forbidden in ("Pet", "SetVictim", "AddThreat", "SetThreat", "NearTeleportTo"):
        assert forbidden not in module
    assert "float Distance2d(float ax, float ay, float bx, float by)" not in replay
