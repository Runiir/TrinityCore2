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


GEAR_MEMORY = "src/server/game/Bots/BotWorldPopulationMgrGearMemory.cpp"


def _function(text: str, signature: str) -> str:
    start = text.index(signature)
    return text[start:text.index("\n}\n", start)]


def test_two_spec_gear_evaluation_never_considers_container_bags():
    text = (ROOT / GEAR_MEMORY).read_text(encoding="utf-8")
    helper = _function(text, "BotGearUpgradeEvaluation EvaluateLoadoutSafeGearUpgrade(Player* bot)")
    # Single-spec characters keep the unchanged all-bags evaluation.
    assert "if (!bot || bot->GetSpecsCount() <= 1)\n        return BotLongTermProgressionBrain::EvaluateGearUpgrade(bot);" in helper
    # Two-spec characters consider only the backpack: no container bag is ever read.
    assert "for (uint8 slot = INVENTORY_SLOT_ITEM_START; slot < INVENTORY_SLOT_ITEM_END; ++slot)" in helper
    assert "GetBagByPos" not in helper and "INVENTORY_SLOT_BAG_START" not in helper
    assert "CanEquipItem(NULL_SLOT, equipDest, item, false) != EQUIP_ERR_OK" in helper
    assert "EvaluateGearTemplate(bot, item->GetTemplate())" in helper
    assert "candidate.PowerDelta <= best.PowerDelta" in helper


def test_both_gear_paths_use_the_loadout_safe_evaluation():
    text = (ROOT / GEAR_MEMORY).read_text(encoding="utf-8")
    decision = _function(text, "bool BotWorldPopulationMgr::TrySmartGearDecision(")
    assert "BotGearUpgradeEvaluation evaluation = EvaluateLoadoutSafeGearUpgrade(bot);" in decision
    assert "BotLongTermProgressionBrain::EvaluateGearUpgrade(" not in decision
    # The equip guard stays as a second line of defence.
    assert "bool const offSpecBagItem = item && bot->GetSpecsCount() > 1" in decision
    assert decision.index("if (offSpecBagItem)") < decision.index("bot->EquipItem(")
    record = _function(text, "void BotWorldPopulationMgr::RecordGearEvaluation(")
    assert "candidate.Bag >= INVENTORY_SLOT_BAG_START && candidate.Bag < INVENTORY_SLOT_BAG_END" in record
    assert "bot->GetSpecsCount() > 1 && bagged\n        ? EvaluateLoadoutSafeGearUpgrade(bot) : candidate;" in record
    assert record.index("EvaluateLoadoutSafeGearUpgrade") < record.index("if (!Cohort().RunId")
    assert len(text.splitlines()) < 1000
