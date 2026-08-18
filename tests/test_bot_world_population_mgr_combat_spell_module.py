from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatSpell.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


MOVED_METHODS = (
    "SelectCombatSpell",
    "TryCastCombatSpell",
    "MoveToWanderPoint",
)


def test_combat_spell_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrCombatSpell.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in text
        assert method in HEADER.read_text()


def test_combat_spell_methods_are_not_left_in_monolith():
    text = SOURCE.read_text()
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" not in text


def test_combat_spell_keeps_target_gates_and_wander_memory_contract():
    text = MODULE.read_text()
    for marker in (
        "min_enemies_not_met",
        "max_enemies_exceeded",
        "requires_ally_target",
        "validation_trash_requires_damage_progress",
        "cohort_threat_established",
        "target_health_gate",
        "self_health_gate",
        "SetFacingToObject",
        "HasNearbyProtectedEncounterTarget",
        "FindMemoryPoiTarget",
        "MarkPoiVisited",
        "GetLocalDangerScore",
        "IsFailedPathRecently",
        "MoveBotToPoint",
    ):
        assert marker in text
