"""A bagged equippable item (a two-spec loadout's off-spec gear) never exposes its on-use effect."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FILES = ("src/server/game/Bots/BotActionExecutor.cpp",
         "src/server/game/Bots/BotClassSpecActionProfileCandidates.cpp")
GUARD = "if (itemTemplate->GetInventoryType() != INVTYPE_NON_EQUIP && !item->IsEquipped())"


def _finder(path: str) -> str:
    text = (ROOT / path).read_text(encoding="utf-8")
    start = re.search(r"Item\* FindOnUseItemForSpell\(Player(?: const)?\* player, uint32 spellId\)\n\{", text)
    assert start, path
    end = text.index("\n}\n", start.end())
    return text[start.start():end]


@pytest.mark.parametrize("path", FILES)
def test_on_use_lookup_rejects_unequipped_equippable_items(path):
    body = _finder(path)
    lambda_body = body[body.index("auto matches"):body.index("};")]
    assert GUARD in lambda_body
    guard = lambda_body.index(GUARD)
    assert lambda_body.index("GetLastPotionId()") < guard < lambda_body.index("itemTemplate->Effects.size()")
    assert lambda_body[guard:].split("\n", 2)[1].strip() == "return false;"
    # Non-equippable consumables in the backpack and in container bags stay usable.
    assert "INVENTORY_SLOT_ITEM_START" in body and "GetBagByPos(bagSlot)" in body


@pytest.mark.parametrize("path", FILES)
def test_guard_files_stay_below_the_module_size_limit(path):
    assert len((ROOT / path).read_text(encoding="utf-8").splitlines()) < 1000
