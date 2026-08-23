from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCES = tuple(sorted((ROOT / "src/server/game/Bots").glob("BotMgr*.cpp")))


def _bot_mgr_sources_containing(marker: str):
    return [
        (path, path.read_text(encoding="utf-8"))
        for path in BOT_SOURCES
        if marker in path.read_text(encoding="utf-8")
    ]


def test_bot_mgr_directly_includes_world_and_object_manager_definitions() -> None:
    world_sources = _bot_mgr_sources_containing("sWorld->")
    object_mgr_sources = _bot_mgr_sources_containing("sObjectMgr->")
    assert world_sources
    assert object_mgr_sources

    owning_sources = {path: source for path, source in world_sources + object_mgr_sources}
    for path, source in owning_sources.items():
        include_block = source[:source.index("BotMgr::")]
        if "sWorld->" in source:
            assert '#include "World.h"' in include_block, path
            assert include_block.index('#include "World.h"') < source.index("sWorld->")
            assert "CONFIG_EXPANSION" in source
        if "sObjectMgr->" in source:
            assert '#include "ObjectMgr.h"' in include_block, path
            assert include_block.index('#include "ObjectMgr.h"') < source.index("sObjectMgr->")


def test_raid_seed_divergence_log_owns_the_group_guid_string() -> None:
    owners = _bot_mgr_sources_containing("memberGroupGuid = bot->GetGroup()")
    assert owners
    source = owners[0][1]

    assert "std::string const memberGroupGuid = bot->GetGroup()" in source
    assert "memberGroupGuid.c_str()" in source
    assert "ObjectGuid::Empty.ToString());" not in source
