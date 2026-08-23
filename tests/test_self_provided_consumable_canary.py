import json
from pathlib import Path

import pytest

from tools.bot_ml.build_phase8_evidence_identity_manifest import _profile_target


REPO_ROOT = Path(__file__).resolve().parents[1]
REQUEST_CATALOG = (
    REPO_ROOT / "experiments/configs/wowsims_cata_dps_reference_requests_v1.json"
)


def _source(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _between(text: str, start: str, end: str) -> str:
    start_index = text.index(start)
    return text[start_index : text.index(end, start_index)]


def test_self_provided_requests_disable_every_external_condition() -> None:
    catalog = json.loads(REQUEST_CATALOG.read_text(encoding="utf-8"))

    assert catalog["reference_class"] == "self_provided_baseline"
    assert catalog["request_count"] == 16
    for row in catalog["requests"]:
        request = row["request"]
        native = request["native_request"]
        assert request["reference_class"] == "self_provided_baseline"
        assert native["party_buffs"] == {}
        assert native["individual_buffs"] == {}
        assert all(value is False for value in native["raid_buffs"].values())
        assert all(value is False for value in native["target_debuffs"].values())
        assert native["professions"] == [
            "ProfessionUnknown",
            "ProfessionUnknown",
        ]
        assert native["consumables"]["tinker_id"] == 0


def test_affliction_request_binds_exact_food_flask_and_two_potion_uses() -> None:
    catalog = json.loads(REQUEST_CATALOG.read_text(encoding="utf-8"))
    affliction = next(
        row for row in catalog["requests"]
        if row["target_spec"] == "affliction_warlock"
    )["request"]
    native = affliction["native_request"]
    expected = affliction["runtime_expected"]

    assert native["consumables"] == {
        "battle_elixir_id": 0,
        "conjured_id": 0,
        "explosive_id": 0,
        "flask_id": 58086,
        "food_id": 62671,
        "guardian_elixir_id": 0,
        "pot_id": 58091,
        "prepot_id": 58091,
        "tinker_id": 0,
    }
    assert expected["flask"] == {
        "item_id": 58086,
        "item_spell_id": 79470,
        "observed_aura_spell_id": 79470,
    }
    assert expected["food"] == {
        "item_id": 62671,
        "item_spell_id": 87587,
        "observed_aura_spell_id": 87547,
    }
    assert expected["prepot"] == {
        "item_id": 58091,
        "item_spell_id": 79476,
        "observed_aura_spell_id": 79476,
        "use_count": 1,
    }
    assert expected["combat_potion"] == {
        "item_id": 58091,
        "item_spell_id": 79476,
        "observed_aura_spell_id": 79476,
        "use_count": 1,
    }


def test_native_self_provided_path_uses_inventory_without_injecting_auras() -> None:
    reference = _source(
        "src/server/game/Bots/BotWorldPopulationMgrCalibrationReference.cpp"
    )
    ensure = _between(
        reference,
        "bool BotWorldPopulationMgr::EnsureCalibrationSelfProvidedConsumables",
        "std::pair<bool, bool> BotWorldPopulationMgr::ApplyCalibrationReferenceConditions",
    )
    apply_conditions = _between(
        reference,
        "std::pair<bool, bool> BotWorldPopulationMgr::ApplyCalibrationReferenceConditions",
        "void BotWorldPopulationMgr::ObserveCalibrationReferenceConditions",
    )
    native_action = _source(
        "src/server/game/Bots/BotWorldPopulationMgrNativeAction.cpp"
    )
    use_item = _between(
        native_action,
        "std::is_same_v<T, BotNativeAction::UseItem>",
        "std::is_same_v<T, BotNativeAction::ReleaseSpirit>",
    )

    assert "AddAura" not in ensure
    assert "SetCount" not in ensure
    assert "DestroyItem" not in ensure
    assert "ExecuteNativeActionIntent" in ensure
    assert "PreUseItemCount > receipt.PostUseItemCount" in ensure
    assert "IsReady(spellInfo, receipt.ItemId)" in ensure
    assert "receipt.NextRetryAtMs = nowMs + 30000" in ensure
    assert apply_conditions.index("if (IsSelfProvidedCalibrationBaseline())") < (
        apply_conditions.index("AddAura")
    )
    assert "HandleUseItemOpcode" in use_item
    assert "AddAura" not in use_item
    assert "SetCount" not in use_item
    assert "DestroyItem" not in use_item


def test_affliction_combat_potion_gate_binds_execute_window_and_prepot_clear() -> None:
    reference = _source(
        "src/server/game/Bots/BotWorldPopulationMgrCalibrationReference.cpp"
    )
    ensure = _between(
        reference,
        "bool BotWorldPopulationMgr::EnsureCalibrationSelfProvidedConsumables",
        "std::pair<bool, bool> BotWorldPopulationMgr::ApplyCalibrationReferenceConditions",
    )
    execution_json = _source(
        "src/server/game/Bots/BotWorldPopulationMgrCalibrationReferenceJson.cpp"
    )
    metrics = _source(
        "src/server/game/Bots/BotWorldPopulationMgrCalibrationMetrics.h"
    )

    assert 'Cohort().CalibrationTargetSpec == "affliction_warlock"' in ensure
    assert "target->GetHealthPct()" in ensure
    assert "AfflictionCombatPotionExecuteHealthPct" in ensure
    assert "AfflictionCombatPotionFinalWindowRemainingMs" in ensure
    assert "bot->HasAura(contract->PrepotAuraSpellId)" in ensure
    assert "TimingGatePrepotAuraBlockedSampleCount" in ensure
    assert "TimingGateFirstEligibleAtMs" in ensure
    assert "return false;" in ensure[ensure.index("if (prepotAuraActive)") :]
    assert "execute_e25_or_remaining_le_26s_no_prepot_overlap" in execution_json
    assert "timing_gate" in execution_json
    assert "TimingGatePrepotAuraClearAtSubmission" in metrics


def test_native_item_completion_retains_consumed_item_identity() -> None:
    spell = _source("src/server/game/Spells/Spell.cpp")
    header = _source("src/server/game/Spells/Spell.h")
    semantic = _source(
        "src/server/game/Bots/BotWorldPopulationMgrSemantic.cpp"
    )
    completion = _between(
        semantic,
        "void BotWorldPopulationMgr::NotifyBotItemSpellFinished",
        "void BotWorldPopulationMgr::FlushPendingHealCast",
    )

    assert "ObjectGuid m_initialCastItemGUID;" in header
    assert "m_initialCastItemGUID = m_castItemGUID;" in spell
    assert "if (m_initialCastItemGUID)" in spell
    assert "m_spellInfo->Id, ok, m_initialCastItemGUID," in spell
    assert "receipt->SubmittedAtMs > receipt->FinishedAtMs" in completion


def test_successful_food_completion_waits_for_native_food_aura() -> None:
    semantic = _source(
        "src/server/game/Bots/BotWorldPopulationMgrSemantic.cpp"
    )
    reference = _source(
        "src/server/game/Bots/BotWorldPopulationMgrCalibrationReference.cpp"
    )
    completion = _between(
        semantic,
        "void BotWorldPopulationMgr::NotifyBotItemSpellFinished",
        "void BotWorldPopulationMgr::FlushPendingHealCast",
    )
    food_completion = _between(
        completion,
        "receipt->NativeUseAwaitingAura = success",
        "break;",
    )

    assert "receipt == &metrics.FoodConsumable" in food_completion
    assert "receipt->NativeUseAuraDeadlineAtMs" in food_completion
    assert "receipt->NativeUseFinishedSuccessfully = success" in food_completion
    assert "SetStandState(UNIT_STAND_STATE_STAND)" not in food_completion
    assert "NativeUseAwaitingAura" in reference
    assert "bot->HasAura(contract->FoodAuraSpellId)" in reference
    ensure = _between(
        reference,
        "auto reconcilePendingFood = [&]()",
        "auto submit = [&](CalibrationMetrics::NativeConsumableReceipt& receipt)",
    )
    assert ensure.index("bot->HasAura(contract->FoodAuraSpellId)") < ensure.index(
        "bot->SetStandState(UNIT_STAND_STATE_STAND);"
    )


def test_food_aura_wait_has_bounded_retry_and_no_spin() -> None:
    reference = _source(
        "src/server/game/Bots/BotWorldPopulationMgrCalibrationReference.cpp"
    )
    ensure = _between(
        reference,
        "bool BotWorldPopulationMgr::EnsureCalibrationSelfProvidedConsumables",
        "std::pair<bool, bool> BotWorldPopulationMgr::ApplyCalibrationReferenceConditions",
    )

    assert "if (reconcilePendingFood())" in ensure
    assert "food.NativeUseAuraDeadlineAtMs" in ensure
    assert "food.NativeUseAuraTimedOutAtMs = nowMs" in ensure
    assert "food.SubmittedItemGuid.Clear()" in ensure
    assert "food.NextRetryAtMs = nowMs + 1000" in ensure
    assert "return true;" in ensure[ensure.index("if (nowMs < food.NativeUseAuraDeadlineAtMs)") :]


def test_consumable_completion_waits_for_a_later_warmup_update() -> None:
    semantic = _source(
        "src/server/game/Bots/BotWorldPopulationMgrSemantic.cpp"
    )
    calibration_bot = _source(
        "src/server/game/Bots/BotWorldPopulationMgrCalibrationBot.cpp"
    )
    reset = _source(
        "src/server/game/Bots/BotWorldPopulationMgrCalibrationReset.cpp"
    )
    completion = _between(
        semantic,
        "void BotWorldPopulationMgr::NotifyBotItemSpellFinished",
        "void BotWorldPopulationMgr::FlushPendingHealCast",
    )
    receipt_completion = _between(
        completion,
        "receipt->NativeUseFinishedSuccessfully = success\n",
        "break;",
    )
    update = calibration_bot[
        calibration_bot.index(
            "void BotWorldPopulationMgr::UpdateCalibrationBot"
        ) :
    ]

    assert "UpdatePetScalingAuras" not in receipt_completion
    assert "UpdateAllStats" not in receipt_completion
    assert "receipt != &metrics.CombatPotionConsumable" in receipt_completion
    assert "metrics.LastPreScoreConsumableFinishedUpdateOrdinal" in (
        receipt_completion
    )
    assert update.index("++metrics.WarmupUpdateOrdinal;") < update.index(
        "if (state.DecisionTimer > diff)"
    )
    assert "metrics.WarmupUpdateOrdinal\n                    > " in reset
    assert "metrics.LastPreScoreConsumableFinishedUpdateOrdinal;" in reset


def test_final_pre_score_boundary_refreshes_pet_before_resource_observation() -> None:
    reset = _source(
        "src/server/game/Bots/BotWorldPopulationMgrCalibrationReset.cpp"
    )
    final_boundary = _between(
        reset,
        "bool consumablesSettled = true;",
        'if (Cohort().CalibrationMode == "single_target_300")',
    )
    resources = _source(
        "src/server/game/Bots/BotWorldPopulationMgrCalibrationResourcesReset.cpp"
    )
    resource_reset_start = resources.index(
        "void BotWorldPopulationMgr::ResetCalibrationInitialResources"
    )
    resource_reset = resources[resource_reset_start:]

    assert final_boundary.index("pet->UpdatePetScalingAuras();") < (
        final_boundary.index("pet->UpdateAllStats();")
    )
    assert final_boundary.index("pet->UpdateAllStats();") < (
        final_boundary.index("ResetCalibrationInitialResources(bot, metrics);")
    )
    assert 'std::string_view(unitKind) != "pet"' in resource_reset
    assert resource_reset.index("unit->GetMaxPower(power)") < (
        resource_reset.index("metrics.InitialResourcesObservedAtMs = NowMs();")
    )


def test_prepot_runs_after_the_only_pre_score_cooldown_reset() -> None:
    reset = _source(
        "src/server/game/Bots/BotWorldPopulationMgrCalibrationReset.cpp"
    )
    reference = _source(
        "src/server/game/Bots/BotWorldPopulationMgrCalibrationReference.cpp"
    )
    ensure = _between(
        reference,
        "bool BotWorldPopulationMgr::EnsureCalibrationSelfProvidedConsumables",
        "std::pair<bool, bool> BotWorldPopulationMgr::ApplyCalibrationReferenceConditions",
    )

    assert reset.index("bot->GetSpellHistory()->ResetAllCooldowns();") < (
        reset.index("metrics.PreScoreCooldownResetComplete = true;")
    )
    assert ensure.index("if (!metrics.PreScoreCooldownResetComplete)") < (
        ensure.index("submit(metrics.PrepotConsumable)")
    )
    assert "&& metrics.PreScoreCooldownResetComplete)\n            continue;" in reset
    assert "bool selfProvidedCooldownResetApplied = false;" in reset
    assert (
        reset.index("metrics.PreScoreCooldownResetComplete = true;")
        < reset.index("if (selfProvidedCooldownResetApplied)")
        < reset.index("calibration_pre_score_state_contract_mismatch")
    )


def test_runner_requires_an_explicit_exclusive_self_provided_mode() -> None:
    runner = _source("tools/bot_ml/run_live_bot_validation.py")

    assert "--calibration-self-provided-baseline" in runner
    assert (
        "args.calibration_reference_conditions and "
        "args.calibration_self_provided_baseline"
    ) in runner
    assert (
        '"BotWorld.CombatCalibration.SelfProvidedBaseline"'
        in runner
    )


def test_evidence_identity_builder_can_bind_the_self_provided_server() -> None:
    builder = _source(
        "tools/bot_ml/build_phase8_evidence_identity_manifest.py"
    )

    assert '"--calibration-self-provided-baseline"' in builder
    assert '"--session-runtime-dir"' in builder
    assert (
        "calibration_reference_conditions="
        "not calibration_self_provided_baseline"
    ) in builder
    assert (
        "calibration_self_provided_baseline="
        "calibration_self_provided_baseline"
    ) in builder


def test_evidence_identity_builder_selects_one_exact_profile_target() -> None:
    catalog = json.loads(
        (REPO_ROOT / "experiments/configs/all_spec_targets_cata_p4_v1.json")
        .read_text(encoding="utf-8")
    )

    target = _profile_target(catalog, "affliction_warlock")
    assert target["class_id"] == 9
    assert target["role"] == "dps"
    assert target["runtime_join_key"] == "affliction_warlock"
    with pytest.raises(RuntimeError, match="must resolve exactly once"):
        _profile_target(catalog, "missing_spec")
