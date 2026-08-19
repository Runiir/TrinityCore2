from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteTerminalArrival.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteTerminalArrival.h"
CONTEXTS = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteContexts.h"
MGR_HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_terminal_arrival_module_is_bounded_and_registered():
    module = MODULE.read_text()
    assert len(module.splitlines()) <= 1000
    assert len(HEADER.read_text().splitlines()) <= 1000
    assert len(MGR_HEADER.read_text().splitlines()) <= 1000
    assert "BotWorldPopulationMgrValidationRouteTerminalArrival.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in module
    assert "struct ObjectiveContext" in HEADER.read_text()
    assert "struct ObjectiveContext;" in CONTEXTS.read_text()
    assert "friend struct BotWorldPopulationMgrValidationRoute::ObjectiveContext;" in MGR_HEADER.read_text()


def test_terminal_arrival_boundary_leaves_only_typed_callbacks_in_monolith():
    source = SOURCE.read_text()
    module = MODULE.read_text()
    assert "bool failedTrashPackComplete" not in source
    assert "terminalArrivalCallbacks.PersistedPackHasLiveMembers" in source
    assert "terminalArrivalCallbacks.ActivePackTarget" in source
    assert "terminalArrivalCallbacks.IsEligibleTrash" in source
    assert "terminalArrivalCallbacks.PartyHasActiveCombat" in source
    assert "terminalArrivalCallbacks.IsOriginalInstanceMember" in source
    assert "terminalArrivalCallbacks.EnrollEngagedPackMembers" in source
    assert "terminalArrivalCallbacks.MoveToRouteAnchor" in source
    assert "terminalArrivalContext.Run()" in source
    terminal_call = source.index("terminalArrivalContext.Run()")
    route_wait = source.index(
        'if (Cohort().Config.ValidationRouteKind != "boss"\n'
        '        && std::string(GetDungeonRole(bot)) != "tank"',
        terminal_call,
    )
    assert terminal_call < route_wait
    for marker in (
        "failed_terminal_reopened_after_pack_death",
        "failed_terminal_reopened_for_live_pack_reapproach",
        "validation_route_partial_wipe_retreat_rendezvous",
        "native_descent_semantics_unavailable",
        "native_descent_landed_path_proven",
        "validation_route_descent_walk_segment",
        "validation_route_arrival_hold",
        "move_to_validation_route_anchor",
        "validation_route_terminal_hold",
    ):
        assert marker in module


def test_terminal_arrival_context_keeps_mutable_anchor_and_native_action_edges():
    header = HEADER.read_text()
    module = MODULE.read_text()
    for marker in (
        "float& RouteAnchorX",
        "float& RouteAnchorY",
        "float& RouteAnchorZ",
        "std::string& RouteAnchorReason",
        "float& RouteDistance",
        "std::function<bool()> MoveToRouteAnchor",
        "Manager.ExecuteNativeActionIntent",
        "Manager.FailValidationAttemptOnce",
        "Manager.MaybeAdvanceValidationRouteManifest",
        "Callbacks.EnrollEngagedPackMembers",
    ):
        assert marker in header or marker in module
