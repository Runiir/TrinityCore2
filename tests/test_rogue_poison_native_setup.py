from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tools.bot_ml.build_all_spec_phase1_catalogs import (
    validate_rogue_poison_provisioning,
)
from tools.bot_ml.validate_validation_provisioning import (
    runtime_consumable_inventory_mismatches,
)


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
INTENTS = ROOT / "src/server/game/Bots/BotNativeActionIntent.h"
TARGETS = ROOT / "experiments/configs/all_spec_targets_cata_p4_v1.json"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"unterminated function: {signature}")


def test_rogue_poison_contract_uses_exact_live_items_spells_and_enchants() -> None:
    setup = function_body(
        read(WORLD),
        "bool BotWorldPopulationMgr::TryEnsurePersistentCombatSetup",
    )

    assert 'profile.SpecTag == "assassination_rogue"' in setup
    assert 'profile.SpecTag == "combat_rogue"' in setup
    assert (
        "EQUIPMENT_SLOT_MAINHAND, 43233, 2823, 7" in setup
    ), "Deadly Poison must be an exact item -> on-use spell -> enchant contract"
    assert (
        "EQUIPMENT_SLOT_OFFHAND, 43231, 8679, 323" in setup
    ), "Instant Poison must be an exact item -> on-use spell -> enchant contract"
    assert "ITEM_SPELLTRIGGER_ON_USE" in setup
    assert "SPELL_EFFECT_ENCHANT_ITEM_TEMPORARY" in setup
    assert "poisonItemTemplate->Effects" in setup
    assert "spellInfo->Effects" in setup


def test_rogue_poison_setup_submits_native_item_use_then_observes_enchant() -> None:
    world = read(WORLD)
    header = read(HEADER)
    setup = function_body(
        world,
        "bool BotWorldPopulationMgr::TryEnsurePersistentCombatSetup",
    )
    native = function_body(
        world,
        "BotActionArbitration::Outcome BotWorldPopulationMgr::ExecuteNativeActionIntent",
    )

    assert "struct NativePoisonSetupReceipt" in header
    assert "BotNativeAction::UseItem useItem" in setup
    assert "ExecuteNativeActionIntent(state, bot, useItem" in setup
    assert "NativeUseSubmittedAtMs = nowMs" in setup
    assert "NativeUseFinishedAtMs = 0" in setup
    assert "NativeUseFinishedSuccessfully = false" in setup
    assert "NativeUseFinishedItemGuid.Clear()" in setup
    assert "NativeUseFinishedWeaponGuid.Clear()" in setup
    assert "EnchantObservedAtMs = nowMs" in setup
    assert "receipt.EnchantObservedAtMs" in setup
    assert "< receipt.NativeUseFinishedAtMs" in setup
    assert "receipt.SubmittedWeaponGuid == weapon->GetGUID()" in setup
    assert "receipt.ObservedWeaponGuid" in setup
    assert "== receipt.SubmittedWeaponGuid" in setup
    assert "receipt.EnchantObservedAtMs = 0" in setup
    assert setup.index("receipt.NativeUseSubmittedAtMs = nowMs") < setup.index(
        "ExecuteNativeActionIntent(state, bot, useItem"
    )

    finish = function_body(
        world, "void BotWorldPopulationMgr::NotifyBotItemSpellFinished"
    )
    assert "recordPoisonSetupFinish" in finish
    assert "receipt->RequiredSpellId != spellId" in finish
    assert "receipt->NativeUseSubmittedAtMs" in finish
    assert "receipt->NativeUseFinishedAtMs = NowMs()" in finish
    assert "receipt->NativeUseFinishedSuccessfully = success" in finish
    assert "receipt->SubmittedItemGuid != castItemGuid" in finish
    assert "receipt->SubmittedWeaponGuid != itemTargetGuid" in finish
    assert "receipt->NativeUseFinishedItemGuid = castItemGuid" in finish
    assert "receipt->NativeUseFinishedWeaponGuid = itemTargetGuid" in finish

    spell_finish = read(ROOT / "src/server/game/Spells/Spell.cpp")
    assert "NotifyBotItemSpellFinished(playerCaster," in spell_finish
    assert "m_castItemGUID" in spell_finish
    assert "m_targets.GetItemTargetGUID()" in spell_finish

    assert "std::is_same_v<T, BotNativeAction::UseItem>" in native
    assert "bot->GetItemByGuid(action.Item)" in native
    assert "bot->GetItemByGuid(action.Target)" in native
    assert "bot->CanUseItem(item)" in native
    assert "bot->CanRequestSpellCast(spellInfo)" in native
    assert "TARGET_FLAG_ITEM" in native
    assert "request.Cast.Target.Item = itemTarget->GetGUID()" in native
    assert "HandleUseItemOpcode(request)" in native


def test_missing_poison_inputs_fail_setup_without_manufacturing_state() -> None:
    setup = function_body(
        read(WORLD),
        "bool BotWorldPopulationMgr::TryEnsurePersistentCombatSetup",
    )
    native = function_body(
        read(WORLD),
        "BotActionArbitration::Outcome BotWorldPopulationMgr::ExecuteNativeActionIntent",
    )

    assert "persistent_setup_poison_item_missing:" in setup
    assert "persistent_setup_poison_spell_contract_missing:" in setup
    assert "persistent_setup_weapon_missing:" in setup
    for forbidden in (
        "SetEnchantment(",
        "SetEnchantmentDuration(",
        "AddAura(",
        "LearnSpell(",
        "StoreNewItem",
        "DestroyItemCount",
    ):
        assert forbidden not in setup
        assert forbidden not in native


def test_poison_readiness_and_previous_window_receipts_are_fail_closed() -> None:
    world = read(WORLD)
    calibration = function_body(
        world, "std::string BotWorldPopulationMgr::GetCombatCalibrationJson() const"
    )

    assert "case CLASS_ROGUE:" in calibration
    assert "state.RoguePoisonSetupRequired" in calibration
    assert "receipt.ItemAvailable" in calibration
    assert "receipt.SpellAvailable" in calibration
    assert "receipt.NativeUseSubmittedAtMs" in calibration
    assert "receipt.EnchantObservedAtMs" in calibration
    assert "receipt.SubmittedWeaponGuid" in calibration
    assert "receipt.ObservedEnchantId" in calibration
    assert "== receipt.RequiredEnchantId" in calibration
    assert "receipt.ObservedEnchantDurationMs >= 900000" in calibration
    assert "IsNativePoisonSetupReady(bot," in calibration
    for json_key in (
        '\\"poison_setup_required\\"',
        '\\"poisons\\"',
        '\\"mainhand\\"',
        '\\"offhand\\"',
        '\\"required_item_entry\\"',
        '\\"required_spell_id\\"',
        '\\"required_enchant_id\\"',
        '\\"item_available\\"',
        '\\"spell_available\\"',
        '\\"native_use_submitted\\"',
        '\\"native_use_submitted_at_ms\\"',
        '\\"native_use_finished\\"',
        '\\"native_use_finished_at_ms\\"',
        '\\"native_use_finished_item_guid\\"',
        '\\"native_use_finished_weapon_guid\\"',
        '\\"submitted_item_guid\\"',
        '\\"submitted_weapon_guid\\"',
        '\\"observed_weapon_guid\\"',
        '\\"enchant_observed\\"',
        '\\"enchant_observed_at_ms\\"',
        '\\"observed_weapon_item_entry\\"',
        '\\"observed_enchant_id\\"',
        '\\"observed_enchant_duration_ms\\"',
    ):
        assert json_key in calibration

    update = function_body(world, "void BotWorldPopulationMgr::Update(uint32 diff)")
    assert 'CalibrationTargetSpec == "assassination_rogue"' in update
    assert 'CalibrationTargetSpec == "combat_rogue"' in update
    assert "calibrationState.RoguePoisonSetupRequired" in update
    assert "IsNativePoisonSetupReady(calibrationBot," in update
    assert update.index("IsNativePoisonSetupReady(calibrationBot,") < update.index(
        "ResetCalibrationScoredWindow()"
    )

    readiness = function_body(
        world, "bool BotWorldPopulationMgr::TryValidationRouteReadiness"
    )
    assert "TryEnsurePersistentCombatSetup(state, bot, pullTarget)" in readiness
    assert 'result.Action = "validation_route_readiness_persistent_setup"' in readiness

    reconciler = function_body(
        world, "bool BotWorldPopulationMgr::IsNativePoisonSetupReady"
    )
    assert "bot->GetItemByEntry(receipt.RequiredItemEntry)" not in reconciler
    assert "receipt.ItemAvailable" in reconciler
    assert "receipt.SpellAvailable" in reconciler
    assert "receipt.NativeUseSubmittedAtMs" in reconciler
    assert "receipt.NativeUseFinishedSuccessfully" in reconciler
    assert "receipt.NativeUseFinishedAtMs >= receipt.NativeUseSubmittedAtMs" in reconciler
    assert "receipt.NativeUseFinishedItemGuid == receipt.SubmittedItemGuid" in reconciler
    assert "receipt.NativeUseFinishedWeaponGuid == receipt.SubmittedWeaponGuid" in reconciler
    assert "receipt.EnchantObservedAtMs >= receipt.NativeUseFinishedAtMs" in reconciler
    assert "receipt.SubmittedWeaponGuid == weapon->GetGUID()" in reconciler
    assert "receipt.ObservedWeaponGuid == weapon->GetGUID()" in reconciler
    assert "receipt.ObservedWeaponGuid == receipt.SubmittedWeaponGuid" in reconciler
    assert "GetEnchantmentId(TEMP_ENCHANTMENT_SLOT)" in reconciler
    assert "GetEnchantmentDuration(TEMP_ENCHANTMENT_SLOT)" in reconciler


def test_consumed_last_poison_item_keeps_the_completed_setup_receipt() -> None:
    setup = function_body(
        read(WORLD),
        "bool BotWorldPopulationMgr::TryEnsurePersistentCombatSetup",
    )

    assert "bool const itemCurrentlyAvailable" in setup
    assert "receipt.ItemAvailable = receipt.ItemAvailable" in setup
    assert "|| itemCurrentlyAvailable" in setup
    assert "sObjectMgr->GetItemTemplate(receipt.RequiredItemEntry)" in setup
    assert "if (!itemCurrentlyAvailable)" in setup
    assert setup.index("if (exactEnchantObserved)") < setup.index(
        "if (!itemCurrentlyAvailable)"
    )


def test_typed_use_item_intent_carries_exact_spell_identity() -> None:
    intents = read(INTENTS)

    assert "struct UseItem { ObjectGuid Item; ObjectGuid Target; uint32 SpellId = 0; };" in intents
    assert "std::is_same_v<T, UseItem>" in intents
    assert "Resource::GlobalCooldown" in intents
    assert "Resource::Cast" in intents
    assert "Resource::Target" in intents


def test_poison_stacks_have_exactly_the_two_rogue_owners() -> None:
    targets = json.loads(TARGETS.read_text(encoding="utf-8"))["targets"]
    validate_rogue_poison_provisioning(targets)
    for target in targets:
        if target["spec_target_id"] in {
            "assassination_rogue", "combat_rogue"
        }:
            assert target["consumable_item_ids"] == target[
                "provisioning_bot"
            ]["consumable_item_ids"]

    contaminated = copy.deepcopy(targets)
    tank = next(
        row for row in contaminated
        if row["spec_target_id"] == "protection_warrior"
    )["provisioning_bot"]
    tank["consumable_item_ids"].append(43233)
    tank["consumables"] = [{"item_id": 43233, "slot": 23, "count": 20}]
    with pytest.raises(ValueError, match="owners must be exactly"):
        validate_rogue_poison_provisioning(contaminated)

    incomplete = copy.deepcopy(targets)
    combat_target = next(
        row for row in incomplete if row["spec_target_id"] == "combat_rogue"
    )
    combat = combat_target["provisioning_bot"]
    combat_target["consumable_item_ids"].remove(43231)
    combat["consumable_item_ids"].remove(43231)
    combat["consumables"] = [
        row for row in combat["consumables"] if row["item_id"] != 43231
    ]
    with pytest.raises(ValueError, match="missing exact slot/count"):
        validate_rogue_poison_provisioning(incomplete)


def test_applied_poison_inventory_readback_fails_closed() -> None:
    expected = [
        {"item_id": 43233, "slot": 23, "count": 20},
        {"item_id": 43231, "slot": 24, "count": 20},
    ]
    good = {
        23: {
            "bag": 0, "slot": 23, "item_id": 43233,
            "owner_guid": 10, "count": 20,
        },
        24: {
            "bag": 0, "slot": 24, "item_id": 43231,
            "owner_guid": 10, "count": 20,
        },
    }
    assert runtime_consumable_inventory_mismatches(10, expected, good) == []

    stale = copy.deepcopy(good)
    stale[23]["count"] = 19
    stale[24]["item_id"] = 99999
    stale[24]["owner_guid"] = 11
    mismatches = runtime_consumable_inventory_mismatches(10, expected, stale)
    assert mismatches[0]["wrong_fields"] == ["count"]
    assert mismatches[1]["wrong_fields"] == ["item_id", "owner_guid"]

    missing = copy.deepcopy(good)
    del missing[24]
    mismatches = runtime_consumable_inventory_mismatches(10, expected, missing)
    assert mismatches == [{
        "slot": 24,
        "wrong_fields": ["slot", "item_id", "owner_guid", "count"],
        "expected": {
            "bag": 0, "slot": 24, "item_id": 43231,
            "owner_guid": 10, "count": 20,
        },
        "actual": {
            "bag": 0, "slot": 0, "item_id": 0,
            "owner_guid": 0, "count": 0,
        },
    }]
