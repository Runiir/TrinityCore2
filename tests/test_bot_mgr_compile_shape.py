from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_bot_mgr_directly_includes_world_and_object_manager_definitions() -> None:
    source = (ROOT / "src/server/game/Bots/BotMgr.cpp").read_text(encoding="utf-8")
    include_block = source[:source.index("namespace")]

    assert '#include "ObjectMgr.h"' in include_block
    assert '#include "World.h"' in include_block
    assert include_block.index('#include "ObjectMgr.h"') < source.index("sObjectMgr->")
    assert include_block.index('#include "World.h"') < source.index("sWorld->")
    assert "CONFIG_EXPANSION" in source


def test_raid_seed_divergence_log_owns_the_group_guid_string() -> None:
    source = (ROOT / "src/server/game/Bots/BotMgr.cpp").read_text(encoding="utf-8")

    assert "std::string const memberGroupGuid = bot->GetGroup()" in source
    assert "memberGroupGuid.c_str()" in source
    assert "ObjectGuid::Empty.ToString());" not in source
