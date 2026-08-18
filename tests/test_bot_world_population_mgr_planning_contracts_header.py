from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrPlanningContracts.h"


def test_planning_contract_fragment_is_bounded_and_included_in_manager():
    source = SOURCE.read_text()
    module = MODULE.read_text()
    assert len(module.splitlines()) <= 1000
    assert '#include "Bots/BotWorldPopulationMgrPlanningContracts.h"' in source
    assert "struct QuestObjectivePlan" in module
    assert "struct DungeonTrashPackFeatures" in module
    assert "struct BossMechanicFeatures" in module
    assert "struct PolicyModelTrace" in module


def test_planning_contracts_are_not_duplicated_in_main_header():
    source = SOURCE.read_text()
    assert source.count("struct QuestObjectivePlan") == 0
    assert source.count("struct BossMechanicFeatures") == 0
    assert '#include "BotWorldPopulationMgr.cpp"' not in source
