"""A composition recovery return keeps the route anchor on the boss node.

Round 6 (r05 Maloriak): after the second wipe every member had two deaths
near the node. The legacy death-loop fallback moved the route anchor to a
remembered safe position 79 yards from the boss; the recovery return walks
the member on that anchor and hands it to the encounter plan within 35 yards,
so it never arrived, the plans stayed yielded and the shard ended on the
semantic progress plateau. The return only arms at composition raid boss
nodes, so Stonecore, calibration and legacy Magmaw keep the fallback.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"
FOCUS = BOTS / "BotWorldPopulationMgrValidationFocus.cpp"
RETURN = BOTS / "BotValidationRouteRecoveryReturn.h"
RETURN_ADAPTER = BOTS / "BotWorldPopulationMgrValidationRouteRecoveryReturn.cpp"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def anchor_logic() -> str:
    source = read(FOCUS)
    start = source.index("BotWorldPopulationMgr::ResolveValidationRouteAnchor(")
    return source[start:source.index("state.QuestRouteDestination.Valid = true;", start)]


def test_return_pending_blocks_the_safe_memory_fallback() -> None:
    logic = anchor_logic()
    assert "bool const recoveryReturnPending = state.ValidationRecoveryReturn.Pending;" in logic
    repeated = logic.index("bool repeatedDeathNearRoute = !recoveryReturnPending")
    install = logic.index("else if (!routeHasActiveCombatIntent && repeatedDeathNearRoute")
    assert repeated < install
    # An override installed before the return armed is cleared while it runs.
    clear = logic.index("state.ValidationRouteAnchorOverrideValid && recoveryReturnPending")
    use = logic.index("routeAnchorX = state.ValidationRouteAnchorOverrideX;")
    assert clear < use
    block = logic[clear:logic.index("}", clear)]
    assert '"validation_route_safe_memory_after_death_loop"' in block
    assert "state.ValidationRouteAnchorOverrideValid = false;" in block


def test_the_return_is_scoped_to_composition_raid_boss_nodes() -> None:
    adapter = read(RETURN_ADAPTER)
    assert "node.CompositionRecovery" in adapter
    assert 'cohort.Config.ValidationRouteKind == "boss"' in adapter
    assert "cohort.Raid.RaidInstance" in adapter
    header = read(RETURN)
    assert "constexpr float HandOffYards = 35.0f;" in header
