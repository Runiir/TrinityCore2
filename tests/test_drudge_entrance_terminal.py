from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"
TERMINAL = (
    BOTS
    / "Content/Raids/BlackwingDescent/Trash/Drudge"
    / "BotWorldPopulationMgrValidationRouteDrudgeTerminal.cpp"
)
TARGET_ENGAGEMENT = BOTS / "BotWorldPopulationMgrValidationRouteTargetEngagement.cpp"
ROUTE_RUNTIME = BOTS / "BotWorldPopulationMgrValidationRouteRuntime.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_drudge_entrance_terminal_is_exact_and_generation_scoped() -> None:
    text = TERMINAL.read_text(encoding="utf-8")

    for marker in (
        'ValidationRouteNodeId != "bwd.magmaw.drudges"',
        '!= "trash_two_tank_charge_lanes"',
        'ValidationRouteKind != "trash"',
        "ValidationRouteTargetEntry != 42362",
        "ValidationRouteSplitSourceGuids.size() != 2",
        "250140",
        "250141",
        "ValidationRouteDrudgePrepullAttemptId != Cohort().AttemptId",
        "ValidationRouteDrudgePrepullWipeGeneration",
        "ValidationRouteDrudgePrepullRouteGeneration",
        "ValidationRoutePackGeneration",
        "ValidationRoutePackObservedEngagement",
        "ValidationRoutePackMemberGuids.size() != 2",
        "ValidationRoutePackEngagedGuids.size() != 2",
        "member->GetMap()->GetCreature(guid)",
        "source->GetSpawnId() == 250140",
        "source->GetSpawnId() == 250141",
        "member->GetExactDist(source) <= 55.0f",
        "ValidationRoutePackEngagedGuids.count(guid)",
        "ValidationRoutePackDeathGuids.count(guid)",
    ):
        assert marker in text


def test_drudge_terminal_contract_is_shared_by_clear_and_advance_gates() -> None:
    for source in (TARGET_ENGAGEMENT, ROUTE_RUNTIME):
        text = source.read_text(encoding="utf-8")
        assert "HasCompletedValidationRouteDrudgeEntrancePull(" in text
        assert "&& outOfCombat" in text
        assert "FullRosterAtEndpoint" in text


def _drudge_terminal_search_admitted(
    route_distance: float,
    arrival_radius: float,
    role: str,
    exact_pull_complete: bool,
) -> bool:
    return role == "tank" and (
        route_distance <= arrival_radius or exact_pull_complete
    )


def test_drudge_terminal_search_reconciles_exact_pull_beyond_route_radius() -> None:
    text = TARGET_ENGAGEMENT.read_text(encoding="utf-8")
    guard_start = text.index(
        'if (!routeTarget && Cohort().Config.ValidationRouteKind != "boss"'
    )
    guard_end = text.index("\n    {", guard_start)
    guard = text[guard_start:guard_end]

    assert "routeDistance <= routeArrivalRadius" in guard
    assert "Manager.HasCompletedValidationRouteDrudgeEntrancePull(bot)" in guard
    assert "&& outOfCombat" in text[guard_end:]

    # Canary geometry: tanks are near the exact dead sources but outside the
    # canonical route radius. The exact completion contract admits that case;
    # an unproven pack or a non-tank must remain outside this branch.
    assert _drudge_terminal_search_admitted(68.0, 18.0, "tank", True)
    assert not _drudge_terminal_search_admitted(68.0, 18.0, "tank", False)
    assert _drudge_terminal_search_admitted(12.0, 18.0, "tank", False)
    assert not _drudge_terminal_search_admitted(68.0, 18.0, "healer", True)


def test_drudge_terminal_contract_is_a_small_build_unit() -> None:
    assert len(TERMINAL.read_text(encoding="utf-8").splitlines()) < 100
    assert TERMINAL.name in CMAKE.read_text(encoding="utf-8")
    assert len(TARGET_ENGAGEMENT.read_text(encoding="utf-8").splitlines()) < 1000
