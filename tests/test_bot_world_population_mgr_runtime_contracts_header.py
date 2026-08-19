from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrRuntimeContracts.h"


def test_runtime_contracts_are_in_a_bounded_class_fragment():
    source = SOURCE.read_text()
    module = MODULE.read_text()

    assert len(SOURCE.read_text().splitlines()) <= 1000
    assert len(module.splitlines()) <= 1000
    assert '#include "Bots/BotWorldPopulationMgrRuntimeContracts.h"' in source
    for marker in ("struct PartyRuntime", "struct RaidRuntime", "struct CohortRuntime", "struct BotGuidLease"):
        assert marker in module


def test_runtime_contracts_are_not_duplicated_in_the_primary_header():
    source = SOURCE.read_text()

    for marker in ("struct PartyRuntime", "struct RaidRuntime", "struct CohortRuntime", "struct BotGuidLease"):
        assert source.count(marker) == 0
    assert '#include "BotWorldPopulationMgr.cpp"' not in source
