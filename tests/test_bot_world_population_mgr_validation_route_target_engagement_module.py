from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteTargetEngagement.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteTargetEngagement.h"
OBJECTIVE_HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteTerminalArrival.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_target_engagement_module_is_bounded_registered_and_friended():
    assert len(MODULE.read_text().splitlines()) <= 1000
    assert len(HEADER.read_text().splitlines()) <= 1000
    assert "BotWorldPopulationMgrValidationRouteTargetEngagement.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in MODULE.read_text()
    assert "struct TargetEngagementCallbacks" in HEADER.read_text()
    assert "RunTargetEngagement" in OBJECTIVE_HEADER.read_text()


def test_target_engagement_moves_once_after_the_boss_activation_gate():
    source = SOURCE.read_text()
    module = MODULE.read_text()
    assert "Unit* preAnchorTrashTarget = nullptr;" not in source
    assert module.count("Unit* preAnchorTrashTarget = nullptr;") == 1
    assert source.count("terminalArrivalContext.RunTargetEngagement") == 1
    assert module.count("bool ObjectiveContext::RunTargetEngagement") == 1
    assert source.index("boss_route_early_activation") < source.index(
        "terminalArrivalContext.RunTargetEngagement"
    )
    for marker in (
        "target_ready_before_route_anchor",
        "canonical_boss_recovery_no_visible_target",
        "boss_route_undeclared_prerequisite_blocked",
        "trash_cluster_cleared",
        "validation_route_melee_engagement",
        "terminal_party_combat_focus_acquired",
    ):
        assert marker in module
        assert marker not in source


def test_target_engagement_passes_typed_search_activation_recovery_and_profile_edges():
    source = SOURCE.read_text()
    header = HEADER.read_text()
    for callback in (
        "DiscoveryLeg",
        "RouteEngageRange",
        "CurrentValidationRouteTargetSpawnId",
        "FindTrashClusterThreatTarget",
        "FindNearestTrashClusterMob",
        "IsValidationRouteScriptTarget",
        "IsValidationRouteCombatTarget",
        "MakeExistingValidationRouteCombatReady",
        "TryCanonicalValidationRouteBossRecovery",
        "TryValidationRouteActivation",
        "RecoverAuthoritativeFocus",
        "TryValidationRouteInterrupt",
        "MaybeValidationPrerequisiteNoProgressAssist",
        "TryRouteGroupHeal",
        "MarkTrashClusterCleared",
    ):
        assert f"targetEngagementCallbacks.{callback}" in source
        assert callback in header
