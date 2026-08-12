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
